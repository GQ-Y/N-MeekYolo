"""
节点CRUD操作
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union
import logging
import httpx
import asyncio
from sqlalchemy import and_
from sqlalchemy.orm import Session, joinedload

from models.database import Node, Task, SubTask
from models.responses import NodeCreate, NodeUpdate
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

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
            max_tasks=node.max_tasks,
            node_type=node.node_type,
            service_type=node.service_type,
            compute_type=node.compute_type,
            memory_usage=0,
            gpu_memory_usage=0
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
    def get_node_by_service_type(db: Session, service_type: int) -> Optional[Node]:
        """通过服务类型获取节点"""
        return db.query(Node).filter(Node.service_type == service_type).first()

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
        if node_update.node_type is not None:
            db_node.node_type = node_update.node_type
        if node_update.service_type is not None:
            db_node.service_type = node_update.service_type
        if node_update.compute_type is not None:
            db_node.compute_type = node_update.compute_type
        if node_update.memory_usage is not None:
            db_node.memory_usage = node_update.memory_usage
        if node_update.gpu_memory_usage is not None:
            db_node.gpu_memory_usage = node_update.gpu_memory_usage
            
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
    async def check_node_health(node: Node) -> bool:
        """
        检查单个节点健康状态
        
        参数:
        - node: 节点对象
        
        返回:
        - 节点是否健康
        """
        try:
            node_url = f"http://{node.ip}:{node.port}/health"
            logger.info(f"正在检查节点 {node.id} ({node.ip}:{node.port}) 健康状态: {node_url}")
            
            async with httpx.AsyncClient(timeout=5.0) as client:
                try:
                    response = await client.get(node_url)
                    if response.status_code == 200:
                        data = response.json()
                        logger.info(f"节点 {node.id} 健康检查响应: {data}")
                        if data.get("success") and data.get("data", {}).get("status") == "healthy":
                            # 更新资源使用情况
                            if "memory_usage" in data.get("data", {}):
                                node.memory_usage = data["data"]["memory_usage"]
                            if "gpu_memory_usage" in data.get("data", {}):
                                node.gpu_memory_usage = data["data"]["gpu_memory_usage"]
                            logger.info(f"节点 {node.id} 健康检查成功，节点状态正常")
                            return True
                        else:
                            logger.warning(f"节点 {node.id} 响应异常: {data}")
                            return False
                    else:
                        logger.warning(f"节点 {node.id} 响应状态码: {response.status_code}")
                        return False
                except Exception as e:
                    logger.error(f"请求节点 {node.id} 健康接口失败: {str(e)}")
                    return False
        except Exception as e:
            logger.error(f"检查节点 {node.id} 健康状态失败: {str(e)}")
            return False

    @staticmethod
    async def check_nodes_health(db: Session, timeout_minutes: int = 5) -> None:
        """
        检查节点健康状态，并处理故障节点的任务迁移
        
        参数:
        - db: 数据库会话
        - timeout_minutes: 超时时间（分钟）
        """
        # 获取所有节点
        nodes = db.query(Node).all()
        updated_nodes = []
        
        logger.info(f"开始检查 {len(nodes)} 个节点的健康状态")
        offline_nodes = []
        
        # 检查每个节点的健康状态
        for node in nodes:
            old_status = node.service_status
            is_healthy = await NodeCRUD.check_node_health(node)
            
            # 更新节点状态
            if is_healthy:
                node.service_status = "online"
                node.last_heartbeat = datetime.now()
                if old_status != "online":
                    logger.info(f"节点 {node.id} ({node.ip}:{node.port}) 从 {old_status} 状态恢复为在线状态")
                    updated_nodes.append(node)
            else:
                if node.service_status != "offline":
                    node.service_status = "offline"
                    logger.warning(f"节点 {node.id} ({node.ip}:{node.port}) 标记为离线状态")
                    updated_nodes.append(node)
                    offline_nodes.append(node)
        
        # 提交所有节点状态更改
        if updated_nodes:
            db.commit()
            logger.info(f"健康检查更新了 {len(updated_nodes)} 个节点状态")
        
        # 处理离线节点上的任务
        task_count = 0
        migrated_count = 0
        
        for offline_node in offline_nodes:
            # 查找该节点上的运行中任务
            tasks = db.query(Task).options(
                joinedload(Task.streams),
                joinedload(Task.models),
                joinedload(Task.sub_tasks)
            ).filter(
                and_(
                    Task.node_id == offline_node.id,
                    Task.status.in_(["running", "starting"])
                )
            ).all()
            
            if not tasks:
                logger.info(f"节点 {offline_node.id} 没有运行中的任务需要迁移")
                continue
                
            task_count += len(tasks)
            logger.warning(f"节点 {offline_node.id} ({offline_node.ip}:{offline_node.port}) 离线，发现 {len(tasks)} 个需要迁移的任务")
            
            # 查找在线的节点
            available_node = NodeCRUD.get_available_node(db)
            if not available_node:
                logger.error("没有可用节点，无法迁移任务")
                continue
                
            logger.info(f"找到可用节点 {available_node.id} ({available_node.ip}:{available_node.port})，开始迁移任务")
            
            for task in tasks:
                logger.info(f"开始迁移任务 {task.id}")
                
                # 检查任务必要的关联是否存在
                if not task.streams or not task.models:
                    logger.warning(f"任务 {task.id} 缺少必要的关联(流或模型)，跳过")
                    continue
                
                # 获取当前任务的子任务
                sub_tasks = task.sub_tasks
                
                # 统计流任务数量
                stream_count = len(task.streams)
                
                try:
                    # 停止当前所有子任务并删除
                    old_sub_tasks_to_delete = []
                    for sub_task in sub_tasks:
                        if sub_task.status == "running":
                            # 停止子任务的分析任务
                            try:
                                await NodeCRUD._stop_analysis_task(offline_node, sub_task.analysis_task_id)
                            except Exception as e:
                                logger.error(f"停止子任务 {sub_task.id} 分析任务失败: {str(e)}")
                            
                            old_sub_tasks_to_delete.append(sub_task)
                    
                    # 删除旧的子任务
                    for old_sub_task in old_sub_tasks_to_delete:
                        db.delete(old_sub_task)
                    
                    if old_sub_tasks_to_delete:
                        logger.info(f"已删除任务 {task.id} 的 {len(old_sub_tasks_to_delete)} 个子任务")
                    
                    # 更新任务节点
                    task.node_id = available_node.id
                    
                    # 减少旧节点的任务计数
                    if offline_node.stream_task_count >= stream_count:
                        offline_node.stream_task_count -= stream_count
                    else:
                        offline_node.stream_task_count = 0
                    
                    # 增加新节点的任务计数
                    available_node.stream_task_count += stream_count
                    
                    # 重启任务
                    if await NodeCRUD._restart_task(available_node, task):
                        migrated_count += 1
                        logger.info(f"任务 {task.id} 迁移成功")
                    else:
                        logger.error(f"任务 {task.id} 迁移失败")
                        
                except Exception as e:
                    logger.error(f"迁移任务 {task.id} 失败: {str(e)}")
                    continue
            
            # 提交更改
            db.commit()
            
        if task_count > 0:
            logger.info(f"共发现 {task_count} 个需要迁移的任务，成功迁移 {migrated_count} 个")
        else:
            logger.info("没有需要迁移的任务")

    @staticmethod
    async def _stop_analysis_task(node: Node, analysis_task_id: str) -> bool:
        """停止分析任务"""
        try:
            node_url = f"http://{node.ip}:{node.port}/api/v1/analyze/stream/{analysis_task_id}/stop"
            logger.info(f"尝试停止节点 {node.id} 上的分析任务 {analysis_task_id}")
            
            async with httpx.AsyncClient(timeout=5.0) as client:
                try:
                    response = await client.post(node_url)
                    if response.status_code == 200:
                        logger.info(f"成功停止分析任务 {analysis_task_id}")
                        return True
                    else:
                        logger.warning(f"停止分析任务失败，状态码: {response.status_code}")
                        return False
                except Exception as e:
                    logger.error(f"请求停止分析任务失败: {str(e)}")
                    return False
        except Exception as e:
            logger.error(f"停止分析任务 {analysis_task_id} 出错: {str(e)}")
            return False

    @staticmethod
    async def _restart_task(node: Node, task: Task) -> bool:
        """在新节点上重启任务"""
        try:
            node_url = f"http://{node.ip}:{node.port}"
            logger.info(f"在节点 {node.id} ({node.ip}:{node.port}) 上重启任务 {task.id}")
            
            # 获取回调URL列表
            callback_urls = []
            if task.enable_callback and task.callbacks:
                callback_urls = [callback.url for callback in task.callbacks]
            
            # 获取任务配置
            config = task.config or {}
            
            # 创建新的子任务列表
            new_sub_tasks = []
            
            for stream in task.streams:
                for model in task.models:
                    try:
                        # 构建任务名称
                        task_name = f"{task.name}-{stream.name}-{model.name}"
                        
                        # 调用节点分析API创建任务
                        async with httpx.AsyncClient() as client:
                            response = await client.post(
                                f"{node_url}/api/v1/analyze/stream",
                                json={
                                    "model_code": model.code,
                                    "stream_url": stream.url,
                                    "task_name": task_name,
                                    "callback_urls": callback_urls,
                                    "enable_callback": task.enable_callback and bool(callback_urls),
                                    "save_result": task.save_result,
                                    "config": config,
                                    "analysis_type": "detection"
                                }
                            )
                            response.raise_for_status()
                            data = response.json()
                            analysis_task_id = data.get("data", {}).get("task_id")
                            
                            logger.info(f"在节点 {node.id} 上成功创建分析任务: {analysis_task_id}")
                            
                            # 创建子任务记录
                            sub_task = SubTask(
                                task_id=task.id,
                                analysis_task_id=analysis_task_id,
                                stream_id=stream.id,
                                model_id=model.id,
                                status="running",
                                started_at=datetime.now()
                            )
                            new_sub_tasks.append(sub_task)
                            
                    except Exception as e:
                        logger.error(f"创建子任务失败: {str(e)}")
            
            if not new_sub_tasks:
                logger.error(f"任务 {task.id} 没有创建任何子任务")
                return False
            
            # 批量添加子任务
            task.status = "running"
            task.started_at = datetime.now()
            for stream in task.streams:
                stream.status = 1  # 在线状态
            
            db_session = Session.object_session(task)
            db_session.bulk_save_objects(new_sub_tasks)
            db_session.commit()
            
            logger.info(f"任务 {task.id} 启动成功，创建了 {len(new_sub_tasks)} 个子任务")
            return True
            
        except Exception as e:
            logger.error(f"重启任务 {task.id} 失败: {str(e)}")
            return False

    @staticmethod
    def get_available_node(db: Session) -> Optional[Node]:
        """
        获取可用节点（用于负载均衡）
        
        算法：
        1. 过滤出在线的分析服务节点
        2. 计算每个节点的负载百分比（当前任务数/最大任务数）
        3. 按权重和负载百分比排序，返回负载最低且权重最高的节点
        
        参数:
        - db: 数据库会话
        
        返回:
        - 最佳可用节点，如无可用节点则返回None
        """
        # 获取所有在线的分析服务节点
        nodes = (
            db.query(Node)
            .filter(Node.service_status == "online")
            .filter(Node.is_active == True)
            .filter(Node.service_type == 1)  # 只选择分析服务节点
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