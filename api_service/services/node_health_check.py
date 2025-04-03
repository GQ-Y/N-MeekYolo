"""节点健康检查服务"""
import asyncio
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
from crud.node import NodeCRUD
from models.database import Node
from core.database import SessionLocal
from shared.utils.logger import setup_logger
import httpx
from models.database import Task, SubTask
from sqlalchemy import and_
from sqlalchemy.orm import joinedload
from typing import List

# 配置日志
logger = setup_logger(__name__)

class NodeHealthChecker:
    def __init__(self, check_interval: int = 60):
        """
        初始化节点健康检查器
        :param check_interval: 检查间隔时间（秒），默认10秒
        """
        self.check_interval = check_interval
        self.is_running = False
        self.check_count = 0

    async def start(self):
        """启动健康检查服务"""
        logger.info("节点健康检查服务启动")
        self.is_running = True
        while self.is_running:
            try:
                self.check_count += 1
                logger.info(f"开始第 {self.check_count} 次节点健康检查...")
                start_time = datetime.now()
                
                await self.check_nodes_health()
                
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                logger.info(f"第 {self.check_count} 次节点健康检查完成，耗时: {duration:.2f} 秒")
                
            except Exception as e:
                logger.error(f"节点健康检查失败: {str(e)}")
            
            logger.debug(f"等待 {self.check_interval} 秒后进行下一次检查...")
            await asyncio.sleep(self.check_interval)

    def stop(self):
        """停止健康检查服务"""
        logger.info("节点健康检查服务停止")
        self.is_running = False

    async def check_nodes_health(self):
        """执行节点健康检查"""
        db = SessionLocal()
        try:
            logger.info("==================== 节点健康检查开始 ====================")
            try:
                # 先检查是否有节点表，使用text()函数包装SQL语句
                db.execute(text("SELECT 1 FROM nodes LIMIT 1"))
            except SQLAlchemyError as e:
                logger.error(f"节点表不存在或数据库错误: {str(e)}")
                return

            # 获取当前在线节点数量
            online_count = db.query(Node).filter_by(service_status="online").count()
            logger.info(f"当前在线节点数: {online_count}")

            # 检查节点健康状态
            before_check = datetime.now()
            
            # 获取所有节点
            nodes = db.query(Node).all()
            logger.info(f"数据库中共有 {len(nodes)} 个节点需要检查")
            
            if not nodes:
                logger.warning("数据库中没有节点记录，健康检查结束")
                logger.info("==================== 节点健康检查结束 ====================")
                return
                
            updated_nodes = []
            offline_nodes = []
            recovered_nodes = []  # 新增：记录从离线恢复为在线的节点
            
            # 检查每个节点的健康状态
            for node in nodes:
                try:
                    logger.info(f"------- 开始检查节点 {node.id} ({node.ip}:{node.port}) -------")
                    old_status = node.service_status
                    logger.info(f"节点 {node.id} 原状态: {old_status}")
                    
                    is_healthy = False
                    try:
                        is_healthy = await self._check_node_health(node)
                    except Exception as e:
                        logger.error(f"检查节点 {node.id} 健康状态时发生异常: {str(e)}")
                        import traceback
                        logger.error(traceback.format_exc())
                    
                    logger.info(f"节点 {node.id} 健康检查结果: {'正常' if is_healthy else '异常'}")
                    
                    # 更新节点状态
                    if is_healthy:
                        node.service_status = "online"
                        node.last_heartbeat = datetime.now()
                        if old_status != "online":
                            logger.info(f"节点 {node.id} ({node.ip}:{node.port}) 从 {old_status} 状态恢复为在线状态")
                            updated_nodes.append(node)
                            # 记录节点恢复在线，后续需要处理恢复逻辑
                            recovered_nodes.append(node)
                    else:
                        if node.service_status != "offline":
                            node.service_status = "offline"
                            logger.warning(f"节点 {node.id} ({node.ip}:{node.port}) 标记为离线状态")
                            updated_nodes.append(node)
                            offline_nodes.append(node)
                    
                    logger.info(f"节点 {node.id} 当前状态: {node.service_status}")
                    logger.info(f"------- 节点 {node.id} 检查完成 -------")
                except Exception as e:
                    logger.error(f"检查节点 {node.id} 状态时出错: {str(e)}")
                    import traceback
                    logger.error(traceback.format_exc())
            
            # 提交所有节点状态更改
            try:
                if updated_nodes:
                    logger.info(f"提交 {len(updated_nodes)} 个节点的状态更新到数据库")
                    db.commit()
                    logger.info(f"数据库提交成功")
                else:
                    logger.info("没有节点状态变化，无需提交数据库")
            except Exception as e:
                logger.error(f"提交数据库更新失败: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
            
            # 处理离线节点上的任务
            task_count = 0
            migrated_count = 0
            
            for offline_node in offline_nodes:
                try:
                    logger.info(f"处理离线节点 {offline_node.id} 上的任务")
                    # 查找该节点上的运行中子任务
                    subtasks = db.query(SubTask).options(
                        joinedload(SubTask.task)
                    ).filter(
                        and_(
                            SubTask.node_id == offline_node.id,
                            SubTask.status.in_(["running", "starting"])
                        )
                    ).all()
                    
                    if not subtasks:
                        logger.info(f"节点 {offline_node.id} 没有运行中的子任务需要迁移")
                        continue
                        
                    # 获取涉及的主任务ID列表
                    task_ids = {subtask.task_id for subtask in subtasks}
                    tasks = db.query(Task).options(
                        joinedload(Task.streams),
                        joinedload(Task.models),
                        joinedload(Task.sub_tasks)
                    ).filter(
                        Task.id.in_(task_ids)
                    ).all()
                    
                    task_count = len(tasks)
                    logger.warning(f"节点 {offline_node.id} ({offline_node.ip}:{offline_node.port}) 离线，发现 {task_count} 个任务的 {len(subtasks)} 个子任务需要迁移")
                    
                    # 查找在线的节点
                    available_nodes = db.query(Node).filter(
                        Node.service_status == "online",
                        Node.is_active == True
                    ).all()
                    
                    if not available_nodes:
                        logger.error("没有可用节点，无法迁移任务")
                        continue
                    
                    logger.info(f"找到 {len(available_nodes)} 个可用节点")
                    
                    # 计算负载最低的节点
                    best_node = None
                    min_load = float('inf')
                    
                    for node in available_nodes:
                        total_tasks = node.image_task_count + node.video_task_count + node.stream_task_count
                        if total_tasks < node.max_tasks and total_tasks < min_load:
                            min_load = total_tasks
                            best_node = node
                    
                    if not best_node:
                        logger.error("没有负载合适的可用节点，无法迁移任务")
                        continue
                        
                    logger.info(f"找到可用节点 {best_node.id} ({best_node.ip}:{best_node.port})，开始迁移任务")
                    
                    for task in tasks:
                        try:
                            logger.info(f"开始迁移任务 {task.id}")
                            
                            # 找出该任务下需要迁移的子任务（在离线节点上的子任务）
                            affected_subtasks = [
                                subtask for subtask in task.sub_tasks 
                                if subtask.node_id == offline_node.id and 
                                subtask.status in ["running", "starting"]
                            ]
                            
                            if not affected_subtasks:
                                logger.info(f"任务 {task.id} 没有需要在节点 {offline_node.id} 上迁移的子任务")
                                continue
                            
                            # 记录子任务数量
                            subtask_count = len(affected_subtasks)
                            logger.info(f"任务 {task.id} 有 {subtask_count} 个子任务需要迁移")
                            
                            # 更新子任务的节点信息
                            for subtask in affected_subtasks:
                                # 记录原始信息
                                old_analysis_task_id = subtask.analysis_task_id
                                
                                # 更新子任务节点和状态
                                subtask.node_id = best_node.id
                                subtask.status = "created"  # 重置为待启动状态
                                subtask.error_message = f"从节点 {offline_node.id} 迁移到节点 {best_node.id}"
                                subtask.analysis_task_id = None  # 清除原始分析任务ID
                                
                                logger.info(f"子任务 {subtask.id} 已更新节点: {offline_node.id} -> {best_node.id}")
                            
                            # 减少旧节点任务数
                            if offline_node.stream_task_count >= subtask_count:
                                offline_node.stream_task_count -= subtask_count
                            else:
                                offline_node.stream_task_count = 0
                                
                            # 增加新节点任务数
                            best_node.stream_task_count += subtask_count
                            
                            # 检查主任务状态 - 如果所有子任务都需要迁移，则设置任务为待处理状态
                            if subtask_count == len(task.sub_tasks):
                                task.status = "pending"
                                task.error_message = "所有子任务需要迁移，任务设为待启动状态"
                                logger.info(f"任务 {task.id} 的所有子任务都需要迁移，设置任务状态为pending")
                            else:
                                # 部分子任务迁移，设置为运行中
                                task.status = "running"
                                task.error_message = f"{subtask_count}个子任务迁移到节点{best_node.id}"
                                logger.info(f"任务 {task.id} 部分子任务迁移，保持running状态")
                            
                            # 提交更改
                            db.commit()
                            
                            logger.info(f"任务 {task.id} 的 {subtask_count} 个子任务已成功迁移到节点 {best_node.id}")
                            migrated_count += 1
                        
                        except Exception as e:
                            logger.error(f"迁移任务 {task.id} 失败: {str(e)}")
                            import traceback
                            logger.error(traceback.format_exc())
                            db.rollback()
                except Exception as e:
                    logger.error(f"处理离线节点 {offline_node.id} 上的任务时出错: {str(e)}")
                    import traceback
                    logger.error(traceback.format_exc())
            
            if task_count > 0:
                logger.info(f"总任务迁移情况：{migrated_count}/{task_count} 成功")
            
            # 检查是否有在线节点
            online_nodes = db.query(Node).filter(
                Node.service_status == "online",
                Node.is_active == True
            ).all()
            
            # 处理节点恢复在线的情况，重新分配所有运行中的任务
            if online_nodes:  # 只要有在线节点，就尝试分配任务
                # 检查是否有任务需要分配
                running_tasks = db.query(Task).filter(
                    Task.status.in_(["running", "starting"])
                ).count()
                
                if running_tasks > 0:
                    logger.info(f"系统中有 {running_tasks} 个运行中任务和 {len(online_nodes)} 个在线节点，尝试重新分配任务")
                    await self._handle_node_recovery(db, online_nodes)
                else:
                    logger.info("没有运行中任务需要分配")
            else:
                logger.warning("没有在线节点，无法分配任务")
            
            # 无论是否有任务迁移，都检查并启动待处理的任务
            await self._start_pending_tasks(db)
            
            after_check = datetime.now()

            # 获取更新后的在线节点数量
            new_online_count = db.query(Node).filter_by(service_status="online").count()
            offline_count = online_count - new_online_count if online_count > new_online_count else 0
            online_increase = new_online_count - online_count if new_online_count > online_count else 0

            if offline_count > 0:
                logger.warning(f"发现 {offline_count} 个节点离线")
            if online_increase > 0:
                logger.info(f"发现 {online_increase} 个节点恢复在线")
            if offline_count == 0 and online_increase == 0:
                logger.info("所有节点状态正常")

            duration = (after_check - before_check).total_seconds()
            logger.info(f"健康检查耗时: {duration:.2f} 秒")
            logger.info("==================== 节点健康检查结束 ====================")

        except Exception as e:
            logger.error(f"节点健康检查出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            db.close()
    
    async def _check_node_health(self, node: Node) -> bool:
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
            
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    logger.info(f"开始发送请求到节点 {node.id} 的健康接口...")
                    response = await client.get(node_url)
                    logger.info(f"节点 {node.id} 响应状态码: {response.status_code}")
                    
                    if response.status_code == 200:
                        data = response.json()
                        logger.info(f"节点 {node.id} 健康检查响应: {data}")
                        
                        if data.get("success") and data.get("data", {}).get("status") == "healthy":
                            logger.info(f"节点 {node.id} 健康检查成功，节点状态正常")
                            return True
                        else:
                            logger.warning(f"节点 {node.id} 响应异常: {data}")
                            return False
                    else:
                        logger.warning(f"节点 {node.id} 响应状态码异常: {response.status_code}")
                        return False
            except httpx.ConnectError:
                logger.warning(f"节点 {node.id} 连接失败，服务可能未运行")
                return False
            except httpx.TimeoutException:
                logger.warning(f"节点 {node.id} 请求超时，服务可能响应慢或不可用")
                return False
            except Exception as e:
                logger.error(f"请求节点 {node.id} 健康接口时发生异常: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                return False
        except Exception as e:
            logger.error(f"检查节点 {node.id} 健康状态失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def _start_pending_tasks(self, db: Session):
        """启动处于pending状态的任务"""
        try:
            logger.info("开始处理待启动的任务...")
            # 查找待处理的任务
            pending_tasks = db.query(Task).options(
                joinedload(Task.streams),
                joinedload(Task.models),
                joinedload(Task.sub_tasks)
            ).filter(
                Task.status == "pending"
            ).all()
            
            if not pending_tasks:
                logger.info("没有待处理的任务需要启动")
                return
                
            logger.info(f"找到 {len(pending_tasks)} 个待处理任务")
            
            # 获取可用节点
            available_nodes = db.query(Node).filter(
                Node.service_status == "online",
                Node.is_active == True,
                Node.service_type == 1  # 分析服务
            ).all()
            
            if not available_nodes:
                logger.warning("没有可用的分析服务节点，无法启动任务")
                for task in pending_tasks:
                    task.status = "no_node"
                    task.error_message = "没有可用的分析节点"
                db.commit()
                return
            
            # 导入task_crud
            from crud import task as task_crud
            
            started_count = 0
            for task in pending_tasks:
                try:
                    logger.info(f"开始启动任务 {task.id}")
                    success, message = await task_crud.start_task(db, task.id)
                    if success:
                        logger.info(f"任务 {task.id} 启动成功")
                        started_count += 1
                    else:
                        logger.error(f"任务 {task.id} 启动失败: {message}")
                except Exception as e:
                    logger.error(f"启动任务 {task.id} 时出错: {str(e)}")
                    import traceback
                    logger.error(traceback.format_exc())
            
            logger.info(f"总启动情况：{started_count}/{len(pending_tasks)} 个任务启动成功")
            
        except Exception as e:
            logger.error(f"处理待启动任务时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

    async def _handle_node_recovery(self, db: Session, recovered_nodes: List[Node]):
        """
        处理节点恢复在线的情况，检查出错的子任务并迁移到新节点
        
        参数:
        - db: 数据库会话
        - recovered_nodes: 在线的节点列表，可以是新恢复的也可以是一直在线的
        """
        try:
            logger.info(f"处理 {len(recovered_nodes)} 个恢复在线的节点...")
            
            # 从crud导入task模块
            from crud import task as task_crud
            
            # 查找需要迁移的子任务 - 找出所有状态为error的子任务
            subtasks_to_migrate = db.query(SubTask).join(
                Task, SubTask.task_id == Task.id
            ).filter(
                SubTask.status == "error",
                Task.status.in_(["running", "error"])  # 主任务仍在运行或处于错误状态
            ).all()
            
            # 检查是否有因为节点离线而导致状态不正确的子任务
            # 这些子任务状态为running但节点已离线
            offline_subtasks = db.query(SubTask).join(
                Node, SubTask.node_id == Node.id
            ).filter(
                SubTask.status == "running",
                Node.service_status == "offline"
            ).all()
            
            # 将离线节点的运行中子任务标记为错误状态
            for subtask in offline_subtasks:
                subtask.status = "error"
                subtask.error_message = "节点离线，需要重新分配"
                subtasks_to_migrate.append(subtask)
            
            # 提交更改
            if offline_subtasks:
                db.commit()
                logger.info(f"将 {len(offline_subtasks)} 个离线节点的子任务标记为错误状态")
            
            if not subtasks_to_migrate:
                logger.info("没有需要迁移的子任务")
                return
            
            logger.info(f"找到 {len(subtasks_to_migrate)} 个需要迁移的子任务")
            
            # 对可用节点进行排序
            available_nodes = []
            for node in recovered_nodes:
                # 只选择分析服务节点
                if (node.service_status == "online" and 
                    node.is_active and 
                    node.service_type == 1):  # 1 表示分析服务
                    # 计算当前负载
                    total_tasks = node.image_task_count + node.video_task_count + node.stream_task_count
                    if total_tasks < node.max_tasks:
                        available_nodes.append(node)
            
            if not available_nodes:
                logger.warning("没有可用的分析服务节点，无法迁移子任务")
                return
            
            logger.info(f"有 {len(available_nodes)} 个可用的分析服务节点用于子任务迁移")
            
            # 按任务分组迁移子任务
            tasks_to_update = set()
            migrated_count = 0
            
            # 将子任务按任务ID分组
            subtasks_by_task = {}
            for subtask in subtasks_to_migrate:
                if subtask.task_id not in subtasks_by_task:
                    subtasks_by_task[subtask.task_id] = []
                subtasks_by_task[subtask.task_id].append(subtask)
            
            # 为每个任务调用检查和迁移方法
            for task_id, subtasks in subtasks_by_task.items():
                try:
                    logger.info(f"迁移任务 {task_id} 的 {len(subtasks)} 个子任务")
                    
                    # 准备子任务的流、模型和配置信息
                    for subtask in subtasks:
                        # 重置子任务状态
                        subtask.status = "created"
                        subtask.error_message = None
                        subtask.started_at = None
                        subtask.completed_at = None
                        subtask.analysis_task_id = None
                    
                    # 提交更改
                    db.commit()
                    
                    # 调用start_task重新启动整个任务
                    success, message = await task_crud.start_task(db, task_id)
                    
                    if success:
                        logger.info(f"任务 {task_id} 的子任务成功迁移: {message}")
                        migrated_count += 1
                    else:
                        logger.error(f"任务 {task_id} 的子任务迁移失败: {message}")
                
                except Exception as e:
                    logger.error(f"迁移任务 {task_id} 的子任务时出错: {str(e)}")
                    import traceback
                    logger.error(traceback.format_exc())
                    db.rollback()
            
            logger.info(f"总共迁移了 {migrated_count}/{len(subtasks_by_task)} 个任务的子任务")
            
        except Exception as e:
            logger.error(f"处理节点恢复时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

# 创建健康检查器实例
health_checker = NodeHealthChecker()

# 启动健康检查服务的协程函数
async def start_health_checker():
    """启动节点健康检查服务"""
    await health_checker.start()

# 停止健康检查服务的函数
def stop_health_checker():
    """停止节点健康检查服务"""
    health_checker.stop() 