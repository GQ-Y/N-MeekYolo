"""
MQTT测试客户端
用于模拟分析节点与API服务通信
"""
import json
import time
import uuid
import random
import threading
import argparse
import socket
import platform
import paho.mqtt.client as mqtt_client

# 添加psutil库用于获取系统资源使用情况
import psutil

# 配置信息
DEFAULT_CONFIG = {
    "broker_host": "mqtt.yingzhu.net",
    "broker_port": 1883,
    "username": "yolo",
    "password": "yolo",
    "topic_prefix": "yolo/",
    "qos": 1,
    "keepalive": 60
}

class MQTTTestClient:
    """MQTT测试客户端类"""
    
    def __init__(self, config=None, node_id=None, service_type="analysis"):
        """
        初始化MQTT测试客户端
        
        Args:
            config: MQTT配置（可选）
            node_id: 节点ID（可选，不提供则基于MAC地址自动生成）
            service_type: 服务类型，默认为analysis（可选）
        """
        self.config = config or DEFAULT_CONFIG
        
        # 如果没有提供节点ID，则基于MAC地址生成
        if not node_id:
            # 获取MAC地址
            mac = uuid.getnode()
            mac_str = ':'.join(("%012X" % mac)[i:i+2] for i in range(0, 12, 2))
            node_id = mac_str  # 结果如 "6A:C4:09:90:EF:DA"
        
        self.node_id = node_id
        # 客户端ID与节点ID保持一致，不再添加时间戳
        self.client_id = self.node_id
        self.service_type = service_type
        self.connected = False
        self.running = False
        
        # 任务计数器
        self.task_count = 0
        
        # 创建MQTT客户端（使用paho-mqtt 2.0版本API）
        self.client = mqtt_client.Client(
            client_id=self.client_id,
            callback_api_version=mqtt_client.CallbackAPIVersion.VERSION1
        )
        
        # 设置回调函数
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        
        # 设置认证信息
        if self.config.get("username") and self.config.get("password"):
            self.client.username_pw_set(
                self.config.get("username"), 
                self.config.get("password")
            )
        
        # 获取系统信息
        self.hostname = socket.gethostname()
        try:
            self.ip = socket.gethostbyname(self.hostname)
        except:
            self.ip = "127.0.0.1"
            
        self.os_info = platform.platform()
        
        # 打印初始化信息
        print(f"MQTT测试客户端初始化完成")
        print(f"节点ID/客户端ID: {self.node_id}")
        print(f"服务类型: {self.service_type}")
        print(f"主机名: {self.hostname}")
        print(f"IP地址: {self.ip}")
        print(f"操作系统: {self.os_info}")
    
    def get_system_resource_usage(self):
        """
        获取系统资源使用情况
        
        Returns:
            Dict: 包含CPU、内存、GPU使用率的字典
        """
        # 获取CPU使用率
        cpu_usage = psutil.cpu_percent(interval=0.5)
        
        # 获取内存使用率
        memory = psutil.virtual_memory()
        memory_usage = memory.percent
        
        # 获取GPU使用率（如果可用）
        gpu_usage = 0
        try:
            # 尝试导入GPUtil库
            import GPUtil
            gpus = GPUtil.getGPUs()
            if gpus:
                # 存在GPU，获取第一个GPU使用率
                gpu_usage = gpus[0].memoryUtil * 100
            else:
                # 没有可用GPU
                print("未检测到GPU设备")
        except ImportError:
            print("未安装GPUtil库，无法获取GPU信息")
        except Exception as e:
            print(f"获取GPU信息时出错: {e}")
        
        return {
            "cpu_usage": cpu_usage,
            "memory_usage": memory_usage,
            "gpu_usage": gpu_usage,
            "task_count": self.task_count
        }
    
    def connect(self):
        """连接到MQTT Broker并设置遗嘱消息"""
        try:
            # 构造离线状态消息
            offline_payload = self._create_status_payload("offline")
            
            # 设置遗嘱消息（当客户端异常断开时发送）
            topic_prefix = self.config.get("topic_prefix", "yolo/")
            topic = f"{topic_prefix}nodes/{self.node_id}/status"
            
            self.client.will_set(
                topic=topic,
                payload=json.dumps(offline_payload),
                qos=self.config.get("qos", 1),
                retain=False
            )
            
            # 连接到MQTT Broker
            print(f"正在连接到MQTT Broker: {self.config.get('broker_host')}:{self.config.get('broker_port')}...")
            self.client.connect(
                self.config.get("broker_host", "mqtt.yingzhu.net"),
                self.config.get("broker_port", 1883),
                keepalive=self.config.get("keepalive", 60)
            )
            
            # 启动网络循环
            self.client.loop_start()
            return True
        except Exception as e:
            print(f"连接MQTT Broker失败: {e}")
            return False
    
    def disconnect(self):
        """断开与MQTT Broker的连接"""
        self.running = False
        try:
            # 发布离线状态
            self.publish_status("offline")
            time.sleep(1)  # 等待消息发送完成
            
            # 停止循环并断开连接
            self.client.loop_stop()
            self.client.disconnect()
            print("已断开与MQTT Broker的连接")
        except Exception as e:
            print(f"断开连接时出错: {e}")
    
    def _on_connect(self, client, userdata, flags, rc):
        """连接成功回调函数"""
        if rc == 0:
            print("成功连接到MQTT Broker!")
            self.connected = True
            
            # 订阅相关主题
            topic_prefix = self.config.get("topic_prefix", "yolo/")
            qos = self.config.get("qos", 1)
            
            # 订阅任务相关主题
            tasks_topic = f"{topic_prefix}tasks/{self.node_id}/+/request"
            self.client.subscribe(tasks_topic, qos=qos)
            print(f"已订阅主题: {tasks_topic}")
            
            # 发布上线状态
            self.publish_status("online")
            print("已发送初始状态")
            
            # 启动资源定时上报线程
            self.start_resource_reporter()
            print("已启动资源上报线程，每60秒报告一次系统状态")
        else:
            connection_results = {
                1: "连接被拒绝 - 协议版本不正确",
                2: "连接被拒绝 - 客户端ID无效",
                3: "连接被拒绝 - 服务器不可用",
                4: "连接被拒绝 - 用户名或密码错误",
                5: "连接被拒绝 - 未授权"
            }
            print(f"连接失败，返回码: {rc} - {connection_results.get(rc, '未知错误')}")
            self.connected = False
    
    def _on_disconnect(self, client, userdata, rc):
        """断开连接回调函数"""
        if rc != 0:
            print(f"意外断开连接，返回码: {rc}")
        self.connected = False
    
    def _on_message(self, client, userdata, msg):
        """消息接收回调函数"""
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode())
            
            print(f"\n收到消息:")
            print(f"主题: {topic}")
            print(f"载荷: {json.dumps(payload, ensure_ascii=False, indent=2)}")
            
            # 处理任务请求
            topic_prefix = self.config.get("topic_prefix", "yolo/")
            if topic.startswith(f"{topic_prefix}tasks/") and topic.endswith("/request"):
                self._handle_task_request(topic, payload)
        except Exception as e:
            print(f"处理消息时出错: {e}")
    
    def _handle_task_request(self, topic, payload):
        """处理任务请求"""
        try:
            # 解析任务信息
            task_id = payload.get("task_id", "unknown")
            print(f"收到任务请求，任务ID: {task_id}")
            
            # 增加任务计数
            self.task_count += 1
            print(f"当前任务数: {self.task_count}")
            
            # 模拟任务处理
            print("模拟任务处理中...")
            time.sleep(2)
            
            # 发送任务状态（接受任务）
            self._publish_task_status(task_id, "accepted")
            time.sleep(1)
            
            # 模拟任务执行
            print("模拟任务执行中...")
            time.sleep(3)
            
            # 发送任务状态（完成任务）
            self._publish_task_status(task_id, "completed")
            
            # 发送任务结果
            self._publish_task_result(task_id, {
                "status": "success",
                "data": {
                    "results": ["模拟的结果数据"]
                }
            })
            
            # 减少任务计数
            self.task_count -= 1
            print(f"任务 {task_id} 处理完成，当前任务数: {self.task_count}")
        except Exception as e:
            print(f"处理任务请求时出错: {e}")
            # 确保任务计数正确
            if self.task_count > 0:
                self.task_count -= 1
    
    def _publish_task_status(self, task_id, status):
        """发布任务状态"""
        if not self.connected:
            print("未连接到MQTT Broker，无法发布任务状态")
            return
        
        topic_prefix = self.config.get("topic_prefix", "yolo/")
        topic = f"{topic_prefix}tasks/{task_id}/status"
        
        payload = {
            "timestamp": int(time.time()),
            "payload": {
                "task_id": task_id,
                "node_id": self.node_id,
                "status": status
            }
        }
        
        self.client.publish(
            topic=topic,
            payload=json.dumps(payload),
            qos=self.config.get("qos", 1)
        )
        print(f"已发布任务 {task_id} 状态: {status}")
    
    def _publish_task_result(self, task_id, result_data):
        """发布任务结果"""
        if not self.connected:
            print("未连接到MQTT Broker，无法发布任务结果")
            return
        
        topic_prefix = self.config.get("topic_prefix", "yolo/")
        topic = f"{topic_prefix}tasks/{task_id}/result"
        
        payload = {
            "timestamp": int(time.time()),
            "payload": {
                "task_id": task_id,
                "node_id": self.node_id,
                "result": result_data
            }
        }
        
        self.client.publish(
            topic=topic,
            payload=json.dumps(payload),
            qos=self.config.get("qos", 1)
        )
        print(f"已发布任务 {task_id} 结果")
    
    def _create_status_payload(self, status):
        """创建状态消息载荷"""
        # 获取真实系统资源使用情况
        resource = self.get_system_resource_usage()
        
        return {
            "timestamp": int(time.time()),
            "payload": {
                "node_id": self.node_id,
                "service_type": self.service_type,
                "status": status,
                "metadata": {
                    "ip": self.ip,
                    "port": 8002,
                    "hostname": self.hostname,
                    "version": "1.0.0",
                    "os": self.os_info,
                    "resource": resource
                }
            }
        }
    
    def publish_status(self, status):
        """发布节点状态"""
        if not self.connected and status != "offline":
            print("未连接到MQTT Broker，无法发布状态")
            return
        
        topic_prefix = self.config.get("topic_prefix", "yolo/")
        topic = f"{topic_prefix}nodes/{self.node_id}/status"
        
        payload = self._create_status_payload(status)
        
        result = self.client.publish(
            topic=topic,
            payload=json.dumps(payload),
            qos=self.config.get("qos", 1)
        )
        
        if result.rc == 0:
            print(f"已发布节点状态: {status}")
        else:
            print(f"发布节点状态失败，错误码: {result.rc}")
    
    def start_resource_reporter(self):
        """启动资源使用情况报告线程"""
        self.running = True
        
        def report_resources():
            """定期报告资源使用情况"""
            print("资源报告线程已启动")
            print(f"将每60秒向主题 yolo/nodes/{self.node_id}/status 发送状态更新")
            
            while self.running and self.connected:
                try:
                    # 立即发送第一次状态更新
                    resource = self.get_system_resource_usage()
                    print(f"准备发送状态更新...")
                    self.publish_status("online")
                    print(f"\n定时上报系统资源: CPU={resource['cpu_usage']:.1f}%, "
                          f"内存={resource['memory_usage']:.1f}%, "
                          f"GPU={resource['gpu_usage']:.1f}%, "
                          f"任务数={self.task_count}")
                    
                    # 等待下一次更新
                    print("等待60秒后发送下一次状态更新...")
                    for _ in range(60):
                        if not self.running or not self.connected:
                            print(f"线程停止：running={self.running}, connected={self.connected}")
                            return
                        time.sleep(1)
                          
                except Exception as e:
                    print(f"报告资源使用情况时出错: {e}")
                    if not self.connected:
                        print("MQTT连接已断开，停止资源上报")
                        break
                    time.sleep(5)  # 出错后短暂休眠
        
        # 创建并启动报告线程
        self.resource_thread = threading.Thread(target=report_resources)
        self.resource_thread.daemon = True
        self.resource_thread.start()
    
    def run(self):
        """运行测试客户端"""
        if self.connect():
            print("MQTT测试客户端已启动")
            
            try:
                while True:
                    cmd = input("\n输入命令 (help查看帮助): ")
                    cmd = cmd.strip().lower()
                    
                    if cmd == "help":
                        print("可用命令:")
                        print("  status [状态]  - 发布节点状态，可选值: online, busy, offline")
                        print("  resource      - 立即发送资源使用报告")
                        print("  info          - 显示节点信息")
                        print("  quit/exit     - 退出程序")
                    elif cmd.startswith("status"):
                        parts = cmd.split(maxsplit=1)
                        status = parts[1] if len(parts) > 1 else "online"
                        self.publish_status(status)
                    elif cmd == "resource":
                        self.publish_status("online")
                        print("已发送资源使用报告")
                    elif cmd == "info":
                        print(f"节点ID/客户端ID: {self.node_id}")
                        print(f"服务类型: {self.service_type}")
                        print(f"连接状态: {'已连接' if self.connected else '未连接'}")
                        resource = self.get_system_resource_usage()
                        print(f"CPU使用率: {resource['cpu_usage']:.1f}%")
                        print(f"内存使用率: {resource['memory_usage']:.1f}%")
                        print(f"GPU使用率: {resource['gpu_usage']:.1f}%")
                        print(f"当前任务数: {self.task_count}")
                    elif cmd in ["quit", "exit"]:
                        break
                    else:
                        print(f"未知命令: {cmd}，输入help查看帮助")
            except KeyboardInterrupt:
                print("\n接收到终止信号，正在退出...")
            finally:
                self.disconnect()
        else:
            print("无法连接到MQTT Broker，程序退出")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="MQTT测试客户端")
    parser.add_argument("--node-id", help="节点ID和客户端ID，不提供则基于MAC地址自动生成，格式为node_XXXXXXXXXXXX")
    parser.add_argument("--service-type", default="analysis", help="服务类型，默认为analysis")
    parser.add_argument("--broker", default=DEFAULT_CONFIG["broker_host"], help=f"MQTT Broker地址，默认为{DEFAULT_CONFIG['broker_host']}")
    parser.add_argument("--port", type=int, default=DEFAULT_CONFIG["broker_port"], help=f"MQTT Broker端口，默认为{DEFAULT_CONFIG['broker_port']}")
    args = parser.parse_args()
    
    # 更新配置
    config = DEFAULT_CONFIG.copy()
    config["broker_host"] = args.broker
    config["broker_port"] = args.port
    
    # 创建并运行客户端
    client = MQTTTestClient(config=config, node_id=args.node_id, service_type=args.service_type)
    client.run()

if __name__ == "__main__":
    main()
