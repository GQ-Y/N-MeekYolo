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
    "topic_prefix": "meek/",  # 修改为与API服务一致的前缀
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
        
        # 获取MAC地址作为节点标识
        mac = uuid.getnode()
        self.mac_address = ':'.join(("%012X" % mac)[i:i+2] for i in range(0, 12, 2))
        
        # 如果提供了节点ID，使用提供的节点ID，否则使用MAC地址
        self.node_id = node_id if node_id else self.mac_address
        
        # 客户端ID与节点ID保持一致
        self.client_id = self.node_id
        self.service_type = service_type
        self.connected = False
        self.running = False
        
        # 任务计数器和数据
        self.task_count = 0
        self.running_tasks = {}  # 存储正在运行的任务信息
        
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
        print(f"MAC地址: {self.mac_address}")
        print(f"节点ID: {self.node_id}")
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
            "cpu": cpu_usage,
            "memory": memory_usage,
            "gpu": gpu_usage,
            "running_tasks": self.task_count
        }
    
    def connect(self):
        """连接到MQTT Broker并设置遗嘱消息"""
        try:
            # 构造离线状态消息
            offline_payload = {
                "mac_address": self.mac_address,
                "node_id": self.node_id,  # 添加节点ID
                "client_id": self.client_id,  # 添加客户端ID
                "status": "offline",
                "node_type": self.service_type,
                "timestamp": int(time.time()),
                "metadata": {
                    "ip": self.ip,
                    "hostname": self.hostname,
                    "port": 8002,  # 假设分析服务端口
                    "version": "1.0.0",
                    "is_active": False,  # 离线状态设为False
                    "capabilities": {
                        "max_tasks": 10,
                        "supported_models": ["yolov5", "yolov8", "efficientdet"],
                        "supported_sources": ["image", "video", "stream"]
                    }
                }
            }
            
            # 设置遗嘱消息（当客户端异常断开时发送）
            topic_prefix = self.config.get("topic_prefix", "meek/")
            topic = f"{topic_prefix}connection"
            
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
            self.publish_connection_status("offline")
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
            topic_prefix = self.config.get("topic_prefix", "meek/")
            qos = self.config.get("qos", 1)
            
            # 订阅任务请求主题 - 使用MAC地址作为主题的一部分
            request_topic = f"{topic_prefix}{self.mac_address}/request_setting"
            self.client.subscribe(request_topic, qos=qos)
            print(f"已订阅请求主题: {request_topic}")
            
            # 发布上线状态
            self.publish_connection_status("online")
            print("已发送上线状态")
            
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
            topic_prefix = self.config.get("topic_prefix", "meek/")
            if f"{topic_prefix}{self.mac_address}/request_setting" == topic:
                self._handle_request(payload)
        except Exception as e:
            print(f"处理消息时出错: {e}")
    
    def _handle_request(self, payload):
        """处理请求消息"""
        try:
            # 检查消息类型
            request_type = payload.get("request_type")
            if not request_type:
                print("请求消息缺少request_type字段")
                return
                
            # 获取确认回复主题和消息ID
            confirmation_topic = payload.get("confirmation_topic", f"{self.config.get('topic_prefix', 'meek/')}node_config_reply")
            message_id = payload.get("message_id")
            message_uuid = payload.get("message_uuid")
            
            print(f"收到请求: {request_type}, message_uuid: {message_uuid}")
            
            # 处理任务命令
            if request_type == "task_cmd":
                data = payload.get("data", {})
                cmd_type = data.get("cmd_type")
                
                if cmd_type == "start_task":
                    # 提取任务信息
                    task_id = data.get("task_id")
                    subtask_id = data.get("subtask_id")
                    source = data.get("source", {})
                    config = data.get("config", {})
                    result_config = data.get("result_config", {})
                    
                    print(f"收到任务请求: task_id={task_id}, subtask_id={subtask_id}")
                    
                    # 回复接受任务
                    self._send_config_reply(confirmation_topic, message_id, message_uuid, "success", {
                        "cmd_type": "start_task",
                        "task_id": task_id,
                        "subtask_id": subtask_id,
                        "message": "任务已接受"
                    })
                    
                    # 异步处理任务
                    threading.Thread(target=self._process_task, 
                                    args=(task_id, subtask_id, source, config, result_config)).start()
                    
                elif cmd_type == "stop_task":
                    # 处理停止任务命令
                    task_id = data.get("task_id")
                    subtask_id = data.get("subtask_id")
                    
                    print(f"收到停止任务请求: task_id={task_id}, subtask_id={subtask_id}")
                    
                    # 检查任务是否存在
                    task_key = f"{task_id}_{subtask_id}"
                    if task_key in self.running_tasks:
                        # 标记任务需要停止
                        self.running_tasks[task_key]["stop"] = True
                        
                        # 回复接受停止命令
                        self._send_config_reply(confirmation_topic, message_id, message_uuid, "success", {
                            "cmd_type": "stop_task",
                            "task_id": task_id,
                            "subtask_id": subtask_id,
                            "message": "任务停止命令已接受"
                        })
                    else:
                        # 回复任务不存在
                        self._send_config_reply(confirmation_topic, message_id, message_uuid, "error", {
                            "cmd_type": "stop_task",
                            "task_id": task_id,
                            "subtask_id": subtask_id,
                            "message": "任务不存在"
                        })
                        
                else:
                    # 不支持的命令类型
                    self._send_config_reply(confirmation_topic, message_id, message_uuid, "error", {
                        "cmd_type": cmd_type,
                        "message": f"不支持的命令类型: {cmd_type}"
                    })
            
            # 处理其他类型请求
            else:
                # 回复不支持的请求类型
                self._send_config_reply(confirmation_topic, message_id, message_uuid, "error", {
                    "message": f"不支持的请求类型: {request_type}"
                })
                
        except Exception as e:
            print(f"处理请求消息时出错: {e}")
            import traceback
            print(traceback.format_exc())
    
    def _send_config_reply(self, topic, message_id, message_uuid, status, data):
        """发送配置回复"""
        if not self.connected:
            print("未连接到MQTT Broker，无法发送配置回复")
            return
            
        # 确保data中包含节点ID信息
        if status == "success" and data.get("cmd_type") == "start_task":
            # 确保响应中包含mac_address信息，以便API服务正确关联
            if "mac_address" not in data:
                data["mac_address"] = self.mac_address
                
            print(f"为任务启动回复添加节点信息: mac_address={self.mac_address}")
            
        payload = {
            "message_id": message_id,
            "message_uuid": message_uuid,
            "status": status,
            "data": data,
            "timestamp": int(time.time()),
            "mac_address": self.mac_address  # 添加mac_address到顶层，确保API服务可以识别
        }
        
        result = self.client.publish(
            topic=topic,
            payload=json.dumps(payload),
            qos=self.config.get("qos", 1)
        )
        
        if result.rc == 0:
            print(f"已发送配置回复: status={status}, message_uuid={message_uuid}")
        else:
            print(f"发送配置回复失败，错误码: {result.rc}")
    
    def _process_task(self, task_id, subtask_id, source, config, result_config):
        """
        处理任务
        
        Args:
            task_id: 任务ID
            subtask_id: 子任务ID
            source: 数据源配置
            config: 任务配置
            result_config: 结果配置
        """
        try:
            # 记录任务信息
            task_key = f"{task_id}_{subtask_id}"
            self.running_tasks[task_key] = {
                "task_id": task_id,
                "subtask_id": subtask_id,
                "start_time": time.time(),
                "stop": False
            }
            
            # 增加任务计数
            self.task_count += 1
            print(f"开始处理任务: {task_id}/{subtask_id}, 当前任务数: {self.task_count}")
            
            # 发送任务状态 - 运行中
            self._send_task_status(task_id, subtask_id, "running")
            
            # 模拟任务处理时间
            source_type = source.get("type", "image")
            process_time = 5  # 默认5秒
            
            if source_type == "video":
                process_time = 10
            elif source_type == "stream":
                process_time = 15
                
            # 模拟任务执行
            print(f"模拟任务执行中，将花费 {process_time} 秒...")
            
            # 分段执行，支持中途停止
            for i in range(process_time):
                # 检查是否需要停止
                if self.running_tasks[task_key]["stop"]:
                    print(f"任务 {task_id}/{subtask_id} 被请求停止")
                    # 发送任务失败状态
                    self._send_task_status(task_id, subtask_id, "failed", "任务被手动停止")
                    break
                    
                # 等待1秒
                time.sleep(1)
                print(f"任务 {task_id}/{subtask_id} 处理中: {i+1}/{process_time}")
            
            # 如果没有被停止，则完成任务
            if not self.running_tasks[task_key]["stop"]:
                # 生成模拟结果数据
                result_data = self._generate_result(source_type, config)
                
                # 发送任务完成状态
                self._send_task_status(task_id, subtask_id, "completed")
                
                # 发送任务结果
                self._send_task_result(task_id, subtask_id, result_data, result_config)
                
                print(f"任务 {task_id}/{subtask_id} 处理完成")
            
            # 清理任务记录
            del self.running_tasks[task_key]
            
            # 减少任务计数
            self.task_count -= 1
            print(f"任务 {task_id}/{subtask_id} 处理结束，当前任务数: {self.task_count}")
            
        except Exception as e:
            print(f"处理任务 {task_id}/{subtask_id} 时出错: {e}")
            import traceback
            print(traceback.format_exc())
            
            # 发送任务失败状态
            self._send_task_status(task_id, subtask_id, "failed", str(e))
            
            # 清理任务记录
            if task_key in self.running_tasks:
                del self.running_tasks[task_key]
                
            # 确保任务计数正确
            if self.task_count > 0:
                self.task_count -= 1
    
    def _generate_result(self, source_type, config):
        """生成模拟结果数据"""
        model_code = config.get("model_code", "unknown")
        
        if source_type == "image":
            # 图像分析结果
            return {
                "objects": [
                    {
                        "type": "person",
                        "confidence": round(random.uniform(0.85, 0.99), 2),
                        "bbox": [random.randint(10, 100), random.randint(10, 100), 
                                random.randint(50, 150), random.randint(150, 300)]
                    },
                    {
                        "type": "car",
                        "confidence": round(random.uniform(0.7, 0.95), 2),
                        "bbox": [random.randint(200, 300), random.randint(200, 300), 
                                random.randint(100, 200), random.randint(50, 150)]
                    }
                ],
                "model_info": {
                    "model_code": model_code,
                    "version": "1.0.0",
                    "processing_time": round(random.uniform(0.05, 0.2), 3)
                }
            }
        elif source_type == "video":
            # 视频分析结果
            return {
                "frames": [
                    {
                        "frame_id": 0,
                        "objects": [
                            {
                                "type": "person",
                                "confidence": round(random.uniform(0.85, 0.99), 2),
                                "bbox": [random.randint(10, 100), random.randint(10, 100), 
                                        random.randint(50, 150), random.randint(150, 300)]
                            }
                        ]
                    },
                    {
                        "frame_id": 10,
                        "objects": [
                            {
                                "type": "car",
                                "confidence": round(random.uniform(0.7, 0.95), 2),
                                "bbox": [random.randint(200, 300), random.randint(200, 300), 
                                        random.randint(100, 200), random.randint(50, 150)]
                            }
                        ]
                    }
                ],
                "model_info": {
                    "model_code": model_code,
                    "version": "1.0.0",
                    "total_frames": 20,
                    "processing_time": round(random.uniform(0.5, 2.0), 3)
                }
            }
        else:
            # 通用分析结果
            return {
                "status": "success",
                "source_type": source_type,
                "model_code": model_code,
                "timestamp": int(time.time()),
                "processing_time": round(random.uniform(0.1, 1.0), 3)
            }
    
    def _send_task_status(self, task_id, subtask_id, status, message=None):
        """发送任务状态"""
        if not self.connected:
            print("未连接到MQTT Broker，无法发送任务状态")
            return
        
        topic_prefix = self.config.get("topic_prefix", "meek/")
        topic = f"{topic_prefix}{self.mac_address}/status"
        
        payload = {
            "timestamp": int(time.time()),
            "task_id": task_id,
            "subtask_id": subtask_id,
            "status": status,
            "node_id": self.node_id,
            "mac_address": self.mac_address
        }
        
        if message:
            payload["message"] = message
        
        result = self.client.publish(
            topic=topic,
            payload=json.dumps(payload),
            qos=self.config.get("qos", 1)
        )
        
        if result.rc == 0:
            print(f"已发送任务 {task_id}/{subtask_id} 状态: {status}")
        else:
            print(f"发送任务状态失败，错误码: {result.rc}")
    
    def _send_task_result(self, task_id, subtask_id, result_data, result_config):
        """发送任务结果"""
        if not self.connected:
            print("未连接到MQTT Broker，无法发送任务结果")
            return
        
        # 使用回调主题或默认主题
        callback_topic = result_config.get("callback_topic")
        if not callback_topic:
            topic_prefix = self.config.get("topic_prefix", "meek/")
            callback_topic = f"{topic_prefix}{self.mac_address}/result"
        
        payload = {
            "timestamp": int(time.time()),
            "task_id": task_id,
            "subtask_id": subtask_id,
            "node_id": self.node_id,
            "mac_address": self.mac_address,
            "status": "success",
            "result": result_data
        }
        
        result = self.client.publish(
            topic=callback_topic,
            payload=json.dumps(payload),
            qos=self.config.get("qos", 1)
        )
        
        if result.rc == 0:
            print(f"已发送任务 {task_id}/{subtask_id} 结果到主题: {callback_topic}")
        else:
            print(f"发送任务结果失败，错误码: {result.rc}")
    
    def publish_connection_status(self, status):
        """发布节点连接状态"""
        if not self.connected and status != "offline":
            print("未连接到MQTT Broker，无法发布连接状态")
            return
        
        topic_prefix = self.config.get("topic_prefix", "meek/")
        topic = f"{topic_prefix}connection"
        
        # 获取系统资源信息
        resource_usage = self.get_system_resource_usage()
        
        # 构建元数据
        metadata = {
            "ip": self.ip,
            "port": 8002,  # 假设分析服务端口
            "hostname": self.hostname,
            "version": "1.0.0",
            "is_active": status == "online",  # online状态设为True，其他状态设为False
            "capabilities": {
                "max_tasks": 10,
                "supported_models": ["yolov5", "yolov8", "efficientdet"],
                "supported_sources": ["image", "video", "stream"]
            }
        }
        
        # 构建连接状态消息
        payload = {
            "mac_address": self.mac_address,
            "node_id": self.node_id,  # 添加节点ID
            "client_id": self.client_id,  # 添加客户端ID
            "status": status,
            "node_type": self.service_type,
            "timestamp": int(time.time()),
            "metadata": metadata
        }
        
        result = self.client.publish(
            topic=topic,
            payload=json.dumps(payload),
            qos=self.config.get("qos", 1)
        )
        
        if result.rc == 0:
            print(f"已发布节点连接状态: {status}")
        else:
            print(f"发布节点连接状态失败，错误码: {result.rc}")
    
    def publish_status_update(self):
        """发布节点状态更新"""
        if not self.connected:
            print("未连接到MQTT Broker，无法发布状态更新")
            return
        
        topic_prefix = self.config.get("topic_prefix", "meek/")
        topic = f"{topic_prefix}{self.mac_address}/status"
        
        # 获取资源使用情况
        resource = self.get_system_resource_usage()
        
        # 构建状态消息
        payload = {
            "timestamp": int(time.time()),
            "status": "online",
            "client_id": self.client_id,  # 添加client_id字段
            "node_id": self.node_id,
            "mac_address": self.mac_address,
            "node_type": self.service_type,  # 添加node_type字段
            "load": resource
        }
        
        result = self.client.publish(
            topic=topic,
            payload=json.dumps(payload),
            qos=self.config.get("qos", 1)
        )
        
        if result.rc == 0:
            print(f"已发布节点状态更新: CPU={resource['cpu']:.1f}%, " 
                  f"内存={resource['memory']:.1f}%, GPU={resource['gpu']:.1f}%, "
                  f"任务数={resource['running_tasks']}")
        else:
            print(f"发布节点状态更新失败，错误码: {result.rc}")
    
    def start_resource_reporter(self):
        """启动资源使用情况报告线程"""
        self.running = True
        
        def report_resources():
            """定期报告资源使用情况"""
            print("资源报告线程已启动")
            print(f"将每60秒向主题 {self.config.get('topic_prefix', 'meek/')}{self.mac_address}/status 发送状态更新")
            
            while self.running and self.connected:
                try:
                    # 发送节点状态更新
                    self.publish_status_update()
                    
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
                        print("  online         - 发送上线状态")
                        print("  offline        - 发送离线状态")
                        print("  status         - 发送状态更新")
                        print("  tasks          - 显示当前任务")
                        print("  info           - 显示节点信息")
                        print("  quit/exit      - 退出程序")
                    elif cmd == "online":
                        self.publish_connection_status("online")
                    elif cmd == "offline":
                        self.publish_connection_status("offline")
                    elif cmd == "status":
                        self.publish_status_update()
                    elif cmd == "tasks":
                        if self.running_tasks:
                            print("当前运行任务:")
                            for key, task in self.running_tasks.items():
                                elapsed = time.time() - task["start_time"]
                                print(f"  任务ID: {task['task_id']}/{task['subtask_id']}, 已运行: {elapsed:.1f}秒")
                        else:
                            print("当前没有运行中的任务")
                    elif cmd == "info":
                        print(f"节点ID: {self.node_id}")
                        print(f"MAC地址: {self.mac_address}")
                        print(f"服务类型: {self.service_type}")
                        print(f"连接状态: {'已连接' if self.connected else '未连接'}")
                        resource = self.get_system_resource_usage()
                        print(f"CPU使用率: {resource['cpu']:.1f}%")
                        print(f"内存使用率: {resource['memory']:.1f}%")
                        print(f"GPU使用率: {resource['gpu']:.1f}%")
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
    parser.add_argument("--mac", help="节点MAC地址，不提供则使用系统MAC地址")
    parser.add_argument("--service-type", default="analysis", help="服务类型，默认为analysis")
    parser.add_argument("--broker", default=DEFAULT_CONFIG["broker_host"], help=f"MQTT Broker地址，默认为{DEFAULT_CONFIG['broker_host']}")
    parser.add_argument("--port", type=int, default=DEFAULT_CONFIG["broker_port"], help=f"MQTT Broker端口，默认为{DEFAULT_CONFIG['broker_port']}")
    parser.add_argument("--prefix", default=DEFAULT_CONFIG["topic_prefix"], help=f"主题前缀，默认为{DEFAULT_CONFIG['topic_prefix']}")
    args = parser.parse_args()
    
    # 更新配置
    config = DEFAULT_CONFIG.copy()
    config["broker_host"] = args.broker
    config["broker_port"] = args.port
    config["topic_prefix"] = args.prefix
    
    # 创建并运行客户端
    client = MQTTTestClient(config=config, node_id=args.mac, service_type=args.service_type)
    client.run()

if __name__ == "__main__":
    main()
