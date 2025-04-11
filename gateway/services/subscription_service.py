"""
订阅管理服务层
处理与用户订阅、套餐相关的业务逻辑
"""
import logging # 导入 logging
import datetime # 导入 datetime
from dateutil.relativedelta import relativedelta # 导入 relativedelta
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional

from core.database import get_db
from core.exceptions import GatewayException, NotFoundException, InvalidInputException, AlreadyExistsException # 导入 InvalidInputException
from core.schemas import SubscriptionResponse # 导入响应模型
from core.models.user import User # 正确导入 User
from core.models.subscription import SubscriptionPlan, UserSubscription # 正确导入订阅模型
# from core.models import User, SubscriptionPlan, UserSubscription, Subscription # 删除旧的导入
# from core.schemas import ... # 可能需要引入 Schema 用于返回类型提示，但暂时省略

logger = logging.getLogger(__name__) # 获取 logger

class SubscriptionService:
    def __init__(self, db: Session):
        """
        初始化订阅服务

        :param db: 数据库会话
        """
        self.db = db
        logger.debug("SubscriptionService initialized")

    def get_active_plans(self) -> List[SubscriptionPlan]:
        """获取所有当前激活的订阅计划列表"""
        logger.info("获取所有激活的订阅计划")
        try:
            plans = self.db.query(SubscriptionPlan).filter(SubscriptionPlan.is_active == True).all()
            logger.debug(f"找到 {len(plans)} 个激活计划")
            return plans
        except Exception as e:
            logger.error(f"获取激活套餐时出错: {e}", exc_info=True)
            raise GatewayException(message=f"获取可用订阅计划时发生错误: {e}", code=500)

    def get_user_current_subscription(self, user_id: int) -> Optional[UserSubscription]:
        """获取指定用户的当前活动订阅信息 (包含关联的套餐信息)"""
        logger.info(f"获取用户 {user_id} 的当前活动订阅")
        try:
            subscription = self.db.query(UserSubscription).options(
                joinedload(UserSubscription.plan) # 预加载关联的 plan
            ).filter(
                UserSubscription.tenant_id == user_id,
                UserSubscription.status == 0 # 0: active
            ).order_by(UserSubscription.start_date.desc()).first()
            
            if subscription:
                logger.debug(f"找到用户 {user_id} 的活动订阅 ID: {subscription.id}, 计划 ID: {subscription.plan_id}")
            else:
                logger.debug(f"用户 {user_id} 没有找到活动订阅")
            return subscription
        except Exception as e:
            logger.error(f"获取用户 {user_id} 当前订阅时出错: {e}", exc_info=True)
            raise GatewayException(message=f"获取当前订阅信息时发生错误: {e}", code=500)

    def get_user_subscription_history(self, user_id: int) -> List[UserSubscription]:
        """获取指定用户的所有历史订阅记录 (包含关联的套餐信息)"""
        logger.info(f"获取用户 {user_id} 的订阅历史")
        try:
            subscriptions = self.db.query(UserSubscription).options(
                joinedload(UserSubscription.plan)
            ).filter(
                UserSubscription.tenant_id == user_id
            ).order_by(UserSubscription.start_date.desc()).all()
            logger.debug(f"找到用户 {user_id} 的 {len(subscriptions)} 条订阅历史记录")
            return subscriptions
        except Exception as e:
            logger.error(f"获取用户 {user_id} 订阅历史时出错: {e}", exc_info=True)
            raise GatewayException(message=f"获取订阅历史记录时发生错误: {e}", code=500)

    def change_user_subscription(self, user_id: int, new_plan_id: int) -> UserSubscription:
        """更改用户的订阅计划"""
        logger.info(f"用户 {user_id} 尝试更改订阅计划至 {new_plan_id}")
        now = datetime.datetime.utcnow()
        try:
            # --- 1. 验证新计划 --- 
            new_plan = self.db.query(SubscriptionPlan).filter(
                SubscriptionPlan.id == new_plan_id,
                SubscriptionPlan.is_active == True
            ).first()
            if not new_plan:
                logger.warning(f"用户 {user_id} 尝试切换到无效或未激活的计划 ID: {new_plan_id}")
                raise NotFoundException(f"未找到有效的订阅计划 ID: {new_plan_id}")
            logger.debug(f"新计划 {new_plan_id} ('{new_plan.name}') 验证通过")

            # --- 2. 获取当前活动订阅 --- 
            current_subscription = self.get_user_current_subscription(user_id)

            # --- 3. 处理旧订阅 (如果存在) --- 
            if current_subscription:
                logger.debug(f"用户 {user_id} 当前活动订阅 ID: {current_subscription.id}, 计划 ID: {current_subscription.plan_id}")
                if current_subscription.plan_id == new_plan_id:
                    logger.warning(f"用户 {user_id} 尝试切换到相同的计划 ID: {new_plan_id}")
                    raise InvalidInputException("您当前已订阅此计划，无需更改。")
                # 将旧订阅设置为非活动状态
                current_subscription.status = 1 # 1: inactive
                current_subscription.end_date = now # 记录结束时间为当前
                current_subscription.auto_renew = False # 明确禁用自动续订
                # 注意：这里不立即 commit，等待新订阅创建成功后一起提交
                logger.info(f"将用户 {user_id} 的旧订阅 {current_subscription.id} 标记为非活动")

            # --- 4. 创建新订阅记录 --- 
            start_date = now
            end_date = None
            auto_renew = False # 默认为 False，除非是周期性计划

            # 根据新计划的计费周期计算结束日期
            if new_plan.billing_cycle == 1: # 1: monthly
                end_date = start_date + relativedelta(months=1)
                auto_renew = True
            elif new_plan.billing_cycle == 2: # 2: annual
                end_date = start_date + relativedelta(years=1)
                auto_renew = True
            # billing_cycle 为 0 (none/one-time) 时，end_date 保持 None，auto_renew 保持 False

            new_subscription = UserSubscription(
                tenant_id=user_id,
                plan_id=new_plan_id,
                start_date=start_date,
                end_date=end_date,
                status=0, # 0: active
                auto_renew=auto_renew
                # created_at 和 updated_at 由数据库默认值或 onupdate 触发器处理
            )

            self.db.add(new_subscription)
            
            # --- 5. 提交事务 --- 
            self.db.commit()
            logger.info(f"用户 {user_id} 成功更改订阅至计划 {new_plan_id}，新订阅 ID: {new_subscription.id}")
            
            # 刷新对象以获取数据库生成的值 (如 id) 并预加载 plan
            self.db.refresh(new_subscription)
            # 手动加载关联 plan，确保返回的对象包含 plan 信息
            # (如果在 get_user_current_subscription 中没有预加载，或者希望确保最新)
            # 或者在 UserSubscriptionResponse 模型中使用 model_validate(..., from_attributes=True) 来自动加载
            # 这里假设 Pydantic 模型处理关系加载

            # TODO: (可选) 触发支付/账单逻辑
            # 例如: 调用 BillingService 生成与新订阅相关的账单
            # billing_service = BillingService(self.db)
            # billing_service.generate_bill_for_new_subscription(new_subscription)

            return new_subscription

        except (NotFoundException, InvalidInputException, GatewayException) as e:
            logger.warning(f"更改用户 {user_id} 订阅至 {new_plan_id} 失败: {e}")
            self.db.rollback()
            raise e
        except Exception as e:
            logger.error(f"更改用户 {user_id} 订阅至 {new_plan_id} 时发生意外错误: {e}", exc_info=True)
            self.db.rollback()
            raise GatewayException(message=f"更改订阅计划时发生内部错误", code=500)

    def cancel_user_subscription(self, user_id: int) -> UserSubscription:
        """取消用户的当前活动订阅 (实现为禁用自动续订)"""
        logger.info(f"用户 {user_id} 尝试取消当前订阅")
        now = datetime.datetime.utcnow()
        try:
            # --- 1. 获取当前活动订阅 --- 
            current_subscription = self.get_user_current_subscription(user_id)

            # --- 2. 检查订阅状态 --- 
            if not current_subscription:
                logger.warning(f"用户 {user_id} 尝试取消订阅，但未找到活动订阅")
                raise NotFoundException("未找到有效的活动订阅，无法取消。")

            if not current_subscription.auto_renew:
                logger.warning(f"用户 {user_id} 尝试取消订阅 {current_subscription.id}，但已设置为不自动续订")
                raise InvalidInputException("此订阅已设置为不自动续订。")
            
            logger.debug(f"准备取消用户 {user_id} 的订阅 {current_subscription.id} (禁用自动续订)")
            # --- 3. 修改订阅设置 --- 
            current_subscription.auto_renew = False
            # current_subscription.status = 2 # 可选：如果需要明确标记为"已取消"状态
            # current_subscription.end_date = now # 如果取消是立即生效，则设置 end_date，但通常是到期停止
            # updated_at 会自动更新

            # --- 4. 提交事务 --- 
            self.db.commit()
            logger.info(f"用户 {user_id} 的订阅 {current_subscription.id} 已成功设置为不自动续订")
            self.db.refresh(current_subscription) # 刷新以获取最新状态

            # TODO: (可选) 触发通知逻辑
            # notification_service = NotificationService(self.db)
            # notification_service.create_subscription_cancellation_notice(current_subscription)

            return current_subscription
            
        except (NotFoundException, InvalidInputException, GatewayException) as e:
            logger.warning(f"取消用户 {user_id} 订阅失败: {e}")
            self.db.rollback()
            raise e
        except Exception as e:
            logger.error(f"取消用户 {user_id} 订阅时发生意外错误: {e}", exc_info=True)
            self.db.rollback()
            raise GatewayException(message=f"取消订阅时发生内部错误", code=500)

    def create_subscription(self, user_id: int, plan_id: int) -> UserSubscription:
        """
        为用户创建新的订阅

        :param user_id: 用户ID
        :param plan_id: 订阅计划ID
        :return: 创建的 Subscription 对象
        :raises NotFoundException: 如果用户或计划未找到
        :raises AlreadyExistsException: 如果用户已有活动订阅
        :raises GatewayException: 如果发生数据库错误
        """
        logger.info(f"尝试为用户 {user_id} 创建计划 {plan_id} 的订阅")
        try:
            # TODO: 检查用户是否存在
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                raise NotFoundException(f"用户 {user_id} 未找到")

            # TODO: 检查计划是否存在
            plan = self.db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()
            if not plan:
                raise NotFoundException(f"订阅计划 {plan_id} 未找到")

            # 检查用户是否已有活动订阅 (使用 UserSubscription 模型)
            existing_subscription = self.db.query(UserSubscription).filter( # <-- 使用 UserSubscription
                UserSubscription.tenant_id == user_id,
                UserSubscription.status == 0 # 假设 0 表示活动
            ).first()
            if existing_subscription:
                raise AlreadyExistsException(f"用户 {user_id} 已存在活动订阅")

            # --- 4. 创建新订阅记录 --- # <-- 移动并修正创建逻辑
            now = datetime.datetime.utcnow()
            start_date = now
            end_date = None
            auto_renew = False

            # 根据计划的计费周期计算结束日期
            if plan.billing_cycle == 1: # 1: monthly
                end_date = start_date + relativedelta(months=1)
                auto_renew = True
            elif plan.billing_cycle == 2: # 2: annual
                end_date = start_date + relativedelta(years=1)
                auto_renew = True

            new_subscription = UserSubscription(
                tenant_id=user_id,
                plan_id=plan_id,
                start_date=start_date,
                end_date=end_date,
                status=0, # 0: active
                auto_renew=auto_renew
            )
            self.db.add(new_subscription)
            self.db.commit()
            self.db.refresh(new_subscription)
            
            # 手动加载关联的 plan 以便在响应中显示
            # 确保 Pydantic 模型 (SubscriptionResponse) 能够正确处理
            # 或者依赖 Pydantic 的 from_attributes=True (如果配置正确)
            # 为了安全起见，显式加载
            self.db.refresh(new_subscription, with_for_update=None, attribute_names=['plan'])

            logger.info(f"为用户 {user_id} 成功创建计划 {plan_id} 的订阅，ID: {new_subscription.id}")
            return new_subscription
        except (NotFoundException, AlreadyExistsException) as e:
            self.db.rollback()
            logger.warning(f"为用户 {user_id} 创建计划 {plan_id} 订阅失败: {e}")
            raise e
        except Exception as e:
            self.db.rollback()
            logger.error(f"为用户 {user_id} 创建计划 {plan_id} 订阅时出错: {e}", exc_info=True)
            raise GatewayException("创建订阅时发生内部错误", code=500)

    def get_user_subscription(self, user_id: int) -> Optional[UserSubscription]:
        """
        获取指定用户的当前活动订阅信息 (如果有)
        """
        logger.info(f"尝试获取用户 {user_id} 的活动订阅")
        try:
            # 使用 UserSubscription 模型进行查询
            subscription = self.db.query(UserSubscription).filter( # <-- 使用 UserSubscription
                UserSubscription.tenant_id == user_id, 
                UserSubscription.status == 0 # 假设 0 表示活动
            ).order_by(UserSubscription.start_date.desc()).first()
            
            if subscription:
                logger.info(f"找到用户 {user_id} 的活动订阅 (ID: {subscription.id})")
            else:
                logger.info(f"未找到用户 {user_id} 的活动订阅")
            return subscription
        except Exception as e:
            logger.error(f"获取用户 {user_id} 订阅时出错: {e}", exc_info=True)
            raise GatewayException("获取用户订阅信息时发生内部错误", code=500)

    def cancel_subscription(self, user_id: int) -> bool:
        """取消用户的当前活动订阅 (将其标记为非活动，或禁用自动续订)"""
        logger.info(f"尝试取消用户 {user_id} 的活动订阅")
        try:
            # 获取用户的活动订阅
            subscription = self.db.query(UserSubscription).filter( # <-- 使用 UserSubscription
                UserSubscription.tenant_id == user_id,
                UserSubscription.status == 0 # 假设 0 是活动
            ).first()

            if not subscription:
                logger.warning(f"取消订阅失败：未找到用户 {user_id} 的活动订阅")
                raise NotFoundException(f"未找到用户 {user_id} 的活动订阅可取消")

            # 修正：实现取消订阅的逻辑
            # - 修改 status 为非活动状态 (例如 1: inactive)
            # - 禁用自动续订
            # - （可选）记录取消时间或保留原结束时间
            subscription.status = 1  # 标记为非活动
            subscription.auto_renew = False # 禁用自动续订
            # subscription.end_date = datetime.datetime.utcnow() # 如果需要立即结束
            # subscription.canceled_at = datetime.datetime.utcnow() # 如果有此字段
            
            self.db.commit()
            logger.info(f"成功取消用户 {user_id} 的订阅 (ID: {subscription.id})")
            return True
        except NotFoundException as e:
            self.db.rollback()
            raise e
        except Exception as e:
            self.db.rollback()
            logger.error(f"取消用户 {user_id} 订阅时出错: {e}", exc_info=True)
            raise GatewayException("取消订阅时发生内部错误", code=500)

    # TODO: 添加其他订阅相关方法，例如:
    # - 获取所有订阅计划列表 (list_subscription_plans)
    # - 更新订阅计划 (管理员权限)
    # - 获取订阅历史记录