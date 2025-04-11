"""
节点健康检查服务
使用Redis和MQTT监听机制替代传统HTTP轮询机制
"""
import asyncio
import time
from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import or_
from core.database import SessionLocal
from models.database import Node, Task, SubTask
from .node_manager import NodeManager
from core.redis_manager import RedisManager
from services.mqtt.mqtt_message_processor import MQTTMessageProcessor
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class NodeHealthChecker:
    """节点健康检查服务"""
    
    def __init__(self):
        """初始化健康检查服务"""
        # 节点管理器
        self.node_manager = NodeManager.get_instance()
        
        # Redis管理器
        self.redis = RedisManager.get_instance()
        
        # MQTT消息处理器
        self.mqtt_processor = MQTTMessageProcessor.get_instance()
        
        # 健康检查间隔（秒）
        self.check_interval = 30.0
        
        # 节点超时时间（秒）
        self.node_timeout = 120.0
        
        # 运行状态
        self.running = False
        
        # 健康检查任务
        self.check_task = None
        
        # 节点最后心跳时间
        self.node_heartbeats: Dict[int, float] = {}
        
        # 正在迁移的节点
        self.migrating_nodes: Set[int] = set()

    async def start(self):
        """启动健康检查服务"""
        if self.running:
            logger.info("节点健康检查服务已经在运行中")
            return
            
        self.running = True
        
        # 启动健康检查定时任务
        self.check_task = asyncio.create_task(self._health_check_loop())
                
        # 注册MQTT消息处理器
        self._register_mqtt_handlers()
        
        logger.info(f"节点健康检查服务已启动，检查间隔: {self.check_interval}秒")
    
    async def stop(self):
        """停止健康检查服务"""
        if not self.running:
            return
            
        self.running = False
        
        # 取消健康检查任务
        if self.check_task:
            self.check_task.cancel()
            try:
                await self.check_task
            except asyncio.CancelledError:
                pass
            
        logger.info("节点健康检查服务已停止")
    
    async def check_nodes_health(self):
        """检查所有节点的健康状态"""
        try:
            db = SessionLocal()
            try:
                # 获取当前时间
                now = datetime.now()
                timeout_threshold = now - timedelta(seconds=self.node_timeout)
            
                # 查询超时的在线节点
                offline_nodes = db.query(Node).filter(
                    Node.service_status == "online",
                    Node.is_active == True,
                    Node.last_heartbeat < timeout_threshold
                ).all()
            
                if not offline_nodes:
                    logger.info("所有节点健康状态正常")
                    return
            
                logger.warning(f"发现 {len(offline_nodes)} 个节点超时，标记为离线并迁移任务")
                
                # 处理每个离线节点
                for node in offline_nodes:
                    # 检查是否已经在迁移中
                    if node.id in self.migrating_nodes:
                        logger.info(f"节点 {node.id} 的任务迁移正在进行中，跳过")
                        continue
                    
                    # 标记为正在迁移
                    self.migrating_nodes.add(node.id)
                    
                    try:
                        # 标记节点为离线，并获取运行中的任务
                        tasks = await self.node_manager.mark_node_offline(node.id, db)
                        
                        if tasks:
                            logger.info(f"开始迁移节点 {node.id} 的 {len(tasks)} 个任务")
                    
                            # 迁移任务到其他节点
                            results = await self.node_manager.migrate_tasks(node.id, tasks, db)
                            
                            logger.info(f"节点 {node.id} 任务迁移完成: 成功={results['migrated']}, 失败={results['failed']}")
                        else:
                            logger.info(f"节点 {node.id} 没有运行中的任务需要迁移")
                    
                    finally:
                        # 移除迁移标记
                        self.migrating_nodes.discard(node.id)
            
            finally:
                db.close()
            
        except Exception as e:
            logger.error(f"节点健康检查失败: {str(e)}")

    async def handle_node_connect(self, node_id: int, metadata: Optional[Dict[str, Any]] = None):
        """
        处理节点连接事件
        
        Args:
            node_id: 节点ID
            metadata: 节点元数据
        """
        try:
            db = SessionLocal()
            try:
                # 更新节点为在线状态
                await self.node_manager.mark_node_online(node_id, db, metadata)
                    
                # 更新最后心跳时间
                self.node_heartbeats[node_id] = time.time()
                
                logger.info(f"节点 {node_id} 已连接")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"处理节点 {node_id} 连接事件失败: {str(e)}")
    
    async def handle_node_disconnect(self, node_id: int):
        """
        处理节点断开连接事件
        
        Args:
            node_id: 节点ID
        """
        try:
            db = SessionLocal()
            try:
                # 移除心跳记录
                self.node_heartbeats.pop(node_id, None)
                
                # 标记节点为离线，并获取运行中的任务
                tasks = await self.node_manager.mark_node_offline(node_id, db)
                
                if tasks:
                    logger.info(f"开始迁移节点 {node_id} 的 {len(tasks)} 个任务")
                    
                    # 迁移任务到其他节点
                    results = await self.node_manager.migrate_tasks(node_id, tasks, db)
                    
                    logger.info(f"节点 {node_id} 任务迁移完成: 成功={results['migrated']}, 失败={results['failed']}")
                
                logger.info(f"节点 {node_id} 已断开连接")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"处理节点 {node_id} 断开连接事件失败: {str(e)}")
    
    async def handle_node_heartbeat(self, node_id: int, metadata: Optional[Dict[str, Any]] = None):
        """
        处理节点心跳事件
        
        Args:
            node_id: 节点ID
            metadata: 节点元数据
        """
        try:
            # 更新最后心跳时间
            self.node_heartbeats[node_id] = time.time()
            
            # 如果有资源数据，更新节点资源信息
            if metadata and isinstance(metadata, dict) and "resource" in metadata:
                await self.node_manager.update_node_resource(node_id, metadata["resource"])
            
            logger.debug(f"收到节点 {node_id} 的心跳")
        except Exception as e:
            logger.error(f"处理节点 {node_id} 心跳事件失败: {str(e)}")
    
    def _register_mqtt_handlers(self):
        """注册MQTT消息处理器"""
        if not self.mqtt_processor:
            logger.warning("MQTT消息处理器未初始化，无法注册处理器")
            return
            
        try:
            # 注册节点连接处理器
            self.mqtt_processor.register_handler(
                "meek/connection",
                self._mqtt_connection_handler
            )
            
            # 注册节点心跳处理器
            self.mqtt_processor.register_handler(
                "meek/heartbeat",
                self._mqtt_heartbeat_handler
            )
            
            logger.info("已注册MQTT节点状态处理器")
        except Exception as e:
            logger.error(f"注册MQTT处理器失败: {str(e)}")
    
    def _mqtt_connection_handler(self, topic: str, payload: Any):
        """
        MQTT连接状态处理器
        
        Args:
            topic: 消息主题
            payload: 消息内容
        """
        try:
            if not isinstance(payload, dict):
                logger.warning(f"无效的MQTT连接消息格式: {payload}")
                return
            
            node_id = payload.get("node_id")
            if not node_id:
                logger.warning("MQTT连接消息缺少node_id字段")
                return
                
            status = payload.get("status")
            if not status:
                logger.warning("MQTT连接消息缺少status字段")
                return
                
            # 转换为整数ID
            try:
                node_id = int(node_id)
            except (ValueError, TypeError):
                logger.warning(f"无效的节点ID: {node_id}")
                return
                
            # 处理连接/断开事件
            if status == "online":
                metadata = payload.get("metadata", {})
                asyncio.create_task(self.handle_node_connect(node_id, metadata))
            elif status == "offline":
                asyncio.create_task(self.handle_node_disconnect(node_id))
            else:
                logger.warning(f"未知的连接状态: {status}")
            
        except Exception as e:
            logger.error(f"处理MQTT连接消息失败: {str(e)}")
    
    def _mqtt_heartbeat_handler(self, topic: str, payload: Any):
        """
        MQTT心跳处理器
        
        Args:
            topic: 消息主题
            payload: 消息内容
        """
        try:
            if not isinstance(payload, dict):
                logger.warning(f"无效的MQTT心跳消息格式: {payload}")
                return
            
            node_id = payload.get("node_id")
            if not node_id:
                logger.warning("MQTT心跳消息缺少node_id字段")
                return
            
            # 转换为整数ID
            try:
                node_id = int(node_id)
            except (ValueError, TypeError):
                logger.warning(f"无效的节点ID: {node_id}")
                return
                
            # 处理心跳事件
            asyncio.create_task(self.handle_node_heartbeat(node_id, payload))
            
        except Exception as e:
            logger.error(f"处理MQTT心跳消息失败: {str(e)}")
    
    async def _health_check_loop(self):
        """健康检查循环"""
        logger.info("健康检查循环已启动")
        
        while self.running:
            try:
                # 执行健康检查
                await self.check_nodes_health()
        
                # 等待下一次检查
                await asyncio.sleep(self.check_interval)
                
            except asyncio.CancelledError:
                logger.info("健康检查循环已取消")
                break
            except Exception as e:
                logger.error(f"健康检查循环出错: {str(e)}")
                await asyncio.sleep(10)  # 出错后等待10秒再重试
        
        logger.info("健康检查循环已停止")

# 全局健康检查服务实例
_health_checker = None

async def start_health_checker() -> NodeHealthChecker:
    """
    启动节点健康检查服务
    
    Returns:
        NodeHealthChecker: 健康检查服务实例
    """
    global _health_checker
    
    if _health_checker is None:
        _health_checker = NodeHealthChecker()
        
    await _health_checker.start()
    return _health_checker

async def stop_health_checker():
    """停止节点健康检查服务"""
    global _health_checker
    
    if _health_checker:
        await _health_checker.stop()
        _health_checker = None
        
    logger.info("节点健康检查服务已停止")

def get_health_checker() -> Optional[NodeHealthChecker]:
    """
    获取健康检查服务实例
    
    Returns:
        Optional[NodeHealthChecker]: 健康检查服务实例
    """
    return _health_checker 