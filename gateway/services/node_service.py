"""
节点管理服务层
处理用户节点的增删改查及相关业务逻辑
"""
import logging # 导入 logging
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_ # 导入 or_
from typing import List, Optional, Dict, Any
import math

from core.models.user import User
from core.models.node import UserNode
from core.models.subscription import UserSubscription, SubscriptionPlan
from core.models.task import Task
from core.exceptions import GatewayException, NotFoundException, ForbiddenException, PermissionDeniedException
from core.schemas import PaginationData # 导入分页模型
# from services.subscription_service import SubscriptionService # 可以考虑注入 SubscriptionService

logger = logging.getLogger(__name__) # 获取 logger

class NodeService:
    def __init__(self, db: Session):
        """
        初始化节点服务

        :param db: 数据库会话
        """
        self.db = db
        logger.debug("NodeService initialized")
        # self.subscription_service = SubscriptionService(db) # 考虑注入

    def _check_node_limit(self, user_id: int) -> None:
        """检查用户是否达到节点数量限制"""
        logger.debug(f"检查用户 {user_id} 的节点限制")
        # 替代方案：直接查询，避免循环依赖或显式注入 SubscriptionService
        current_subscription = self.db.query(UserSubscription).options(joinedload(UserSubscription.plan)).filter(
            UserSubscription.tenant_id == user_id,
            UserSubscription.status == 0 # Active
        ).order_by(UserSubscription.start_date.desc()).first()

        if not current_subscription or not current_subscription.plan:
            logger.warning(f"用户 {user_id} 尝试创建节点但无有效订阅")
            raise ForbiddenException(message="无法创建节点：无有效订阅计划")

        node_limit = current_subscription.plan.node_limit
        if node_limit is not None: # None 表示无限制
            current_node_count = self.db.query(UserNode).filter(UserNode.tenant_id == user_id).count()
            logger.debug(f"用户 {user_id} 当前节点数: {current_node_count}, 限制: {node_limit}")
            if current_node_count >= node_limit:
                logger.warning(f"用户 {user_id} 创建节点失败，已达数量限制 ({node_limit})")
                raise ForbiddenException(message=f"无法创建节点：已达到订阅计划允许的最大节点数 ({node_limit})个")
        else:
            logger.debug(f"用户 {user_id} 订阅计划无节点数量限制")

    def create_node(self, user_id: int, node_data: dict) -> UserNode:
        """
        为指定用户创建新节点

        :param user_id: 所属用户的ID
        :param node_data: 包含节点信息的字典 (应符合 NodeCreate schema)
        :return: 创建的 Node 对象
        :raises NotFoundException: 如果用户未找到
        :raises GatewayException: 如果发生数据库错误
        """
        logger.info(f"尝试为用户 {user_id} 创建新节点")
        try:
            # 检查用户是否存在
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                raise NotFoundException(f"创建节点失败：未找到用户 ID {user_id}")
                
            # TODO: 可以添加更具体的验证逻辑，例如检查 config_details 的结构

            # 创建 UserNode 对象
            # node_data 包含了 name, config_details, description (如果提供了)
            new_node = UserNode(**node_data, tenant_id=user_id) # <-- 使用 tenant_id
            
            self.db.add(new_node)
            self.db.commit()
            self.db.refresh(new_node)
            logger.info(f"成功为用户 {user_id} 创建节点 (ID: {new_node.id})")
            return new_node
        except NotFoundException as e:
            self.db.rollback()
            logger.warning(f"创建节点失败: {e}")
            raise e
        except Exception as e:
            self.db.rollback()
            logger.error(f"为用户 {user_id} 创建节点时出错: {e}", exc_info=True)
            raise GatewayException("创建节点时发生内部错误", code=500)

    def list_user_nodes(self, user_id: int, page: int = 1, size: int = 10) -> dict:
        """
        获取指定用户的节点列表 (分页)

        :param user_id: 用户ID
        :param page: 当前页码 (从 1 开始)
        :param size: 每页显示数量
        :return: 包含节点列表和分页信息的字典
        :raises GatewayException: 如果发生数据库错误
        """
        logger.info(f"尝试获取用户 {user_id} 的节点列表，页码: {page}，大小: {size}")
        if page < 1:
            page = 1
        if size < 1:
            size = 10
        elif size > 100:
            size = 100
        skip = (page - 1) * size

        try:
            # 基础查询，按用户过滤
            query = self.db.query(UserNode).filter(UserNode.tenant_id == user_id) # <-- 使用 tenant_id

            # 计算总数 (在应用分页前)
            total_count = query.count()
            logger.debug(f"用户 {user_id} 的节点总数: {total_count}")

            # 获取当前页数据
            nodes = query.order_by(UserNode.id.asc()).offset(skip).limit(size).all()
            logger.debug(f"查询到用户 {user_id} 当前页节点数量: {len(nodes)}")

            # 计算总页数
            total_pages = math.ceil(total_count / size) if total_count > 0 else 1

            pagination_data = {
                "total": total_count,
                "page": page,
                "size": size,
                "total_pages": total_pages
            }

            result = {
                "items": nodes,
                "pagination": pagination_data
            }
            logger.info(f"成功获取用户 {user_id} 的节点列表 (页码: {page}, 大小: {size})")
            return result
        except Exception as e:
            logger.error(f"获取用户 {user_id} 节点列表时出错: {e}", exc_info=True)
            raise GatewayException("获取节点列表时发生内部错误", code=500)

    def get_node_details(self, user_id: int, node_id: int) -> UserNode:
        """
        获取指定用户拥有的特定节点的详细信息

        :param user_id: 用户ID
        :param node_id: 节点ID
        :return: Node 对象
        :raises NotFoundException: 如果节点未找到或不属于该用户
        :raises GatewayException: 如果发生数据库错误
        """
        logger.info(f"尝试获取用户 {user_id} 的节点 {node_id} 详情")
        try:
            node = self.db.query(UserNode).filter(UserNode.id == node_id, UserNode.tenant_id == user_id).first()
            if not node:
                logger.warning(f"获取节点详情失败：用户 {user_id} 未找到节点 {node_id} 或无权限")
                # 统一返回 NotFoundException，不区分是节点不存在还是权限不足
                raise NotFoundException(f"未找到节点 {node_id}")
            
            logger.info(f"成功获取用户 {user_id} 的节点 {node_id} 详情")
            return node
        except NotFoundException as e:
            raise e
        except Exception as e:
            logger.error(f"获取节点 {node_id} (用户 {user_id}) 详情时出错: {e}", exc_info=True)
            raise GatewayException("获取节点详情时发生内部错误", code=500)

    def update_node(self, user_id: int, node_id: int, update_data: dict) -> UserNode:
        """
        更新指定用户拥有的特定节点的信息

        :param user_id: 用户ID
        :param node_id: 节点ID
        :param update_data: 包含更新信息的字典 (应符合 NodeUpdate schema)
        :return: 更新后的 Node 对象
        :raises NotFoundException: 如果节点未找到或不属于该用户
        :raises GatewayException: 如果发生数据库错误
        """
        logger.info(f"尝试更新用户 {user_id} 的节点 {node_id}")
        try:
            node = self.db.query(UserNode).filter(UserNode.id == node_id, UserNode.tenant_id == user_id).first()
            if not node:
                logger.warning(f"更新节点失败：用户 {user_id} 未找到节点 {node_id} 或无权限")
                raise NotFoundException(f"未找到节点 {node_id}")

            # TODO: 校验 update_data (例如，不允许修改 user_id)
            update_data.pop('user_id', None) # 防止意外修改 user_id
            update_data.pop('id', None)      # 防止意外修改 id

            for key, value in update_data.items():
                if hasattr(node, key):
                    setattr(node, key, value)
                else:
                    logger.warning(f"尝试为节点 {node_id} 更新非法字段: {key}")
            
            self.db.commit()
            self.db.refresh(node)
            logger.info(f"成功更新用户 {user_id} 的节点 {node_id}")
            return node
        except NotFoundException as e:
            self.db.rollback()
            raise e
        except Exception as e:
            self.db.rollback()
            logger.error(f"更新节点 {node_id} (用户 {user_id}) 时出错: {e}", exc_info=True)
            raise GatewayException("更新节点信息时发生内部错误", code=500)

    def delete_node(self, user_id: int, node_id: int) -> bool:
        """
        删除指定用户拥有的特定节点

        :param user_id: 用户ID
        :param node_id: 节点ID
        :return: 如果成功删除则返回 True
        :raises NotFoundException: 如果节点未找到或不属于该用户
        :raises GatewayException: 如果发生数据库错误
        """
        logger.info(f"尝试删除用户 {user_id} 的节点 {node_id}")
        try:
            node = self.db.query(UserNode).filter(UserNode.id == node_id, UserNode.tenant_id == user_id).first()
            if not node:
                logger.warning(f"删除节点失败：用户 {user_id} 未找到节点 {node_id} 或无权限")
                raise NotFoundException(f"未找到节点 {node_id}")
            
            # TODO: 检查是否有依赖该节点的任务或其他资源，根据业务逻辑决定是否允许删除
            # if self.db.query(Task).filter(Task.node_id == node_id, Task.status == 'active').count() > 0:
            #     raise PermissionDeniedException(f"节点 {node_id} 存在活动任务，无法删除")

            self.db.delete(node)
            self.db.commit()
            logger.info(f"成功删除用户 {user_id} 的节点 {node_id}")
            return True
        except NotFoundException as e:
            self.db.rollback()
            raise e
        # except PermissionDeniedException as e:
        #     self.db.rollback()
        #     logger.warning(f"删除节点 {node_id} 失败: {e}")
        #     raise e
        except Exception as e:
            self.db.rollback()
            logger.error(f"删除节点 {node_id} (用户 {user_id}) 时出错: {e}", exc_info=True)
            raise GatewayException("删除节点时发生内部错误", code=500) 