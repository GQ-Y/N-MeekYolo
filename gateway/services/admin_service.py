"""
后台管理服务层
处理用户管理、系统配置等后台操作逻辑
"""
import logging
from sqlalchemy.orm import Session
from sqlalchemy import func # 导入 func 用于 count
import math # 导入 math 用于向上取整计算总页数
import asyncio
from typing import Dict, Optional, List, Tuple
from sqlalchemy import or_
from core.models.user import User # 正确导入 User
from core.models.node import UserNode # 修正：从 core.models.node 导入 UserNode
from core.models.task import Task # 添加导入
from core.exceptions import GatewayException, NotFoundException # 导入 GatewayException 和 NotFoundException
from datetime import datetime

# 导入 SystemLog 模型 和 Pydantic 响应模型
from core.models.log import SystemLog 
from core.schemas import SystemLogResponse, SystemLogListResponse, PaginationData 

logger = logging.getLogger(__name__)

class AdminService:
    def __init__(self, db: Session):
        self.db = db
        logger.debug("AdminService initialized")

    # --- 获取系统概览信息 --- 
    def get_system_overview(self) -> dict:
        """获取系统运行状态和关键指标概览信息，从数据库查询。"""
        logger.info("开始从数据库获取系统概览信息")
        try:
            # 查询用户总数
            user_count = self.db.query(func.count(User.id)).scalar()
            logger.debug(f"查询到用户总数: {user_count}")
            
            # 修正：使用 UserNode 进行查询
            node_count = self.db.query(func.count(UserNode.id)).scalar()
            logger.debug(f"查询到节点总数: {node_count}")

            # 查询活动任务数 (假设 Task 模型的活动状态字段不同，需要修改这里的 filter 条件
            active_task_count = self.db.query(func.count(Task.id)).filter(Task.status == 1).scalar()
            logger.debug(f"查询到活动任务数: {active_task_count}")
            
            overview = {
                "total_users": user_count,
                "total_nodes": node_count,
                "active_tasks": active_task_count,
                "status": "Operational" # 保持状态为 Operational，除非检测到严重问题
            }
            logger.info(f"成功获取系统概览信息: {overview}")
            return overview
        except Exception as e:
            logger.error(f"获取系统概览信息时发生数据库错误: {e}", exc_info=True)
            # 抛出 GatewayException，让上层路由处理具体的 HTTP 响应
            raise GatewayException("获取系统概览信息失败", code=500)

    # --- 新增：查询系统日志 --- 
    def list_system_logs(
        self,
        page: int = 1,
        size: int = 10,
        level: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        user_id: Optional[int] = None # 新增 user_id 过滤
    ) -> dict: # 返回包含 items 和 pagination 的字典
        """查询系统日志记录 (分页、过滤)"""
        logger.info(f"查询系统日志，页码: {page}, 大小: {size}, 级别: {level}, 开始日期: {start_date}, 结束日期: {end_date}, 用户ID: {user_id}")
        if page < 1: page = 1
        if size < 1: size = 10
        elif size > 100: size = 100
        skip = (page - 1) * size

        try:
            query = self.db.query(SystemLog)

            # 添加过滤条件
            if level:
                level_int = SystemLog.get_level_int(level) # 使用模型方法转换级别名称为整数
                query = query.filter(SystemLog.level == level_int)
            if start_date:
                query = query.filter(SystemLog.timestamp >= start_date)
            if end_date:
                # 注意：为了包含 end_date 当天的日志，可能需要调整为小于 end_date + 1 day
                # 这里暂时使用 <=，意味着包含 end_date 的 00:00:00 时刻
                query = query.filter(SystemLog.timestamp <= end_date)
            if user_id is not None:
                query = query.filter(SystemLog.user_id == user_id)

            # 获取总数
            total_logs = query.with_entities(func.count(SystemLog.id)).scalar()
            logger.debug(f"系统日志总数 (过滤后): {total_logs}")

            # 获取当前页数据 (按时间戳降序)
            logs = query.order_by(SystemLog.timestamp.desc()).offset(skip).limit(size).all()
            logger.debug(f"查询到当前页日志数量: {len(logs)}")

            # 准备 Pydantic 响应模型列表
            # 手动映射 level (整数) 到 level_name (字符串)
            log_items = []
            for log_entry in logs:
                log_dict = log_entry.__dict__ # 获取 ORM 对象的字典表示
                log_dict['level'] = log_entry.level_name # 使用 level_name 替换 level
                log_items.append(SystemLogResponse.model_validate(log_dict))

            # 计算总页数
            total_pages = math.ceil(total_logs / size) if total_logs > 0 else 1

            pagination_data = PaginationData(
                total=total_logs,
                page=page,
                size=size,
                total_pages=total_pages
            )

            result = {
                "items": log_items, # 返回 Pydantic 模型列表
                "pagination": pagination_data
            }
            logger.info("成功获取系统日志列表")
            return result
        except Exception as e:
            logger.error(f"查询系统日志时出错: {e}", exc_info=True)
            raise GatewayException("查询系统日志时发生内部错误", code=500)

    # --- 用户管理 --- 
    def list_users(self, page: int = 1, size: int = 10, username: Optional[str] = None) -> dict:
        """获取用户列表 (分页)

        :param page: 当前页码 (从 1 开始)
        :param size: 每页显示数量
        :param username: 用户名过滤条件
        :return: 包含用户列表和分页信息的字典
        :raises GatewayException: 如果发生数据库错误
        """
        logger.info(f"尝试获取用户列表，页码: {page}，大小: {size}")
        
        if page < 1:
            page = 1
        if size < 1:
            size = 10 # 默认或最小尺寸
        elif size > 100: # 防止一次请求过多数据
            size = 100

        skip = (page - 1) * size

        try:
            # 1. 获取总用户数
            total_users = self.db.query(func.count(User.id)).scalar()
            logger.debug(f"查询到总用户数: {total_users}")

            # 2. 获取当前页的用户数据
            # 按 ID 排序以保证分页一致性
            users_query = self.db.query(User).order_by(User.id.asc())
            if username:
                users_query = users_query.filter(User.username.like(f"%{username}%"))
            users = users_query.offset(skip).limit(size).all()
            logger.debug(f"查询到当前页用户数量: {len(users)}")

            # 3. 计算总页数
            total_pages = math.ceil(total_users / size) if total_users > 0 else 1

            # 4. 构建分页信息
            pagination_data = {
                "total": total_users,
                "page": page,
                "size": size,
                "total_pages": total_pages
            }
            
            # 5. 构建最终结果
            # 注意：这里返回的是 ORM 模型列表，路由层需要将其转换为 UserResponse 列表
            result = {
                "items": users,
                "pagination": pagination_data
            }
            
            logger.info(f"成功获取用户列表 (页码: {page}, 大小: {size})")
            return result

        except Exception as e:
            logger.error(f"获取用户列表时发生数据库错误 (页码: {page}, 大小: {size}): {e}", exc_info=True)
            raise GatewayException("获取用户列表失败", code=500)

    # --- 添加 get_user_details 方法 ---
    def get_user_details(self, user_id: int) -> User:
        """获取指定用户的详细信息

        :param user_id: 要查询的用户ID
        :return: 用户 ORM 对象
        :raises NotFoundException: 如果用户未找到
        :raises GatewayException: 如果发生数据库错误
        """
        logger.info(f"尝试获取用户ID为 {user_id} 的详细信息")
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.warning(f"获取用户详情失败：未找到用户ID {user_id}")
                raise NotFoundException(f"未找到用户ID为 {user_id} 的用户")
            
            logger.info(f"成功获取用户ID {user_id} 的详细信息")
            return user
        except NotFoundException as e:
            raise e # 直接向上抛出
        except Exception as e:
            logger.error(f"获取用户ID {user_id} 详细信息时发生数据库错误: {e}", exc_info=True)
            raise GatewayException(f"获取用户 {user_id} 详细信息时出错", code=500)

    # --- 添加 update_user_status 方法 ---
    def update_user_status(self, user_id: int, status: int) -> User:
        """更新指定用户的状态

        :param user_id: 要更新的用户ID
        :param status: 新的状态值 (例如 0: 正常, 1: 禁用)
        :return: 更新后的用户 ORM 对象
        :raises NotFoundException: 如果用户未找到
        :raises ValueError: 如果 status 值无效 (可选，也可在路由层校验)
        :raises GatewayException: 如果发生数据库错误
        """
        logger.info(f"尝试更新用户ID {user_id} 的状态为 {status}")
        
        # 可选：在此处或路由层添加对 status 值的基本校验
        # if status not in [0, 1]: # 假设 0 和 1 是有效状态
        #     logger.warning(f"尝试为用户 {user_id} 设置无效状态值: {status}")
        #     raise ValueError(f"无效的用户状态值: {status}")

        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.warning(f"更新用户状态失败：未找到用户ID {user_id}")
                raise NotFoundException(f"未找到用户ID为 {user_id} 的用户")

            # 更新状态
            user.status = status
            
            self.db.commit()
            self.db.refresh(user) # 获取更新后的数据
            logger.info(f"成功更新用户ID {user_id} 的状态为 {status}")
            return user
        except NotFoundException as e:
            self.db.rollback() # 确保回滚（虽然这里可能不需要）
            raise e
        # except ValueError as e: # 如果添加了状态校验
        #     self.db.rollback()
        #     raise e
        except Exception as e:
            self.db.rollback()
            logger.error(f"更新用户ID {user_id} 状态时发生数据库错误: {e}", exc_info=True)
            raise GatewayException(f"更新用户 {user_id} 状态时出错", code=500)

    # --- 其他后台管理方法占位符 ---
    # def list_subscription_plans(self):
    #     pass
    # 
    # def update_subscription_plan(self, plan_id: int, data: dict):
    #     pass 