import json
import time
import uuid
import logging
from typing import Dict, Any, Callable, List, Optional
from paho.mqtt import client as mqtt_client
from core.database import SessionLocal
from crud.mqtt_node import MQTTNodeCRUD
from models.database import MQTTNode  # 显式导入MQTTNode模型
import socket
import platform
import psutil
import traceback  # 添加traceback模块用于打印详细错误

logger = logging.getLogger(__name__)

class MQTTClient:
    """
    MQTT客户端服务类，用于API服务与分析服务之间的MQTT通信
    """
    def __init__(self, config: Dict[str, Any]):
        """
        初始化MQTT客户端
        
        Args:
            config: MQTT配置信息，包含broker_host, broker_port等
        """
        self.config = config
        self.client_id = f"{config.get('client_id', 'api_service')}-{str(uuid.uuid4())}"
        
        # 兼容paho-mqtt 2.0版本
        self.client = mqtt_client.Client(
            client_id=self.client_id,
            callback_api_version=mqtt_client.CallbackAPIVersion.VERSION1  # 使用旧版API
        )
        
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        
        # 用户认证
        if config.get('username') and config.get('password'):
            self.client.username_pw_set(config.get('username'), config.get('password'))
        
        # TLS配置
        if config.get('use_tls', False):
            self.client.tls_set(ca_certs=config.get('tls_ca_certs'))
        
        # 连接状态
        self.connected = False
        
        # 回调函数映射
        self.topic_handlers: Dict[str, List[Callable]] = {}
        
        # 任务结果缓存
        self.task_results: Dict[str, Any] = {}
        
        # 节点状态缓存
        self.nodes: Dict[str, Any] = {}
        
    def connect(self) -> bool:
        """
        连接到MQTT Broker
        
        Returns:
            bool: 连接是否成功
        """
        try:
            # API服务作为管理者不需要设置遗嘱消息
            logger.info(f"正在连接到MQTT Broker: {self.config.get('broker_host', 'localhost')}:{self.config.get('broker_port', 1883)}")
            
            # 连接到broker
            self.client.connect(
                self.config.get('broker_host', 'localhost'),
                self.config.get('broker_port', 1883),
                keepalive=self.config.get('keepalive', 60)
            )
            
            # 启动循环
            self.client.loop_start()
            return True
        except Exception as e:
            logger.error(f"MQTT连接失败: {e}")
            return False
    
    def disconnect(self):
        """
        断开与MQTT Broker的连接
        """
        try:
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False
        except Exception as e:
            logger.error(f"MQTT断开连接失败: {e}")
    
    def _on_connect(self, client, userdata, flags, rc):
        """
        连接回调函数
        """
        if rc == 0:
            logger.info("已连接到MQTT Broker!")
            self.connected = True
            
            # 获取主题前缀和QoS
            topic_prefix = self.config.get('topic_prefix', 'yolo/')
            qos = self.config.get('qos', 1)
            
            # 订阅主题
            self.client.subscribe(f"{topic_prefix}system/#", qos=qos)
            self.client.subscribe(f"{topic_prefix}nodes/+/status", qos=qos)
            self.client.subscribe(f"{topic_prefix}tasks/+/status", qos=qos)
            self.client.subscribe(f"{topic_prefix}tasks/+/result", qos=qos)
            
            # API服务不需要发布自身状态，只作为消息管理和接收者
            logger.info("MQTT客户端初始化完成，开始监听消息")
        else:
            logger.error(f"连接失败，返回码: {rc}")
            self.connected = False
    
    def _on_disconnect(self, client, userdata, rc):
        """
        断开连接回调函数
        """
        logger.warning(f"MQTT Broker断开连接，返回码: {rc}")
        self.connected = False
    
    def _on_message(self, client, userdata, msg):
        """
        消息接收回调函数
        """
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode())
            
            logger.debug(f"接收到消息: Topic={topic}, Payload={payload}")
            
            topic_prefix = self.config.get('topic_prefix', 'yolo/')
            
            # 处理任务状态更新
            if topic.startswith(f"{topic_prefix}tasks/") and topic.endswith("/status"):
                self._handle_task_status(topic, payload)
            
            # 处理任务结果
            elif topic.startswith(f"{topic_prefix}tasks/") and topic.endswith("/result"):
                self._handle_task_result(topic, payload)
            
            # 处理节点状态
            elif topic.startswith(f"{topic_prefix}nodes/") and topic.endswith("/status"):
                self._handle_node_status(topic, payload)
            
            # 调用注册的主题处理函数
            handlers = self._get_matched_handlers(topic)
            for handler in handlers:
                try:
                    handler(topic, payload)
                except Exception as e:
                    logger.error(f"处理主题回调时出错: {e}")
        except Exception as e:
            logger.error(f"处理消息时出错: {e}")
    
    def _get_matched_handlers(self, topic: str) -> List[Callable]:
        """
        获取匹配主题的所有处理函数
        """
        result = []
        for pattern, handlers in self.topic_handlers.items():
            if self._match_topic(pattern, topic):
                result.extend(handlers)
        return result
    
    def _match_topic(self, pattern: str, topic: str) -> bool:
        """
        检查主题是否匹配模式
        支持MQTT通配符: + (单层) 和 # (多层)
        """
        pattern_parts = pattern.split('/')
        topic_parts = topic.split('/')
        
        if len(pattern_parts) > len(topic_parts) and pattern_parts[-1] != '#':
            return False
        
        for i, pattern_part in enumerate(pattern_parts):
            if pattern_part == '#':
                return True
            if pattern_part != '+' and pattern_part != topic_parts[i]:
                return False
            if i == len(pattern_parts) - 1 and i < len(topic_parts) - 1:
                return False
        
        return len(pattern_parts) == len(topic_parts)
    
    def _handle_task_status(self, topic: str, payload: Dict[str, Any]):
        """
        处理任务状态更新消息
        """
        if not isinstance(payload, dict) or not payload.get('payload', {}).get('task_id'):
            return
        
        task_id = payload['payload']['task_id']
        status = payload['payload'].get('status')
        
        if task_id and status:
            if task_id not in self.task_results:
                self.task_results[task_id] = {}
            
            self.task_results[task_id].update({
                'status': status,
                'updated_at': payload.get('timestamp', int(time.time()))
            })
            
            logger.info(f"任务状态更新: {task_id} -> {status}")
    
    def _handle_task_result(self, topic: str, payload: Dict[str, Any]):
        """
        处理任务结果消息
        """
        if not isinstance(payload, dict) or not payload.get('payload', {}).get('task_id'):
            return
        
        task_id = payload['payload']['task_id']
        result = payload['payload'].get('result')
        
        if task_id and result:
            if task_id not in self.task_results:
                self.task_results[task_id] = {}
            
            self.task_results[task_id].update({
                'result': result,
                'updated_at': payload.get('timestamp', int(time.time()))
            })
            
            logger.info(f"收到任务结果: {task_id}")
    
    def _handle_node_status(self, topic: str, payload: Dict[str, Any]):
        """
        处理节点状态更新消息
        """
        logger.info(f"接收到节点状态消息 - 主题: {topic}")
        logger.info(f"消息内容: {json.dumps(payload, ensure_ascii=False)}")
        
        if not isinstance(payload, dict):
            logger.error(f"消息格式错误: payload不是字典类型 - {type(payload)}")
            return
        
        if not payload.get('payload', {}).get('node_id'):
            logger.error(f"消息格式错误: 缺少node_id - {payload}")
            return
        
        topic_prefix = self.config.get('topic_prefix', 'yolo/')
        node_id = payload['payload']['node_id']
        status = payload['payload'].get('status')
        
        logger.info(f"提取的节点信息 - ID: {node_id}, 状态: {status}")
        
        # 跳过API服务自身的节点ID处理
        if node_id.startswith("api_service-"):
            logger.info(f"跳过API服务自身的节点ID: {node_id}")
            return
        
        # 解析主题中的节点ID
        # 格式: {topic_prefix}nodes/{node_id}/status
        parts = topic.split('/')
        if len(parts) >= 3:
            topic_node_id = parts[-2]  # 倒数第二个部分是节点ID
            logger.info(f"从主题提取的节点ID: {topic_node_id}")
            
            # 跳过API服务自身的节点ID处理（从主题中获取）
            if topic_node_id.startswith("api_service-"):
                logger.info(f"跳过API服务自身的节点ID(从主题): {topic_node_id}")
                return
            
            if node_id != topic_node_id:
                logger.warning(f"节点ID不匹配: 主题={topic_node_id}, 负载={node_id}")
                node_id = topic_node_id  # 以主题中的ID为准
        
        if node_id and status:
            metadata = payload['payload'].get('metadata', {})
            service_type = payload['payload'].get('service_type', 'unknown')
            
            # 再次检查服务类型，跳过API服务
            if service_type == "api":
                logger.info(f"跳过API服务类型的节点: {node_id}")
                return
            
            if node_id not in self.nodes:
                logger.info(f"发现新节点: {node_id} ({service_type})")
                self.nodes[node_id] = {}
            else:
                logger.info(f"更新已知节点: {node_id} ({service_type})")
            
            self.nodes[node_id].update({
                'node_id': node_id,
                'status': status,
                'service_type': service_type,
                'metadata': metadata,
                'updated_at': payload.get('timestamp', int(time.time()))
            })
            
            logger.info(f"接收到节点状态更新: {node_id} ({service_type}) -> {status}")
            
            # 保存到数据库
            try:
                logger.info(f"开始保存节点 {node_id} 状态到数据库...")
                db = SessionLocal()
                
                # 提取IP和端口信息（如果有）
                ip = None
                port = None
                hostname = None
                version = None
                
                if metadata:
                    logger.info(f"节点元数据: {json.dumps(metadata, ensure_ascii=False)}")
                    ip = metadata.get('ip')
                    port = metadata.get('port')
                    hostname = metadata.get('hostname')
                    version = metadata.get('version')
                    
                    logger.info(f"解析元数据 - IP: {ip}, 端口: {port}, 主机名: {hostname}, 版本: {version}")
                
                # 构建节点数据
                node_data = {
                    'node_id': node_id,
                    'client_id': node_id,  # 使用node_id作为client_id
                    'service_type': service_type,
                    'status': status,
                    'node_metadata': metadata,  # 字段已修改
                    'ip': ip,
                    'port': port,
                    'hostname': hostname,
                    'version': version
                }
                
                logger.info(f"准备更新或创建节点，节点数据: {json.dumps(node_data, ensure_ascii=False, default=str)}")
                
                # 检查节点是否已存在
                existing_node = db.query(MQTTNode).filter(MQTTNode.node_id == node_id).first()
                if existing_node:
                    logger.info(f"节点 {node_id} 已存在，更新状态...")
                else:
                    logger.info(f"节点 {node_id} 不存在，将创建新记录")
                
                # 更新或创建节点
                try:
                    result = MQTTNodeCRUD.update_mqtt_node_status(db, node_id, status, metadata)
                    if result:
                        logger.info(f"成功更新节点 {node_id} 状态为 {status}")
                    else:
                        logger.warning(f"未找到节点 {node_id}，尝试创建新节点")
                        node_obj = MQTTNodeCRUD.create_mqtt_node(db, node_data)
                        if node_obj:
                            logger.info(f"成功创建节点 {node_id}")
                        else:
                            logger.error(f"创建节点 {node_id} 失败")
                except Exception as e:
                    logger.error(f"更新/创建节点状态时出错: {e}")
                    logger.error(f"错误详情: {traceback.format_exc()}")
                
                db.close()
                logger.info(f"节点 {node_id} 状态处理完成")
            except Exception as e:
                logger.error(f"保存MQTT节点状态到数据库失败: {e}")
                logger.error(f"错误详情: {traceback.format_exc()}")
    
    def _publish_node_status(self, status: str):
        """
        API服务作为管理者，不应发布自身状态。
        此方法已禁用，保留仅为兼容性。

        Args:
            status: 节点状态 (online/offline)
        """
        logger.info(f"_publish_node_status方法已禁用，API服务不应发布自身状态")
        return None  # 直接返回，不执行任何发布操作
    
    def publish_task_request(self, task_id: str, task_type: str, config: Dict[str, Any]) -> bool:
        """
        发布任务请求
        
        Args:
            task_id: 任务ID
            task_type: 任务类型 (image_analysis, video_analysis, stream_analysis)
            config: 任务配置
            
        Returns:
            bool: 是否发送成功
        """
        if not self.connected:
            logger.error("MQTT客户端未连接，无法发送任务请求")
            return False
        
        topic_prefix = self.config.get('topic_prefix', 'yolo/')
        
        # 构建任务请求消息
        payload = {
            "version": "2.0.0",
            "message_type": "task_request",
            "timestamp": int(time.time()),
            "payload": {
                "task_id": task_id,
                "task_type": task_type,
                "source": config.get("source", {}),
                "config": config.get("config", {}),
                "result_config": config.get("result_config", {})
            }
        }
        
        # 发布任务请求
        topic = f"{topic_prefix}tasks/{task_id}/request"
        result = self.client.publish(
            topic, 
            json.dumps(payload), 
            qos=self.config.get('qos', 1)
        )
        
        if result.rc == 0:
            logger.info(f"任务请求已发布: {task_id}")
            return True
        else:
            logger.error(f"任务请求发布失败: {task_id}, 错误码: {result.rc}")
            return False
    
    def publish_task_control(self, task_id: str, action: str, params: Optional[Dict[str, Any]] = None) -> bool:
        """
        发布任务控制命令
        
        Args:
            task_id: 任务ID
            action: 控制动作 (stop, pause, resume)
            params: 附加参数
            
        Returns:
            bool: 是否发送成功
        """
        if not self.connected:
            logger.error("MQTT客户端未连接，无法发送任务控制命令")
            return False
        
        topic_prefix = self.config.get('topic_prefix', 'yolo/')
        
        # 构建任务控制消息
        payload = {
            "version": "2.0.0",
            "message_type": "task_control",
            "timestamp": int(time.time()),
            "payload": {
                "task_id": task_id,
                "action": action,
                "params": params or {}
            }
        }
        
        # 发布任务控制命令
        topic = f"{topic_prefix}tasks/{task_id}/control"
        result = self.client.publish(
            topic, 
            json.dumps(payload), 
            qos=self.config.get('qos', 1)
        )
        
        if result.rc == 0:
            logger.info(f"任务控制命令已发布: {task_id}, 动作: {action}")
            return True
        else:
            logger.error(f"任务控制命令发布失败: {task_id}, 错误码: {result.rc}")
            return False
    
    def register_handler(self, topic_pattern: str, handler: Callable):
        """
        注册主题处理函数
        
        Args:
            topic_pattern: 主题模式，支持MQTT通配符
            handler: 处理函数，接收(topic, payload)参数
        """
        if topic_pattern not in self.topic_handlers:
            self.topic_handlers[topic_pattern] = []
        
        self.topic_handlers[topic_pattern].append(handler)
    
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        获取任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            Dict: 任务状态信息
        """
        return self.task_results.get(task_id, {})
    
    def get_node_status(self, node_id: str) -> Dict[str, Any]:
        """
        获取节点状态
        
        Args:
            node_id: 节点ID
            
        Returns:
            Dict: 节点状态信息
        """
        return self.nodes.get(node_id, {})
    
    def get_all_nodes(self) -> Dict[str, Any]:
        """
        获取所有节点状态
        
        Returns:
            Dict: 所有节点状态信息
        """
        return self.nodes 