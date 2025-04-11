"""
用户相关路由
"""
import logging # 添加 logging
from fastapi import APIRouter, Depends, HTTPException, Request, status # <-- 导入 status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any
from types import NoneType # <-- 导入 NoneType
from core.database import get_db
from core.models.user import User
from core.schemas import UserProfileUpdate, PasswordUpdate, StandardResponse, UserResponse
from core.auth import Auth, JWTBearer # <-- 移除 get_current_active_user
from services.user_service import UserService, get_user_service # <-- 导入 get_user_service
from core.exceptions import InvalidCredentialsException, NotFoundException, GatewayException
import uuid
from core.schemas import StandardResponse

# 获取 logger
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/user",
    tags=["用户接口"], # 更新 tag 名称
    responses={
        401: {"description": "认证失败"},
        404: {"description": "资源未找到"}, # 添加 404
        500: {"description": "内部服务器错误"} # 添加 500
    }
)

# 路由处理函数
@router.get(
    "/profile",
    response_model=StandardResponse[UserResponse],
    summary="获取当前用户信息",
    description="获取当前登录用户的详细个人信息",
    responses={
        200: {"description": "成功获取用户信息"},
        401: {"description": "认证失败"},
        404: {"description": "资源未找到"},
        500: {"description": "内部服务器错误"},
    },
    dependencies=[Depends(JWTBearer())] # <-- 使用 JWTBearer()
)
async def get_profile(
    current_user: User = Depends(JWTBearer()), # <-- 使用 JWTBearer()
    service: UserService = Depends(get_user_service),
    request: Request = None # 获取 Request 对象
):
    """
    获取当前用户的个人资料
    """
    request_id = getattr(request.state, "request_id", "N/A") if request else "N/A"
    logger.info(f"用户 {current_user.id} 正在尝试获取个人资料")
    try:
        # service 层现在应该直接返回 User 模型或者处理好的 UserResponse 数据
        # 这里假设 service.get_user_info 返回的是 UserResponse 兼容的数据或 User 模型
        # 如果 service 返回 User 模型，需要在这里转换为 UserResponse
        # 为了简化，我们假设 current_user 已经是填充好的 User 模型
        
        # 直接从 current_user 构建 UserResponse
        user_info = UserResponse.model_validate(current_user) 

        logger.info(f"成功获取用户 {current_user.id} 的个人资料")
        # 使用 StandardResponse 包装返回数据
        return StandardResponse(
            success=True,
            message="用户信息获取成功",
            code=200,
            data=user_info,
            requestId=request_id,
            path=request.url.path if request else "/api/v1/user/profile"
        )
    except Exception as e:
        logger.error(f"获取用户 {current_user.id} 信息时发生未知错误: {e}", exc_info=True)
        # 统一错误响应格式
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=StandardResponse(
                success=False,
                message="获取用户信息时发生内部错误",
                code=500,
                requestId=request_id,
                path=request.url.path if request else "/api/v1/user/profile"
            ).model_dump() # 返回 StandardResponse 的 dict 表示
        )

@router.post(
    "/profile",
    response_model=StandardResponse[UserResponse],
    summary="更新当前用户信息",
    description="更新当前登录用户的个人信息，如昵称、电话等",
    responses={
        200: {"description": "用户信息更新成功"},
        401: {"description": "认证失败"},
        404: {"description": "资源未找到"},
        500: {"description": "内部服务器错误"},
    },
)
async def update_profile(
    request: Request,
    profile_update: UserProfileUpdate, 
    service: UserService = Depends(get_user_service), # <-- 使用依赖注入获取 Service
    current_user: User = Depends(JWTBearer())
) -> StandardResponse:
    """更新当前用户的个人信息"""
    # user_service = UserService(db) # <-- 移除手动实例化
    request_id = getattr(request.state, "request_id", str(uuid.uuid4())) # 获取 request_id
    try:
        updated_user = service.update_user_profile(current_user.id, profile_update)
        updated_user_data = UserResponse.model_validate(updated_user)

        return StandardResponse(
            requestId=request_id,
            path=request.url.path,
            success=True, # <-- 添加 success
            message="用户信息更新成功",
            code=200, # <-- 添加 code
            data=updated_user_data
        )
    except NotFoundException as e:
        logger.warning(f"更新用户 {current_user.id} 信息失败: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except GatewayException as e:
        logger.error(f"更新用户 {current_user.id} 信息时服务端出错: {e}", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"更新用户 {current_user.id} 信息时发生未知错误: {e}", exc_info=True)
        # 可以在这里检查 e 是否为 IntegrityError 并给出更具体的提示
        # 但目前保持通用错误
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="更新用户信息时发生内部错误" # 可以考虑返回 StandardResponse 结构
        )

@router.post(
    "/password",
    response_model=StandardResponse[NoneType],
    summary="修改当前用户密码",
    description="修改当前登录用户的密码，需要提供旧密码进行验证",
    responses={
        200: {"description": "密码修改成功"},
        401: {"description": "认证失败"},
        400: {"description": "旧密码错误或新密码格式无效"}, # 添加400错误描述
        404: {"description": "资源未找到"},
        500: {"description": "内部服务器错误"},
    },
)
async def update_password(
    request: Request,
    password_update: PasswordUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(JWTBearer())
) -> StandardResponse: # 添加返回类型提示
    """修改当前用户的密码"""
    try:
        if not Auth.verify_password(password_update.old_password, current_user.password):
            logger.warning(f"用户 {current_user.id} 修改密码失败：旧密码错误")
            raise InvalidCredentialsException("旧密码不正确")

        current_user.password = Auth.hash_password(password_update.new_password)
        db.commit()
        logger.info(f"用户 {current_user.id} 密码修改成功")

        return StandardResponse(
            requestId=getattr(request.state, "request_id", str(uuid.uuid4())),
            path=request.url.path,
            success=True,
            message="密码修改成功",
            code=200,
            data=None
        )
    except InvalidCredentialsException as e:
        # 此异常由 Auth.verify_password 或手动引发
        raise HTTPException(status_code=400, detail=str(e)) # 返回 400 Bad Request
    except Exception as e:
        db.rollback() # 确保回滚
        logger.error(f"用户 {current_user.id} 修改密码时发生未知错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="修改密码时发生内部错误") 