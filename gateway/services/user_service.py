""":mod:`services.user_service`
用户服务层
处理用户相关的业务逻辑，如个人资料管理、用户列表等
"""
import logging
from sqlalchemy.orm import Session
from core.database import get_db
from core.models.user import User
from core.exceptions import NotFoundException, GatewayException
from core.schemas import UserProfileUpdate # 假设这个 Pydantic 模型已定义或将在后续定义
from fastapi import Depends

logger = logging.getLogger(__name__)

class UserService:
    def __init__(self, db: Session):
        """
        初始化用户服务
        
        :param db: 数据库会话
        """
        self.db = db
        logger.debug("UserService initialized")

    def get_user_profile(self, user_id: int) -> User:
        """
        根据用户ID获取用户公开信息

        :param user_id: 用户ID
        :return: 用户对象
        :raises NotFoundException: 如果用户未找到
        :raises GatewayException: 如果发生数据库错误
        """
        logger.info(f"尝试获取用户ID为 {user_id} 的信息")
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.warning(f"获取用户信息失败：未找到用户ID {user_id}")
                raise NotFoundException(f"未找到用户ID为 {user_id} 的用户")
            
            logger.info(f"成功获取用户ID {user_id} 的信息")
            # 注意：这里返回的是 ORM 模型，路由层需要将其转换为 Pydantic 模型
            return user
        except NotFoundException as e:
            raise e # 直接抛出 NotFoundException
        except Exception as e:
            logger.error(f"获取用户ID {user_id} 信息时发生数据库错误: {e}", exc_info=True)
            raise GatewayException(message=f"获取用户信息时出错", code=500)

    def update_user_profile(self, user_id: int, profile_data: UserProfileUpdate) -> User:
        """
        更新指定用户的个人资料

        :param user_id: 要更新的用户ID
        :param profile_data: 包含更新信息的用户资料 Pydantic 模型
        :return: 更新后的用户对象
        :raises NotFoundException: 如果用户未找到
        :raises GatewayException: 如果发生数据库错误
        """
        logger.info(f"尝试更新用户ID为 {user_id} 的个人资料")
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.warning(f"更新用户信息失败：未找到用户ID {user_id}")
                raise NotFoundException(f"未找到用户ID为 {user_id} 的用户")

            # 使用 Pydantic 模型的 .model_dump() 方法 (v2) 或 .dict() (v1) 获取更新数据
            # exclude_unset=True 确保只更新传入的字段
            update_data = profile_data.model_dump(exclude_unset=True)

            for key, value in update_data.items():
                # 确保只更新 User 模型中存在的字段，防止恶意注入
                if hasattr(user, key):
                    setattr(user, key, value)
                else:
                    logger.warning(f"尝试更新用户 {user_id} 的非法字段: {key}")

            self.db.commit()
            self.db.refresh(user)
            logger.info(f"成功更新用户ID {user_id} 的个人资料")
            return user
        except NotFoundException as e:
            self.db.rollback() # 更新失败时回滚
            raise e
        except Exception as e:
            self.db.rollback()
            logger.error(f"更新用户ID {user_id} 信息时发生数据库错误: {e}", exc_info=True)
            raise GatewayException(message=f"更新用户信息时出错", code=500)

    # TODO: 添加其他用户管理功能，例如:
    # - 获取用户列表 (分页, 搜索)
    # - 管理用户状态 (激活/禁用)
    # - ... 

# 依赖工厂函数
def get_user_service(db: Session = Depends(get_db)) -> UserService:
    """
    FastAPI 依赖项，用于获取 UserService 实例。
    
    :param db: 数据库会话依赖
    :return: UserService 实例
    """
    return UserService(db) 