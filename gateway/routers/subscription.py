"""
用户订阅管理相关路由
"""
import logging # 添加 logging
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
# 移除本地 Pydantic 定义
# from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Any, Dict
import datetime
import uuid # 添加 uuid

from core.database import get_db
# 从 core.schemas 导入标准模型
from core.schemas import (
    StandardResponse, 
    SubscriptionPlanResponse, 
    SubscriptionResponse, 
    SubscriptionCreateRequest
)
from core.auth import JWTBearer
from core.models.user import User # 正确导入 User
from core.models.subscription import SubscriptionPlan, UserSubscription # 正确导入订阅相关模型
# 导入服务和异常
from services.subscription_service import SubscriptionService
from core.exceptions import (
    GatewayException, 
    NotFoundException, 
    AlreadyExistsException # 添加 AlreadyExistsException
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/subscription",
    tags=["用户订阅"], # 更新 tag
    responses={
        400: {"description": "无效请求"},
        401: {"description": "认证失败"},
        404: {"description": "资源未找到"},
        409: {"description": "冲突 (例如，订阅已存在)"},
        500: {"description": "内部服务器错误"}
    }
)

# --- 移除本地 Pydantic 模型定义 ---
# class SubscriptionPlanResponse(BaseModel):
#     ...
# class UserSubscriptionResponse(BaseModel):
#     ...
# class SubscriptionChangeRequest(BaseModel):
#     ...

# --- 路由 --- 

# 路由: 获取可用订阅计划 (GET /plans)
@router.get(
    "/plans", # <-- 使用 /plans 路径
    response_model=StandardResponse[List[SubscriptionPlanResponse]], # 返回计划列表
    summary="获取可用订阅计划"
)
async def get_available_plans(
    request: Request,
    db: Session = Depends(get_db)
    # 这个接口通常不需要用户认证，所以移除 current_user: User = Depends(JWTBearer())
) -> StandardResponse:
    """获取所有当前激活的订阅计划列表"""
    sub_service = SubscriptionService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        # 调用服务层获取激活计划
        plans = sub_service.get_active_plans()
        # 转换 ORM 列表为 Pydantic 响应模型列表
        response_data = [SubscriptionPlanResponse.model_validate(plan) for plan in plans]
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            message="获取可用订阅计划成功",
            code=200,
            data=response_data
        )
    except GatewayException as e:
        logger.error(f"获取可用套餐路由出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"获取可用套餐路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="获取可用订阅计划时发生内部错误")

# 重构获取当前订阅的路由
@router.get(
    "/current", 
    response_model=StandardResponse[Optional[SubscriptionResponse]], # data 可以是 SubscriptionResponse 或 None
    summary="获取当前用户活动订阅"
)
async def get_my_subscription(
    request: Request,
    current_user: User = Depends(JWTBearer()),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """获取当前认证用户的活动订阅信息"""
    sub_service = SubscriptionService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        # 调用服务层获取活动订阅 (可能返回 None)
        subscription = sub_service.get_user_subscription(current_user.id)
        
        response_data: Optional[SubscriptionResponse] = None
        if subscription:
            # 转换 ORM 模型为 Pydantic 模型
            response_data = SubscriptionResponse.model_validate(subscription)
            message = "获取当前订阅成功"
        else:
            message = "未找到有效的活动订阅计划"
            
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            message=message,
            code=200,
            data=response_data
        )
    except GatewayException as e:
        logger.error(f"获取当前订阅路由出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"获取当前订阅路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="获取当前订阅信息时发生内部错误")

# TODO: 暂时注释掉未实现服务方法的路由
# @router.get(
#     "/history/list", 
#     response_model=StandardResponse[List[SubscriptionResponse]], # 更新响应模型
#     summary="获取用户订阅历史"
# )
# async def get_subscription_history(
#     request: Request,
#     current_user: User = Depends(JWTBearer()),
#     db: Session = Depends(get_db)
# ) -> StandardResponse:
#     """获取当前用户的所有历史订阅记录"""
#     sub_service = SubscriptionService(db)
#     req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
#     try:
#         # TODO: 实现 SubscriptionService.get_user_subscription_history()
#         subscriptions = sub_service.get_user_subscription_history(current_user.id)
#         response_data = [SubscriptionResponse.model_validate(sub) for sub in subscriptions]
#         return StandardResponse(
#             requestId=req_id,
#             path=request.url.path,
#             success=True,
#             message="获取订阅历史成功",
#             code=200,
#             data=response_data
#         )
#     except GatewayException as e:
#         logger.error(f"获取订阅历史路由出错: {e} (Request ID: {req_id})", exc_info=True)
#         raise HTTPException(status_code=e.code, detail=e.message)
#     except Exception as e:
#         logger.error(f"获取订阅历史路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
#         raise HTTPException(status_code=500, detail="获取订阅历史记录时发生内部错误")

# 添加创建订阅的路由
@router.post(
    "/create",
    response_model=StandardResponse[SubscriptionResponse],
    status_code=201,
    summary="创建新的订阅"
)
async def create_subscription_route(
    request_body: SubscriptionCreateRequest,
    request: Request,
    current_user: User = Depends(JWTBearer()),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """为当前认证用户创建新的订阅"""
    sub_service = SubscriptionService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        # 调用服务层创建订阅
        new_subscription = sub_service.create_subscription(
            user_id=current_user.id,
            plan_id=request_body.plan_id
        )
        # 转换模型
        response_data = SubscriptionResponse.model_validate(new_subscription)
        logger.info(f"用户 {current_user.id} 成功创建订阅 {response_data.id} (Request ID: {req_id})")
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            message="订阅创建成功",
            code=201,
            data=response_data
        )
    except AlreadyExistsException as e:
        logger.warning(f"创建订阅失败: {e} (Request ID: {req_id})")
        raise HTTPException(status_code=409, detail=str(e))
    except NotFoundException as e:
        logger.warning(f"创建订阅失败: {e} (Request ID: {req_id})")
        raise HTTPException(status_code=404, detail=str(e))
    except GatewayException as e:
        logger.error(f"创建订阅路由出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"创建订阅路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="创建订阅时发生内部错误")

# TODO: 暂时注释掉未实现服务方法的路由
# @router.post(
#     "/change", 
#     response_model=StandardResponse[SubscriptionResponse], # 更新响应模型
#     summary="更改订阅计划"
# )
# async def change_subscription(
#     request_body: SubscriptionChangeRequest, # 需要更新为 core.schemas 中的模型或创建一个
#     request: Request,
#     current_user: User = Depends(JWTBearer()),
#     db: Session = Depends(get_db)
# ) -> StandardResponse:
#     """用户选择或更改其订阅计划"""
#     sub_service = SubscriptionService(db)
#     req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
#     try:
#         # TODO: 实现 SubscriptionService.change_user_subscription()
#         updated_subscription = sub_service.change_user_subscription(
#             user_id=current_user.id,
#             new_plan_id=request_body.plan_id
#         )
#         response_data = SubscriptionResponse.model_validate(updated_subscription)
#         return StandardResponse(
#             requestId=req_id,
#             path=request.url.path,
#             success=True,
#             message="订阅计划更改成功",
#             code=200,
#             data=response_data
#         )
#     except NotImplementedError as e:
#         logger.warning(f"尝试调用未实现的更改订阅功能 (Request ID: {req_id})")
#         raise HTTPException(status_code=501, detail=str(e))
#     except NotFoundException as e:
#         logger.warning(f"更改订阅失败: {e} (Request ID: {req_id})")
#         raise HTTPException(status_code=404, detail=str(e))
#     except GatewayException as e:
#         logger.error(f"更改订阅路由出错: {e} (Request ID: {req_id})", exc_info=True)
#         raise HTTPException(status_code=e.code, detail=e.message)
#     except Exception as e:
#         logger.error(f"更改订阅路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
#         raise HTTPException(status_code=500, detail="更改订阅计划时发生内部错误")

# 重构取消订阅的路由
@router.delete(
    "/current", # 使用 DELETE /current
    response_model=StandardResponse[None], # 成功时 data 为 None
    summary="取消当前活动订阅"
)
async def cancel_my_subscription(
    request: Request,
    current_user: User = Depends(JWTBearer()),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """取消当前认证用户的活动订阅 (或取消自动续订，具体行为由服务层定义)"""
    sub_service = SubscriptionService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        # 调用服务层取消订阅
        success = sub_service.cancel_subscription(user_id=current_user.id)
        
        # 修正：检查服务层返回结果
        if success:
            logger.info(f"用户 {current_user.id} 成功取消订阅 (Request ID: {req_id})")
            return StandardResponse(
                requestId=req_id,
                path=request.url.path,
                success=True,
                message="订阅已成功取消",
                code=200,
                data=None
            )
        else:
            # 理论上，如果 cancel_subscription 返回 False 而不是抛 NotFoundException，
            # 这里可以处理这种情况。但在当前实现下，可能不会执行到这里。
            logger.warning(f"取消用户 {current_user.id} 订阅失败，服务层返回 False (Request ID: {req_id})")
            # 返回 404 或其他适当错误
            raise HTTPException(status_code=404, detail="无法取消订阅，未找到活动订阅或发生错误。") 
            
    except NotFoundException as e:
        logger.warning(f"取消订阅失败: {e} (Request ID: {req_id})")
        raise HTTPException(status_code=404, detail=str(e))
    except GatewayException as e:
        logger.error(f"取消订阅路由出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"取消订阅路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="取消订阅时发生内部错误") 