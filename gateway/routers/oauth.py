"""
OAuth 认证相关路由
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from core.database import get_db
from core.schemas import StandardResponse, TokenResponse
from core.auth import JWTBearer, Auth
from core.models.user import User, UserAuthentication
from core.exceptions import InvalidCredentialsException, UserExistsException, NotFoundException
import logging

router = APIRouter(
    prefix="/api/v1/auth", # 继续使用 /auth 前缀
    tags=["oauth"],       # 单独的 tag
    responses={401: {"description": "认证失败"}}
)

# Pydantic 模型
class OAuthDeleteRequest(BaseModel):
    authentication_id: int

class UserAuthenticationResponse(BaseModel):
    id: int
    provider: str
    provider_user_id: str # 注意：可能需要隐藏部分 ID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

logger = logging.getLogger(__name__)

@router.get("/{provider}/login", summary="重定向到第三方登录")
async def oauth_login(provider: str, request: Request):
    """根据 provider 重定向到相应的第三方认证页面"""
    # TODO: 实现服务层逻辑 OAuthService.get_authorization_url(provider, request)
    # 返回 RedirectResponse
    raise NotImplementedError("OAuth 登录端点待实现")

@router.get("/{provider}/callback", summary="处理第三方回调")
async def oauth_callback(provider: str, request: Request, db: Session = Depends(get_db)):
    """处理第三方认证回调，完成用户登录或注册，并返回 JWT"""
    # TODO: 实现服务层逻辑 OAuthService.handle_callback(provider, request, db)
    # 返回包含 JWT 的 StandardResponse
    raise NotImplementedError("OAuth 回调端点待实现")

@router.get(
    "/authentications/list",
    response_model=StandardResponse,
    summary="获取用户绑定的认证方式"
)
async def get_user_authentications(
    current_user: User = Depends(JWTBearer()),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """获取当前用户已绑定的所有第三方认证方式"""
    # TODO: 可以移到 services.user_service.get_authentications(current_user.id, db)
    authentications = db.query(UserAuthentication).filter(
        UserAuthentication.tenant_id == current_user.id
    ).all()
    
    # 转换数据格式，避免暴露敏感信息（如果 provider_user_id 敏感）
    response_data = [UserAuthenticationResponse.model_validate(auth) for auth in authentications]
    
    return StandardResponse(
        message="获取认证方式成功",
        data=response_data
    )

@router.post(
    "/authentications/delete",
    response_model=StandardResponse,
    summary="解绑认证方式"
)
async def delete_user_authentication(
    request_body: OAuthDeleteRequest,
    current_user: User = Depends(JWTBearer()),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """解绑当前用户指定的某个认证方式"""
    # TODO: 移到 services.user_service.delete_authentication(current_user.id, request_body.authentication_id, db)
    auth_to_delete = db.query(UserAuthentication).filter(
        UserAuthentication.id == request_body.authentication_id,
        UserAuthentication.tenant_id == current_user.id
    ).first()
    
    if not auth_to_delete:
        raise HTTPException(status_code=404, detail="未找到要解绑的认证方式")
        
    # 考虑添加逻辑：如果用户只剩下最后一种认证方式，是否允许解绑？
    # count = db.query(UserAuthentication).filter(UserAuthentication.tenant_id == current_user.id).count()
    # if count <= 1:
    #     raise HTTPException(status_code=400, detail="无法解绑唯一的认证方式")
        
    db.delete(auth_to_delete)
    db.commit()
    
    return StandardResponse(message="认证方式解绑成功") 