"""
任务管理服务层
处理任务的查询、创建、取消等业务逻辑
"""
import logging # 导入 logging
import datetime # 导入 datetime
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional, Dict, Any
from sqlalchemy import func
import math

# from core.models.user import User, Task, UserNode, Node # 删除错误的合并导入
from core.models.user import User # 从 user.py 导入 User
from core.models.task import Task # 从 task.py 导入 Task
from core.models.node import UserNode # 从 node.py 导入 UserNode

from core.exceptions import GatewayException, NotFoundException, ForbiddenException, InvalidInputException # 导入 InvalidInputException
from core.schemas import PaginationData # 导入分页模型

logger = logging.getLogger(__name__) # 获取 logger

class TaskService:
    def __init__(self, db: Session):
        self.db = db
        logger.debug("TaskService initialized")

    def search_user_tasks(self, user_id: int, status: Optional[int] = None, node_id: Optional[int] = None) -> List[Task]:
        """获取指定用户的任务列表，支持按状态和节点过滤"""
        log_msg = f"搜索用户 {user_id} 的任务" 
        if status is not None:
            log_msg += f", 状态: {status}"
        if node_id is not None:
            log_msg += f", 节点 ID: {node_id}"
        logger.info(log_msg)
        try:
            query = self.db.query(Task).options(joinedload(Task.node)).filter(Task.tenant_id == user_id)
            
            if status is not None:
                query = query.filter(Task.status == status)
            if node_id is not None:
                # 添加节点归属权校验，防止用户查询不属于自己的节点上的任务 (尽管 tenant_id 应该已经限制)
                # node = self.db.query(UserNode).filter(UserNode.id == node_id, UserNode.tenant_id == user_id).first()
                # if not node:
                #    raise ForbiddenException(f"无权访问节点 ID {node_id} 的任务") 
                # 简单过滤即可，因为 Task.tenant_id 已经保证了任务归属
                query = query.filter(Task.node_id == node_id)
                
            tasks = query.order_by(Task.created_at.desc()).all()
            logger.debug(f"找到用户 {user_id} 的 {len(tasks)} 个任务")
            return tasks
        except Exception as e:
            logger.error(f"搜索用户 {user_id} 任务时出错: {e}", exc_info=True)
            raise GatewayException(message=f"搜索任务时发生错误: {e}", code=500)

    def get_task_detail(self, user_id: int, task_id: int) -> Task:
        """获取指定任务的详细信息，确保任务属于该用户"""
        logger.info(f"获取用户 {user_id} 的任务详情 (ID: {task_id})")
        try:
            task = self.db.query(Task).options(joinedload(Task.node)).filter(
                Task.id == task_id,
                Task.tenant_id == user_id
            ).first()
            
            if not task:
                logger.warning(f"用户 {user_id} 尝试获取不存在或不属于他的任务详情 (ID: {task_id})")
                raise NotFoundException(message=f"未找到 ID 为 {task_id} 的任务")
                
            logger.debug(f"成功获取到任务 {task_id} 的详情")
            return task
        except NotFoundException as e:
             raise e
        except Exception as e:
            logger.error(f"获取用户 {user_id} 任务 {task_id} 详情时出错: {e}", exc_info=True)
            raise GatewayException(message=f"获取任务详情时发生错误: {e}", code=500)

    # --- 占位符方法 (待未来实现) ---

    def create_task(self, user_id: int, task_data: dict) -> Task:
        """
        为指定用户创建新任务

        :param user_id: 所属用户的ID
        :param task_data: 包含任务信息的字典 (应符合 TaskCreate schema)
        :return: 创建的 Task 对象
        :raises NotFoundException: 如果关联的节点未找到或不属于该用户
        :raises GatewayException: 如果发生数据库错误
        """
        logger.info(f"尝试为用户 {user_id} 创建新任务")
        node_id = task_data.get('node_id')
        if not node_id:
             # 或者根据 TaskCreate schema 的定义决定是否必须
            raise ValueError("创建任务必须指定 node_id") 
            
        try:
            # 检查关联的节点是否存在且属于该用户
            node = self.db.query(UserNode).filter(UserNode.id == node_id, UserNode.tenant_id == user_id).first()
            if not node:
                logger.warning(f"创建任务失败：用户 {user_id} 未找到节点 {node_id} 或无权限")
                raise NotFoundException(f"未找到节点 {node_id} not found")
            
            # TODO: 检查用户是否有权限在此节点创建任务 (例如基于订阅计划)

            # TODO: 校验 task_data (例如任务类型、参数等)

            # 创建 Task 对象
            # task_data 包含了 name, task_type, params (如果提供)
            new_task = Task(**task_data, tenant_id=user_id)

            # 设置初始状态等
            new_task.status = 0 # 假设 0 是 'pending'

            self.db.add(new_task)
            self.db.commit()
            self.db.refresh(new_task)
            logger.info(f"成功为用户 {user_id} 在节点 {node_id} 上创建任务 (ID: {new_task.id})")
            return new_task
        except NotFoundException as e:
            self.db.rollback()
            logger.warning(f"创建任务失败: {e}")
            raise e
        except ValueError as e: # 捕获 node_id 缺失错误
            self.db.rollback()
            logger.warning(f"创建任务失败: {e}")
            raise e # 或者包装成 BadRequestException
        except Exception as e:
            self.db.rollback()
            logger.error(f"为用户 {user_id} 创建任务时出错: {e}", exc_info=True)
            raise GatewayException("创建任务时发生内部错误", code=500)

    def cancel_task(self, user_id: int, task_id: int) -> Task:
        """取消一个正在进行或排队的任务"""
        logger.info(f"用户 {user_id} 尝试取消任务 {task_id}")
        now = datetime.datetime.utcnow()
        try:
            # --- 1. 获取任务并验证状态 --- 
            task = self.get_task_detail(user_id, task_id) # 复用详情获取及归属权验证
            logger.debug(f"找到任务 {task_id}, 当前状态: {task.status}")
            
            if task.status == 0 or task.status == 1: # 0: pending, 1: running
                # --- 2. 更新状态 --- 
                original_status = task.status
                task.status = 4 # 4: canceled
                if original_status == 1 and not task.end_time:
                     task.end_time = now 
                     logger.debug(f"任务 {task_id} 从 running 状态取消，记录结束时间")
                
                # --- 3. (可选) 触发后续逻辑 --- 
                # e.g., notify_worker_to_stop(task.id)
                # logger.info(f"用户 {user_id} 取消了任务 {task.id}")
                self.db.commit()
                self.db.refresh(task)
                logger.info(f"用户 {user_id} 成功取消任务 {task_id} (原状态: {original_status})")
                return task
            else:
                # 如果任务已完成、失败或已取消，则无法再次取消
                status_map = {2: "已完成", 3: "失败", 4: "已取消"}
                current_status_desc = status_map.get(task.status, f"状态 {task.status}")
                logger.warning(f"用户 {user_id} 尝试取消任务 {task_id} 失败，任务状态为 {current_status_desc}")
                raise InvalidInputException(f"无法取消任务，任务当前状态为: {current_status_desc}")
                
        except (NotFoundException, InvalidInputException, GatewayException) as e:
            logger.warning(f"用户 {user_id} 取消任务 {task_id} 失败: {e}")
            self.db.rollback() # 确保回滚
            raise e
        except Exception as e:
            logger.error(f"用户 {user_id} 取消任务 {task_id} 时发生意外错误: {e}", exc_info=True)
            self.db.rollback()
            # logger.error(f"用户 {user_id} 取消任务 {task_id} 时发生意外错误: {e}", exc_info=True)
            raise GatewayException(message=f"取消任务时发生内部错误", code=500)

    def get_task_output(self, user_id: int, task_id: int) -> Optional[str]:
        """获取任务的输出结果"""
        logger.info(f"用户 {user_id} 尝试获取任务 {task_id} 的输出")
        try:
            task = self.get_task_detail(user_id, task_id) # 验证归属权
            logger.debug(f"成功获取任务 {task_id} 的输出 (长度: {len(task.output) if task.output else 0})")
            return task.output
        except NotFoundException as e:
            logger.warning(f"用户 {user_id} 获取任务 {task_id} 输出失败: {e}")
            raise e # 任务未找到
        except Exception as e:
            logger.error(f"获取用户 {user_id} 任务 {task_id} 输出时出错: {e}", exc_info=True)
            raise GatewayException(message=f"获取任务输出时发生错误", code=500)

    def get_task_logs(self, user_id: int, task_id: int) -> Optional[str]:
        """获取任务的日志"""
        logger.info(f"用户 {user_id} 尝试获取任务 {task_id} 的日志")
        try:
            task = self.get_task_detail(user_id, task_id) # 验证归属权
            logger.debug(f"成功获取任务 {task_id} 的日志 (长度: {len(task.logs) if task.logs else 0})")
            return task.logs
        except NotFoundException as e:
            logger.warning(f"用户 {user_id} 获取任务 {task_id} 日志失败: {e}")
            raise e # 任务未找到
        except Exception as e:
            logger.error(f"获取用户 {user_id} 任务 {task_id} 日志时出错: {e}", exc_info=True)
            raise GatewayException(message=f"获取任务日志时发生错误", code=500)

    def list_user_tasks(self, user_id: int, page: int = 1, size: int = 10, node_id: Optional[int] = None) -> dict:
        """
        获取指定用户的任务列表 (分页)，可按节点过滤

        :param user_id: 用户ID
        :param page: 当前页码 (从 1 开始)
        :param size: 每页显示数量
        :param node_id: (可选) 要过滤的节点ID
        :return: 包含任务列表和分页信息的字典
        :raises GatewayException: 如果发生数据库错误
        """
        log_suffix = f"，页码: {page}，大小: {size}"
        if node_id:
            log_suffix += f"，节点ID: {node_id}"
        logger.info(f"尝试获取用户 {user_id} 的任务列表{log_suffix}")
        
        if page < 1:
            page = 1
        if size < 1:
            size = 10
        elif size > 100:
            size = 100
        skip = (page - 1) * size

        try:
            # 构建基础查询
            query = self.db.query(Task).filter(Task.tenant_id == user_id)

            # 添加节点过滤
            if node_id is not None:
                # 验证用户是否有权访问此节点 (可选，增加安全性)
                node = self.db.query(UserNode.id).filter(UserNode.id == node_id, UserNode.user_id == user_id).first()
                if not node:
                    logger.warning(f"获取任务列表失败：用户 {user_id} 无权访问节点 {node_id}")
                    # 返回空列表而不是抛出异常，因为这只是过滤条件
                    return {"items": [], "pagination": {"total": 0, "page": page, "size": size, "total_pages": 1}}
                query = query.filter(Task.node_id == node_id)

            # 获取总数
            total_tasks = query.with_entities(func.count(Task.id)).scalar()
            logger.debug(f"用户 {user_id} 的任务总数 (过滤后): {total_tasks}")

            # 获取当前页数据 (按创建时间降序排序)
            tasks = query.order_by(Task.created_at.desc()).offset(skip).limit(size).all()
            logger.debug(f"查询到用户 {user_id} 当前页任务数量: {len(tasks)}")

            # 计算总页数
            total_pages = math.ceil(total_tasks / size) if total_tasks > 0 else 1

            pagination_data = {
                "total": total_tasks,
                "page": page,
                "size": size,
                "total_pages": total_pages
            }

            result = {
                "items": tasks,
                "pagination": pagination_data
            }
            logger.info(f"成功获取用户 {user_id} 的任务列表{log_suffix}")
            return result
        except Exception as e:
            logger.error(f"获取用户 {user_id} 任务列表时出错: {e}", exc_info=True)
            raise GatewayException("获取任务列表时发生内部错误", code=500)

    def update_task(self, user_id: int, task_id: int, update_data: dict) -> Task:
        """
        更新指定用户拥有的特定任务的信息 (例如状态或参数)

        :param user_id: 用户ID
        :param task_id: 任务ID
        :param update_data: 包含更新信息的字典 (应符合 TaskUpdate schema)
        :return: 更新后的 Task 对象
        :raises NotFoundException: 如果任务未找到或不属于该用户
        :raises GatewayException: 如果发生数据库错误
        """
        logger.info(f"尝试更新用户 {user_id} 的任务 {task_id}")
        try:
            # 查询任务，确保其存在且属于该用户
            task = self.db.query(Task).filter(Task.id == task_id, Task.tenant_id == user_id).first()
            if not task:
                logger.warning(f"更新任务失败：用户 {user_id} 未找到任务 {task_id} 或无权限")
                raise NotFoundException(f"未找到任务 {task_id}")

            # TODO: 校验 update_data (例如，不允许修改 user_id, node_id, 创建时间)
            update_data.pop('user_id', None)
            update_data.pop('id', None)
            update_data.pop('node_id', None)
            update_data.pop('created_at', None)
            
            # TODO: 检查是否允许更新 (例如，只有特定状态的任务才能被更新)
            # if task.status == 'completed' or task.status == 'failed':
            #     raise PermissionDeniedException("不能更新已完成或失败的任务")

            for key, value in update_data.items():
                if hasattr(task, key):
                    setattr(task, key, value)
                else:
                    logger.warning(f"尝试为任务 {task_id} 更新非法字段: {key}")
            
            self.db.commit()
            self.db.refresh(task)
            logger.info(f"成功更新用户 {user_id} 的任务 {task_id}")
            return task
        except NotFoundException as e:
            self.db.rollback()
            raise e
        # except PermissionDeniedException as e:
        #     self.db.rollback()
        #     logger.warning(f"更新任务 {task_id} 失败: {e}")
        #     raise e
        except Exception as e:
            self.db.rollback()
            logger.error(f"更新任务 {task_id} (用户 {user_id}) 时出错: {e}", exc_info=True)
            raise GatewayException("更新任务信息时发生内部错误", code=500)

    def delete_task(self, user_id: int, task_id: int) -> bool:
        """
        删除指定用户拥有的特定任务

        :param user_id: 用户ID
        :param task_id: 任务ID
        :return: 如果成功删除则返回 True
        :raises NotFoundException: 如果任务未找到或不属于该用户
        :raises PermissionDeniedException: 如果任务状态不允许删除 (例如正在运行)
        :raises GatewayException: 如果发生数据库错误
        """
        logger.info(f"尝试删除用户 {user_id} 的任务 {task_id}")
        try:
            task = self.db.query(Task).filter(Task.id == task_id, Task.tenant_id == user_id).first()
            if not task:
                logger.warning(f"删除任务失败：用户 {user_id} 未找到任务 {task_id} 或无权限")
                raise NotFoundException(f"未找到任务 {task_id}")
            
            # TODO: 检查任务状态是否允许删除 (例如，不允许删除正在运行的任务)
            # if task.status == 'running':
            #     raise PermissionDeniedException("无法删除正在运行的任务")

            self.db.delete(task)
            self.db.commit()
            logger.info(f"成功删除用户 {user_id} 的任务 {task_id}")
            return True
        except NotFoundException as e:
            self.db.rollback()
            raise e
        # except PermissionDeniedException as e:
        #     self.db.rollback()
        #     logger.warning(f"删除任务 {task_id} 失败: {e}")
        #     raise e
        except Exception as e:
            self.db.rollback()
            logger.error(f"删除任务 {task_id} (用户 {user_id}) 时出错: {e}", exc_info=True)
            raise GatewayException("删除任务时发生内部错误", code=500) 