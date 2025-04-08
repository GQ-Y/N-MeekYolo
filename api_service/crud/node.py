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
import traceback

from models.database import Node, Task, SubTask, MQTTNode, Stream
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
    async def check_node_health(db: Session, node: Node) -> bool:
        """
        检查单个节点健康状态
        
        参数:
        - db: 数据库会话
        - node: 节点对象
        
        返回:
        - 节点是否健康
        """
        try:
            # 验证数据库连接
            try:
                db.execute("SELECT 1")
                logger.info(f"数据库连接正常，开始检查节点 {node.id} ({node.ip}:{node.port}) 健康状态")
            except Exception as e:
                logger.error(f"数据库连接异常: {str(e)}")
                return False

            node_url = f"http://{node.ip}:{node.port}/health"
            logger.info(f"开始请求节点健康检查接口: {node_url}")
            
            async with httpx.AsyncClient(timeout=5.0) as client:
                try:
                    response = await client.get(node_url)
                    logger.info(f"节点 {node.id} 健康检查接口响应状态码: {response.status_code}")
                    
                    if response.status_code == 200:
                        data = response.json()
                        logger.info(f"节点 {node.id} 健康检查响应数据: {data}")
                        
                        if data.get("success") and data.get("data", {}).get("status") == "healthy":
                            # 更新资源使用情况
                            node_data = data.get("data", {})
                            current_time = datetime.now()
                            
                            try:
                                logger.info(f"开始获取节点 {node.id} 的数据库记录")
                                # 获取最新的节点数据，使用悲观锁
                                db_node = db.query(Node).filter(Node.id == node.id).with_for_update(nowait=True).first()
                                if not db_node:
                                    logger.error(f"节点 {node.id} 在数据库中不存在")
                                    return False
                                
                                logger.info(f"成功获取节点 {node.id} 的数据库记录，当前状态: service_status={db_node.service_status}, cpu_usage={db_node.cpu_usage}, memory_usage={db_node.memory_usage}")
                                
                                # 更新CPU使用率
                                cpu_str = node_data.get("cpu", "0%")
                                old_cpu = db_node.cpu_usage
                                try:
                                    db_node.cpu_usage = float(cpu_str.rstrip("%"))
                                    logger.info(f"节点 {node.id} CPU使用率从 {old_cpu}% 更新为 {db_node.cpu_usage}%")
                                except (ValueError, AttributeError) as e:
                                    logger.warning(f"解析CPU使用率失败: {str(e)}, 设置为0%")
                                    db_node.cpu_usage = 0
                                    
                                # 更新GPU使用率
                                gpu_str = node_data.get("gpu", "N/A")
                                old_gpu = db_node.gpu_usage
                                if gpu_str != "N/A":
                                    try:
                                        db_node.gpu_usage = float(gpu_str.rstrip("%"))
                                        logger.info(f"节点 {node.id} GPU使用率从 {old_gpu}% 更新为 {db_node.gpu_usage}%")
                                    except (ValueError, AttributeError) as e:
                                        logger.warning(f"解析GPU使用率失败: {str(e)}, 设置为0%")
                                        db_node.gpu_usage = 0
                                else:
                                    db_node.gpu_usage = 0
                                    logger.info(f"节点 {node.id} 不支持GPU，使用率设置为0%")
                                    
                                # 更新内存使用率
                                memory_str = node_data.get("memory", "0%")
                                old_memory = db_node.memory_usage
                                try:
                                    db_node.memory_usage = float(memory_str.rstrip("%"))
                                    logger.info(f"节点 {node.id} 内存使用率从 {old_memory}% 更新为 {db_node.memory_usage}%")
                                except (ValueError, AttributeError) as e:
                                    logger.warning(f"解析内存使用率失败: {str(e)}, 设置为0%")
                                    db_node.memory_usage = 0
                                
                                # 更新节点状态和时间戳
                                old_status = db_node.service_status
                                db_node.service_status = "online"
                                db_node.last_heartbeat = current_time
                                db_node.updated_at = current_time
                                
                                logger.info(f"准备提交节点 {node.id} 的更新：status: {old_status}->{db_node.service_status}, CPU: {old_cpu}%->{db_node.cpu_usage}%, Memory: {old_memory}%->{db_node.memory_usage}%")
                                
                                try:
                                    # 提交更改
                                    db.commit()
                                    logger.info(f"成功提交节点 {node.id} 的更新到数据库")
                                    
                                    # 验证更新是否成功
                                    db.refresh(db_node)
                                    logger.info(f"刷新后的节点 {node.id} 数据：CPU={db_node.cpu_usage}%, GPU={db_node.gpu_usage}%, Memory={db_node.memory_usage}%")
                                    
                                    # 更新传入的节点对象
                                    node.cpu_usage = db_node.cpu_usage
                                    node.gpu_usage = db_node.gpu_usage
                                    node.memory_usage = db_node.memory_usage
                                    node.service_status = db_node.service_status
                                    node.last_heartbeat = db_node.last_heartbeat
                                    node.updated_at = db_node.updated_at
                                    
                                    return True
                                    
                                except Exception as e:
                                    logger.error(f"提交节点 {node.id} 更新时发生错误: {str(e)}")
                                    db.rollback()
                                    return False
                                    
                            except Exception as e:
                                logger.error(f"更新节点 {node.id} 数据时发生错误: {str(e)}")
                                db.rollback()
                                return False
                        else:
                            logger.warning(f"节点 {node.id} 响应异常: {data}")
                            return False
                    else:
                        logger.warning(f"节点 {node.id} 响应状态码异常: {response.status_code}")
                        return False
                except Exception as e:
                    logger.error(f"请求节点 {node.id} 健康接口失败: {str(e)}")
                    return False
        except Exception as e:
            logger.error(f"检查节点 {node.id} 健康状态时发生未预期的错误: {str(e)}")
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
        offline_nodes = []
        
        logger.info(f"开始检查 {len(nodes)} 个节点的健康状态")
        
        # 检查每个节点的健康状态
        for node in nodes:
            old_status = node.service_status
            is_healthy = await NodeCRUD.check_node_health(db, node)
            
            # 如果节点不健康，添加到离线节点列表
            if not is_healthy:
                if node.service_status != "offline":
                    node.service_status = "offline"
                    node.updated_at = datetime.now()
                    # 更新离线状态到数据库
                    db.execute(
                        """
                        UPDATE nodes 
                        SET service_status = :service_status,
                            updated_at = :updated_at
                        WHERE id = :node_id
                        """,
                        {
                            "service_status": "offline",
                            "updated_at": datetime.now(),
                            "node_id": node.id
                        }
                    )
                    db.commit()
                    logger.warning(f"节点 {node.id} ({node.ip}:{node.port}) 标记为离线状态")
                offline_nodes.append(node)
        
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
        2. 综合考虑多项指标：
           - CPU使用率
           - 内存使用率
           - GPU使用率（如果有）
           - 任务负载（当前任务/最大任务）
           - 节点权重
        3. 计算综合得分，返回得分最高的节点
        
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
            
        # 计算每个节点的综合得分
        available_nodes = []
        for node in nodes:
            # 计算当前任务总数
            total_tasks = node.image_task_count + node.video_task_count + node.stream_task_count
            
            # 如果节点任务已满，跳过
            if total_tasks >= node.max_tasks:
                continue
            
            # 计算任务负载比例
            task_load_ratio = total_tasks / node.max_tasks if node.max_tasks > 0 else 1.0
            
            # 资源权重配置
            cpu_weight = 0.25  # CPU权重
            memory_weight = 0.15  # 内存权重
            task_weight = 0.40  # 任务负载权重
            node_weight = 0.20  # 节点权重因子
            
            # 计算基础资源得分（值越低越好）
            resource_score = (
                (node.cpu_usage or 0) * cpu_weight + 
                (node.memory_usage or 0) * memory_weight
            )
            
            # 如果是GPU节点，考虑GPU使用率
            if node.compute_type == "gpu" and node.gpu_memory_usage is not None:
                # 为GPU节点调整权重
                gpu_weight = 0.25
                cpu_weight = 0.15
                memory_weight = 0.10
                task_weight = 0.30 
                node_weight = 0.20
                
                # 添加GPU得分
                resource_score += node.gpu_memory_usage * gpu_weight
            
            # 任务负载得分
            task_score = task_load_ratio * task_weight
            
            # 节点权重因子（权重越高分数越低，表示优先级越高）
            weight_factor = 1.0 - (min(1.0, max(0.1, node.weight / 10)) * node_weight)
            
            # 综合得分 (值越低越好)
            final_score = resource_score + task_score + weight_factor
            
            # 剩余可用槽位数
            free_slots = node.max_tasks - total_tasks
            
            available_nodes.append({
                "node": node,
                "score": final_score,
                "total_tasks": total_tasks,
                "free_slots": free_slots,
                "cpu_usage": node.cpu_usage,
                "memory_usage": node.memory_usage,
                "gpu_usage": node.gpu_memory_usage
            })
        
        if not available_nodes:
            return None
            
        # 按得分升序排序（分数越低越好）
        available_nodes.sort(key=lambda x: x["score"])
        
        # 记录选择的节点信息
        best_node = available_nodes[0]["node"]
        best_score = available_nodes[0]["score"]
        logger.info(f"选择节点ID={best_node.id}, IP={best_node.ip}:{best_node.port}, "
                   f"任务={available_nodes[0]['total_tasks']}/{best_node.max_tasks}, "
                   f"CPU={best_node.cpu_usage}%, MEM={best_node.memory_usage}%, "
                   f"GPU={best_node.gpu_memory_usage}%, 得分={best_score:.2f}")
        
        # 返回得分最高的节点
        return best_node