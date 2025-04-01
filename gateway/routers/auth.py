"""
认证相关路由
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..core.auth import Auth
from ..core.models import LoginRequest, RegisterRequest, TokenResponse, StandardResponse
from ..core.exceptions import InvalidCredentialsException, UserExistsException

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

@router.post("/register")
async def register(
    request: RegisterRequest,
    db: Session = Depends(get_db)
) -> StandardResponse:
    """用户注册"""
    try:
        user_data = Auth.register_user(
            db=db,
            username=request.username,
            password=request.password,
            token=request.token
        )
        
        # 创建访问令牌
        access_token = Auth.create_access_token(data=user_data)
        
        return StandardResponse(
            success=True,
            message="注册成功",
            code=200,
            data=TokenResponse(
                access_token=access_token,
                token_type="bearer",
                expires_in=3600
            ).dict()
        )
    except UserExistsException as e:
        return StandardResponse(
            success=False,
            message=str(e),
            code=409,
            data=None
        )
    except Exception as e:
        return StandardResponse(
            success=False,
            message=str(e),
            code=500,
            data=None
        )

@router.post("/login")
async def login(
    request: LoginRequest,
    db: Session = Depends(get_db)
) -> StandardResponse:
    """用户登录"""
    try:
        user_data = Auth.authenticate_user(
            db=db,
            username=request.username,
            password=request.password,
            token=request.token
        )
        
        # 检查是否需要注册
        if "needs_registration" in user_data:
            return StandardResponse(
                success=False,
                message="用户不存在，请先注册",
                code=404,
                data={"needs_registration": True}
            )
        
        # 创建访问令牌
        access_token = Auth.create_access_token(data=user_data)
        
        return StandardResponse(
            success=True,
            message="登录成功",
            code=200,
            data=TokenResponse(
                access_token=access_token,
                token_type="bearer",
                expires_in=3600
            ).dict()
        )
    except InvalidCredentialsException as e:
        return StandardResponse(
            success=False,
            message=str(e),
            code=401,
            data=None
        )
    except Exception as e:
        return StandardResponse(
            success=False,
            message=str(e),
            code=500,
            data=None
        ) 