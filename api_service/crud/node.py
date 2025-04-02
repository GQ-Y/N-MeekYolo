"""
节点CRUD操作
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union

from api_service.models.node import Node
from api_service.models.responses import NodeCreate, NodeUpdate

class NodeCRUD:
    """节点CRUD操作类"""
    
    @staticmethod
    def create_node(db: Session, node: NodeCreate) -> Node:
        """
        创建新节点
        
        参数:
        - db: 数据库会话
        - node: 节点创建参数
        
        返回:
        - 创建的节点对象
        """
        db_node = Node(
            ip=node.ip,
            port=node.port,
            service_name=node.service_name,
            service_status="offline",
            last_heartbeat=datetime.now(),
            image_task_count=0,
            video_task_count=0,
            stream_task_count=0,
            weight=node.weight,
            max_tasks=node.max_tasks
        )
        db.add(db_node)
        db.commit()
        db.refresh(db_node)
        return db_node

    @staticmethod
    def get_nodes(
        db: Session,
        skip: int = 0,
        limit: int = 100
    ) -> List[Node]:
        """
        获取节点列表
        
        参数:
        - db: 数据库会话
        - skip: 跳过的记录数
        - limit: 返回的最大记录数
        
        返回:
        - 节点列表
        """
        return db.query(Node).offset(skip).limit(limit).all()

    @staticmethod
    def get_node(db: Session, node_id: int) -> Optional[Node]:
        """
        获取指定节点
        
        参数:
        - db: 数据库会话
        - node_id: 节点ID
        
        返回:
        - 节点对象，如不存在则返回None
        """
        return db.query(Node).filter(Node.id == node_id).first()

    @staticmethod
    def get_node_by_ip_port(db: Session, ip: str, port: str) -> Optional[Node]:
        """通过IP和端口获取节点"""
        return db.query(Node).filter(
            and_(Node.ip == ip, Node.port == port)
        ).first()

    @staticmethod
    def update_node(
        db: Session,
        node_id: int,
        node_update: NodeUpdate
    ) -> Optional[Node]:
        """
        更新节点基本信息
        
        参数:
        - db: 数据库会话
        - node_id: 节点ID
        - node_update: 更新信息
        
        返回:
        - 更新后的节点对象，如不存在则返回None
        """
        db_node = NodeCRUD.get_node(db, node_id)
        if not db_node:
            return None
            
        # 更新基本信息
        if node_update.ip is not None:
            db_node.ip = node_update.ip
        if node_update.port is not None:
            db_node.port = node_update.port
        if node_update.service_name is not None:
            db_node.service_name = node_update.service_name
        if node_update.service_status is not None:
            db_node.service_status = node_update.service_status
            db_node.last_heartbeat = datetime.now()
        if node_update.weight is not None:
            db_node.weight = node_update.weight
        if node_update.max_tasks is not None:
            db_node.max_tasks = node_update.max_tasks
            
        db.commit()
        db.refresh(db_node)
        return db_node

    @staticmethod
    def update_node_status(
        db: Session,
        node_id: int,
        service_status: str,
        task_counts: Optional[Dict[str, int]] = None
    ) -> Optional[Node]:
        """
        更新节点状态和任务数量
        
        参数:
        - db: 数据库会话
        - node_id: 节点ID
        - service_status: 服务状态
        - task_counts: 任务数量字典，包含image、video、stream三类任务数量
        
        返回:
        - 更新后的节点对象，如不存在则返回None
        """
        db_node = NodeCRUD.get_node(db, node_id)
        if not db_node:
            return None
            
        # 更新状态
        db_node.service_status = service_status
        db_node.last_heartbeat = datetime.now()
        
        # 更新任务数量
        if task_counts:
            if 'image' in task_counts:
                db_node.image_task_count = task_counts['image']
            if 'video' in task_counts:
                db_node.video_task_count = task_counts['video']
            if 'stream' in task_counts:
                db_node.stream_task_count = task_counts['stream']
                
        db.commit()
        db.refresh(db_node)
        return db_node

    @staticmethod
    def delete_node(db: Session, node_id: int) -> bool:
        """
        删除节点
        
        参数:
        - db: 数据库会话
        - node_id: 节点ID
        
        返回:
        - 删除是否成功
        """
        db_node = NodeCRUD.get_node(db, node_id)
        if not db_node:
            return False
            
        db.delete(db_node)
        db.commit()
        return True

    @staticmethod
    def check_nodes_health(db: Session, timeout_minutes: int = 5) -> None:
        """
        检查节点健康状态
        
        参数:
        - db: 数据库会话
        - timeout_minutes: 超时时间（分钟）
        """
        timeout = datetime.now() - timedelta(minutes=timeout_minutes)
        nodes = (
            db.query(Node)
            .filter(
                and_(
                    Node.service_status == "online",
                    Node.last_heartbeat < timeout
                )
            )
            .all()
        )
        
        for node in nodes:
            node.service_status = "offline"
            
        if nodes:
            db.commit()

    @staticmethod
    def get_available_node(db: Session) -> Optional[Node]:
        """
        获取可用节点（用于负载均衡）
        
        算法：
        1. 过滤出在线节点
        2. 计算每个节点的负载百分比（当前任务数/最大任务数）
        3. 按权重和负载百分比排序，返回负载最低且权重最高的节点
        
        参数:
        - db: 数据库会话
        
        返回:
        - 最佳可用节点，如无可用节点则返回None
        """
        # 获取所有在线节点
        nodes = (
            db.query(Node)
            .filter(Node.service_status == "online")
            .filter(Node.is_active == True)
            .all()
        )
        
        if not nodes:
            return None
            
        # 计算每个节点的负载情况
        available_nodes = []
        for node in nodes:
            total_tasks = node.image_task_count + node.video_task_count + node.stream_task_count
            # 如果节点已满，跳过
            if total_tasks >= node.max_tasks:
                continue
                
            # 计算负载百分比
            load_percentage = total_tasks / node.max_tasks if node.max_tasks > 0 else 1.0
            
            # 计算加权分数（权重越高，负载越低，分数越高）
            # 权重因子在0.1-1之间，负载因子在0-1之间
            weight_factor = min(1.0, max(0.1, node.weight / 10))  # 将权重归一化到0.1-1
            load_factor = 1.0 - load_percentage
            
            # 最终分数
            score = weight_factor * load_factor
            
            available_nodes.append({
                "node": node,
                "score": score,
                "total_tasks": total_tasks,
                "free_slots": node.max_tasks - total_tasks
            })
        
        if not available_nodes:
            return None
            
        # 按分数降序排序
        available_nodes.sort(key=lambda x: x["score"], reverse=True)
        
        # 返回得分最高的节点
        return available_nodes[0]["node"]