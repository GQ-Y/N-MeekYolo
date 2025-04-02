"""节点健康检查服务"""
import asyncio
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
from api_service.crud.node import NodeCRUD
from api_service.models.node import Node
from api_service.core.database import SessionLocal
from shared.utils.logger import setup_logger
import httpx
from api_service.models.database import Task, SubTask
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
                        
                            # 记录任务数量
                            stream_count = len(task.streams)
                            
                            # 删除旧的子任务记录
                            if task.sub_tasks:
                                logger.info(f"删除任务 {task.id} 的 {len(task.sub_tasks)} 个旧子任务记录")
                                for sub_task in task.sub_tasks:
                                    logger.info(f"删除子任务记录: ID={sub_task.id}, 分析任务ID={sub_task.analysis_task_id}")
                                    db.delete(sub_task)
                                    
                                # 提交删除操作
                                db.commit()
                                logger.info(f"子任务记录删除完成")
                            
                            # 更新节点和任务计数
                            task.node_id = best_node.id
                            
                            # 减少旧节点任务数
                            if offline_node.stream_task_count >= stream_count:
                                offline_node.stream_task_count -= stream_count
                            else:
                                offline_node.stream_task_count = 0
                                
                            # 增加新节点任务数
                            best_node.stream_task_count += stream_count
                            
                            # 设置任务为待处理状态，等待下次启动
                            task.status = "pending"
                            task.error_message = "节点离线，已迁移"
                            
                            # 提交更改
                            db.commit()
                            
                            logger.info(f"任务 {task.id} 已成功迁移到节点 {best_node.id}")
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
                joinedload(Task.sub_tasks),
                joinedload(Task.node)
            ).filter(
                Task.status == "pending"
            ).all()
            
            if not pending_tasks:
                logger.info("没有待处理的任务需要启动")
                return
                
            logger.info(f"找到 {len(pending_tasks)} 个待处理任务")
            
            # 导入TaskController
            from api_service.services.task_controller import TaskController
            task_controller = TaskController()
            
            started_count = 0
            for task in pending_tasks:
                try:
                    # 检查任务的节点是否在线
                    if not task.node or task.node.service_status != "online" or not task.node.is_active:
                        logger.warning(f"任务 {task.id} 的节点不在线或不存在，无法启动")
                        continue
                        
                    logger.info(f"开始启动任务 {task.id}，节点ID: {task.node_id}")
                    success = await task_controller.start_task(db, task.id)
                    if success:
                        logger.info(f"任务 {task.id} 启动成功")
                        started_count += 1
                    else:
                        logger.error(f"任务 {task.id} 启动失败")
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
        处理节点恢复在线的情况，重新分配所有运行中的任务
        
        参数:
        - db: 数据库会话
        - recovered_nodes: 在线的节点列表，可以是新恢复的也可以是一直在线的
        """
        try:
            logger.info(f"处理 {len(recovered_nodes)} 个恢复在线的节点...")
            
            # 获取所有运行中的任务，不论节点状态如何
            # 当所有节点都曾经离线过，任务虽然状态是running但实际已经停止
            all_running_tasks = db.query(Task).options(
                joinedload(Task.streams),
                joinedload(Task.models),
                joinedload(Task.sub_tasks),
                joinedload(Task.node)
            ).filter(
                Task.status.in_(["running", "starting"])
            ).all()
            
            logger.info(f"查询到 {len(all_running_tasks)} 个处于运行状态的任务")
            
            # 这里不再只过滤无节点或节点离线的任务
            # 而是将所有任务视为需要重新分配，因为所有节点曾经离线过
            tasks_to_reassign = all_running_tasks
                    
            if not tasks_to_reassign:
                logger.info("没有需要重新分配的任务")
                return
                
            logger.info(f"找到 {len(tasks_to_reassign)} 个需要重新分配的任务")
            
            # 对恢复的节点按负载进行排序
            available_nodes = []
            for node in recovered_nodes:
                if node.service_status == "online" and node.is_active:
                    # 计算当前负载
                    total_tasks = node.image_task_count + node.video_task_count + node.stream_task_count
                    if total_tasks < node.max_tasks:
                        available_nodes.append({
                            "node": node,
                            "free_slots": node.max_tasks - total_tasks
                        })
            
            if not available_nodes:
                logger.warning("没有可用的恢复节点，无法重新分配任务")
                return
            
            logger.info(f"有 {len(available_nodes)} 个可用节点用于任务重新分配")
                
            # 按空闲槽位排序
            available_nodes.sort(key=lambda x: x["free_slots"], reverse=True)
            
            # 导入TaskController
            from api_service.services.task_controller import TaskController
            task_controller = TaskController()
            
            # 重新分配任务
            reassigned_count = 0
            for task in tasks_to_reassign:
                try:
                    # 选择负载最低的节点
                    best_node = available_nodes[0]["node"]
                    
                    logger.info(f"准备将任务 {task.id} 重新分配到恢复节点 {best_node.id}")
                    
                    # 更新任务状态
                    old_node_id = task.node_id
                    old_node = None
                    if old_node_id:
                        old_node = db.query(Node).filter(Node.id == old_node_id).first()
                        
                    # 清理旧子任务
                    if task.sub_tasks:
                        logger.info(f"删除任务 {task.id} 的 {len(task.sub_tasks)} 个旧子任务记录")
                        for sub_task in task.sub_tasks:
                            logger.info(f"删除子任务记录: ID={sub_task.id}, 分析任务ID={sub_task.analysis_task_id}")
                            db.delete(sub_task)
                            
                        # 提交删除操作
                        db.commit()
                        logger.info(f"子任务记录删除完成")
                    
                    # 更新任务节点
                    task.node_id = best_node.id
                    
                    # 更新任务计数
                    stream_count = len(task.streams)
                    
                    # 如果原节点存在且在线，减少其任务计数
                    if old_node:
                        if old_node.stream_task_count >= stream_count:
                            old_node.stream_task_count -= stream_count
                        else:
                            old_node.stream_task_count = 0
                    
                    # 增加新节点任务数
                    best_node.stream_task_count += stream_count
                    
                    # 更新任务状态为待处理
                    task.status = "pending"
                    task.error_message = "节点恢复，重新分配任务"
                    
                    # 更新节点负载信息
                    available_nodes[0]["free_slots"] -= stream_count
                    
                    # 重新排序节点列表
                    available_nodes.sort(key=lambda x: x["free_slots"], reverse=True)
                    
                    # 提交更改
                    db.commit()
                    
                    logger.info(f"任务 {task.id} 成功重新分配到节点 {best_node.id}")
                    reassigned_count += 1
                    
                except Exception as e:
                    logger.error(f"重新分配任务 {task.id} 失败: {str(e)}")
                    import traceback
                    logger.error(traceback.format_exc())
                    db.rollback()
                    
                    # 如果出错，移到下一个节点尝试
                    if len(available_nodes) > 1:
                        available_nodes = available_nodes[1:] + [available_nodes[0]]
            
            logger.info(f"总共重新分配了 {reassigned_count}/{len(tasks_to_reassign)} 个任务")
            
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