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
from sqlalchemy import and_, or_
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
                    # 查找该节点上的所有子任务
                    subtasks = db.query(SubTask).options(
                        joinedload(SubTask.task)
                    ).filter(
                        SubTask.node_id == offline_node.id
                    ).all()
                    
                    if not subtasks:
                        logger.info(f"节点 {offline_node.id} 没有子任务需要迁移")
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
                    
                    # 更新所有子任务为未启动状态，但不处理用户手动停止的任务的子任务
                    for subtask in subtasks:
                        # 检查主任务状态，跳过用户手动停止的任务的子任务
                        task = db.query(Task).filter(Task.id == subtask.task_id).first()
                        if task and task.status == 2 and task.error_message == "任务由用户手动停止":
                            logger.info(f"子任务 {subtask.id} 属于用户手动停止的任务 {task.id}，不进行处理")
                            continue
                        
                        # 检查子任务是否是运行中状态(1)
                        if subtask.status == 1:
                            # 记录原始信息
                            old_analysis_task_id = subtask.analysis_task_id
                            old_status = subtask.status
                            
                            # 更新子任务状态 - 改为未启动(0)
                            subtask.status = 0  # 设为未启动状态(0)
                            subtask.error_message = f"节点 {offline_node.id} 离线，任务需要重新分配"
                            subtask.analysis_task_id = None  # 清除原始分析任务ID
                            
                            logger.info(f"子任务 {subtask.id} 状态从 {old_status} 改为未启动，待重新分配")
                    
                    # 减少离线节点任务计数
                    if offline_node.stream_task_count > 0:
                        offline_node.stream_task_count = 0
                    
                    # 提交更改
                    db.commit()
                    
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
            
            # 处理任务分配
            if online_nodes:  # 只要有在线节点，就尝试分配所有未启动的子任务
                logger.info(f"系统中有 {len(online_nodes)} 个在线节点，尝试分配所有未启动状态的子任务")
                await self._handle_node_recovery(db, online_nodes)
            else:
                logger.warning("没有在线节点，无法分配任务")
            
            # 如果有待处理的任务，尝试启动
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
        检查单个节点健康状态，并更新节点资源使用信息
        
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
                        
                        # 处理新的标准响应格式
                        node_data = data.get("data", {}) if isinstance(data, dict) else {}
                        
                        # 检查是否为新的标准格式响应
                        if data.get("success") and node_data.get("status") == "healthy":
                            # 更新节点资源使用情况
                            self._update_node_resources(node, node_data)
                            logger.info(f"节点 {node.id} 健康检查成功，节点状态正常")
                            return True
                        
                        # 兼容旧格式
                        elif data.get("status") == "ok" or (isinstance(node_data, dict) and node_data.get("status") == "healthy"):
                            logger.info(f"节点 {node.id} 健康检查成功，节点状态正常(旧格式)")
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

    def _update_node_resources(self, node: Node, node_data: dict):
        """
        更新节点资源使用信息
        
        参数:
        - node: 节点对象
        - node_data: 节点响应数据
        """
        try:
            # 提取CPU使用率
            cpu_usage = node_data.get("cpu", "")
            if cpu_usage:
                try:
                    # 尝试从百分比字符串(如"45.2%")中提取数值
                    cpu_value = float(cpu_usage.rstrip("%"))
                    node.cpu_usage = cpu_value
                    logger.info(f"更新节点 {node.id} CPU使用率: {cpu_value}%")
                except (ValueError, AttributeError):
                    logger.warning(f"无法解析CPU使用率数据: {cpu_usage}")
            
            # 提取GPU使用率
            gpu_usage = node_data.get("gpu", "")
            if gpu_usage and gpu_usage != "N/A":
                try:
                    # 尝试从百分比字符串中提取数值
                    gpu_value = float(gpu_usage.rstrip("%"))
                    node.gpu_usage = gpu_value
                    logger.info(f"更新节点 {node.id} GPU使用率: {gpu_value}%")
                except (ValueError, AttributeError):
                    logger.warning(f"无法解析GPU使用率数据: {gpu_usage}")
            
            # 提取内存使用率
            memory_usage = node_data.get("memory", "")
            if memory_usage:
                try:
                    # 尝试从百分比字符串中提取数值
                    memory_value = float(memory_usage.rstrip("%"))
                    node.memory_usage = memory_value
                    logger.info(f"更新节点 {node.id} 内存使用率: {memory_value}%")
                except (ValueError, AttributeError):
                    logger.warning(f"无法解析内存使用率数据: {memory_usage}")
                    
        except Exception as e:
            logger.error(f"更新节点 {node.id} 资源使用信息时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

    async def _start_pending_tasks(self, db: Session):
        """启动处于未启动状态的任务"""
        try:
            logger.info("开始处理待启动的任务...")
            
            # 先查询所有任务状态，用于诊断
            task_status_counts = db.execute(text("""
                SELECT status, COUNT(*) as count 
                FROM tasks 
                GROUP BY status
            """)).fetchall()
            
            logger.info(f"当前任务状态分布: {', '.join([f'{status}: {count}' for status, count in task_status_counts])}")
            
            # 查找运行中(状态1)的主任务中有未启动(状态0)的子任务
            running_tasks_with_not_started_subtasks = db.query(Task).join(
                SubTask, Task.id == SubTask.task_id
            ).filter(
                Task.status == 1,  # 主任务状态为运行中(1)
                SubTask.status == 0,  # 子任务状态为未启动(0)
                Task.error_message != "任务由用户手动停止"  # 明确排除用户手动停止的任务
            ).options(
                joinedload(Task.streams),
                joinedload(Task.models),
                joinedload(Task.sub_tasks)
            ).distinct().all()
            
            if not running_tasks_with_not_started_subtasks:
                logger.info("没有待启动的任务")
                return
            
            logger.info(f"找到 {len(running_tasks_with_not_started_subtasks)} 个运行中但有未启动子任务的任务，任务ID: {[task.id for task in running_tasks_with_not_started_subtasks]}")
            
            # 获取可用节点
            available_nodes = db.query(Node).filter(
                Node.service_status == "online",
                Node.is_active == True,
                Node.service_type == 1  # 分析服务
            ).all()
            
            if not available_nodes:
                logger.warning("没有可用的分析服务节点，无法启动任务")
                return
            
            logger.info(f"可用节点: {[f'{node.id}({node.ip}:{node.port})' for node in available_nodes]}")
            
            # 导入task_crud
            from crud import task as task_crud
            
            started_count = 0
            for task in running_tasks_with_not_started_subtasks:
                try:
                    # 打印任务详情
                    logger.info(f"任务 {task.id} 信息: 状态={task.status}, 子任务数={len(task.sub_tasks)}, 错误消息={task.error_message}")
                    
                    # 打印子任务状态
                    subtask_status = {}
                    for subtask in task.sub_tasks:
                        status = subtask.status
                        if status not in subtask_status:
                            subtask_status[status] = 0
                        subtask_status[status] += 1
                    
                    logger.info(f"任务 {task.id} 的子任务状态分布: {subtask_status}")
                    
                    # 只有主任务为运行中状态(1)时才启动子任务
                    if task.status == 1:
                        logger.info(f"开始启动任务 {task.id}")
                        success, message = await task_crud.start_task(db, task.id)
                        if success:
                            logger.info(f"任务 {task.id} 启动成功: {message}")
                            started_count += 1
                        else:
                            logger.error(f"任务 {task.id} 启动失败: {message}")
                    else:
                        logger.info(f"任务 {task.id} 状态为 {task.status}，不是运行中状态，跳过启动")
                except Exception as e:
                    logger.error(f"启动任务 {task.id} 时出错: {str(e)}")
                    import traceback
                    logger.error(traceback.format_exc())
            
            logger.info(f"总启动情况：{started_count}/{len(running_tasks_with_not_started_subtasks)} 个任务启动成功")
            
        except Exception as e:
            logger.error(f"处理待启动任务时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

    async def _handle_node_recovery(self, db: Session, recovered_nodes: List[Node]):
        """
        处理节点恢复在线的情况，重新分配子任务
        
        参数:
        - db: 数据库会话
        - recovered_nodes: 可用的节点列表
        """
        try:
            logger.info(f"处理任务分配，当前有 {len(recovered_nodes)} 个可用节点...")
            
            # 从crud导入task模块
            from crud import task as task_crud
            
            # 查找所有需要处理的未启动状态子任务
            # 1. 连接Task表，只处理非用户手动停止的任务
            # 2. 过滤掉Task.status=2且错误消息='任务由用户手动停止'的子任务
            subtasks_to_handle = db.query(SubTask).join(
                Task, SubTask.task_id == Task.id
            ).filter(
                SubTask.status == 0,  # 子任务状态为未启动(0)
                or_(
                    Task.status != 2,  # 主任务非停止状态
                    # 如果主任务是停止状态，确保不是用户手动停止的
                    and_(
                        Task.status == 2,  # 主任务为已停止(2)
                        Task.error_message != "任务由用户手动停止"  # 排除用户手动停止的任务
                    )
                )
            ).all()
            
            if not subtasks_to_handle:
                logger.info("没有未启动状态的子任务需要处理")
                return
            
            logger.info(f"找到 {len(subtasks_to_handle)} 个未启动状态的子任务")
            
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
                logger.warning("没有可用的分析服务节点，无法处理未启动的子任务")
                return
            
            logger.info(f"有 {len(available_nodes)} 个可用的分析服务节点用于任务分配")
            
            # 按任务分组处理子任务
            subtasks_by_task = {}
            for subtask in subtasks_to_handle:
                if subtask.task_id not in subtasks_by_task:
                    subtasks_by_task[subtask.task_id] = []
                subtasks_by_task[subtask.task_id].append(subtask)
            
            # 为每个任务调用start_task方法
            task_started_count = 0
            for task_id, subtasks in subtasks_by_task.items():
                try:
                    # 再次检查任务状态，确保不处理用户手动停止的任务
                    task = db.query(Task).filter(Task.id == task_id).first()
                    if not task:
                        logger.error(f"找不到任务 {task_id}，跳过")
                        continue
                    
                    # 如果是用户手动停止的任务，跳过处理
                    if task.status == 2 and task.error_message == "任务由用户手动停止":
                        logger.info(f"任务 {task_id} 是用户手动停止的，跳过处理")
                        continue
                    
                    logger.info(f"准备启动任务 {task_id}，包含 {len(subtasks)} 个未启动的子任务")
                    
                    # 只有当运行中状态(1)的主任务才尝试启动子任务
                    if task.status == 1:
                        # 直接启动任务
                        success, message = await task_crud.start_task(db, task_id)
                        if success:
                            logger.info(f"任务 {task_id} 启动成功: {message}")
                            task_started_count += 1
                        else:
                            logger.error(f"任务 {task_id} 启动失败: {message}")
                    else:
                        logger.info(f"任务 {task_id} 状态为 {task.status}，不是运行中状态，跳过启动")
                
                except Exception as e:
                    logger.error(f"处理任务 {task_id} 时发生错误: {str(e)}")
                    import traceback
                    logger.error(traceback.format_exc())
            
            logger.info(f"总计处理了 {len(subtasks_by_task)} 个任务，成功启动了 {task_started_count} 个")
            
        except Exception as e:
            logger.error(f"处理未启动子任务时出错: {str(e)}")
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