import json
import time
import uuid
import logging
from typing import Dict, Any, Callable, List, Optional, Tuple
from paho.mqtt import client as mqtt_client
from sqlalchemy.orm import Session
from core.database import SessionLocal
from crud.mqtt_node import MQTTNodeCRUD
from crud.task import TaskCRUD
from models.database import MQTTNode, SubTask  # 显式导入MQTTNode模型
import socket
import platform
import psutil
import traceback  # 添加traceback模块用于打印详细错误
import asyncio
from datetime import datetime
import ssl
import threading
from shared.utils.logger import setup_logger
from .mqtt_message_processor import MQTTMessageProcessor

logger = setup_logger(__name__)

class MQTTClient:
    """
    MQTT客户端服务类，用于API服务与分析服务之间的MQTT通信
    基于新的指令式通信协议实现
    """
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化MQTT客户端
        
        Args:
            config: MQTT配置信息，包含broker_host, broker_port等
        """
        # 默认配置
        self.config = {
            "broker_host": "localhost",
            "broker_port": 1883,
            "client_id": f"api-service-{uuid.uuid4().hex[:8]}",
            "username": None,
            "password": None,
            "use_tls": False,
            "tls_ca_cert": None,
            "tls_cert": None,
            "tls_key": None,
            "topic_prefix": "meek",
            "keepalive": 60,
            "reconnect_interval": 5,
            "max_reconnect_attempts": 20
        }
        
        # 更新配置
        if config:
            self.config.update(config)
        
        self.client_id = f"{self.config.get('client_id', 'api_service')}-{str(uuid.uuid4())}"
        
        # 判断是否为API服务（根据client_id前缀判断）
        self.is_api_service = self.client_id.startswith('api_service-')
        
        # 兼容paho-mqtt 2.0版本
        self.client = mqtt_client.Client(
            client_id=self.client_id,
            callback_api_version=mqtt_client.CallbackAPIVersion.VERSION1,  # 使用旧版API
            clean_session=True,
            protocol=mqtt_client.MQTTv311,
            transport="tcp"
        )
        
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        
        # 用户认证
        if self.config.get("username") and self.config.get("password"):
            logger.info(f"使用认证信息连接MQTT: 用户名={self.config.get('username')}")
            self.client.username_pw_set(
                self.config.get("username"),
                self.config.get("password")
            )
        
        # TLS配置
        if self.config.get('use_tls', False):
            if self.config.get('tls_ca_cert'):
                # 单向认证
                self.client.tls_set(
                    ca_certs=self.config.get('tls_ca_cert'),
                    certfile=self.config.get('tls_cert'),
                    keyfile=self.config.get('tls_key'),
                    tls_version=ssl.PROTOCOL_TLS,
                    cert_reqs=ssl.CERT_REQUIRED if self.config.get('tls_cert') else ssl.CERT_NONE
                )
                self.client.tls_insecure_set(False)
        
        # 连接状态
        self.connected = False
        self.connecting = False
        self.reconnect_thread = None
        self.reconnect_attempt = 0
        
        # 回调函数映射
        self.topic_handlers: Dict[str, List[Callable]] = {}
        
        # 任务结果缓存
        self.task_results: Dict[str, Any] = {}
        
        # 节点状态缓存 - 使用MAC地址作为键
        self.nodes: Dict[str, Any] = {}
        
        # 命令响应等待
        self.command_responses: Dict[str, Any] = {}
        
        # 消息等待
        self.waiting_messages: Dict[str, threading.Event] = {}
        self.message_responses: Dict[str, Any] = {}
        
        # 线程锁
        self.lock = threading.RLock()
        
        # 断开连接标志
        self.manually_disconnected = False
        
        # 订阅的主题
        self.subscribed_topics: Set[str] = set()
        
        # 连接锁（用于同步连接过程）
        self.connect_lock = threading.RLock()
        
        # 已发布消息的ID
        self.published_messages: Dict[int, Dict[str, Any]] = {}
        
        # 消息处理器
        self.message_processor = MQTTMessageProcessor.get_instance()
        
    def connect(self) -> bool:
        """
        连接到MQTT Broker
        
        Returns:
            bool: 是否连接成功
        """
        with self.connect_lock:
            if self.connected:
                logger.info("MQTT客户端已连接")
                return True
                
            if self.connecting:
                logger.info("MQTT客户端正在连接中...")
                return False
                
            self.connecting = True
            self.manually_disconnected = False
            
            try:
                logger.info(f"连接到MQTT Broker: {self.config['broker_host']}:{self.config['broker_port']}")
                
                # 设置保活时间
                self.client.connect(
                    host=self.config["broker_host"],
                    port=self.config["broker_port"],
                    keepalive=self.config["keepalive"]
                )
                
                # 启动网络循环（在后台线程中运行）
                self.client.loop_start()
                
                # 等待连接完成
                start_time = time.time()
                timeout = 10.0  # 连接超时时间
                
                while not self.connected and time.time() - start_time < timeout:
                    time.sleep(0.1)
                    
                if not self.connected:
                    logger.error(f"连接MQTT Broker超时: {self.config['broker_host']}:{self.config['broker_port']}")
                    self.connecting = False
                    self.client.loop_stop()
                    return False
                    
                logger.info(f"成功连接到MQTT Broker: {self.config['broker_host']}:{self.config['broker_port']}")
                
                # 发布连接通知
                self._publish_connection_status("online")
                
                # 重新订阅之前的主题
                self._resubscribe_topics()
                
                self.connecting = False
                return True
                
            except Exception as e:
                logger.error(f"连接MQTT Broker失败: {str(e)}")
                self.connected = False
                self.connecting = False
                
                # 启动重连线程
                self._start_reconnect_thread()
                
                return False
    
    def disconnect(self):
        """
        断开与MQTT Broker的连接
        """
        with self.connect_lock:
            if not self.connected:
                return
                
            # 设置手动断开标志，避免自动重连
            self.manually_disconnected = True
            
            # 发布离线通知
            self._publish_connection_status("offline")
            
            # 停止网络循环
            self.client.loop_stop()
            
            # 断开连接
            try:
                self.client.disconnect()
            except Exception as e:
                logger.error(f"断开MQTT连接失败: {str(e)}")
                
            logger.info("已断开MQTT连接")
    
    def _on_connect(self, client, userdata, flags, rc):
        """
        连接回调函数
        """
        if rc == 0:
            logger.info("已连接到MQTT Broker!")
            self.connected = True
            self.connecting = False
            self.reconnect_attempt = 0
            
            # 获取QoS
            qos = self.config.get('qos', 1)
            
            # 根据MQTT通信协议规范订阅主题
            # 连接状态主题
            self.client.subscribe(f"{self.config['topic_prefix']}connection", qos=qos)
            
            # 节点配置和指令回复主题 - 修改为规范中的主题名称
            self.client.subscribe(f"{self.config['topic_prefix']}device_config_reply", qos=qos)
            
            # 节点状态和结果主题 - 使用通配符
            self.client.subscribe(f"{self.config['topic_prefix']}+/status", qos=qos)
            self.client.subscribe(f"{self.config['topic_prefix']}+/result", qos=qos)
            
            logger.info("MQTT客户端初始化完成，开始监听消息")
        else:
            logger.error(f"连接失败，返回码: {rc}")
            self.connected = False
            self.connecting = False
            
            # 启动重连线程
            self._start_reconnect_thread()
    
    def _on_disconnect(self, client, userdata, rc):
        """
        断开连接回调函数
        """
        logger.warning(f"MQTT Broker断开连接，返回码: {rc}")
        self.connected = False
        
        if rc == 0:
            logger.info("已与MQTT Broker正常断开连接")
        else:
            logger.warning(f"MQTT连接意外断开，代码: {rc}")
            
            # 如果不是手动断开，则尝试重连
            if not self.manually_disconnected:
                self._start_reconnect_thread()
    
    def _on_message(self, client, userdata, msg):
        """
        消息接收回调函数
        """
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode())
            
            logger.debug(f"接收到消息: Topic={topic}, Payload={payload}")
            
            # 检查是否是等待的响应
            if isinstance(payload, dict) and "message_id" in payload:
                message_id = payload["message_id"]
                
                with self.lock:
                    if message_id in self.waiting_messages:
                        # 保存响应内容
                        self.message_responses[message_id] = payload
                        # 通知等待线程
                        self.waiting_messages[message_id].set()
                        return
            
            # 处理节点连接消息
            if topic == f"{self.config['topic_prefix']}connection":
                self._handle_connection(topic, payload)
            
            # 处理节点配置回复
            elif topic == f"{self.config['topic_prefix']}device_config_reply":
                self._handle_config_reply(payload)
            
            # 处理心跳消息（特殊处理）
            elif "/status" in topic and isinstance(payload, dict) and payload.get('type') == 'heartbeat':
                self._handle_heartbeat(topic, payload)
            
            # 处理节点状态更新
            elif "/status" in topic:
                self._handle_node_status(topic, payload)
            
            # 处理任务结果
            elif "/result" in topic:
                self._handle_task_result(topic, payload)
            
            # 调用注册的主题处理函数
            handlers = self._get_matched_handlers(topic)
            for handler in handlers:
                try:
                    handler(topic, payload)
                except Exception as e:
                    logger.error(f"处理主题回调时出错: {e}")
        except Exception as e:
            logger.error(f"处理消息时出错: {e}")
            logger.error(traceback.format_exc())
    
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
    
    def _handle_connection(self, topic: str, payload: Dict[str, Any]):
        """
        处理节点连接/断开连接消息
        """
        try:
            logger.info(f"接收到连接状态消息: {json.dumps(payload, ensure_ascii=False)}")
            
            if not isinstance(payload, dict):
                logger.error(f"连接状态消息格式错误: {payload}")
                return
                
            # 获取客户端ID和相关字段
            client_id = payload.get('client_id')
            message_type = payload.get('message_type')
            
            # 确认消息类型为连接消息
            if message_type and message_type != 'connection':
                logger.warning(f"未知的消息类型: {message_type}，期望为'connection'")
            
            # 优先使用node_type，如果不存在则尝试service_type，默认为'analysis'
            service_type = payload.get('node_type') or payload.get('service_type') or 'analysis'
            status = payload.get('status')
            timestamp = payload.get('timestamp')
            
            # 获取或创建metadata对象，确保包含所有原始字段
            metadata = payload.get('metadata', {})
            
            # 将所有顶级字段复制到metadata中，除了'metadata'本身
            for key, value in payload.items():
                if key != 'metadata':
                    metadata[key] = value
            
            # 提取MAC地址，按优先级获取
            if 'mac_address' in payload:
                mac_address = payload.get('mac_address')
            elif 'mac_address' in metadata:
                mac_address = metadata.get('mac_address')
            else:
                # 尝试从mqtt_node_id或node_id或client_id中提取MAC地址
                mac_address = payload.get('mqtt_node_id') or payload.get('node_id') or client_id
                # 如果client_id是复合格式，尝试提取MAC部分
                if not mac_address and client_id and '_' in client_id:
                    mac_address = client_id.split('_')[-1]
            
            logger.info(f"提取到节点信息: mac_address={mac_address}, client_id={client_id}, service_type={service_type}, node_id={payload.get('node_id')}")
            
            if not mac_address or not client_id or not status:
                logger.error(f"连接状态消息缺少必要字段: {payload}")
                return
                
            # 处理节点连接或断开
            if status == 'online':
                self._handle_node_connection(mac_address, client_id, service_type, metadata)
            elif status == 'offline':
                self._handle_node_disconnection(mac_address)
                
        except Exception as e:
            logger.error(f"处理连接状态消息失败: {e}")
            logger.error(traceback.format_exc())

    def _handle_node_connection(self, mac_address: str, client_id: str, service_type: str, metadata: Dict[str, Any]):
        """
        处理节点连接
        """
        try:
            logger.info(f"处理节点连接: MAC={mac_address}, 客户端ID={client_id}, 服务类型={service_type}")
            
            # 获取节点其他信息
            ip_address = metadata.get('ip')
            port = metadata.get('port')  # 添加提取端口信息
            hostname = metadata.get('hostname')
            system_info = metadata.get('system_info', {})
            # 获取资源信息
            resources = metadata.get('resources', {})
            capabilities = metadata.get('capabilities', {})
            
            # 获取最大任务数，优先使用顶层的max_tasks，其次使用capabilities中的max_tasks
            max_tasks = metadata.get('max_tasks') or capabilities.get('max_tasks', 20)
            
            # 获取版本信息
            version = metadata.get('version')
            
            # 更新数据库中的节点记录
            db = SessionLocal()
            try:
                # 首先通过MAC地址查找节点
                node = db.query(MQTTNode).filter(MQTTNode.mac_address == mac_address).first()
                
                if node:
                    logger.info(f"更新已存在的节点记录: MAC={mac_address}")
                    # 检查节点类型是否匹配
                    if node.service_type != service_type:
                        logger.warning(f"节点服务类型变更: {node.service_type} -> {service_type}")
                    
                    # 更新节点状态
                    node.status = 'online'
                    node.client_id = client_id
                    node.service_type = service_type
                    node.ip = ip_address
                    node.port = port  # 更新端口信息
                    node.hostname = hostname
                    node.last_active = datetime.now()
                    # 确保节点处于激活状态
                    node.is_active = True
                    
                    # 更新最大任务数
                    node.max_tasks = max_tasks
                    
                    # 更新版本信息
                    if version:
                        node.version = version
                    
                    # 如果存在资源信息，更新资源使用率
                    if resources:
                        node.cpu_usage = resources.get('cpu', node.cpu_usage)
                        node.memory_usage = resources.get('memory', node.memory_usage)
                        
                        # 更新任务计数
                        node.task_count = metadata.get('active_tasks', 0)
                    
                    # 更新节点元数据
                    if node.node_metadata is None:
                        node.node_metadata = {}
                    node.node_metadata.update(metadata)
                    
                    # 重置节点任务数（如果客户端重启）
                    if client_id != node.client_id:
                        logger.info(f"节点客户端ID变更: {node.client_id} -> {client_id}，重置任务计数")
                        node.task_count = 0
                        
                else:
                    logger.info(f"创建新节点记录: MAC={mac_address}")
                    # 直接从原始消息中提取node_id
                    node_id = metadata.get('node_id', client_id)
                    mqtt_node_id = metadata.get('mqtt_node_id', mac_address)
                    
                    logger.info(f"使用原始数据字段创建节点: node_id={node_id}, mqtt_node_id={mqtt_node_id}")
                    
                    # 创建新节点记录 - 直接使用原始字段
                    node = MQTTNode(
                        node_id=node_id,  # 使用原始node_id
                        mac_address=mac_address,
                        client_id=client_id,
                        service_type=service_type,
                        status='online',
                        ip=ip_address,
                        port=port,
                        hostname=hostname,
                        last_active=datetime.now(),
                        node_metadata=metadata,
                        task_count=metadata.get('active_tasks', 0),
                        max_tasks=max_tasks,
                        version=version,
                        is_active=True
                    )
                    db.add(node)
                    
                db.commit()
                logger.info(f"节点 {mac_address} 已标记为在线")
                
            except Exception as e:
                logger.error(f"更新节点记录失败: {e}")
                logger.error(traceback.format_exc())
                db.rollback()
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"处理节点连接失败: {e}")
            logger.error(traceback.format_exc())

    def _handle_node_disconnection(self, mac_address: str):
        """
        处理节点断开连接
        """
        try:
            logger.info(f"处理节点断开连接：MAC={mac_address}")
            
            # 更新数据库中的节点记录
            db = SessionLocal()
            try:
                # 查找节点
                node = db.query(MQTTNode).filter(MQTTNode.mac_address == mac_address).first()
                
                if node:
                    logger.info(f"更新节点状态为离线：MAC={mac_address}")
                    # 更新节点状态
                    node.status = 'offline'
                    node.last_active = datetime.now()
                    
                    # 设置任务转移标记，由健康检查服务处理离线任务
                    node.node_metadata = node.node_metadata or {}
                    node.node_metadata['need_task_transfer'] = True
                    node.node_metadata['offline_time'] = int(time.time())
                    
                    db.commit()
                    logger.info(f"节点 {mac_address} 已标记为离线，待任务转移")
                else:
                    logger.warning(f"未找到离线节点：MAC={mac_address}")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"处理节点断开连接失败：{e}")
            logger.error(traceback.format_exc())
    
    def _handle_config_reply(self, payload: Dict[str, Any]):
        """
        处理节点配置回复消息
        """
        try:
            logger.info(f"接收到节点配置回复: {json.dumps(payload, ensure_ascii=False)}")
            
            if not isinstance(payload, dict):
                logger.error(f"配置回复消息格式错误: {payload}")
                return
            
            message_id = payload.get('message_id')
            message_uuid = payload.get('message_uuid')
            status = payload.get('status')
            
            if message_uuid:
                # 保存响应到等待队列
                self.command_responses[message_uuid] = payload
                logger.info(f"命令响应已保存: {message_uuid}, 状态: {status}")
                
                # 处理任务指令响应
                if payload.get('data', {}).get('cmd_type') == 'start_task':
                    task_data = payload.get('data', {})
                    task_id = task_data.get('task_id')
                    subtask_id = task_data.get('subtask_id')
                    
                    if task_id and subtask_id:
                        # 更新数据库中的子任务状态
                        db = SessionLocal()
                        try:
                            # 通过subtask_id作为ID直接查找子任务
                            logger.info(f"查找子任务: subtask_id={subtask_id}")
                            subtask = None
                            
                            # 检查subtask_id是否为纯数字
                            if subtask_id.isdigit():
                                subtask = db.query(SubTask).filter(SubTask.id == int(subtask_id)).first()
                                if subtask:
                                    logger.info(f"找到子任务: {subtask.id}")
                                else:
                                    logger.warning(f"未找到子任务: subtask_id={subtask_id}")
                            else:
                                logger.warning(f"子任务ID不是纯数字: {subtask_id}，无法查询数据库")
                            
                            if subtask:
                                if status == 'success':
                                    # 任务被节点成功接收，更新状态为运行中
                                    logger.info(f"MQTT节点接收任务成功: task_id={task_id}, subtask_id={subtask_id}")
                                    subtask.status = 1  # 运行中状态
                                    subtask.started_at = datetime.now()
                                    subtask.error_message = None
                                    
                                    # 关联MQTT节点到子任务
                                    mac_address = payload.get('mac_address')
                                    if mac_address:
                                        mqtt_node = db.query(MQTTNode).filter(MQTTNode.mac_address == mac_address).first()
                                        if mqtt_node:
                                            logger.info(f"关联MQTT节点 {mac_address} 到子任务 {subtask_id}")
                                            subtask.mqtt_node_id = mqtt_node.id
                                            # 更新节点任务计数
                                            mqtt_node.task_count += 1
                                        else:
                                            logger.warning(f"未找到MAC地址为 {mac_address} 的MQTT节点")
                                else:
                                    # 任务被节点拒绝，记录错误信息
                                    error_msg = task_data.get('message', '节点拒绝任务')
                                    logger.warning(f"MQTT节点拒绝任务: task_id={task_id}, subtask_id={subtask_id}, 原因: {error_msg}")
                                    subtask.error_message = f"节点拒绝任务: {error_msg}"
                                
                                db.commit()
                                
                                # 更新主任务状态
                                from crud.task import update_task_status_from_subtasks
                                update_task_status_from_subtasks(db, subtask.task_id)
                            else:
                                logger.warning(f"未找到子任务记录: task_id={task_id}, subtask_id={subtask_id}")
                        except Exception as e:
                            logger.error(f"更新子任务状态失败: {e}")
                            logger.error(traceback.format_exc())
                        finally:
                            db.close()
                
                # 如果是任务指令回复且失败，需要处理任务重新分配
                if status == 'error' and payload.get('data', {}).get('cmd_type') == 'start_task':
                    self._handle_task_failure(payload)
        except Exception as e:
            logger.error(f"处理配置回复消息失败: {e}")
            logger.error(traceback.format_exc())
    
    def _handle_node_status(self, topic: str, payload: Dict[str, Any]):
        """
        处理节点状态更新消息，包括心跳消息和资源更新
        """
        try:
            logger.debug(f"接收到节点状态更新消息 - 主题: {topic}")
            
            # 从主题中提取MAC地址
            parts = topic.split('/')
            if len(parts) < 3:
                logger.error(f"无效的状态主题格式: {topic}")
                return
            
            mac_address = parts[1]  # {topic_prefix}/{mac_address}/status
            
            if not isinstance(payload, dict):
                logger.error(f"状态消息格式错误: {payload}")
                return
                
            # 提取节点状态信息
            status = payload.get('status', 'unknown')
            timestamp = payload.get('timestamp', int(time.time()))
            
            # 检查是否是心跳消息
            is_heartbeat = payload.get('type') == 'heartbeat'
            
            # 如果是心跳消息，使用心跳消息中的MAC地址
            if is_heartbeat and payload.get('mac_address'):
                mac_address = payload.get('mac_address')
                logger.debug(f"从心跳消息中提取MAC地址: {mac_address}")
            
            # 更新数据库中的节点信息
            db = SessionLocal()
            try:
                node = db.query(MQTTNode).filter(MQTTNode.mac_address == mac_address).first()
                
                if node:
                    # 更新基本状态
                    node.status = status if status != 'unknown' else 'online'
                    node.last_active = datetime.now()
                    
                    # 如果是心跳消息，更新更多详细信息
                    if is_heartbeat:
                        node.cpu_usage = payload.get('cpu_usage', node.cpu_usage)
                        node.memory_usage = payload.get('memory_usage', node.memory_usage)
                        node.gpu_usage = payload.get('gpu_usage', node.gpu_usage)
                        node.task_count = payload.get('task_count', node.task_count)
                        node.max_tasks = payload.get('max_tasks', node.max_tasks)
                        node.is_active = payload.get('is_active', node.is_active)
                        
                        # 更新客户端ID和服务类型
                        if payload.get('client_id'):
                            node.client_id = payload.get('client_id')
                        if payload.get('service_type'):
                            node.service_type = payload.get('service_type')
                            
                        logger.debug(f"心跳消息更新节点 {mac_address}: CPU={node.cpu_usage}, MEM={node.memory_usage}, 任务数={node.task_count}/{node.max_tasks}")
                    else:
                        # 处理非心跳状态消息
                        load = payload.get('load', {})
                        node.cpu_usage = load.get('cpu', node.cpu_usage)
                        node.memory_usage = load.get('memory', node.memory_usage)
                        node.gpu_usage = load.get('gpu', node.gpu_usage)
                        node.task_count = load.get('running_tasks', node.task_count)
                    
                    db.commit()
                    logger.debug(f"节点 {mac_address} 状态已更新: {status}")
                else:
                    # 如果节点不存在，尝试创建新节点（仅心跳消息包含足够信息时）
                    if is_heartbeat and payload.get('client_id') and payload.get('service_type'):
                        logger.info(f"收到未知节点 {mac_address} 的心跳，尝试创建节点记录")
                        
                        node = MQTTNode(
                            node_id = payload.get('node_id', payload.get('client_id')),
                            mac_address = mac_address,
                            client_id = payload.get('client_id'),
                            service_type = payload.get('service_type'),
                            status = 'online',
                            last_active = datetime.now(),
                            cpu_usage = payload.get('cpu_usage', 0),
                            memory_usage = payload.get('memory_usage', 0),
                            gpu_usage = payload.get('gpu_usage', 0),
                            task_count = payload.get('task_count', 0),
                            max_tasks = payload.get('max_tasks', 4),
                            is_active = payload.get('is_active', True)
                        )
                        
                        db.add(node)
                        db.commit()
                        logger.info(f"为心跳消息创建了新的节点记录: MAC={mac_address}")
                    else:
                        logger.warning(f"收到未知节点 {mac_address} 的状态更新，但缺少创建节点的必要信息")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"处理节点状态更新失败: {e}")
            logger.error(traceback.format_exc())
    
    def _handle_task_result(self, topic: str, payload: Dict[str, Any]):
        """
        处理任务结果消息
        """
        try:
            logger.info(f"接收到任务结果消息 - 主题: {topic}, 内容: {json.dumps(payload, ensure_ascii=False)[:200]}...")
            
            if not isinstance(payload, dict):
                logger.error(f"任务结果消息格式错误: {payload}")
                return
                
            task_id = payload.get('task_id')
            subtask_id = payload.get('subtask_id')
            status = payload.get('status')
            
            if not task_id or not subtask_id:
                logger.error(f"任务结果消息缺少必要字段: {payload}")
                return
                
            # 更新任务结果缓存
            key = f"{task_id}_{subtask_id}"
            self.task_results[key] = {
                'status': status,
                'result': payload.get('result'),
                'timestamp': payload.get('timestamp', int(time.time()))
            }
            
            # 任务结果到达时，也检查是否有未响应的命令
            # 这是为了处理节点直接返回结果而没有回复配置消息的情况
            for uuid, cmd_response in list(self.command_responses.items()):
                cmd_data = cmd_response.get('data', {})
                if cmd_data.get('task_id') == task_id and cmd_data.get('subtask_id') == subtask_id:
                    logger.info(f"根据任务结果自动更新命令响应: {uuid}")
                    # 不删除响应，只更新状态为成功
                    cmd_response['status'] = 'success'
            
            # 更新数据库中的子任务状态
            db = SessionLocal()
            try:
                # 查找子任务 - 通过subtask_id作为ID直接查找
                logger.info(f"尝试使用subtask_id查找子任务: subtask_id={subtask_id}")
                subtask = None
                
                # 检查subtask_id是否为纯数字
                if subtask_id.isdigit():
                    subtask = db.query(SubTask).filter(SubTask.id == int(subtask_id)).first()
                    if subtask:
                        logger.info(f"通过ID直接找到子任务: {subtask.id}")
                else:
                    logger.warning(f"子任务ID不是纯数字: {subtask_id}，无法查询数据库")
                
                if subtask:
                    # 如果还没有关联MQTT节点，从结果消息中获取mac_address并关联节点
                    if subtask.mqtt_node_id is None and 'mac_address' in payload:
                        mac_address = payload.get('mac_address')
                        mqtt_node = db.query(MQTTNode).filter(MQTTNode.mac_address == mac_address).first()
                        if mqtt_node:
                            logger.info(f"从任务结果中关联子任务到MQTT节点: {mac_address}")
                            subtask.mqtt_node_id = mqtt_node.id
                
                    # 根据状态更新子任务
                    if status == 'completed':
                        subtask.status = 2  # 已完成
                        subtask.completed_at = datetime.now()
                    elif status == 'failed':
                        subtask.status = 3  # 失败
                        subtask.error_message = payload.get('message', '任务执行失败')
                    elif status == 'running' or status == 'success':  # 注意这里增加了对'success'的处理
                        # 状态是运行中或成功，但子任务状态是未启动(0)，则更新为运行中(1)
                        if subtask.status == 0:
                            logger.info(f"子任务 {subtask_id} 从未启动状态改为运行中状态")
                        subtask.status = 1  # 运行中
                        if not subtask.started_at:
                            subtask.started_at = datetime.now()
                        subtask.error_message = None
                    
                    db.commit()
                    logger.info(f"子任务 {subtask_id} 状态已更新: {status}")
                    
                    # 更新主任务状态
                    from crud.task import update_task_status_from_subtasks
                    update_task_status_from_subtasks(db, subtask.task_id)
                else:
                    logger.warning(f"未找到子任务记录: subtask_id={subtask_id}")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"处理任务结果失败: {e}")
            logger.error(traceback.format_exc())
    
    async def _handle_node_offline(self, db: Session, mac_address: str):
        """
        处理节点离线情况，自动转移该节点的任务到其他节点
        
        Args:
            db: 数据库会话
            mac_address: 节点MAC地址
        """
        try:
            logger.info(f"处理节点 {mac_address} 离线，开始任务自动转移流程...")
            
            # 查找节点
            node = db.query(MQTTNode).filter(MQTTNode.mac_address == mac_address).first()
            if not node:
                logger.warning(f"未找到离线节点: {mac_address}")
                return
                
            # 查找该节点上运行的子任务
            running_subtasks = db.query(SubTask).filter(
                SubTask.mqtt_node_id == node.id,
                SubTask.status == 1  # 运行中
            ).all()
            
            if not running_subtasks:
                logger.info(f"节点 {mac_address} 没有运行中的子任务，无需转移")
                return
                
            logger.info(f"节点 {mac_address} 有 {len(running_subtasks)} 个运行中的子任务需要转移")
            
            # 查找可用的其他在线节点
            available_nodes = db.query(MQTTNode).filter(
                MQTTNode.status == "online",
                MQTTNode.is_active == True,
                MQTTNode.mac_address != mac_address,  # 排除当前离线节点
                MQTTNode.task_count < MQTTNode.max_tasks
            ).order_by(MQTTNode.task_count).all()
            
            if not available_nodes:
                logger.warning(f"没有可用的在线节点，所有子任务将重置为未启动状态等待后续分配")
                # 将子任务重置为未启动状态，等待有节点在线时再分配
                for subtask in running_subtasks:
                    subtask.status = 0  # 未启动
                    subtask.mqtt_node_id = None  # 清除节点关联
                    subtask.started_at = None
                    subtask.error_message = f"节点 {mac_address} 离线，等待重新分配"
                    
                    # 同时更新关联的主任务active_subtasks计数
                    task = subtask.task
                    if task and task.active_subtasks > 0:
                        task.active_subtasks -= 1
                
                db.commit()
                logger.info(f"已重置 {len(running_subtasks)} 个子任务为未启动状态")
                return
            
            # 开始任务转移
            transferred_count = 0
            failed_count = 0
            
            for subtask in running_subtasks:
                try:
                    # 获取子任务关联的主任务信息
                    task = subtask.task
                    if not task:
                        logger.warning(f"子任务 {subtask.id} 没有关联的主任务，跳过转移")
                        continue
                    
                    # 获取子任务使用的模型和流信息
                    model = subtask.model
                    stream = subtask.stream
                    
                    if not model or not stream:
                        logger.warning(f"子任务 {subtask.id} 缺少模型或流信息，跳过转移")
                        continue
                    
                    # 使用轮询方式选择节点
                    target_node = available_nodes[transferred_count % len(available_nodes)]
                    
                    logger.info(f"准备将子任务 {subtask.id} 从节点 {mac_address} 转移到节点 {target_node.mac_address}")
                    
                    # 构建任务配置
                    task_config = {
                        "source": {
                            "type": "stream",
                            "urls": [stream.url]
                        },
                        "config": {
                            "model_code": model.code,
                            "analysis_type": subtask.analysis_type,
                            "analysis_interval": task.analysis_interval,  # 新增分析间隔
                            **(subtask.config or {})
                        },
                        "result_config": {
                            "save_result": task.save_result,
                            "save_images": task.save_images,  # 新增保存图像字段
                            "callback_topic": f"meek/{target_node.mac_address}/result"  # 目标节点已存在
                        }
                    }
                    
                    # 发送任务消息到新节点
                    success = await self.send_task_to_node(
                        mac_address=target_node.mac_address,
                        task_id=str(task.id),
                        subtask_id=str(subtask.id),
                        config=task_config,
                        wait_for_response=False
                    )
                    
                    if isinstance(success, tuple):
                        success = success[0]  # 如果返回元组，取第一个元素作为成功标志
                    
                    if success:
                        # 更新子任务信息
                        subtask.mqtt_node_id = target_node.id
                        subtask.status = 1  # 保持运行中状态
                        subtask.error_message = f"已从节点 {mac_address} 自动转移到节点 {target_node.mac_address}"
                        
                        # 更新目标节点任务计数
                        target_node.task_count += 1
                        target_node.stream_task_count += 1
                        
                        transferred_count += 1
                        logger.info(f"成功将子任务 {subtask.id} 转移到节点 {target_node.mac_address}")
                    else:
                        # 转移失败，重置子任务状态
                        subtask.status = 0  # 未启动
                        subtask.mqtt_node_id = None
                        subtask.started_at = None
                        subtask.error_message = f"从节点 {mac_address} 转移失败，等待重新分配"
                        
                        # 更新主任务active_subtasks计数
                        if task.active_subtasks > 0:
                            task.active_subtasks -= 1
                        
                        failed_count += 1
                
                except Exception as e:
                    logger.error(f"转移子任务 {subtask.id} 时出错: {e}")
                    logger.error(traceback.format_exc())
                    
                    # 转移出错，重置子任务状态
                    subtask.status = 0  # 未启动
                    subtask.mqtt_node_id = None
                    subtask.started_at = None
                    subtask.error_message = f"从节点 {mac_address} 转移出错: {str(e)}"
                    
                    # 更新主任务active_subtasks计数
                    task = subtask.task
                    if task and task.active_subtasks > 0:
                        task.active_subtasks -= 1
                    
                    failed_count += 1
            
            # 更新离线节点的任务计数
            node.task_count = max(0, node.task_count - (transferred_count + failed_count))
            node.stream_task_count = max(0, node.stream_task_count - (transferred_count + failed_count))
            
            db.commit()
            logger.info(f"节点 {mac_address} 的任务转移完成: 成功={transferred_count}, 失败={failed_count}")
            
        except Exception as e:
            logger.error(f"处理节点离线任务转移失败: {e}")
            logger.error(traceback.format_exc())    
    def _handle_task_failure(self, payload: Dict[str, Any]):
        """
        处理任务执行失败的情况
        """
        try:
            data = payload.get('data', {})
            task_id = data.get('task_id')
            subtask_id = data.get('subtask_id')
            
            if not task_id or not subtask_id:
                logger.error(f"任务失败消息缺少必要字段: {payload}")
                return
                
            logger.info(f"处理任务执行失败: task_id={task_id}, subtask_id={subtask_id}")
            
            # 更新子任务状态，等待重新分配
            db = SessionLocal()
            try:
                # 查找子任务 - 通过subtask_id作为ID直接查找
                logger.info(f"查找失败的子任务: subtask_id={subtask_id}")
                subtask = None
                
                # 检查subtask_id是否为纯数字
                if subtask_id.isdigit():
                    subtask = db.query(SubTask).filter(SubTask.id == int(subtask_id)).first()
                    if subtask:
                        logger.info(f"找到失败的子任务: {subtask.id}")
                    else:
                        logger.warning(f"未找到失败的子任务: subtask_id={subtask_id}")
                else:
                    logger.warning(f"子任务ID不是纯数字: {subtask_id}，无法查询数据库")
                
                if subtask:
                    subtask.status = 0  # 未启动
                    subtask.mqtt_node_id = None  # 清除节点关联
                    subtask.error_message = data.get('message', '任务执行失败，等待重新分配')
                    db.commit()
                    logger.info(f"子任务 {subtask_id} 已重置为未启动状态，等待重新分配")
                else:
                    logger.warning(f"未找到失败的子任务: subtask_id={subtask_id}")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"处理任务失败情况出错: {e}")
            logger.error(traceback.format_exc())
    
    async def get_available_mqtt_node(self) -> Optional[MQTTNode]:
        """
        获取可用的MQTT节点 - 综合考虑多项指标进行负载均衡
        """
        db = SessionLocal()
        try:
            # 查询所有在线节点
            nodes = db.query(MQTTNode).filter(
                MQTTNode.status == "online",
                MQTTNode.task_count < MQTTNode.max_tasks,
                MQTTNode.is_active == True
            ).all()
            
            if not nodes:
                logger.warning("没有在线或可用的MQTT节点")
                return None
            
            # 使用加权得分系统选择最佳节点
            best_node = None
            best_score = float('inf')  # 分数越低越好
            
            for node in nodes:
                # 计算相对任务负载（当前任务数/最大任务数）
                task_load_ratio = node.task_count / node.max_tasks if node.max_tasks > 0 else 1.0
                
                # 考虑CPU和内存使用率
                cpu_weight = 0.3
                memory_weight = 0.2
                task_weight = 0.5
                
                # 如果节点支持GPU，也考虑GPU使用率
                gpu_score = 0
                if node.gpu_usage is not None:
                    cpu_weight = 0.2
                    memory_weight = 0.15
                    task_weight = 0.4
                    gpu_weight = 0.25
                    gpu_score = node.gpu_usage * gpu_weight
                
                # 计算节点总得分 (值越低越好)
                score = (
                    (node.cpu_usage or 0) * cpu_weight + 
                    (node.memory_usage or 0) * memory_weight + 
                    task_load_ratio * task_weight +
                    gpu_score
                )
                
                # 如果这是最佳节点
                if score < best_score:
                    best_score = score
                    best_node = node
            
            if best_node:
                logger.info(f"选择节点: ID={best_node.id}, MAC={best_node.mac_address}, "
                           f"任务数={best_node.task_count}/{best_node.max_tasks}, "
                           f"CPU={best_node.cpu_usage}%, MEM={best_node.memory_usage}%, "
                           f"得分={best_score:.2f}")
                return best_node
            else:
                # 如果加权算法未能找到节点，回退到简单的按任务数排序
                nodes.sort(key=lambda n: n.task_count)
                selected_node = nodes[0]
                logger.info(f"使用备选算法选择节点: ID={selected_node.id}, MAC={selected_node.mac_address}, 任务数={selected_node.task_count}/{selected_node.max_tasks}")
                return selected_node
        except Exception as e:
            logger.error(f"获取可用MQTT节点失败: {e}")
            logger.error(traceback.format_exc())
            return None
        finally:
            db.close()
    
    async def send_task_to_node(self, mac_address: str, task_id: str, subtask_id: str, 
                               config: Dict[str, Any], wait_for_response: bool = True) -> Tuple[bool, Dict[str, Any]]:
        """
        向指定节点发送任务
        
        Args:
            mac_address: 节点MAC地址
            task_id: 任务ID
            subtask_id: 子任务ID
            config: 任务配置
            wait_for_response: 是否等待节点响应，默认为True
            
        Returns:
            Tuple[bool, Dict[str, Any]]: (是否成功, 响应数据)
        """
        if not self.connected:
            logger.error("MQTT客户端未连接")
            return False, {"error": "MQTT客户端未连接"}
        
        # 生成消息ID和UUID
        message_id = int(time.time())
        message_uuid = str(uuid.uuid4()).replace("-", "")[:16]
        
        # 构建任务消息
        payload = {
            "confirmation_topic": f"{self.config['topic_prefix']}device_config_reply",
            "message_id": message_id,
            "message_uuid": message_uuid,
            "request_type": "task_cmd",
            "data": {
                "cmd_type": "start_task",
                "task_id": task_id,
                "subtask_id": subtask_id,
                "source": config.get("source", {}),
                "config": config.get("config", {}),
                "result_config": {
                    "save_result": config.get("result_config", {}).get("save_result", False),
                    "save_images": config.get("result_config", {}).get("save_images", False),
                    "callback_topic": f"{self.config['topic_prefix']}{mac_address}/result"
                }
            }
        }
        
        # 检查节点是否存在/活跃
        db = SessionLocal()
        try:
            # 检查节点是否存在于数据库中
            mqtt_node = db.query(MQTTNode).filter(MQTTNode.mac_address == mac_address).first()
            if not mqtt_node:
                logger.warning(f"尝试向不存在的节点 {mac_address} 发送任务，检查该节点是否已在系统中注册")
            elif mqtt_node.status != 'online':
                logger.warning(f"尝试向离线节点 {mac_address} 发送任务，当前状态: {mqtt_node.status}")
            elif not mqtt_node.is_active:
                logger.warning(f"尝试向非活跃节点 {mac_address} 发送任务")
            else:
                logger.info(f"节点 {mac_address} 处于在线状态，可接收任务")
        except Exception as e:
            logger.error(f"检查节点状态时出错: {e}")
        finally:
            db.close()
        
        # 发布消息
        topic = f"{self.config['topic_prefix']}{mac_address}/request_setting"
        logger.info(f"向节点 {mac_address} 发送任务: {task_id}/{subtask_id}，主题: {topic}")
        
        # 清除可能存在的旧响应
        if message_uuid in self.command_responses:
            del self.command_responses[message_uuid]
        
        # 发布前记录一下所有当前的响应，便于诊断
        logger.debug(f"当前响应缓存中有 {len(self.command_responses)} 个条目")
        
        # 预先创建响应对象，用于存储可能来自其他主题的响应
        self.command_responses[message_uuid] = {
            'status': 'pending',
            'data': {
                'cmd_type': 'start_task',
                'task_id': task_id,
                'subtask_id': subtask_id,
                'mac_address': mac_address
            },
            'timestamp': int(time.time())
        }
        
        # 添加重试逻辑
        max_retries = 3
        for retry in range(max_retries):
            result = self.client.publish(
                topic,
                json.dumps(payload),
                qos=self.config.get('qos', 2)
            )
            
            if result.rc != 0:
                logger.error(f"发布任务消息失败: {result.rc}，尝试重试 {retry+1}/{max_retries}")
                if retry == max_retries - 1:
                    return False, {"error": f"发布消息失败: {result.rc}，已尝试 {max_retries} 次"}
                await asyncio.sleep(1)  # 等待1秒后重试
                continue
            
            logger.info(f"消息已发布到主题 {topic}，消息ID: {message_id}, UUID: {message_uuid}")
            
            # 如果不等待响应，直接返回成功
            if not wait_for_response:
                logger.info(f"已发送任务消息到节点 {mac_address}，不等待响应")
                # 即使不等待响应，也先尝试检查结果主题中是否已有相关消息
                result_key = f"{task_id}_{subtask_id}"
                if result_key in self.task_results:
                    logger.info(f"发现任务结果缓存中已有相关消息: {result_key}")
                    return True, {"success": True, "message": "任务已开始执行，发现结果缓存"}
                return True, {"success": True, "message": "消息已发送，不等待响应"}
            
            # 等待响应，增加等待时间
            wait_time = 10  # 增加到10秒
            wait_steps = wait_time * 10  # 每步0.1秒，共wait_time秒
            
            for step in range(wait_steps):
                # 首先检查命令响应
                if message_uuid in self.command_responses:
                    response = self.command_responses[message_uuid]
                    status = response.get("status", "pending")
                    
                    if status == "success":
                        logger.info(f"节点 {mac_address} 成功接受任务: {task_id}/{subtask_id}")
                        return True, response
                    elif status != "pending":  # 如果状态已更新且不是成功
                        error_msg = response.get('data', {}).get('message', '未知错误')
                        logger.warning(f"节点 {mac_address} 拒绝任务: {task_id}/{subtask_id}, 原因: {error_msg}")
                        return False, response
                
                # 其次，检查结果消息
                result_key = f"{task_id}_{subtask_id}"
                if result_key in self.task_results:
                    logger.info(f"通过结果消息确认任务已启动: {task_id}/{subtask_id}")
                    # 更新命令响应状态
                    self.command_responses[message_uuid]['status'] = 'success'
                    return True, {"success": True, "message": "任务已开始执行，发现结果消息"}
                
                # 每秒打印一次等待状态
                if step % 10 == 0:
                    logger.debug(f"等待节点 {mac_address} 响应中... {step//10}/{wait_time}秒")
                
                await asyncio.sleep(0.1)
            
            # 如果最后一次重试也超时
            if retry == max_retries - 1:
                logger.warning(f"等待节点 {mac_address} 响应超时，已等待 {wait_time} 秒")
                # 再次检查节点状态
                try:
                    db = SessionLocal()
                    mqtt_node = db.query(MQTTNode).filter(MQTTNode.mac_address == mac_address).first()
                    if mqtt_node:
                        logger.info(f"节点 {mac_address} 当前状态: {mqtt_node.status}, 最后活跃时间: {mqtt_node.last_active}")
                    db.close()
                except Exception as e:
                    logger.error(f"检查节点状态时出错: {e}")
                
                # 最后一次尝试，检查是否有结果消息
                result_key = f"{task_id}_{subtask_id}"
                if result_key in self.task_results:
                    logger.info(f"超时后通过结果消息确认任务已启动: {task_id}/{subtask_id}")
                    # 更新命令响应状态
                    self.command_responses[message_uuid]['status'] = 'success'
                    return True, {"success": True, "message": "任务已开始执行，发现结果消息"}
                
                return False, {"error": "节点响应超时"}
            
            logger.warning(f"等待节点 {mac_address} 响应超时，重试 {retry+1}/{max_retries}")
        
        logger.error(f"向节点 {mac_address} 发送任务失败，已尝试 {max_retries} 次")
        return False, {"error": "节点响应超时，已达到最大重试次数"}
    
    def register_handler(self, topic_pattern: str, handler: Callable):
        """
        注册主题处理函数
        
        Args:
            topic_pattern: 主题模式
            handler: 处理函数
        """
        if topic_pattern not in self.topic_handlers:
            self.topic_handlers[topic_pattern] = []
        self.topic_handlers[topic_pattern].append(handler)
    
    def unregister_handler(self, topic_pattern: str, handler: Callable) -> bool:
        """
        取消注册主题处理函数
        
        Args:
            topic_pattern: 主题模式
            handler: 处理函数
            
        Returns:
            bool: 是否成功
        """
        if topic_pattern in self.topic_handlers:
            if handler in self.topic_handlers[topic_pattern]:
                self.topic_handlers[topic_pattern].remove(handler)
                return True
        return False
    
    def _publish_connection_status(self, status: str):
        """
        发布API服务连接状态
        
        Args:
            status: 状态，'online'或'offline'
        """
        # API服务不应发布连接状态
        if self.is_api_service:
            logger.debug(f"跳过API服务连接状态发布: {status}")
            return
        
        try:
            if not self.client.is_connected():
                logger.warning(f"无法发布连接状态，MQTT客户端未连接")
                return
                
            # 准备连接状态消息
            hostname = socket.gethostname()
            ip_address = None
            try:
                ip_address = socket.gethostbyname(hostname)
            except:
                ip_address = "unknown"
                
            # 获取系统信息
            system_info = {
                "os": platform.system(),
                "version": platform.version(),
                "hostname": hostname,
                "cpu_count": psutil.cpu_count(),
                "memory_total": psutil.virtual_memory().total
            }
                
            payload = {
                "client_id": self.client_id,
                "service_type": "api_service",
                "status": status,
                "timestamp": int(time.time()),
                "metadata": {
                    "ip": ip_address,
                    "hostname": hostname,
                    "system_info": system_info
                }
            }
            
            # 发布状态
            logger.info(f"发布API服务连接状态: {status}")
            result = self.client.publish(
                f"{self.config['topic_prefix']}connection",
                json.dumps(payload),
                qos=self.config.get('qos', 1),
                retain=False
            )
            
            if result.rc != 0:
                logger.error(f"发布连接状态失败: {result.rc}")
            else:
                logger.info(f"成功发布API服务连接状态: {status}")
                
        except Exception as e:
            logger.error(f"发布连接状态时出错: {e}")
            logger.error(traceback.format_exc())
    
    def _handle_heartbeat(self, topic: str, payload: Dict[str, Any]):
        """
        处理心跳消息
        """
        try:
            # 不记录详细的心跳数据，避免日志过大
            logger.debug(f"接收到心跳消息 - 主题: {topic}")
            
            if not isinstance(payload, dict):
                logger.error(f"心跳消息格式错误: {payload}")
                return
                
            # 提取节点信息
            mac_address = payload.get('mac_address')
            if not mac_address:
                # 尝试从client_id中提取
                client_id = payload.get('client_id')
                if client_id and '_' in client_id:
                    mac_address = client_id.split('_')[-1]
                else:
                    logger.error("心跳消息缺少MAC地址")
                    return
            
            timestamp = payload.get('timestamp', int(time.time()))
            cpu_usage = payload.get('cpu_usage', 0)
            memory_usage = payload.get('memory_usage', 0)
            gpu_usage = payload.get('gpu_usage', 0)
            task_count = payload.get('task_count', 0)
            
            # 更新数据库中的节点状态
            db = SessionLocal()
            try:
                node = db.query(MQTTNode).filter(MQTTNode.mac_address == mac_address).first()
                
                if node:
                    # 更新节点状态信息
                    node.last_active = datetime.now()
                    node.cpu_usage = cpu_usage
                    node.memory_usage = memory_usage
                    node.gpu_usage = gpu_usage
                    node.task_count = task_count  # 使用客户端报告的任务数
                    
                    # 确保节点状态为在线
                    if node.status != 'online':
                        logger.info(f"节点 {mac_address} 状态从 {node.status} 更新为 online")
                        node.status = 'online'
                    
                    # 确保节点处于激活状态
                    if not node.is_active:
                        logger.info(f"节点 {mac_address} 从非激活状态激活")
                        node.is_active = True
                    
                    db.commit()
                    logger.debug(f"节点 {mac_address} 心跳已更新")
                else:
                    logger.warning(f"收到未知节点 {mac_address} 的心跳，尝试创建节点记录")
                    # 尝试使用最小信息创建节点记录
                    client_id = payload.get('client_id', f"unknown_{mac_address}")
                    service_type = payload.get('service_type', 'analysis')
                    
                    node = MQTTNode(
                        node_id=client_id,
                        mac_address=mac_address,
                        client_id=client_id,
                        service_type=service_type,
                        status='online',
                        last_active=datetime.now(),
                        cpu_usage=cpu_usage,
                        memory_usage=memory_usage,
                        gpu_usage=gpu_usage,
                        task_count=task_count,
                        max_tasks=10,  # 默认最大任务数
                        is_active=True  # 默认激活
                    )
                    
                    db.add(node)
                    db.commit()
                    logger.info(f"为心跳消息创建了新的节点记录: MAC={mac_address}")
            except Exception as e:
                logger.error(f"更新节点心跳失败: {e}")
                db.rollback()
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"处理心跳消息失败: {e}")
            logger.error(traceback.format_exc())
    
    def _subscribe_default_topics(self):
        """订阅默认主题"""
        pass
    
    def _resubscribe_topics(self):
        """重新订阅之前的主题"""
        for topic in self.subscribed_topics:
            self.client.subscribe(topic)
            logger.info(f"重新订阅主题: {topic}")
    
    def subscribe(self, topic: str, qos: int = 0) -> bool:
        """
        订阅主题
        
        Args:
            topic: 主题
            qos: 服务质量
            
        Returns:
            bool: 是否成功
        """
        result = self.client.subscribe(topic, qos)
        if result[0] == 0:
            self.subscribed_topics.add(topic)
            logger.info(f"订阅主题成功: {topic}")
            return True
        else:
            logger.error(f"订阅主题失败: {topic}, 错误码: {result[0]}")
            return False
    
    def _start_reconnect_thread(self):
        """启动重连线程"""
        if self.reconnect_thread and self.reconnect_thread.is_alive():
            # 已有重连线程在运行
            return
            
        # 创建并启动重连线程
        self.reconnect_thread = threading.Thread(
            target=self._reconnect_worker,
            name="MQTTReconnectThread",
            daemon=True
        )
        self.reconnect_thread.start()
    
    def _reconnect_worker(self):
        """重连工作线程"""
        logger.info("MQTT重连线程已启动")
        
        max_attempts = self.config["max_reconnect_attempts"]
        interval = self.config["reconnect_interval"]
        
        while not self.connected and not self.manually_disconnected:
            # 增加重连计数
            self.reconnect_attempt += 1
            
            if max_attempts > 0 and self.reconnect_attempt > max_attempts:
                logger.error(f"MQTT重连失败，已达到最大重试次数 ({max_attempts})")
                break
                
            # 计算重连间隔（指数退避）
            if self.reconnect_attempt > 1:
                # 指数退避，但最大不超过60秒
                backoff = min(interval * (2 ** (self.reconnect_attempt - 1)), 60)
            else:
                backoff = interval
                
            logger.info(f"第 {self.reconnect_attempt} 次尝试重连MQTT, {backoff:.1f}秒后重试...")
            time.sleep(backoff)
            
            # 尝试连接
            with self.connect_lock:
                if self.manually_disconnected:
                    break
                    
                try:
                    self.client.reconnect()
                except Exception as e:
                    logger.error(f"MQTT重连失败: {str(e)}")
                    continue
                    
            # 等待连接完成或超时
            timeout = 10.0
            start_time = time.time()
            
            while not self.connected and time.time() - start_time < timeout:
                if self.manually_disconnected:
                    break
                time.sleep(0.1)
                
            # 检查连接结果
            if self.connected:
                logger.info(f"MQTT重连成功 (第 {self.reconnect_attempt} 次尝试)")
                break
                
        logger.info("MQTT重连线程已结束")

# 全局MQTT客户端实例
_mqtt_client = None

def get_mqtt_client(config: Dict[str, Any] = None, external_client: MQTTClient = None) -> MQTTClient:
    """
    获取MQTT客户端全局实例
    
    Args:
        config: MQTT配置信息，仅在首次调用时有效
        external_client: 外部提供的MQTT客户端实例，如果提供则使用该实例
        
    Returns:
        MQTTClient: MQTT客户端实例
    """
    global _mqtt_client
    
    if external_client:
        # 如果外部提供了客户端实例，使用它并替换全局实例
        _mqtt_client = external_client
        logger.info("使用外部提供的MQTT客户端实例")
    elif _mqtt_client is None:
        # 如果没有全局实例，创建一个新的
        _mqtt_client = MQTTClient(config)
        logger.info("创建新的MQTT客户端全局实例")
        
    return _mqtt_client
