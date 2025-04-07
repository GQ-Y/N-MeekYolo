"""
MQTT节点管理CRUD模块
"""
import logging
import time
import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc, or_
from models.database import MQTTNode

logger = logging.getLogger(__name__)

class MQTTNodeCRUD:
    """MQTT节点CRUD操作"""
    
    @staticmethod
    def create_mqtt_node(db: Session, node_data: Dict[str, Any]) -> MQTTNode:
        """
        创建MQTT节点
        
        Args:
            db: 数据库会话
            node_data: 节点数据
            
        Returns:
            MQTTNode: 创建的MQTT节点对象
        """
        try:
            # 检查是否已存在相同node_id的节点
            existing_node = db.query(MQTTNode).filter(MQTTNode.node_id == node_data.get('node_id')).first()
            if existing_node:
                # 更新现有节点
                for key, value in node_data.items():
                    setattr(existing_node, key, value)
                existing_node.updated_at = datetime.now()
                existing_node.last_active = datetime.now()
                db.commit()
                db.refresh(existing_node)
                logger.info(f"更新MQTT节点: {existing_node.node_id}")
                return existing_node
            
            # 创建新节点
            mqtt_node = MQTTNode(**node_data)
            mqtt_node.last_active = datetime.now()
            db.add(mqtt_node)
            db.commit()
            db.refresh(mqtt_node)
            logger.info(f"创建MQTT节点: {mqtt_node.node_id}")
            return mqtt_node
        except Exception as e:
            db.rollback()
            logger.error(f"创建MQTT节点失败: {e}")
            raise
    
    @staticmethod
    def get_mqtt_nodes(
        db: Session, 
        skip: int = 0, 
        limit: int = 100,
        service_type: Optional[str] = None,
        status: Optional[str] = None,
        is_active: Optional[bool] = None,
        keyword: Optional[str] = None,
        order_by: str = "id",
        order_direction: str = "desc"
    ) -> Tuple[List[MQTTNode], int]:
        """
        获取MQTT节点列表
        
        Args:
            db: 数据库会话
            skip: 跳过条数
            limit: 限制条数
            service_type: 服务类型过滤
            status: 状态过滤
            is_active: 是否启用过滤
            keyword: 关键词搜索
            order_by: 排序字段
            order_direction: 排序方向
            
        Returns:
            Tuple[List[MQTTNode], int]: MQTT节点列表和总数
        """
        try:
            query = db.query(MQTTNode)
            
            # 应用过滤条件
            if service_type:
                query = query.filter(MQTTNode.service_type == service_type)
            
            if status:
                query = query.filter(MQTTNode.status == status)
            
            if is_active is not None:
                query = query.filter(MQTTNode.is_active == is_active)
            
            if keyword:
                query = query.filter(
                    or_(
                        MQTTNode.node_id.like(f"%{keyword}%"),
                        MQTTNode.client_id.like(f"%{keyword}%"),
                        MQTTNode.ip.like(f"%{keyword}%"),
                        MQTTNode.hostname.like(f"%{keyword}%"),
                        MQTTNode.remark.like(f"%{keyword}%")
                    )
                )
            
            # 获取总数
            total = query.count()
            
            # 应用排序
            if hasattr(MQTTNode, order_by):
                order_column = getattr(MQTTNode, order_by)
                if order_direction.lower() == "asc":
                    query = query.order_by(asc(order_column))
                else:
                    query = query.order_by(desc(order_column))
            else:
                query = query.order_by(desc(MQTTNode.id))
            
            # 应用分页
            nodes = query.offset(skip).limit(limit).all()
            
            return nodes, total
        except Exception as e:
            logger.error(f"获取MQTT节点列表失败: {e}")
            raise
    
    @staticmethod
    def get_mqtt_node(db: Session, node_id: int) -> Optional[MQTTNode]:
        """
        获取单个MQTT节点
        
        Args:
            db: 数据库会话
            node_id: 节点ID
            
        Returns:
            Optional[MQTTNode]: MQTT节点对象
        """
        try:
            return db.query(MQTTNode).filter(MQTTNode.id == node_id).first()
        except Exception as e:
            logger.error(f"获取MQTT节点失败: {e}")
            raise
    
    @staticmethod
    def get_mqtt_node_by_node_id(db: Session, node_id: str) -> Optional[MQTTNode]:
        """
        根据Node ID获取MQTT节点
        
        Args:
            db: 数据库会话
            node_id: 节点ID字符串
            
        Returns:
            Optional[MQTTNode]: MQTT节点对象
        """
        try:
            return db.query(MQTTNode).filter(MQTTNode.node_id == node_id).first()
        except Exception as e:
            logger.error(f"根据Node ID获取MQTT节点失败: {e}")
            raise
    
    @staticmethod
    def update_mqtt_node(db: Session, node_id: int, node_data: Dict[str, Any]) -> Optional[MQTTNode]:
        """
        更新MQTT节点
        
        Args:
            db: 数据库会话
            node_id: 节点ID
            node_data: 节点数据
            
        Returns:
            Optional[MQTTNode]: 更新后的MQTT节点对象
        """
        try:
            mqtt_node = db.query(MQTTNode).filter(MQTTNode.id == node_id).first()
            if not mqtt_node:
                return None
            
            for key, value in node_data.items():
                if hasattr(mqtt_node, key):
                    setattr(mqtt_node, key, value)
            
            mqtt_node.updated_at = datetime.now()
            db.commit()
            db.refresh(mqtt_node)
            logger.info(f"更新MQTT节点: {mqtt_node.node_id}")
            return mqtt_node
        except Exception as e:
            db.rollback()
            logger.error(f"更新MQTT节点失败: {e}")
            raise
    
    @staticmethod
    def update_mqtt_node_status(db: Session, node_id: str, status: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[MQTTNode]:
        """
        更新MQTT节点状态
        
        Args:
            db: 数据库会话
            node_id: 节点ID字符串
            status: 状态
            metadata: 元数据
            
        Returns:
            Optional[MQTTNode]: 更新后的MQTT节点对象
        """
        try:
            mqtt_node = db.query(MQTTNode).filter(MQTTNode.node_id == node_id).first()
            if not mqtt_node:
                return None
            
            mqtt_node.status = status
            mqtt_node.last_active = datetime.now()
            
            if metadata:
                # 更新元数据
                if not mqtt_node.node_metadata:
                    mqtt_node.node_metadata = {}
                
                mqtt_node.node_metadata.update(metadata)
                
                # 如果元数据中包含资源信息，更新相应字段
                resource = metadata.get('resource', {})
                if resource:
                    if 'cpu_usage' in resource:
                        mqtt_node.cpu_usage = resource['cpu_usage']
                    if 'memory_usage' in resource:
                        mqtt_node.memory_usage = resource['memory_usage']
                    if 'gpu_usage' in resource:
                        mqtt_node.gpu_usage = resource['gpu_usage']
                    if 'task_count' in resource:
                        mqtt_node.task_count = resource['task_count']
            
            db.commit()
            db.refresh(mqtt_node)
            return mqtt_node
        except Exception as e:
            db.rollback()
            logger.error(f"更新MQTT节点状态失败: {e}")
            raise
    
    @staticmethod
    def delete_mqtt_node(db: Session, node_id: int) -> bool:
        """
        删除MQTT节点
        
        Args:
            db: 数据库会话
            node_id: 节点ID
            
        Returns:
            bool: 是否删除成功
        """
        try:
            mqtt_node = db.query(MQTTNode).filter(MQTTNode.id == node_id).first()
            if not mqtt_node:
                return False
            
            db.delete(mqtt_node)
            db.commit()
            logger.info(f"删除MQTT节点: {node_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"删除MQTT节点失败: {e}")
            raise
    
    @staticmethod
    def toggle_mqtt_node_active(db: Session, node_id: int, is_active: bool) -> Optional[MQTTNode]:
        """
        启用/停用MQTT节点
        
        Args:
            db: 数据库会话
            node_id: 节点ID
            is_active: 是否启用
            
        Returns:
            Optional[MQTTNode]: 更新后的MQTT节点对象
        """
        try:
            mqtt_node = db.query(MQTTNode).filter(MQTTNode.id == node_id).first()
            if not mqtt_node:
                return None
            
            mqtt_node.is_active = is_active
            mqtt_node.updated_at = datetime.now()
            db.commit()
            db.refresh(mqtt_node)
            
            status = "启用" if is_active else "停用"
            logger.info(f"{status}MQTT节点: {mqtt_node.node_id}")
            
            # 尝试向MQTT发送节点状态变更消息
            try:
                from app import app
                if hasattr(app.state, 'analysis_client') and app.state.analysis_client and app.state.analysis_client.mqtt_client:
                    mqtt_client = app.state.analysis_client.mqtt_client
                    if mqtt_client.connected:
                        # 发布节点控制消息
                        topic_prefix = mqtt_client.config.get('topic_prefix', 'yolo/')
                        topic = f"{topic_prefix}nodes/{mqtt_node.node_id}/control"
                        
                        # 构建控制消息
                        control_msg = {
                            "version": "2.0.0",
                            "message_type": "node_control",
                            "timestamp": int(time.time()),
                            "payload": {
                                "node_id": mqtt_node.node_id,
                                "action": "enable" if is_active else "disable",
                                "params": {
                                    "reason": f"通过API手动{status}"
                                }
                            }
                        }
                        
                        # 发布消息
                        mqtt_client.client.publish(
                            topic,
                            json.dumps(control_msg),
                            qos=mqtt_client.config.get('qos', 1)
                        )
                        
                        logger.info(f"已发送MQTT节点控制消息: {mqtt_node.node_id} -> {status}")
            except Exception as e:
                logger.error(f"发送MQTT节点控制消息失败: {e}")
            
            return mqtt_node
        except Exception as e:
            db.rollback()
            logger.error(f"切换MQTT节点状态失败: {e}")
            raise 