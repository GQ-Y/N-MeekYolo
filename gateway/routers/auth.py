"""
认证相关路由
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from core.database import get_db
from core.schemas import (
    LoginRequest, 
    RegisterRequest, 
    PasswordResetRequest,
    PasswordResetConfirm,
    StandardResponse
)
from core.exceptions import InvalidCredentialsException, UserExistsException, GatewayException, InvalidTokenException
from services.auth_service import AuthService
from pydantic import BaseModel, Field
import logging
import uuid

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/auth", 
    tags=["认证与授权"],
    responses={
        400: {"description": "无效请求"},
        401: {"description": "认证失败"},
        404: {"description": "资源未找到"},
        409: {"description": "冲突 (例如，用户已存在)"},
        500: {"description": "内部服务器错误"}
    }
)

@router.post(
    "/register", 
    status_code=201,
    response_model=StandardResponse,
    summary="用户注册"
) 
async def register(
    request_body: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db)
) -> StandardResponse:
    """用户注册接口"""
    auth_service = AuthService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        new_user = auth_service.register_user(
            username=request_body.username,
            password=request_body.password,
            email=request_body.email,
            nickname=request_body.nickname
        )
        logger.info(f"用户 {new_user.username} (ID: {new_user.id}) 注册成功")
        return StandardResponse(
            requestId=req_id, 
            path=request.url.path,
            success=True,
            message="注册成功，请登录",
            code=201,
        )
    except UserExistsException as e:
        logger.warning(f"注册失败: {e} (Request ID: {req_id})")
        raise HTTPException(status_code=409, detail=str(e))
    except GatewayException as e:
        logger.error(f"注册时网关错误: {e} (Request ID: {req_id})")
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"注册时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="注册过程中发生内部错误")

@router.post(
    "/login",
    response_model=StandardResponse,
    summary="用户登录"
)
async def login(
    request_body: LoginRequest,
    request: Request,
    db: Session = Depends(get_db)
) -> StandardResponse:
    """用户登录接口，成功则返回 JWT 令牌和用户信息"""
    auth_service = AuthService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        auth_result = auth_service.authenticate_user(
            username=request_body.username,
            password=request_body.password
        )
        logger.info(f"用户 {request_body.username} 登录成功 (Request ID: {req_id})")
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            message="登录成功",
            code=200,
            data=auth_result
        )
    except InvalidCredentialsException as e:
        logger.warning(f"登录失败: {e} (Request ID: {req_id})")
        raise HTTPException(status_code=401, detail=str(e))
    except GatewayException as e:
        logger.error(f"登录时网关错误: {e} (Request ID: {req_id})")
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"登录时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="登录过程中发生内部错误")

@router.post(
    "/password/request-reset",
    response_model=StandardResponse,
    summary="请求密码重置",
    status_code=200
)
async def request_password_reset_endpoint(
    request_body: PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db)
) -> StandardResponse:
    """用户提交邮箱以请求密码重置链接/令牌"""
    auth_service = AuthService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        _ = auth_service.request_password_reset(email=request_body.email)
        logger.info(f"收到邮箱 {request_body.email} 的密码重置请求 (Request ID: {req_id})")
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True, 
            code=200,
            message="如果邮箱地址存在于我们的系统中，您将很快收到一封包含密码重置说明的邮件。"
        )
    except GatewayException as e:
        logger.error(f"请求密码重置时网关错误: {e} (Request ID: {req_id})")
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"请求密码重置时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="请求密码重置时发生内部错误")

@router.post(
    "/password/reset",
    response_model=StandardResponse,
    summary="使用令牌重置密码"
)
async def reset_password_endpoint(
    request_body: PasswordResetConfirm,
    request: Request,
    db: Session = Depends(get_db)
) -> StandardResponse:
    """使用从邮件中获取的有效令牌和新密码来重置用户密码"""
    auth_service = AuthService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        success = auth_service.reset_password(
            token=request_body.token,
            new_password=request_body.new_password
        )
        logger.info(f"密码重置成功 (Request ID: {req_id})")
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            code=200,
            message="密码已成功重置，您现在可以使用新密码登录。"
        )
    except InvalidTokenException as e:
        logger.warning(f"密码重置失败: {e} (Request ID: {req_id})")
        raise HTTPException(status_code=400, detail=str(e) or "密码重置令牌无效或已过期，请重新请求。")
    except GatewayException as e:
        logger.error(f"重置密码时网关错误: {e} (Request ID: {req_id})")
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"重置密码时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="重置密码时发生内部错误") 