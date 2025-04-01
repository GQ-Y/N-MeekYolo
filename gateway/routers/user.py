"""
用户相关路由
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any
from ..core.database import get_db
from ..core.models import User, ProfileUpdate, PasswordUpdate, TokenUpdate, StandardResponse
from ..core.auth import Auth, JWTBearer
from ..core.exceptions import InvalidCredentialsException
import uuid

router = APIRouter(
    prefix="/api/v1/user",
    tags=["user"],
    responses={401: {"description": "认证失败"}}
)

# 请求模型
class ProfileUpdate(BaseModel):
    """个人资料更新请求"""
    nickname: str
    phone: Optional[str] = None

class PasswordUpdate(BaseModel):
    """密码更新请求"""
    old_password: str
    new_password: str

class TokenUpdate(BaseModel):
    """口令更新请求"""
    old_token: str
    new_token: str

# 路由处理函数
@router.get(
    "/profile",
    response_model=StandardResponse,
    summary="获取用户信息",
    description="获取当前登录用户的个人信息，包括用户名、昵称和电话号码"
)
async def get_profile(
    request: Request,
    db: Session = Depends(get_db),
    token_data: dict = Depends(JWTBearer())
):
    """获取用户信息"""
    user = db.query(User).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    return StandardResponse(
        requestId=str(uuid.uuid4()),
        path=request.url.path,
        success=True,
        message="获取用户信息成功",
        code=200,
        data={
            "username": user.username,
            "nickname": user.nickname,
            "phone": user.phone
        }
    )

@router.post(
    "/profile",
    response_model=StandardResponse,
    summary="更新用户信息",
    description="更新当前登录用户的个人信息，包括昵称和电话号码"
)
async def update_profile(
    request: Request,
    profile: ProfileUpdate,
    db: Session = Depends(get_db),
    token_data: dict = Depends(JWTBearer())
):
    """更新用户信息"""
    user = db.query(User).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    user.nickname = profile.nickname
    user.phone = profile.phone
    
    db.commit()
    db.refresh(user)
    
    return StandardResponse(
        requestId=str(uuid.uuid4()),
        path=request.url.path,
        success=True,
        message="用户信息更新成功",
        code=200,
        data={
            "username": user.username,
            "nickname": user.nickname,
            "phone": user.phone
        }
    )

@router.post(
    "/password",
    response_model=StandardResponse,
    summary="修改密码",
    description="修改当前登录用户的密码，需要提供旧密码进行验证"
)
async def update_password(
    request: Request,
    password_update: PasswordUpdate,
    db: Session = Depends(get_db),
    token_data: dict = Depends(JWTBearer())
):
    """修改密码"""
    user = db.query(User).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if not Auth.verify_password(password_update.old_password, user.password):
        raise InvalidCredentialsException()
        
    user.password = Auth.hash_password(password_update.new_password)
    
    db.commit()
    
    return StandardResponse(
        requestId=str(uuid.uuid4()),
        path=request.url.path,
        success=True,
        message="密码修改成功",
        code=200,
        data=None
    )

@router.post(
    "/token",
    response_model=StandardResponse,
    summary="修改口令",
    description="修改当前登录用户的口令，需要提供旧口令进行验证"
)
async def update_token(
    request: Request,
    token_update: TokenUpdate,
    db: Session = Depends(get_db),
    token_data: dict = Depends(JWTBearer())
):
    """修改口令"""
    user = db.query(User).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if not Auth.verify_token(token_update.old_token, user.token):
        raise InvalidCredentialsException()
        
    user.token = Auth.hash_token(token_update.new_token)
    
    db.commit()
    
    return StandardResponse(
        requestId=str(uuid.uuid4()),
        path=request.url.path,
        success=True,
        message="口令修改成功",
        code=200,
        data=None
    ) 