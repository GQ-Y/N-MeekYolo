"""
认证相关工具类
"""
import jwt
import hashlib
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from fastapi import Request, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session, joinedload
from .database import get_db
from .models.user import User, Role
from .exceptions import (
    InvalidCredentialsException,
    TokenExpiredException,
    InvalidTokenException,
    UserExistsException
)
from sqlalchemy.sql import func

# --- 从配置导入 JWT 设置 --- 
from core.config import settings

class Auth:
    """认证工具类"""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """对密码进行哈希"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        return Auth.hash_password(plain_password) == hashed_password
    
    @staticmethod
    def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """创建访问令牌"""
        to_encode = data.copy()
        if expires_delta:
            expire = time.time() + expires_delta.total_seconds()
        else:
            # 使用配置中的过期时间
            expire = time.time() + settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60 
        to_encode.update({"exp": expire})
        # 使用配置中的密钥和算法
        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return encoded_jwt
    
    @staticmethod
    def decode_token(token: str) -> Dict[str, Any]:
        """解码令牌"""
        try:
            # 使用配置中的密钥和算法
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            if payload["exp"] < time.time():
                raise TokenExpiredException()
            return payload
        except jwt.ExpiredSignatureError:
            raise TokenExpiredException()
        except jwt.InvalidTokenError:
            raise InvalidTokenException()
    
    @classmethod
    def register_user(cls, db: Session, username: str, password: str, email: Optional[str] = None, nickname: Optional[str] = None) -> User:
        """注册新用户 (用户名/密码方式)
        
        Args:
            db: 数据库会话
            username: 用户名
            password: 密码
            email: 邮箱 (可选，但推荐)
            nickname: 昵称 (可选)
            
        Returns:
            User: 创建的用户对象 (不含密码)
            
        Raises:
            UserExistsException: 用户名或邮箱已存在
        """
        # 检查用户名或邮箱是否已存在
        existing_user = db.query(User).filter(
            (User.username == username) | (User.email == email if email else False)
        ).first()
        if existing_user:
            raise UserExistsException()
            
        # 获取默认用户角色 ID (假设普通用户角色 ID 为 2)
        # TODO: 在实际应用中，应该查询数据库获取角色 ID 或使用常量
        default_user_role = db.query(Role).filter(Role.name == 'user').first()
        if not default_user_role:
            # 这是一个严重的配置错误，系统中必须存在名为 'user' 的角色
            # TODO: 记录详细错误日志
            raise HTTPException(status_code=500, detail="系统角色配置错误")
        default_user_role_id = default_user_role.id
            
        # 创建新用户
        new_user = User(
            username=username,
            password=cls.hash_password(password),
            role_id=default_user_role_id
        )
        db.add(new_user)
        # db.commit() # 推迟 commit
        # db.refresh(new_user)
        
        # TODO: 可以考虑同时创建 UserAuthentication 记录 (provider='email')
        # 确保 email 和 nickname 被使用
        if email:
            new_user.email = email
        if nickname:
            new_user.nickname = nickname
        elif not new_user.nickname: # 如果用户没提供且模型没有默认值，则生成一个
             new_user.nickname = f"用户_{username}"
        
        try:
            db.commit()
            db.refresh(new_user)
        except Exception as e:
            db.rollback()
            # 可以在这里处理特定的数据库错误，例如唯一约束冲突
            # 并记录日志
            raise e # 重新抛出异常，让上层处理

        # 返回用户信息，但不包含密码等敏感信息
        return new_user
    
    @classmethod
    def authenticate_user(cls, db: Session, username: str, password: str) -> Dict[str, Any]:
        """用户认证 (用户名/密码)
        
        Args:
            db: 数据库会话
            username: 用户名
            password: 密码
            
        Returns:
            Dict[str, Any]: 包含 access_token, token_type, expires_in, user_info 的字典
            
        Raises:
            InvalidCredentialsException: 认证失败
        """
        # 获取用户
        user = db.query(User).filter(User.username == username).first()
        
        # 如果没有用户，返回需要注册 (或者直接抛异常)
        if user is None:
            raise InvalidCredentialsException()
            
        # 验证密码和口令 (只验证密码)
        if not cls.verify_password(password, user.password):
            raise InvalidCredentialsException()
            
        # 更新最后登录时间
        user.last_login_at = func.now()
        db.commit()
        
        # 认证成功，生成 JWT
        # 使用配置中的过期时间
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = cls.create_access_token(
            data={"sub": str(user.id)}, # 使用用户 ID 作为 subject
            expires_delta=access_token_expires
        )
        
        # return {"sub": username}
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": access_token_expires.total_seconds(),
            "user_info": { # 可以选择性返回一些用户信息
                "id": user.id,
                "username": user.username,
                "nickname": user.nickname,
                "role_id": user.role_id
            }
        }

class JWTBearer(HTTPBearer):
    """JWT Bearer认证
    
    增加了基于角色的访问控制。
    调用示例: Depends(JWTBearer(required_roles=['admin', 'super_admin']))
    """
    
    def __init__(self, required_roles: Optional[List[str]] = None, auto_error: bool = True):
        super().__init__(auto_error=auto_error)
        self.required_roles = set(required_roles) if required_roles else None
        self.auto_error = auto_error
    
    async def __call__(self, request: Request, db: Session = Depends(get_db)) -> User:
        # 返回 User 对象而不是字典，方便路由函数直接使用
        credentials: HTTPAuthorizationCredentials = await super().__call__(request)
        if not credentials:
            if self.auto_error:
                raise InvalidTokenException("未提供凭证")
            else:
                return None # 或者根据需要返回特定值
            
        if credentials.scheme.lower() != "bearer":
            if self.auto_error:
                raise InvalidTokenException("无效的认证方案")
            else:
                return None
            
        try:
            payload = Auth.decode_token(credentials.credentials)
            user_id = payload.get("sub")
            if user_id is None:
                raise InvalidTokenException("Token 中缺少用户信息")
                
            # 根据 user_id 查询用户及其角色
            user = db.query(User).options(joinedload(User.role)).filter(User.id == int(user_id)).first()
            if user is None:
                raise InvalidCredentialsException("找不到用户") # Token有效但用户不存在
                
            # 检查角色权限
            if self.required_roles:
                if user.role is None or user.role.name not in self.required_roles:
                    raise HTTPException(status_code=403, detail="权限不足")
                    
            # 返回 User 对象，包含角色信息
            return user
            
        except (InvalidTokenException, TokenExpiredException, InvalidCredentialsException) as e:
            if self.auto_error:
                raise e # 重新抛出认证异常
            else:
                return None
        except Exception as e:
            # 处理其他可能的错误，例如数据库查询错误
            # 考虑记录日志
            if self.auto_error:
                raise HTTPException(status_code=500, detail="认证服务内部错误")
            else:
                return None 