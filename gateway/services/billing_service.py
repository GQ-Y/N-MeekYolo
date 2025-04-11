"""
账单与支付服务层
处理账单记录查询、优惠券应用等业务逻辑
"""
import logging # 导入 logging
import datetime
from decimal import Decimal # 导入 Decimal 用于精确计算
from sqlalchemy.orm import Session, joinedload # 导入 joinedload
from typing import List, Optional, Dict, Any
import stripe # 导入 stripe
from sqlalchemy import func
import math

from core.exceptions import NotFoundException, GatewayException, InvalidInputException, ForbiddenException
from core.schemas import BillingRecordResponse, ApplyCouponResponse # 导入 Pydantic 模型
import stripe

from core.models.user import User
from core.models.billing import BillingRecord, Coupon, UserAppliedCoupon
from core.models.admin import PaymentGateway

from core.config import settings # 导入 settings
from core.database import get_db

logger = logging.getLogger(__name__) # 获取 logger

class BillingService:
    def __init__(self, db: Session):
        """
        初始化账单服务

        :param db: 数据库会话
        """
        self.db = db
        logger.debug("BillingService initialized")

    def search_billing_records(self, user_id: int, search_params: Dict[str, Any], page: int = 1, size: int = 10) -> dict:
        """
        搜索指定用户的账单记录 (分页)

        :param user_id: 用户ID
        :param search_params: 搜索参数字典 (例如: status, start_date, end_date)
        :param page: 当前页码 (从 1 开始)
        :param size: 每页显示数量
        :return: 包含账单记录列表和分页信息的字典
        :raises GatewayException: 如果发生数据库错误
        """
        logger.info(f"尝试搜索用户 {user_id} 的账单记录，参数: {search_params}，页码: {page}，大小: {size}")
        if page < 1: page = 1
        if size < 1: size = 10
        elif size > 100: size = 100
        skip = (page - 1) * size

        try:
            # 基础查询，按用户过滤
            query = self.db.query(BillingRecord).filter(BillingRecord.tenant_id == user_id)

            # 添加其他过滤条件
            status = search_params.get('status')
            if status is not None:
                query = query.filter(BillingRecord.status == status)

            # TODO: 根据 search_params 添加过滤条件
            # 例如: status, date range
            # start_date = search_params.get('start_date')
            # end_date = search_params.get('end_date')
            # if start_date:
            #     query = query.filter(BillingRecord.created_at >= start_date)
            # if end_date:
            #     query = query.filter(BillingRecord.created_at <= end_date)

            # 获取总数
            total_records = query.with_entities(func.count(BillingRecord.id)).scalar()
            logger.debug(f"用户 {user_id} 的账单记录总数 (过滤后): {total_records}")

            # 获取当前页数据 (按创建时间降序)
            records = query.order_by(BillingRecord.created_at.desc()).offset(skip).limit(size).all()
            logger.debug(f"查询到用户 {user_id} 当前页账单记录数量: {len(records)}")

            # 计算总页数
            total_pages = math.ceil(total_records / size) if total_records > 0 else 1

            pagination_data = {
                "total": total_records,
                "page": page,
                "size": size,
                "total_pages": total_pages
            }

            result = {
                "items": records, # 返回 ORM 对象列表
                "pagination": pagination_data
            }
            logger.info(f"成功获取用户 {user_id} 的账单记录列表")
            return result
        except Exception as e:
            logger.error(f"搜索用户 {user_id} 账单记录时出错: {e}", exc_info=True)
            raise GatewayException("搜索账单记录时发生内部错误", code=500)

    def get_billing_details(self, user_id: int, billing_id: int) -> BillingRecord:
        """
        获取指定用户拥有的特定账单记录的详细信息

        :param user_id: 用户ID
        :param billing_id: 账单记录ID
        :return: BillingRecord 对象
        :raises NotFoundException: 如果账单记录未找到或不属于该用户
        :raises GatewayException: 如果发生数据库错误
        """
        logger.info(f"尝试获取用户 {user_id} 的账单记录 {billing_id} 详情")
        try:
            record = self.db.query(BillingRecord).filter(
                BillingRecord.id == billing_id, 
                BillingRecord.tenant_id == user_id
            ).first()
            if not record:
                logger.warning(f"获取账单详情失败：用户 {user_id} 未找到账单 {billing_id} 或无权限")
                raise NotFoundException(f"未找到账单记录 {billing_id}")
            
            logger.info(f"成功获取用户 {user_id} 的账单 {billing_id} 详情")
            return record
        except NotFoundException as e:
            raise e
        except Exception as e:
            logger.error(f"获取账单 {billing_id} (用户 {user_id}) 详情时出错: {e}", exc_info=True)
            raise GatewayException("获取账单详情时发生内部错误", code=500)

    def apply_coupon(self, user_id: int, coupon_code: str) -> Dict[str, Any]:
        """
        用户尝试应用优惠券代码

        :param user_id: 用户ID
        :param coupon_code: 优惠券代码
        :return: 包含应用结果信息的字典 (例如: 是否成功, 折扣金额/类型, 消息)
        :raises NotFoundException: 如果优惠券代码无效或已过期/使用
        :raises InvalidInputException: 如果优惠券不适用于该用户或当前场景
        :raises GatewayException: 如果发生数据库错误
        """
        logger.info(f"用户 {user_id} 尝试应用优惠券: {coupon_code}")
        try:
            # TODO: 查询优惠券是否存在且有效
            coupon = self.db.query(Coupon).filter(
                Coupon.code == coupon_code,
                Coupon.is_active == True,
                Coupon.expiry_date >= datetime.datetime.utcnow() 
                # Coupon.use_limit > Coupon.times_used # 检查使用次数限制
            ).first()

            if not coupon:
                logger.warning(f"应用优惠券失败：优惠券代码 {coupon_code} 无效或已过期")
                raise NotFoundException("无效或已过期的优惠券代码")
            
            # TODO: 检查优惠券是否适用于该用户 (例如，新用户专享)
            # if coupon.is_new_user_only and self.db.query(BillingRecord).filter(BillingRecord.user_id == user_id).count() > 0:
            #     raise InvalidInputException("此优惠券仅限新用户使用")

            # TODO: 检查优惠券是否已应用于用户的当前未支付账单或下一个订阅周期
            # (取决于业务逻辑，优惠券是应用于一次性支付还是订阅)
            # has_applied = ... 
            # if has_applied:
            #     raise InvalidInputException("优惠券已应用或不适用")
            
            # TODO: 计算折扣并返回结果
            discount_amount = 0.0
            discount_type = "fixed" # or "percentage"
            if coupon.discount_type == 'fixed':
                discount_amount = coupon.discount_value
            elif coupon.discount_type == 'percentage':
                # 需要计算基于什么金额的百分比，可能需要关联订单/订阅信息
                # base_amount = ...
                # discount_amount = base_amount * (coupon.discount_value / 100.0)
                pass # 暂缓实现百分比逻辑
            else:
                discount_type = "unknown"
                
            result = {
                "success": True,
                "message": "优惠券应用成功",
                "coupon_code": coupon.code,
                "discount_type": discount_type,
                "discount_value": coupon.discount_value, # 返回原始值 (可能是金额或百分比)
                "calculated_discount": discount_amount # 返回计算后的折扣金额 (暂定)
            }
            logger.info(f"用户 {user_id} 应用优惠券 {coupon_code} 成功: {result}")
            return result

        except (NotFoundException, InvalidInputException) as e:
            logger.warning(f"应用优惠券 {coupon_code} 失败: {e}")
            # 可以考虑在结果字典中返回失败信息，而不是抛出异常
            # return {"success": False, "message": str(e), "coupon_code": coupon_code}
            # 但为了保持接口一致性，暂时向上抛出异常
            raise e 
        except Exception as e:
            logger.error(f"应用优惠券 {coupon_code} (用户 {user_id}) 时出错: {e}", exc_info=True)
            raise GatewayException("应用优惠券时发生内部错误", code=500)

    def search_user_billing_records(self, user_id: int, status: Optional[int] = None) -> List[BillingRecord]:
        """获取指定用户的账单列表，支持按状态过滤"""
        logger.info(f"搜索用户 {user_id} 的账单记录, 状态: {status}")
        try:
            query = self.db.query(BillingRecord).filter(BillingRecord.tenant_id == user_id)
            
            if status is not None:
                query = query.filter(BillingRecord.status == status)
                
            records = query.order_by(BillingRecord.created_at.desc()).all()
            logger.debug(f"找到用户 {user_id} 的 {len(records)} 条账单记录")
            return records
        except Exception as e:
            logger.error(f"搜索用户 {user_id} 账单时出错: {e}", exc_info=True)
            raise GatewayException(message=f"搜索账单记录时发生错误: {e}", code=500)

    def get_billing_detail(self, user_id: int, record_id: int) -> BillingRecord:
        """获取指定账单的详细信息，确保账单属于该用户"""
        logger.info(f"获取用户 {user_id} 的账单详情 (ID: {record_id})")
        try:
            # record = self.db.query(BillingRecord).filter(
            #     BillingRecord.id == record_id,
            #     BillingRecord.tenant_id == user_id
            # ).first() # 这个版本没有预加载，在 apply_coupon 中需要手动预加载
            
            # 如果需要在多个地方使用预加载，可以考虑创建一个内部方法
            record = self._get_billing_record_with_relations(user_id, record_id)
            
            if not record:
                logger.warning(f"用户 {user_id} 尝试获取不存在或不属于他的账单详情 (ID: {record_id})")
                raise NotFoundException(message=f"未找到 ID 为 {record_id} 的账单记录")
            
            logger.debug(f"成功获取到账单 {record_id} 的详情")
            return record
        except NotFoundException as e:
             raise e
        except Exception as e:
            logger.error(f"获取用户 {user_id} 账单 {record_id} 详情时出错: {e}", exc_info=True)
            raise GatewayException(message=f"获取账单详情时发生错误: {e}", code=500)
            
    def _get_billing_record_with_relations(self, user_id: int, record_id: int) -> Optional[BillingRecord]:
        """内部辅助方法：获取账单并预加载关联的订阅和计划"""
        return self.db.query(BillingRecord).options(
            joinedload(BillingRecord.subscription).joinedload(UserSubscription.plan) 
        ).filter(
            BillingRecord.id == record_id,
            BillingRecord.tenant_id == user_id
        ).first()

    def apply_coupon_to_user(self, user_id: int, coupon_code: str, record_id: Optional[int] = None) -> BillingRecord:
        """用户尝试应用一个有效的优惠券码到指定的待支付账单"""
        logger.info(f"用户 {user_id} 尝试应用优惠券 '{coupon_code}' 到账单 {record_id}")
        now = datetime.datetime.utcnow()

        if record_id is None:
            logger.warning(f"用户 {user_id} 应用优惠券 '{coupon_code}' 时未提供 record_id")
            raise InvalidInputException("必须指定要应用优惠券的账单 ID (record_id)")

        try:
            # --- 1. 查找并验证优惠券 --- 
            coupon = self.db.query(Coupon).filter(Coupon.code == coupon_code).first()
            if not coupon:
                logger.warning(f"尝试应用不存在的优惠券码: '{coupon_code}'")
                raise NotFoundException(f"优惠券码 '{coupon_code}' 不存在")
            logger.debug(f"找到优惠券: ID={coupon.id}, Code='{coupon.code}'")
            if not coupon.is_active:
                 logger.warning(f"尝试应用无效优惠券: '{coupon_code}' (ID: {coupon.id})")
                 raise InvalidInputException(f"优惠券 '{coupon_code}' 当前无效")
            if coupon.expiry_date and coupon.expiry_date < now:
                logger.warning(f"尝试应用已过期优惠券: '{coupon_code}' (ID: {coupon.id}), 过期时间: {coupon.expiry_date}")
                raise InvalidInputException(f"优惠券 '{coupon_code}' 已过期 ({coupon.expiry_date.strftime('%Y-%m-%d')})")
            logger.debug(f"优惠券 '{coupon.code}' 激活且未过期")

            # --- 2. 检查优惠券使用限制 --- 
            # 全局使用次数
            if coupon.usage_limit is not None:
                global_usage_count = self.db.query(UserAppliedCoupon).filter(UserAppliedCoupon.coupon_id == coupon.id).count()
                logger.debug(f"优惠券 '{coupon.code}' 全局已使用 {global_usage_count}/{coupon.usage_limit} 次")
                if global_usage_count >= coupon.usage_limit:
                    logger.warning(f"优惠券 '{coupon.code}' 已达全局使用上限")
                    raise InvalidInputException(f"优惠券 '{coupon_code}' 已达到最大使用次数限制")
            
            # 用户使用次数
            user_usage_count = self.db.query(UserAppliedCoupon).filter(
                UserAppliedCoupon.tenant_id == user_id,
                UserAppliedCoupon.coupon_id == coupon.id
            ).count()
            logger.debug(f"用户 {user_id} 已使用优惠券 '{coupon.code}' {user_usage_count}/{coupon.user_limit} 次")
            if user_usage_count >= coupon.user_limit:
                 logger.warning(f"用户 {user_id} 已达优惠券 '{coupon.code}' 使用上限")
                 raise InvalidInputException(f"您已达到此优惠券的最大使用次数 ({coupon.user_limit}次)")
            logger.debug(f"优惠券 '{coupon.code}' 使用限制检查通过")

            # --- 3. 查找并验证目标账单 --- 
            logger.debug(f"查找用户 {user_id} 的账单 {record_id}")
            record = self._get_billing_record_with_relations(user_id, record_id)
            if not record:
                 logger.warning(f"用户 {user_id} 应用优惠券 '{coupon.code}' 失败，未找到账单 {record_id}")
                 raise NotFoundException(f"未找到 ID 为 {record_id} 的账单记录")
            logger.debug(f"找到账单 {record_id}, 状态: {record.status}, 当前折扣: {record.discount_amount}")
            if record.status != 0:
                logger.warning(f"尝试对非待支付账单 {record_id} (状态: {record.status}) 应用优惠券 '{coupon.code}'")
                raise InvalidInputException(f"此账单状态不为待支付，无法应用优惠券")
            if record.discount_amount > Decimal('0.00'):
                logger.warning(f"尝试对已应用折扣的账单 {record_id} 再次应用优惠券 '{coupon.code}'")
                raise InvalidInputException("此账单已应用过优惠券")
            logger.debug(f"账单 {record_id} 状态和折扣检查通过")

            # --- 4. 检查优惠券适用性 --- 
            billable_amount = record.fixed_amount + record.usage_amount
            logger.debug(f"账单 {record_id} 可计费金额: {billable_amount}, 优惠券最低要求: {coupon.min_purchase_amount}")
            if billable_amount < coupon.min_purchase_amount:
                logger.warning(f"账单 {record_id} 金额 {billable_amount} 未达优惠券 '{coupon.code}' 最低要求 {coupon.min_purchase_amount}")
                raise InvalidInputException(f"账单金额未达到优惠券最低消费要求 (￥{coupon.min_purchase_amount:.2f})")
                
            # 检查适用计划
            if coupon.applicable_plan_ids: # 如果列表不为空
                logger.debug(f"优惠券 '{coupon.code}' 适用于计划: {coupon.applicable_plan_ids}")
                if not record.subscription or not record.subscription.plan_id:
                     logger.warning(f"账单 {record_id} 未关联有效计划，无法判断优惠券 '{coupon.code}' 适用性")
                     raise InvalidInputException("此账单未关联有效订阅计划，无法判断优惠券适用性")
                logger.debug(f"账单 {record_id} 关联计划 ID: {record.subscription.plan_id}")
                if record.subscription.plan_id not in coupon.applicable_plan_ids:
                    logger.warning(f"优惠券 '{coupon.code}' 不适用账单 {record_id} 的计划 {record.subscription.plan_id}")
                    raise InvalidInputException(f"此优惠券不适用于您当前的订阅计划")
            logger.debug(f"优惠券 '{coupon.code}' 适用性检查通过")

            # --- 5. 计算折扣 --- 
            discount_value = Decimal('0.00')
            if coupon.type == 0: # 0: percentage
                # 百分比折扣，coupon.value 存储的是百分比值 (e.g., 10 for 10%)
                discount_value = billable_amount * (Decimal(coupon.value) / Decimal('100'))
            elif coupon.type == 1: # 1: fixed_amount
                discount_value = Decimal(coupon.value)
            else:
                # 未知优惠券类型，记录错误或忽略
                # logger.warning(f"未知的优惠券类型: {coupon.type} for coupon {coupon.code}")
                pass 

            # 折扣金额不能超过账单可计费金额
            actual_discount = min(discount_value, billable_amount)
            # 保留两位小数 (虽然 Decimal 内部精确，但最好显式处理)
            actual_discount = actual_discount.quantize(Decimal('0.01'))
            logger.debug(f"优惠券 '{coupon.code}' (类型: {coupon.type}, 值: {coupon.value}) 计算得出实际折扣: {actual_discount} 应用于账单 {record_id}")

            # --- 6. 更新账单并创建应用记录 --- 
            record.discount_amount = actual_discount
            record.total_amount_due = billable_amount - actual_discount
            # total_amount_due 也应保留两位小数
            record.total_amount_due = record.total_amount_due.quantize(Decimal('0.01'))
            # updated_at 会自动更新
            
            new_applied_record = UserAppliedCoupon(
                tenant_id=user_id,
                coupon_id=coupon.id,
                billing_record_id=record_id,
                applied_at=now,
                discount_applied=actual_discount
            )
            self.db.add(new_applied_record)
            logger.debug(f"创建 UserAppliedCoupon 记录: user={user_id}, coupon={coupon.id}, record={record_id}, discount={actual_discount}")

            # --- 7. 更新优惠券使用次数 (如果需要，但模型中没有 used_count) --- 
            # 如果 Coupon 模型有 used_count 字段:
            # if coupon.usage_limit is not None:
            #     coupon.used_count = (coupon.used_count or 0) + 1

            # --- 8. 提交事务 --- 
            self.db.commit()
            logger.info(f"用户 {user_id} 成功应用优惠券 '{coupon.code}' (ID: {coupon.id}) 到账单 {record_id}")
            self.db.refresh(record) # 刷新账单对象以获取更新后的状态

            return record

        except (NotFoundException, InvalidInputException, ForbiddenException, GatewayException) as e:
            logger.warning(f"应用优惠券 '{coupon_code}' 到用户 {user_id} 账单 {record_id} 失败: {e}")
            self.db.rollback()
            raise e
        except Exception as e:
            logger.error(f"应用优惠券 '{coupon_code}' 到用户 {user_id} 账单 {record_id} 时发生意外错误: {e}", exc_info=True)
            self.db.rollback()
            raise GatewayException(message=f"应用优惠券时发生内部错误", code=500)

    # --- 支付流程相关方法 --- 

    def initiate_payment(self, user_id: int, record_id: int, gateway_name: str = 'stripe') -> Dict[str, Any]:
        """
        为指定账单发起支付流程 (使用 Stripe)。
        
        :param user_id: 用户 ID
        :param record_id: 待支付账单记录 ID
        :param gateway_name: 支付网关名称 (目前仅支持 'stripe')
        :return: 包含 Stripe PaymentIntent client_secret 的字典
        :raises NotFoundException: 如果账单或支付网关配置 (Stripe密钥) 未找到
        :raises InvalidInputException: 如果账单状态不正确或金额为零
        :raises GatewayException: 如果与 Stripe API 交互时出错或发生内部错误
        """
        logger.info(f"用户 {user_id} 尝试为账单 {record_id} 通过网关 '{gateway_name}' 发起支付")
        if gateway_name != 'stripe':
             logger.error(f"尝试使用不支持的支付网关: {gateway_name}")
             raise InvalidInputException(f"当前仅支持 Stripe 支付网关")
        
        if not settings.STRIPE_SECRET_KEY:
            logger.error("Stripe Secret Key 未在配置中设置 (STRIPE_SECRET_KEY)")
            raise GatewayException("支付网关配置错误", code=503) # Service Unavailable

        stripe.api_key = settings.STRIPE_SECRET_KEY # 设置 Stripe API Key

        try:
            # 1. 获取账单详情，验证归属权和状态
            record = self.get_billing_detail(user_id, record_id)
            if record.status != 0: # 0: pending
                logger.warning(f"尝试支付非待处理账单 {record_id} (状态: {record.status})")
                raise InvalidInputException(f"账单状态不正确，无法支付")
            if record.total_amount_due <= Decimal('0.00'):
                logger.warning(f"尝试支付零金额账单 {record_id}")
                raise InvalidInputException("账单金额为零或负数，无需支付")

            # 2. 获取支付网关信息 (可选，主要为了记录 gateway_id)
            gateway = self.db.query(PaymentGateway).filter(PaymentGateway.name == gateway_name).first()
            if not gateway:
                 # 如果数据库中没有 stripe 网关记录，可以考虑自动创建或记录警告
                 logger.warning(f"数据库中未找到名为 '{gateway_name}' 的支付网关记录，但仍将继续支付流程")
                 gateway_id = None
            else:
                 gateway_id = gateway.id
            
            # 3. 创建 Stripe PaymentIntent
            try:
                # 将金额转换为最小货币单位 (例如，分)
                # TODO: 需要确定货币类型 (例如从 settings 或 plan 获取)
                currency = 'cny' # 或者 'usd' 等, 应该来自配置
                amount_in_cents = int(record.total_amount_due * 100)
                
                logger.debug(f"为账单 {record_id} 创建 Stripe PaymentIntent: 金额={amount_in_cents}{currency.upper()}, Metadata={{'billing_record_id': {record.id}, 'user_id': {user_id}}}")
                
                payment_intent = stripe.PaymentIntent.create(
                    amount=amount_in_cents,
                    currency=currency,
                    metadata={
                        'billing_record_id': str(record.id), # Metadata 值必须是字符串
                        'user_id': str(user_id)
                    },
                    # 可以添加其他参数，如 payment_method_types, description 等
                    description=f"支付账单 #{record.id}",
                    # receipt_email=... # 可以考虑从 User 模型获取用户邮箱
                )
                
                client_secret = payment_intent.client_secret
                logger.info(f"成功为账单 {record_id} 创建 Stripe PaymentIntent (ID: {payment_intent.id})")

            except stripe.error.StripeError as e:
                logger.error(f"创建 Stripe PaymentIntent 时出错 (账单 {record_id}): {e}", exc_info=True)
                raise GatewayException(f"与支付网关通信失败: {e.user_message or e.code}", code=502) # Bad Gateway
            except Exception as e:
                logger.error(f"创建 Stripe PaymentIntent 时发生未知错误 (账单 {record_id}): {e}", exc_info=True)
                raise GatewayException("创建支付意图时发生内部错误", code=500)

            # 4. (可选) 更新账单记录的 payment_gateway_id
            if gateway_id and record.payment_gateway_id != gateway_id:
                 record.payment_gateway_id = gateway_id
                 try:
                     self.db.commit()
                     logger.debug(f"账单 {record_id} 的 payment_gateway_id 已更新为 {gateway_id}")
                 except Exception as e:
                     self.db.rollback()
                     logger.error(f"更新账单 {record_id} 的 payment_gateway_id 时出错: {e}", exc_info=True)
                     # 即使这里失败，支付意图已创建，所以不影响主流程
            
            # 5. 返回 client_secret 给前端
            return {"client_secret": client_secret}

        except (NotFoundException, InvalidInputException, GatewayException) as e:
            logger.warning(f"为账单 {record_id} 发起支付失败: {e}")
            raise e
        except Exception as e:
            logger.error(f"为用户 {user_id} 账单 {record_id} 发起支付时发生意外错误: {e}", exc_info=True)
            raise GatewayException("发起支付时发生内部错误", code=500)

    def handle_payment_callback(self, gateway_name: str, payload_bytes: bytes, headers: Dict[str, str]) -> bool:
        """
        处理来自支付网关的异步回调通知 (Webhook) (Stripe)。
        
        :param gateway_name: 发送回调的支付网关名称 (应为 'stripe')
        :param payload_bytes: 原始请求体字节串
        :param headers: 回调请求头 (包含 Stripe-Signature)
        :return: bool 指示处理是否成功
        :raises ForbiddenException: 如果 Webhook 签名验证失败
        :raises GatewayException: 如果处理过程中发生内部错误
        """
        logger.info(f"收到来自 '{gateway_name}' 的支付回调 Webhook")
        if gateway_name != 'stripe':
             logger.error(f"收到不支持的支付网关 '{gateway_name}' 的 Webhook")
             # 返回 True 告知网关已收到但无法处理，避免重试
             return True 
             
        if not settings.STRIPE_WEBHOOK_SECRET:
            logger.error("Stripe Webhook Secret 未在配置中设置 (STRIPE_WEBHOOK_SECRET)")
            raise GatewayException("支付网关 Webhook 配置错误", code=500)
        
        webhook_secret = settings.STRIPE_WEBHOOK_SECRET
        signature = headers.get('stripe-signature')
        
        if not signature:
            logger.error("Stripe Webhook 请求缺少 'Stripe-Signature' header")
            raise ForbiddenException("缺少 Webhook 签名")

        try:
            # 1. 验证 Webhook 签名并构造事件对象
            try:
                event = stripe.Webhook.construct_event(
                    payload_bytes, signature, webhook_secret
                )
                logger.info(f"Webhook 签名验证成功, 事件 ID: {event.id}, 类型: {event.type}")
            except ValueError as e:
                # 无效的 payload
                logger.error(f"Webhook 载荷无效: {e}", exc_info=True)
                raise GatewayException("Webhook 载荷无效", code=400)
            except stripe.error.SignatureVerificationError as e:
                # 无效的签名
                logger.error(f"Webhook 签名验证失败: {e}", exc_info=True)
                raise ForbiddenException("Webhook 签名验证失败")
            except Exception as e:
                logger.error(f"Webhook 事件构造时发生未知错误: {e}", exc_info=True)
                raise GatewayException("处理 Webhook 时发生内部错误", code=500)

            # 2. 从事件中提取数据
            event_type = event.type
            data_object = event.data.object # 这通常是 PaymentIntent 或其他相关对象
            metadata = data_object.get('metadata', {}) # PaymentIntent 对象包含 metadata
            billing_record_id_str = metadata.get('billing_record_id')
            user_id_str = metadata.get('user_id') # 我们之前也放了 user_id

            logger.info(f"处理 Webhook 事件: 类型='{event_type}', Metadata={{'billing_record_id': '{billing_record_id_str}', 'user_id': '{user_id_str}'}}")

            if not billing_record_id_str:
                 logger.error(f"Webhook 事件 {event.id} (类型: {event_type}) 缺少 metadata.billing_record_id")
                 return True # 无法处理，告知网关已收到
            
            try:
                billing_record_id = int(billing_record_id_str)
            except ValueError:
                logger.error(f"Webhook 事件 {event.id} 中的 billing_record_id 无效 ('{billing_record_id_str}')")
                return True

            # 3. 根据事件类型更新账单状态 (主要关注 PaymentIntent 事件)
            if event_type.startswith('payment_intent.'):
                payment_intent_id = data_object.id
                if event_type == 'payment_intent.succeeded':
                    logger.info(f"PaymentIntent Succeeded: ID={payment_intent_id}, 账单 ID={billing_record_id}")
                    record = self.db.query(BillingRecord).filter(BillingRecord.id == billing_record_id).first()
                    if not record:
                        logger.error(f"支付成功回调关联的账单记录 {billing_record_id} (PI: {payment_intent_id}) 未找到")
                        return True 
                    
                    if record.status == 0: # 仅更新待支付状态
                        record.status = 1 # 1: paid
                        record.paid_at = datetime.datetime.utcnow()
                        record.transaction_id = payment_intent_id # 记录 PI ID
                        # record.payment_gateway_id 应该在 initiate 时已设置，或在此处设置
                        gateway = self.db.query(PaymentGateway).filter(PaymentGateway.name == gateway_name).first()
                        if gateway:
                            record.payment_gateway_id = gateway.id
                        
                        self.db.commit()
                        logger.info(f"账单 {billing_record_id} (PI: {payment_intent_id}) 状态已更新为 Paid")
                        # TODO: 触发后续逻辑
                    else:
                        logger.warning(f"收到账单 {billing_record_id} (PI: {payment_intent_id}) 的支付成功事件，但账单当前状态为 {record.status}，不执行更新")
                        
                elif event_type == 'payment_intent.payment_failed':
                     logger.warning(f"PaymentIntent Failed: ID={payment_intent_id}, 账单 ID={billing_record_id}")
                     record = self.db.query(BillingRecord).filter(BillingRecord.id == billing_record_id).first()
                     if record and record.status == 0:
                         record.status = 2 # 2: failed
                         record.transaction_id = payment_intent_id # 也记录失败的 PI ID
                         self.db.commit()
                         logger.info(f"账单 {billing_record_id} (PI: {payment_intent_id}) 状态已更新为 Failed")
                         # TODO: 触发支付失败通知
                     else:
                         logger.warning(f"收到账单 {billing_record_id} (PI: {payment_intent_id}) 的支付失败事件，但未找到账单或状态不为 pending ({record.status if record else 'Not Found'})，不执行更新")
                else:
                     logger.info(f"收到未处理的 PaymentIntent 事件类型: '{event_type}' (PI: {payment_intent_id})，忽略")
            else:
                # 可以根据需要处理其他类型的事件，如 invoice.paid, checkout.session.completed 等
                 logger.info(f"收到非 PaymentIntent 事件类型: '{event_type}' (事件 ID: {event.id})，忽略")

            # 4. 返回成功
            return True

        except (ForbiddenException, GatewayException) as e:
            # 签名失败或内部网关错误
            logger.error(f"处理来自 '{gateway_name}' 的 Webhook 失败: {e}")
            # 通常不应将内部错误细节返回给外部调用者
            # 对于签名失败，应该返回 403 或根据网关要求
            # 这里统一抛出，让上层路由返回合适的错误码
            raise e 
        except Exception as e:
            logger.error(f"处理来自 '{gateway_name}' 的 Webhook 时发生意外错误: {e}", exc_info=True)
            # 抛出 GatewayException 避免将原始异常暴露
            raise GatewayException("处理支付回调时发生内部错误", code=500)

    # 可能还需要支付相关的服务方法，例如：
    # def initiate_payment(self, user_id: int, record_id: int) -> Dict[str, Any]:
    #     """为特定账单发起支付流程"""
    #     raise NotImplementedError("发起支付服务逻辑待实现")
    # 
    # def handle_payment_callback(self, gateway_name: str, payload: Dict[str, Any]) -> None:
    #     """处理来自支付网关的回调"""
    #     raise NotImplementedError("处理支付回调服务逻辑待实现") 