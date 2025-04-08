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
                self._handle_connection_message(payload)
            
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
    
    def _handle_connection_message(self, payload: Dict[str, Any]):
        """
        处理节点连接状态消息
        """
        try:
            logger.info(f"接收到节点连接状态消息: {json.dumps(payload, ensure_ascii=False)}")
            
            if not isinstance(payload, dict) or 'mac_address' not in payload:
                logger.error(f"连接消息格式错误，缺少必要字段: {payload}")
                return
            
            mac_address = payload.get('mac_address')
            status = payload.get('status', 'offline')
            node_type = payload.get('node_type', 'unknown')
            timestamp = payload.get('timestamp', int(time.time()))
            metadata = payload.get('metadata', {})
            
            if not mac_address:
                logger.error("连接消息缺少MAC地址")
                return
                
            # 从metadata提取信息
            ip = metadata.get('ip')
            port = metadata.get('port')
            hostname = metadata.get('hostname')
            version = metadata.get('version')
            capabilities = metadata.get('capabilities', {})
            
            # 构建节点数据
            node_data = {
                'node_id': mac_address,  # 使用MAC地址作为节点ID
                'mac_address': mac_address,
                'client_id': mac_address,
                'service_type': node_type,
                'status': status,
                'ip': ip,
                'port': port,
                'hostname': hostname,
                'version': version,
                'max_tasks': capabilities.get('max_tasks', 10),
                'node_metadata': metadata,
                'last_active': datetime.now() if status == 'online' else None
            }
            
            # 保存到内存缓存
            self.nodes[mac_address] = {
                'status': status,
                'metadata': metadata,
                'updated_at': timestamp
            }
            
            # 保存到数据库
            db = SessionLocal()
            try:
                # 更新或创建节点
                MQTTNodeCRUD.create_mqtt_node(db, node_data)
                logger.info(f"节点 {mac_address} 连接状态已更新: {status}")
                
                # 如果节点离线，需要处理该节点的任务重新分配
                if status == 'offline':
                    self._handle_node_offline(db, mac_address)
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"处理节点连接消息失败: {e}")
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
                # 查找子任务
                subtask = db.query(SubTask).filter(
                    SubTask.task_id == int(task_id),
                    SubTask.analysis_task_id == subtask_id
                ).first()
                
                if subtask:
                    # 根据状态更新子任务
                    if status == 'completed':
                        subtask.status = 2  # 已完成
                        subtask.completed_at = datetime.now()
                    elif status == 'failed':
                        subtask.status = 3  # 失败
                        subtask.error_message = payload.get('message', '任务执行失败')
                    elif status == 'running':
                        subtask.status = 1  # 运行中
                        if not subtask.started_at:
                            subtask.started_at = datetime.now()
                    
                    db.commit()
                    logger.info(f"子任务 {subtask_id} 状态已更新: {status}")
                    
                    # 更新主任务状态
                    TaskCRUD.update_task_status(db, int(task_id))
                else:
                    logger.warning(f"未找到子任务记录: task_id={task_id}, subtask_id={subtask_id}")
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
                subtask = db.query(SubTask).filter(
                    SubTask.task_id == int(task_id),
                    SubTask.analysis_task_id == subtask_id
                ).first()
                
                if subtask:
                    subtask.status = 0  # 未启动
                    subtask.mqtt_node_id = None  # 清除节点关联
                    subtask.error_message = data.get('message', '任务执行失败，等待重新分配')
                    db.commit()
                    logger.info(f"子任务 {subtask_id} 已重置为未启动状态，等待重新分配")
                else:
                    logger.warning(f"未找到失败的子任务: task_id={task_id}, subtask_id={subtask_id}")
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"处理任务失败情况出错: {e}")
            logger.error(traceback.format_exc())
    
    async def get_available_mqtt_node(self) -> Optional[MQTTNode]:
        """
        获取可用的MQTT节点
        """
        db = SessionLocal()
        try:
            # 查询所有在线且可用的节点
            nodes = db.query(MQTTNode).filter(
                MQTTNode.status == "online",
                MQTTNode.is_active == True,
                MQTTNode.task_count < MQTTNode.max_tasks
            ).all()
            
            if not nodes:
                logger.warning("没有可用的MQTT节点")
                return None
                
            # 根据负载排序，选择负载最低的节点
            nodes.sort(key=lambda n: n.task_count)
            return nodes[0]
        except Exception as e:
            logger.error(f"获取可用MQTT节点失败: {e}")
            return None
        finally:
            db.close()
    
    async def send_task_to_node(self, mac_address: str, task_id: str, subtask_id: str, 
                               config: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        向指定节点发送任务
        
        Args:
            mac_address: 节点MAC地址
            task_id: 任务ID
            subtask_id: 子任务ID
            config: 任务配置
            
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