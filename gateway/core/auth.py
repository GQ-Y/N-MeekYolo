"""
认证相关工具类
"""
import jwt
import hashlib
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from .database import get_db
from .models import User
from .exceptions import (
    InvalidCredentialsException,
    TokenExpiredException,
    InvalidTokenException,
    UserExistsException
)

# 配置信息
JWT_SECRET = "your-secret-key"  # 生产环境应该使用环境变量
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 60

class Auth:
    """认证工具类"""
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        return hashlib.sha256(plain_password.encode()).hexdigest() == hashed_password
    
    @staticmethod
    def verify_token(plain_token: str, hashed_token: str) -> bool:
        """验证口令"""
        return hashlib.sha256(plain_token.encode()).hexdigest() == hashed_token
    
    @staticmethod
    def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """创建访问令牌"""
        to_encode = data.copy()
        if expires_delta:
            expire = time.time() + expires_delta.total_seconds()
        else:
            expire = time.time() + TOKEN_EXPIRE_MINUTES * 60
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
        return encoded_jwt
    
    @staticmethod
    def decode_token(token: str) -> Dict[str, Any]:
        """解码令牌"""
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            if payload["exp"] < time.time():
                raise TokenExpiredException()
            return payload
        except jwt.ExpiredSignatureError:
            raise TokenExpiredException()
        except jwt.InvalidTokenError:
            raise InvalidTokenException()
    
    @classmethod
    def register_user(cls, db: Session, username: str, password: str, token: str) -> Dict[str, Any]:
        """注册用户
        
        Args:
            db: 数据库会话
            username: 用户名
            password: 密码
            token: 口令
            
        Returns:
            Dict[str, Any]: 用户数据
            
        Raises:
            UserExistsException: 已存在用户
        """
        # 检查是否已经存在用户
        if db.query(User).first() is not None:
            raise UserExistsException()
            
        # 创建新用户
        user = User(
            username=username,
            password=hashlib.sha256(password.encode()).hexdigest(),
            token=hashlib.sha256(token.encode()).hexdigest()
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        
        return {"sub": username}
    
    @classmethod
    def authenticate_user(cls, db: Session, username: str, password: str, token: str) -> Dict[str, Any]:
        """用户认证
        
        Args:
            db: 数据库会话
            username: 用户名
            password: 密码
            token: 口令
            
        Returns:
            Dict[str, Any]: 用户数据
            
        Raises:
            InvalidCredentialsException: 认证失败
        """
        # 获取用户
        user = db.query(User).first()
        
        # 如果没有用户，返回需要注册
        if user is None:
            return {"needs_registration": True}
            
        # 验证用户名
        if username != user.username:
            raise InvalidCredentialsException()
            
        # 验证密码和口令
        if not cls.verify_password(password, user.password) or \
           not cls.verify_token(token, user.token):
            raise InvalidCredentialsException()
            
        return {"sub": username}

class JWTBearer(HTTPBearer):
    """JWT Bearer认证"""
    
    def __init__(self, auto_error: bool = True):
        super().__init__(auto_error=auto_error)
    
    async def __call__(self, request: Request, db: Session = Depends(get_db)) -> Dict[str, Any]:
        credentials: HTTPAuthorizationCredentials = await super().__call__(request)
        if not credentials:
            raise InvalidTokenException()
            
        if credentials.scheme.lower() != "bearer":
            raise InvalidTokenException()
            
        return Auth.decode_token(credentials.credentials) 