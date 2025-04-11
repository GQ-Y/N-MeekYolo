"""
通知管理服务层
处理通知查询、状态更新、偏好设置等业务逻辑
"""
import logging # 导入 logging
from sqlalchemy.orm import Session
from sqlalchemy import func, update # 导入 func 用于更新时间 和 update
from sqlalchemy.dialects.mysql import insert as mysql_insert # 导入 MySQL 的 INSERT ... ON DUPLICATE KEY UPDATE
from typing import List, Optional, Dict, Any
import math

from core.database import get_db
from core.exceptions import NotFoundException, GatewayException
from core.models.user import User # 正确导入 User
from core.models.notification import Notification, UserNotificationPreference # 正确导入通知模型
from core.schemas import NotificationResponse, PaginationData # 导入 Pydantic 模型
# 可以在这里定义 Pydantic 模型用于 update_user_preferences 的输入类型，但暂时用 Dict
# from pydantic import BaseModel
# class NotificationPreferenceItemInput(BaseModel):
#     notification_type: str
#     channel: int
#     is_enabled: bool

logger = logging.getLogger(__name__) # 获取 logger

class NotificationService:
    def __init__(self, db: Session):
        """
        初始化通知服务

        :param db: 数据库会话
        """
        self.db = db
        logger.debug("NotificationService initialized")

    def search_user_notifications(self, user_id: int, status: Optional[int] = None) -> List[Notification]:
        """获取指定用户的通知列表，支持按状态过滤"""
        log_msg = f"搜索用户 {user_id} 的通知"
        if status is not None:
            log_msg += f", 状态: {status}"
        logger.info(log_msg)
        try:
            query = self.db.query(Notification).filter(Notification.tenant_id == user_id)
            
            if status is not None:
                query = query.filter(Notification.status == status)
                
            notifications = query.order_by(Notification.created_at.desc()).all()
            logger.debug(f"找到用户 {user_id} 的 {len(notifications)} 条通知")
            return notifications
        except Exception as e:
            logger.error(f"搜索用户 {user_id} 通知时出错: {e}", exc_info=True)
            raise GatewayException(message=f"搜索通知时发生错误: {e}", code=500)

    def mark_notifications_read(self, user_id: int, notification_ids: List[int]) -> int:
        """批量将指定 ID 列表的通知标记为已读"""
        if not notification_ids:
            logger.warning(f"用户 {user_id} 尝试标记空列表的通知为已读")
            return 0 
            
        logger.info(f"用户 {user_id} 尝试标记通知为已读, IDs: {notification_ids}")
        try:
            # 更新状态为已读 (3)，并记录读取时间
            updated_count = self.db.query(Notification).filter(
                Notification.tenant_id == user_id,
                Notification.id.in_(notification_ids),
                Notification.status != 3 # 只更新未读的
            ).update({
                Notification.status: 3, # 3: read
                Notification.read_at: func.now() # 使用 sqlalchemy.func
            }, synchronize_session=False) # 重要：对于批量更新
            
            self.db.commit()
            logger.info(f"成功为用户 {user_id} 标记了 {updated_count} 条通知为已读")
            return updated_count
        except Exception as e:
            logger.error(f"标记用户 {user_id} 通知 {notification_ids} 为已读时出错: {e}", exc_info=True)
            self.db.rollback()
            raise GatewayException(message=f"更新通知状态时发生错误: {e}", code=500)

    def get_user_preferences(self, user_id: int) -> List[UserNotificationPreference]:
        """获取指定用户的通知偏好设置"""
        logger.info(f"获取用户 {user_id} 的通知偏好设置")
        try:
            preferences = self.db.query(UserNotificationPreference).filter(
                UserNotificationPreference.tenant_id == user_id
            ).all()
            logger.debug(f"找到用户 {user_id} 的 {len(preferences)} 条偏好设置")
            return preferences
        except Exception as e:
            logger.error(f"获取用户 {user_id} 通知偏好时出错: {e}", exc_info=True)
            raise GatewayException(message=f"获取通知偏好设置时发生错误: {e}", code=500)

    def update_user_preferences(self, user_id: int, preferences_data: List[Dict[str, Any]]) -> List[UserNotificationPreference]:
        """批量更新或插入用户的通知偏好设置 (Upsert逻辑)"""
        logger.info(f"用户 {user_id} 尝试更新通知偏好设置, 数据项数: {len(preferences_data)}")
        if not preferences_data:
            logger.warning(f"用户 {user_id} 提交了空的偏好设置更新请求")
            return self.get_user_preferences(user_id)
            
        # 校验输入数据格式 (基本检查)
        for item in preferences_data:
            if not all(k in item for k in ('notification_type', 'channel', 'is_enabled')):
                 logger.error(f"用户 {user_id} 提交的偏好设置格式错误: {item}")
                 raise InvalidInputException("偏好设置项缺少必要的字段 (notification_type, channel, is_enabled)")
            if not isinstance(item['is_enabled'], bool):
                raise InvalidInputException("is_enabled 字段必须是布尔值")
            # 可以添加对 notification_type 和 channel 的枚举或范围校验

        try:
            # --- Upsert 逻辑 (这里使用 MySQL 特定的 INSERT ... ON DUPLICATE KEY UPDATE) ---
            # 注意：这种方式依赖特定数据库方言。如果需要跨数据库兼容，
            # 则需要使用更通用的方法，例如先查询，再决定更新或插入，但这会增加查询次数。
            # 或者使用 SQLAlchemy Core 的 insert().on_conflict_do_update() (需要 PostgreSQL 或 SQLite >= 3.24)
            
            # 准备要插入或更新的数据列表
            values_to_upsert = []
            for item in preferences_data:
                values_to_upsert.append({
                    'tenant_id': user_id,
                    'notification_type': item['notification_type'],
                    'channel': item['channel'],
                    'is_enabled': item['is_enabled']
                })

            if values_to_upsert:
                # 构建 INSERT ... ON DUPLICATE KEY UPDATE 语句
                stmt = mysql_insert(UserNotificationPreference).values(values_to_upsert)
                
                # 定义更新逻辑：如果 unique key (tenant_id, notification_type, channel) 已存在
                # 则更新 is_enabled 字段为新传入的值
                # 使用 stmt.inserted 引用 INSERT 语句中相应列的值
                on_duplicate_key_stmt = stmt.on_duplicate_key_update(
                    is_enabled=stmt.inserted.is_enabled
                    # 如果有 updated_at 字段，可以在这里更新: updated_at=func.now()
                )
                
                # 执行语句
                self.db.execute(on_duplicate_key_stmt)
                self.db.commit()
                logger.info(f"用户 {user_id} 的通知偏好设置更新成功")
            else:
                 logger.info(f"用户 {user_id} 提交的偏好设置数据为空，未执行数据库操作")
            
            # --- 返回更新后的所有偏好设置 --- 
            return self.get_user_preferences(user_id)

        except InvalidInputException as e:
            logger.error(f"用户 {user_id} 更新通知偏好失败: 输入无效 - {e}")
            self.db.rollback()
            raise e
        except Exception as e:
            logger.error(f"更新用户 {user_id} 通知偏好时发生意外错误: {e}", exc_info=True)
            self.db.rollback()
            raise GatewayException(message=f"更新通知偏好设置时发生内部错误", code=500)

    def list_user_notifications(self, user_id: int, page: int = 1, size: int = 10, only_unread: bool = False) -> dict:
        """
        获取指定用户的通知列表 (分页)，可选择只看未读

        :param user_id: 用户ID
        :param page: 当前页码 (从 1 开始)
        :param size: 每页显示数量
        :param only_unread: 是否只显示未读通知
        :return: 包含通知列表和分页信息的字典
        :raises GatewayException: 如果发生数据库错误
        """
        log_suffix = f"，页码: {page}，大小: {size}" + (", 只看未读" if only_unread else "")
        logger.info(f"尝试获取用户 {user_id} 的通知列表{log_suffix}")
        
        if page < 1: page = 1
        if size < 1: size = 10
        elif size > 100: size = 100
        skip = (page - 1) * size

        try:
            # 构建基础查询
            query = self.db.query(Notification).filter(Notification.tenant_id == user_id)

            # 添加未读过滤
            if only_unread:
                query = query.filter(Notification.read_at.is_(None)) 

            # 获取总数
            total_notifications = query.with_entities(func.count(Notification.id)).scalar()
            logger.debug(f"用户 {user_id} 的通知总数 (过滤后): {total_notifications}")

            # 获取当前页数据 (按创建时间降序)
            notifications = query.order_by(Notification.created_at.desc()).offset(skip).limit(size).all()
            logger.debug(f"查询到用户 {user_id} 当前页通知数量: {len(notifications)}")

            # 计算总页数
            total_pages = math.ceil(total_notifications / size) if total_notifications > 0 else 1

            pagination_data = {
                "total": total_notifications,
                "page": page,
                "size": size,
                "total_pages": total_pages
            }

            result = {
                "items": notifications, # 返回 ORM 对象列表
                "pagination": pagination_data
            }
            logger.info(f"成功获取用户 {user_id} 的通知列表{log_suffix}")
            return result
        except Exception as e:
            logger.error(f"获取用户 {user_id} 通知列表时出错: {e}", exc_info=True)
            raise GatewayException("获取通知列表时发生内部错误", code=500)

    def mark_notification_as_read(self, user_id: int, notification_id: int) -> Notification:
        """
        将指定用户拥有的特定通知标记为已读

        :param user_id: 用户ID
        :param notification_id: 通知ID
        :return: 更新后的 Notification 对象
        :raises NotFoundException: 如果通知未找到或不属于该用户
        :raises GatewayException: 如果发生数据库错误
        """
        logger.info(f"尝试将用户 {user_id} 的通知 {notification_id} 标记为已读")
        try:
            notification = self.db.query(Notification).filter(
                Notification.id == notification_id, 
                Notification.tenant_id == user_id
            ).first()
            
            if not notification:
                logger.warning(f"标记已读失败：用户 {user_id} 未找到通知 {notification_id} 或无权限")
                raise NotFoundException(f"未找到通知 {notification_id}")
            
            if notification.read_at is None:
                notification.status = 3 # 假设 3 代表已读
                notification.read_at = func.now()
                self.db.commit()
                self.db.refresh(notification)
                logger.info(f"成功将用户 {user_id} 的通知 {notification_id} 标记为已读")
            else:
                 logger.info(f"通知 {notification_id} (用户 {user_id}) 已是已读状态")
                 
            return notification
        except NotFoundException as e:
            self.db.rollback()
            raise e
        except Exception as e:
            self.db.rollback()
            logger.error(f"标记通知 {notification_id} (用户 {user_id}) 为已读时出错: {e}", exc_info=True)
            raise GatewayException("标记通知为已读时发生内部错误", code=500)

    def mark_all_notifications_as_read(self, user_id: int) -> int:
        """
        将指定用户的所有未读通知标记为已读

        :param user_id: 用户ID
        :return: 被标记为已读的通知数量
        :raises GatewayException: 如果发生数据库错误
        """
        logger.info(f"尝试将用户 {user_id} 的所有未读通知标记为已读")
        try:
            # 使用 update() 方法批量更新，更高效
            update_statement = (
                update(Notification)
                .where(Notification.tenant_id == user_id, Notification.read_at.is_(None))
                .values(status=3, read_at=func.now()) # 假设 3 代表已读
                # .execution_options(synchronize_session="fetch") # 根据需要选择同步策略
            )
            result = self.db.execute(update_statement)
            self.db.commit()
            
            marked_count = result.rowcount
            logger.info(f"成功将用户 {user_id} 的 {marked_count} 条未读通知标记为已读")
            return marked_count
        except Exception as e:
            self.db.rollback()
            logger.error(f"标记用户 {user_id} 所有通知为已读时出错: {e}", exc_info=True)
            raise GatewayException("批量标记通知为已读时发生内部错误", code=500)

    def delete_notification(self, user_id: int, notification_id: int) -> bool:
        """
        删除指定用户拥有的特定通知

        :param user_id: 用户ID
        :param notification_id: 通知ID
        :return: 如果成功删除则返回 True
        :raises NotFoundException: 如果通知未找到或不属于该用户
        :raises GatewayException: 如果发生数据库错误
        """
        logger.info(f"尝试删除用户 {user_id} 的通知 {notification_id}")
        try:
            notification = self.db.query(Notification).filter(
                Notification.id == notification_id, 
                Notification.tenant_id == user_id
            ).first()
            
            if not notification:
                logger.warning(f"删除通知失败：用户 {user_id} 未找到通知 {notification_id} 或无权限")
                raise NotFoundException(f"未找到通知 {notification_id}")
            
            self.db.delete(notification)
            self.db.commit()
            logger.info(f"成功删除用户 {user_id} 的通知 {notification_id}")
            return True
        except NotFoundException as e:
            self.db.rollback()
            raise e
        except Exception as e:
            self.db.rollback()
            logger.error(f"删除通知 {notification_id} (用户 {user_id}) 时出错: {e}", exc_info=True)
            raise GatewayException("删除通知时发生内部错误", code=500)

    # TODO: 添加创建通知的方法 (可能由系统事件触发，而非用户直接调用)
    # def create_notification(user_id: int, title: str, message: str, level: str = 'info'):
    #     pass

    # 可能还需要创建通知的服务方法 (供系统内部调用)
    # def create_notification(self, user_id: int, type: str, content: str, channel: int, subject: Optional[str] = None) -> Notification:
    #     """创建一条新通知"""
    #     raise NotImplementedError("创建通知服务逻辑待实现") 