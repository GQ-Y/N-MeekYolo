"""
节点管理器模块
实现智能负载均衡和任务分配
"""
import threading
import asyncio
import time
from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from core.database import SessionLocal
from core.redis_manager import RedisManager
from models.database import Node, Task, SubTask
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class NodeManager:
    """
    节点管理器
    
    负责:
    1. 智能负载均衡
    2. 节点资源监控
    3. 任务分配与迁移
    """
    
    def __init__(self):
        """初始化节点管理器"""
        # Redis管理器
        self.redis = RedisManager.get_instance()
        
        # 节点缓存
        self.nodes_cache: Dict[int, Dict[str, Any]] = {}
        
        # 节点资源缓存
        self.node_resources: Dict[int, Dict[str, Any]] = {}
        
        # 节点任务计数
        self.node_task_counts: Dict[int, Dict[str, int]] = {}
        
        # 线程锁
        self.lock = threading.RLock()
        
        # 缓存过期时间（秒）
        self.cache_ttl = 30.0
        
        # 缓存最后更新时间
        self.last_cache_update = 0.0
        
        # Redis键前缀
        self.node_prefix = "node:"
        self.node_resource_prefix = "node:resource:"
        self.node_task_prefix = "node:tasks:"
        
    async def get_available_node(
        self, 
        task_type: str, 
        db: Session, 
        preferred_node_id: Optional[int] = None
    ) -> Tuple[Optional[Node], Dict[str, Any]]:
        """
        获取可用节点，使用智能负载均衡算法
        
        Args:
            task_type: 任务类型 (image/video/stream)
            db: 数据库会话
            preferred_node_id: 优先选择的节点ID（可选）
            
        Returns:
            Tuple[Node, Dict]: 节点对象和额外信息
        """
        # 检查缓存是否需要刷新
        await self._refresh_cache_if_needed(db)
        
        with self.lock:
            # 先尝试使用优先节点
            if preferred_node_id is not None:
                node = db.query(Node).filter(
                    Node.id == preferred_node_id,
                    Node.is_active == True,
                    Node.service_status == "online"
                ).first()
                
                if node:
                    logger.info(f"使用指定的优先节点: {preferred_node_id}")
                    return node, {"score": 100, "reason": "preferred_node"}
            
            # 获取所有在线节点
            nodes = db.query(Node).filter(
                Node.is_active == True,
                Node.service_status == "online"
            ).all()
            
            if not nodes:
                logger.warning("没有可用的在线节点")
                return None, {"error": "no_nodes_available"}
            
            # 计算每个节点的得分
            node_scores = []
            for node in nodes:
                score = self._calculate_node_score(node, task_type)
                node_scores.append((node, score))
            
            # 按得分排序（降序）
            node_scores.sort(key=lambda x: x[1]["total"], reverse=True)
            
            # 获取得分最高的节点
            if node_scores:
                best_node, score = node_scores[0]
                logger.info(f"为{task_type}任务选择节点 {best_node.id}，得分: {score['total']}")
                
                # 更新节点的任务计数
                self._increment_node_task_count(best_node.id, task_type)
                
                return best_node, {"score": score, "candidates": len(node_scores)}
            
            return None, {"error": "no_suitable_node"}
    
    async def release_node(self, node_id: int, task_type: str):
        """
        释放节点资源（减少任务计数）
        
        Args:
            node_id: 节点ID
            task_type: 任务类型
        """
        with self.lock:
            # 减少节点任务计数
            self._decrement_node_task_count(node_id, task_type)
            
            logger.info(f"已释放节点 {node_id} 的 {task_type} 任务资源")
    
    async def update_node_resource(self, node_id: int, resource_data: Dict[str, Any]):
        """
        更新节点资源信息
        
        Args:
            node_id: 节点ID
            resource_data: 资源数据
        """
        with self.lock:
            # 更新资源缓存
            self.node_resources[node_id] = {
                "timestamp": time.time(),
                "data": resource_data
            }
            
            # 保存到Redis
            key = f"{self.node_resource_prefix}{node_id}"
            await self.redis.set_value(key, {
                "timestamp": time.time(),
                "data": resource_data
            }, ex=300)  # 5分钟过期
            
            logger.debug(f"已更新节点 {node_id} 的资源信息")
    
    async def mark_node_offline(self, node_id: int, db: Session):
        """
        标记节点为离线状态
        
        Args:
            node_id: 节点ID
            db: 数据库会话
        """
        try:
            # 更新数据库中的节点状态
            node = db.query(Node).filter(Node.id == node_id).first()
            if node:
                node.service_status = "offline"
                node.updated_at = datetime.now()
                db.commit()
                
                with self.lock:
                    # 更新缓存
                    if node_id in self.nodes_cache:
                        self.nodes_cache[node_id]["service_status"] = "offline"
                        self.nodes_cache[node_id]["updated_at"] = datetime.now()
                
                logger.info(f"节点 {node_id} 已标记为离线")
                
                # 返回节点上运行的任务，用于迁移
                return await self._get_running_tasks_on_node(node_id, db)
            
            return []
        
        except Exception as e:
            db.rollback()
            logger.error(f"标记节点 {node_id} 为离线状态失败: {str(e)}")
            return []
    
    async def mark_node_online(self, node_id: int, db: Session, metadata: Optional[Dict[str, Any]] = None):
        """
        标记节点为在线状态
        
        Args:
            node_id: 节点ID
            db: 数据库会话
            metadata: 节点元数据
        """
        try:
            # 更新数据库中的节点状态
            node = db.query(Node).filter(Node.id == node_id).first()
            if node:
                node.service_status = "online"
                node.last_heartbeat = datetime.now()
                node.updated_at = datetime.now()
                
                # 重置任务计数
                node.image_task_count = 0
                node.video_task_count = 0
                node.stream_task_count = 0
                
                db.commit()
                
                with self.lock:
                    # 更新缓存
                    if node_id in self.nodes_cache:
                        self.nodes_cache[node_id]["service_status"] = "online"
                        self.nodes_cache[node_id]["last_heartbeat"] = datetime.now()
                        self.nodes_cache[node_id]["updated_at"] = datetime.now()
                        self.nodes_cache[node_id]["image_task_count"] = 0
                        self.nodes_cache[node_id]["video_task_count"] = 0
                        self.nodes_cache[node_id]["stream_task_count"] = 0
                
                # 如果提供了元数据，则更新节点资源信息
                if metadata and isinstance(metadata, dict):
                    resource_data = metadata.get("resource", {})
                    await self.update_node_resource(node_id, resource_data)
                
                logger.info(f"节点 {node_id} 已标记为在线")
                return True
            
            return False
        
        except Exception as e:
            db.rollback()
            logger.error(f"标记节点 {node_id} 为在线状态失败: {str(e)}")
            return False
    
    async def migrate_tasks(self, source_node_id: int, tasks: List[Dict[str, Any]], db: Session) -> Dict[str, Any]:
        """
        迁移任务到其他节点
        
        Args:
            source_node_id: 源节点ID
            tasks: 任务列表
            db: 数据库会话
            
        Returns:
            Dict: 迁移结果统计
        """
        if not tasks:
            return {"total": 0, "migrated": 0, "failed": 0, "details": []}
        
        results = {
            "total": len(tasks),
            "migrated": 0,
            "failed": 0,
            "details": []
        }
        
        for task_info in tasks:
            task_id = task_info.get("task_id")
            subtask_id = task_info.get("subtask_id")
            task_type = task_info.get("task_type", "stream")
            
            try:
                # 获取可用节点
                target_node, node_info = await self.get_available_node(task_type, db)
                
                if not target_node:
                    logger.warning(f"无法为任务 {task_id}/{subtask_id} 找到目标节点，将任务标记为失败")
                    results["failed"] += 1
                    results["details"].append({
                        "task_id": task_id,
                        "subtask_id": subtask_id,
                        "status": "failed",
                        "reason": "no_target_node"
                    })
                    continue
                
                # 更新子任务的节点信息
                subtask = db.query(SubTask).filter(SubTask.id == subtask_id).first()
                if subtask:
                    subtask.node_id = target_node.id
                    subtask.updated_at = datetime.now()
                    db.commit()
                    
                    results["migrated"] += 1
                    results["details"].append({
                        "task_id": task_id,
                        "subtask_id": subtask_id,
                        "status": "migrated",
                        "target_node": target_node.id
                    })
                    
                    logger.info(f"任务 {task_id}/{subtask_id} 已从节点 {source_node_id} 迁移到节点 {target_node.id}")
                else:
                    results["failed"] += 1
                    results["details"].append({
                        "task_id": task_id,
                        "subtask_id": subtask_id,
                        "status": "failed",
                        "reason": "subtask_not_found"
                    })
            
            except Exception as e:
                db.rollback()
                logger.error(f"迁移任务 {task_id}/{subtask_id} 失败: {str(e)}")
                results["failed"] += 1
                results["details"].append({
                    "task_id": task_id,
                    "subtask_id": subtask_id,
                    "status": "failed",
                    "reason": str(e)
                })
        
        return results
    
    async def get_node_status(self, node_id: int) -> Dict[str, Any]:
        """
        获取节点状态信息
        
        Args:
            node_id: 节点ID
            
        Returns:
            Dict: 节点状态信息
        """
        with self.lock:
            # 从缓存获取节点基本信息
            node_info = self.nodes_cache.get(node_id, {})
            
            # 从缓存获取资源信息
            resource_info = self.node_resources.get(node_id, {}).get("data", {})
            
            # 从缓存获取任务计数
            task_counts = self.node_task_counts.get(node_id, {
                "image": 0,
                "video": 0,
                "stream": 0,
                "total": 0
            })
            
            # 合并信息
            status = {
                "node_id": node_id,
                "service_status": node_info.get("service_status", "unknown"),
                "last_heartbeat": node_info.get("last_heartbeat"),
                "task_counts": task_counts,
                "resources": resource_info
            }
            
            return status
            
    def _calculate_node_score(self, node: Node, task_type: str) -> Dict[str, float]:
        """
        计算节点得分
        
        Args:
            node: 节点对象
            task_type: 任务类型
            
        Returns:
            Dict: 得分详情
        """
        # 获取节点资源使用情况
        resource_info = self.node_resources.get(node.id, {}).get("data", {})
        cpu_usage = resource_info.get("cpu_usage", 0)
        memory_usage = resource_info.get("memory_usage", 0)
        gpu_usage = resource_info.get("gpu_usage", 0)
        
        # 获取节点当前任务数
        image_tasks = getattr(node, "image_task_count", 0) or 0
        video_tasks = getattr(node, "video_task_count", 0) or 0
        stream_tasks = getattr(node, "stream_task_count", 0) or 0
        total_tasks = image_tasks + video_tasks + stream_tasks
        
        # 获取节点最大任务数
        max_tasks = getattr(node, "max_tasks", 10) or 10
        
        # 计算负载比例
        load_ratio = total_tasks / max_tasks if max_tasks > 0 else 1.0
        
        # 计算资源得分 (越低越好)
        resource_score = (cpu_usage + memory_usage + gpu_usage) / 3.0
        
        # 计算任务均衡得分
        if task_type == "image":
            task_balance_score = 1.0 - (image_tasks / (max_tasks or 1))
        elif task_type == "video":
            task_balance_score = 1.0 - (video_tasks / (max_tasks or 1))
        elif task_type == "stream":
            task_balance_score = 1.0 - (stream_tasks / (max_tasks or 1))
        else:
            task_balance_score = 1.0 - load_ratio
        
        # 获取节点权重
        weight = getattr(node, "weight", 1.0) or 1.0
        
        # 计算总分 (越高越好)
        # 资源得分需要反转，因为资源使用率越低越好
        resource_factor = 1.0 - resource_score
        
        # 综合评分，考虑各因素权重
        total_score = (
            resource_factor * 0.4 +  # 资源使用情况 (40%)
            task_balance_score * 0.4 +  # 任务均衡 (40%)
            weight * 0.2  # 节点权重 (20%)
        ) * 100  # 转换为百分比
        
        return {
            "resource": resource_factor * 100,
            "task_balance": task_balance_score * 100,
            "weight": weight * 100,
            "total": total_score
        }
    
    def _increment_node_task_count(self, node_id: int, task_type: str):
        """
        增加节点任务计数
        
        Args:
            node_id: 节点ID
            task_type: 任务类型
        """
        with self.lock:
            if node_id not in self.node_task_counts:
                self.node_task_counts[node_id] = {
                    "image": 0,
                    "video": 0,
                    "stream": 0,
                    "total": 0
                }
            
            # 增加特定类型的任务计数
            if task_type in self.node_task_counts[node_id]:
                self.node_task_counts[node_id][task_type] += 1
            
            # 更新总计数
            self.node_task_counts[node_id]["total"] = (
                self.node_task_counts[node_id]["image"] +
                self.node_task_counts[node_id]["video"] +
                self.node_task_counts[node_id]["stream"]
            )
            
            # 异步更新数据库
            asyncio.create_task(self._update_node_task_count_in_db(node_id, task_type, 1))
    
    def _decrement_node_task_count(self, node_id: int, task_type: str):
        """
        减少节点任务计数
        
        Args:
            node_id: 节点ID
            task_type: 任务类型
        """
        with self.lock:
            if node_id not in self.node_task_counts:
                return
            
            # 减少特定类型的任务计数，确保不小于0
            if task_type in self.node_task_counts[node_id] and self.node_task_counts[node_id][task_type] > 0:
                self.node_task_counts[node_id][task_type] -= 1
            
            # 更新总计数
            self.node_task_counts[node_id]["total"] = (
                self.node_task_counts[node_id]["image"] +
                self.node_task_counts[node_id]["video"] +
                self.node_task_counts[node_id]["stream"]
            )
            
            # 异步更新数据库
            asyncio.create_task(self._update_node_task_count_in_db(node_id, task_type, -1))
    
    async def _update_node_task_count_in_db(self, node_id: int, task_type: str, delta: int):
        """
        在数据库中更新节点任务计数
        
        Args:
            node_id: 节点ID
            task_type: 任务类型
            delta: 变化值 (+1 或 -1)
        """
        try:
            db = SessionLocal()
            try:
                node = db.query(Node).filter(Node.id == node_id).first()
                if node:
                    # 更新对应类型的任务计数
                    if task_type == "image":
                        node.image_task_count = max(0, (node.image_task_count or 0) + delta)
                    elif task_type == "video":
                        node.video_task_count = max(0, (node.video_task_count or 0) + delta)
                    elif task_type == "stream":
                        node.stream_task_count = max(0, (node.stream_task_count or 0) + delta)
                    
                    node.updated_at = datetime.now()
                    db.commit()
                    
                    # 更新缓存
                    with self.lock:
                        if node_id in self.nodes_cache:
                            if task_type == "image":
                                self.nodes_cache[node_id]["image_task_count"] = node.image_task_count
                            elif task_type == "video":
                                self.nodes_cache[node_id]["video_task_count"] = node.video_task_count
                            elif task_type == "stream":
                                self.nodes_cache[node_id]["stream_task_count"] = node.stream_task_count
                            
                            self.nodes_cache[node_id]["updated_at"] = node.updated_at
            finally:
                db.close()
        except Exception as e:
            logger.error(f"更新节点 {node_id} 的任务计数失败: {str(e)}")
    
    async def _get_running_tasks_on_node(self, node_id: int, db: Session) -> List[Dict[str, Any]]:
        """
        获取节点上运行的任务列表
        
        Args:
            node_id: 节点ID
            db: 数据库会话
            
        Returns:
            List: 任务信息列表
        """
        tasks = []
        
        try:
            # 查询在该节点上运行的子任务
            subtasks = db.query(SubTask).filter(
                SubTask.node_id == node_id,
                SubTask.status == 1  # 运行中状态
            ).all()
            
            for subtask in subtasks:
                # 确定任务类型
                task_type = "stream"  # 默认为流任务
                if subtask.type == 1:
                    task_type = "image"
                elif subtask.type == 2:
                    task_type = "video"
                
                tasks.append({
                    "task_id": subtask.task_id,
                    "subtask_id": subtask.id,
                    "task_type": task_type
                })
            
            logger.info(f"节点 {node_id} 上有 {len(tasks)} 个运行中的任务")
            return tasks
            
        except Exception as e:
            logger.error(f"获取节点 {node_id} 上的运行任务失败: {str(e)}")
            return []
    
    async def _refresh_cache_if_needed(self, db: Session):
        """
        如果需要，刷新节点缓存
        
        Args:
            db: 数据库会话
        """
        current_time = time.time()
        
        # 检查是否需要刷新缓存
        if current_time - self.last_cache_update > self.cache_ttl:
            try:
                # 查询所有活跃节点
                nodes = db.query(Node).filter(Node.is_active == True).all()
                
                with self.lock:
                    # 清空并重建缓存
                    self.nodes_cache = {}
                    
                    for node in nodes:
                        self.nodes_cache[node.id] = {
                            "id": node.id,
                            "service_status": node.service_status,
                            "last_heartbeat": node.last_heartbeat,
                            "image_task_count": node.image_task_count,
                            "video_task_count": node.video_task_count,
                            "stream_task_count": node.stream_task_count,
                            "weight": node.weight,
                            "max_tasks": node.max_tasks,
                            "updated_at": node.updated_at
                        }
                        
                        # 初始化任务计数缓存
                        if node.id not in self.node_task_counts:
                            self.node_task_counts[node.id] = {
                                "image": node.image_task_count or 0,
                                "video": node.video_task_count or 0,
                                "stream": node.stream_task_count or 0,
                                "total": (node.image_task_count or 0) + 
                                         (node.video_task_count or 0) + 
                                         (node.stream_task_count or 0)
                            }
                    
                    # 更新最后刷新时间
                    self.last_cache_update = current_time
                
                logger.debug(f"已刷新节点缓存，共 {len(nodes)} 个节点")
                
            except Exception as e:
                logger.error(f"刷新节点缓存失败: {str(e)}")
    
    @classmethod
    def get_instance(cls) -> 'NodeManager':
        """获取节点管理器单例实例"""
        if not hasattr(cls, '_instance'):
            cls._instance = NodeManager()
        return cls._instance 