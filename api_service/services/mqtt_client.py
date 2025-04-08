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

logger = logging.getLogger(__name__)

class MQTTClient:
    """
    MQTT客户端服务类，用于API服务与分析服务之间的MQTT通信
    基于新的指令式通信协议实现
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
        
        # 节点状态缓存 - 使用MAC地址作为键
        self.nodes: Dict[str, Any] = {}
        
        # 命令响应等待
        self.command_responses: Dict[str, Any] = {}
        
        # 主题前缀
        self.topic_prefix = self.config.get('topic_prefix', 'meek/')
        
    def connect(self) -> bool:
        """
        连接到MQTT Broker
        
        Returns:
            bool: 是否连接成功
        """
        if self.connected:
            logger.info("MQTT客户端已连接，无需重新连接")
            return True
            
        try:
            # 设置连接回调
            self.client.on_connect = self._on_connect
            self.client.on_message = self._on_message
            self.client.on_disconnect = self._on_disconnect
            
            # 设置认证
            if self.config.get("username") and self.config.get("password"):
                logger.info(f"使用认证信息连接MQTT: 用户名={self.config.get('username')}")
                self.client.username_pw_set(
                    self.config.get("username"),
                    self.config.get("password")
                )
            
            # 设置遗嘱消息
            if self.topic_prefix and self.client_id:
                logger.info(f"设置遗嘱消息，主题: {self.topic_prefix}connection")
                will_payload = json.dumps({
                    "status": "offline",
                    "client_id": self.client_id,
                    "timestamp": int(time.time())
                })
                self.client.will_set(
                    f"{self.topic_prefix}connection",
                    will_payload,
                    qos=self.config.get("qos", 1),
                    retain=False
                )
            
            # 尝试连接多次
            max_retries = 3
            retry_delay = 1  # 秒
            
            for attempt in range(1, max_retries + 1):
                try:
                    logger.info(f"尝试连接MQTT Broker [{attempt}/{max_retries}]: {self.config.get('broker_host')}:{self.config.get('broker_port')}")
                    
                    # 设置较短的连接超时
                    self.client.connect(
                        self.config.get("broker_host"),
                        self.config.get("broker_port", 1883),
                        keepalive=self.config.get("keepalive", 60)
                    )
                    
                    # 即使没有收到on_connect回调，也需要启动网络循环，否则回调不会被触发
                    self.client.loop_start()
                    
                    # 等待2秒，看是否接收到on_connect回调或检测到连接状态
                    start_time = time.time()
                    while time.time() - start_time < 2:
                        # 使用两种方法检查连接状态
                        if self.connected or self.client.is_connected():
                            if not self.connected and self.client.is_connected():
                                logger.info("通过is_connected()检测到连接成功，但未收到回调")
                                self.connected = True
                            logger.info("MQTT连接成功")
                            break
                        time.sleep(0.1)
                    
                    if self.connected or self.client.is_connected():
                        # 确保connected标志与实际状态一致
                        self.connected = True
                        break
                    else:
                        logger.warning(f"连接尝试 {attempt} 未收到连接确认，可能连接失败")
                        # 停止网络循环，准备下一次尝试
                        self.client.loop_stop()
                        
                    if attempt < max_retries:
                        logger.info(f"等待 {retry_delay} 秒后重试...")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # 指数退避
                        
                except Exception as e:
                    logger.error(f"连接MQTT Broker失败 [{attempt}/{max_retries}]: {e}")
                    if attempt < max_retries:
                        logger.info(f"等待 {retry_delay} 秒后重试...")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # 指数退避
                    else:
                        raise
            
            # 启动网络循环线程（如果已经启动则忽略）
            if not self.client.is_connected() and self.connected:
                logger.info("启动MQTT网络循环")
                self.client.loop_start()
            elif not self.connected and self.client.is_connected():
                # 状态不一致，更新标志
                logger.info("客户端已连接但标志未更新，修正状态")
                self.connected = True
            
            # 发布连接状态
            if self.connected or self.client.is_connected():
                self.connected = True  # 确保状态一致
                logger.info("发布上线状态")
                self._publish_connection_status("online")
                return True
            else:
                logger.error("MQTT客户端无法连接，未收到连接确认")
                return False
                
        except Exception as e:
            logger.error(f"连接MQTT Broker失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
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
            
            # 获取QoS
            qos = self.config.get('qos', 1)
            
            # 订阅新的主题
            # 连接状态主题
            self.client.subscribe(f"{self.topic_prefix}connection", qos=qos)
            
            # 节点配置和指令回复主题
            self.client.subscribe(f"{self.topic_prefix}node_config_reply", qos=qos)
            
            # 节点状态和结果主题 - 使用通配符
            self.client.subscribe(f"{self.topic_prefix}+/status", qos=qos)
            self.client.subscribe(f"{self.topic_prefix}+/result", qos=qos)
            
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
            
            # 处理节点连接消息
            if topic == f"{self.topic_prefix}connection":
                self._handle_connection(topic, payload)
            
            # 处理节点配置回复
            elif topic == f"{self.topic_prefix}node_config_reply":
                self._handle_config_reply(payload)
            
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
        处理连接状态消息
        """
        try:
            logger.info(f"接收到连接状态消息: {json.dumps(payload, ensure_ascii=False)}")
            
            if not isinstance(payload, dict):
                logger.error(f"连接状态消息格式错误: {payload}")
                return
                
            # 获取客户端ID和MAC地址
            client_id = payload.get('client_id')
            # 优先使用node_type，如果不存在则尝试service_type，默认为'analysis'
            service_type = payload.get('node_type') or payload.get('service_type') or 'analysis'
            status = payload.get('status')
            timestamp = payload.get('timestamp')
            metadata = payload.get('metadata', {})
            
            # 提取MAC地址，优先使用顶层的mac_address
            if 'mac_address' in payload:
                mac_address = payload.get('mac_address')
            elif 'mac_address' in metadata:
                mac_address = metadata.get('mac_address')
            else:
                # 尝试从client_id中提取MAC地址
                mac_address = client_id.split('_')[-1] if client_id and '_' in client_id else client_id
            
            logger.info(f"提取到节点信息: mac_address={mac_address}, client_id={client_id}, service_type={service_type}")
            
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
            hostname = metadata.get('hostname')
            system_info = metadata.get('system_info', {})
            
            # 更新数据库中的节点记录
            db = SessionLocal()
            try:
                # 查找节点
                node = db.query(MQTTNode).filter(MQTTNode.mac_address == mac_address).first()
                
                if node:
                    logger.info(f"更新已存在的节点记录: MAC={mac_address}")
                    # 更新节点状态
                    node.status = 'online'
                    node.client_id = client_id
                    node.service_type = service_type
                    node.ip = ip_address
                    node.hostname = hostname
                    node.last_active = datetime.now()
                    # 确保节点处于激活状态
                    node.is_active = True
                    
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
                    # 创建新节点记录
                    node = MQTTNode(
                        node_id=client_id,
                        mac_address=mac_address,
                        client_id=client_id,
                        service_type=service_type,
                        status='online',
                        ip=ip_address,
                        hostname=hostname,
                        last_active=datetime.now(),
                        node_metadata=metadata,
                        task_count=0,
                        max_tasks=20,  # 增加默认最大任务数
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
            logger.info(f"处理节点断开连接: MAC={mac_address}")
            
            # 更新数据库中的节点状态
            db = SessionLocal()
            try:
                # 查找节点
                node = db.query(MQTTNode).filter(MQTTNode.mac_address == mac_address).first()
                
                if node:
                    # 更新节点状态
                    node.status = 'offline'
                    db.commit()
                    logger.info(f"节点 {mac_address} 已标记为离线")
                    
                    # 处理该节点上运行的任务
                    self._handle_node_offline(db, mac_address)
                else:
                    logger.warning(f"未找到节点记录: MAC={mac_address}")
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"处理节点断开连接失败: {e}")
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
                            # 查找子任务 - 首先通过完整的subtask_id查找
                            logger.info(f"尝试使用完整ID查找子任务: subtask_id={subtask_id}")
                            subtask = db.query(SubTask).filter(
                                SubTask.analysis_task_id == subtask_id
                            ).first()
                            
                            # 如果找不到，尝试使用task_id查找
                            if not subtask and "-" in subtask_id:
                                # 解析出原始task_id部分（去除后缀）
                                base_task_id = subtask_id.split("-")[0]
                                logger.info(f"未找到完整ID匹配，尝试使用基础task_id查找: base_task_id={base_task_id}")
                                
                                # 尝试查找analysis_task_id包含base_task_id的子任务
                                subtask = db.query(SubTask).filter(
                                    SubTask.analysis_task_id.like(f"{base_task_id}%")
                                ).first()
                                
                                if subtask:
                                    # 找到后更新其analysis_task_id为完整的subtask_id
                                    logger.info(f"找到基础ID匹配的子任务，更新analysis_task_id: {subtask.analysis_task_id} -> {subtask_id}")
                                    subtask.analysis_task_id = subtask_id
                            
                            if subtask:
                                if status == 'success':
                                    # 任务被节点成功接收，更新状态为运行中
                                    logger.info(f"MQTT节点接收任务成功: task_id={task_id}, subtask_id={subtask_id}")
                                    subtask.status = 1  # 运行中状态
                                    subtask.started_at = datetime.now()
                                    subtask.error_message = None
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
        处理节点状态更新消息
        """
        try:
            logger.info(f"接收到节点状态更新消息 - 主题: {topic}")
            
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
            load = payload.get('load', {})
            
            # 更新内存中的节点信息
            if mac_address in self.nodes:
                self.nodes[mac_address].update({
                    'status': status,
                    'load': load,
                    'updated_at': timestamp
                })
            
            # 更新数据库中的节点信息
            db = SessionLocal()
            try:
                node = db.query(MQTTNode).filter(MQTTNode.mac_address == mac_address).first()
                if node:
                    node.status = status
                    node.cpu_usage = load.get('cpu')
                    node.memory_usage = load.get('memory')
                    node.gpu_usage = load.get('gpu')
                    node.task_count = load.get('running_tasks', 0)
                    node.last_active = datetime.now()
                    db.commit()
                    logger.info(f"节点 {mac_address} 状态已更新: {status}")
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
            logger.info(f"接收到任务结果消息 - 主题: {topic}")
            
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
            
            # 更新数据库中的子任务状态
            db = SessionLocal()
            try:
                # 查找子任务 - 首先通过完整的subtask_id查找
                logger.info(f"尝试使用完整ID查找子任务: subtask_id={subtask_id}")
                subtask = db.query(SubTask).filter(
                    SubTask.analysis_task_id == subtask_id
                ).first()
                
                # 如果找不到，尝试使用task_id查找
                if not subtask and "-" in subtask_id:
                    # 解析出原始task_id部分（去除后缀）
                    base_task_id = subtask_id.split("-")[0]
                    logger.info(f"未找到完整ID匹配，尝试使用基础task_id查找: base_task_id={base_task_id}")
                    
                    # 尝试查找analysis_task_id包含base_task_id的子任务
                    subtask = db.query(SubTask).filter(
                        SubTask.analysis_task_id.like(f"{base_task_id}%")
                    ).first()
                    
                    if subtask:
                        # 找到后更新其analysis_task_id为完整的subtask_id
                        logger.info(f"找到基础ID匹配的子任务，更新analysis_task_id: {subtask.analysis_task_id} -> {subtask_id}")
                        subtask.analysis_task_id = subtask_id
                
                if subtask:
                    # 根据状态更新子任务
                    if status == 'completed':
                        subtask.status = 2  # 已完成
                        subtask.completed_at = datetime.now()
                    elif status == 'failed':
                        subtask.status = 3  # 失败
                        subtask.error_message = payload.get('message', '任务执行失败')
                    elif status == 'running':
                        # 如果状态是运行中，但子任务状态是未启动(0)，则更新为运行中(1)
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
    
    def _handle_node_offline(self, db: Session, mac_address: str):
        """
        处理节点离线情况，重新分配该节点的任务
        """
        try:
            logger.info(f"处理节点 {mac_address} 离线情况...")
            
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
                logger.info(f"节点 {mac_address} 没有运行中的子任务")
                return
                
            logger.info(f"节点 {mac_address} 有 {len(running_subtasks)} 个运行中的子任务需要重新分配")
            
            # 将子任务状态重置为未启动状态，等待健康检查器重新分配
            for subtask in running_subtasks:
                subtask.status = 0  # 未启动
                subtask.mqtt_node_id = None  # 清除节点关联
                subtask.started_at = None
                subtask.error_message = f"节点离线，等待重新分配"
                
                # 同时更新关联的主任务active_subtasks计数
                task = subtask.task
                if task and task.active_subtasks > 0:
                    task.active_subtasks -= 1
            
            db.commit()
            logger.info(f"节点 {mac_address} 的任务已重置为未启动状态")
            
        except Exception as e:
            logger.error(f"处理节点离线失败: {e}")
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
                # 直接使用subtask_id查找，不尝试整数转换
                subtask = db.query(SubTask).filter(
                    SubTask.analysis_task_id == subtask_id
                ).first()
                
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
        获取可用的MQTT节点 - 简单地按负载选择在线节点
        """
        db = SessionLocal()
        try:
            # 查询所有在线节点
            nodes = db.query(MQTTNode).filter(
                MQTTNode.status == "online",
                MQTTNode.task_count < MQTTNode.max_tasks
            ).all()
            
            if not nodes:
                logger.warning("没有在线或可用的MQTT节点")
                return None
            
            # 简单地按任务数排序
            nodes.sort(key=lambda n: n.task_count)
            
            # 返回任务数最少的节点
            selected_node = nodes[0]
            logger.info(f"选择节点: ID={selected_node.id}, MAC={selected_node.mac_address}, 任务数={selected_node.task_count}")
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
            "confirmation_topic": f"{self.topic_prefix}node_config_reply",
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
                    "save_result": config.get("save_result", False),
                    "callback_topic": f"{self.topic_prefix}{mac_address}/result"
                }
            }
        }
        
        # 发布消息
        topic = f"{self.topic_prefix}{mac_address}/request_setting"
        logger.info(f"向节点 {mac_address} 发送任务: {task_id}/{subtask_id}")
        
        result = self.client.publish(
            topic,
            json.dumps(payload),
            qos=self.config.get('qos', 2)
        )
        
        if result.rc != 0:
            logger.error(f"发布任务消息失败: {result.rc}")
            return False, {"error": f"发布消息失败: {result.rc}"}
            
        # 如果不等待响应，直接返回成功
        if not wait_for_response:
            logger.info(f"已发送任务消息到节点 {mac_address}，不等待响应")
            return True, {"success": True, "message": "消息已发送，不等待响应"}
            
        # 等待响应
        for _ in range(30):  # 最多等待3秒
            if message_uuid in self.command_responses:
                response = self.command_responses[message_uuid]
                status = response.get("status", "error")
                
                if status == "success":
                    logger.info(f"节点 {mac_address} 成功接受任务: {task_id}/{subtask_id}")
                    return True, response
                else:
                    logger.warning(f"节点 {mac_address} 拒绝任务: {task_id}/{subtask_id}, 原因: {response.get('data', {}).get('message')}")
                    return False, response
                    
            await asyncio.sleep(0.1)
            
        logger.warning(f"等待节点 {mac_address} 响应超时")
        return False, {"error": "节点响应超时"}
    
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
                f"{self.topic_prefix}connection",
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