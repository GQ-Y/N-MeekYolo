"""
网关服务数据模型定义
"""
from typing import Any, Dict, Optional, Union, List
from pydantic import BaseModel, Field, validator, constr
from enum import Enum
import time
import uuid

class HttpMethod(str, Enum):
    """HTTP方法枚举"""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"

class StandardResponse(BaseModel):
    """标准API响应模型"""
    requestId: str = Field(default_factory=lambda: str(uuid.uuid4()), description="请求ID")
    path: str = Field("", description="请求路径")
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="响应消息")
    code: int = Field(..., description="响应代码")
    data: Optional[Union[Dict[str, Any], List[Any]]] = Field(None, description="响应数据")
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000), description="时间戳")

    class Config:
        json_schema_extra = {
            "example": {
                "requestId": "550e8400-e29b-41d4-a716-446655440000",
                "path": "/api/v1/route",
                "success": True,
                "message": "Success",
                "code": 200,
                "data": None,
                "timestamp": 1616633599000
            }
        }

class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")
    token: str = Field(..., description="口令")

class RegisterRequest(BaseModel):
    """注册请求"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")
    token: str = Field(..., description="口令")

class TokenResponse(BaseModel):
    """令牌响应"""
    access_token: str = Field(..., description="访问令牌")
    token_type: str = Field("bearer", description="令牌类型")
    expires_in: int = Field(3600, description="过期时间(秒)")

class RouteRequest(BaseModel):
    """路由请求模型"""
    service: constr(min_length=1, max_length=50) = Field(
        ..., 
        description="目标服务名称",
        example="api"
    )
    path: constr(min_length=1, max_length=500) = Field(
        ..., 
        description="目标路径",
        example="users/profile"
    )
    method: HttpMethod = Field(
        HttpMethod.POST,
        description="HTTP请求方法"
    )
    headers: Dict[str, str] = Field(
        default_factory=dict,
        description="请求头",
        example={"Content-Type": "application/json"}
    )
    query_params: Dict[str, Any] = Field(  # 修改为支持任意类型的值
        default_factory=dict,
        description="查询参数",
        example={
            "name": "测试",
            "url": "rtsp://example.com/stream",
            "description": "测试",
            "group_ids": [1, 2, 3]
        }
    )
    body: Any = Field(
        None,
        description="请求体"
    )

    @validator('path')
    def validate_path(cls, v):
        if '..' in v:
            raise ValueError('Path traversal is not allowed')
        if not v.strip('/'):
            raise ValueError('Path cannot be empty')
        return v.strip('/')

    @validator('headers')
    def validate_headers(cls, v):
        # 移除敏感头部
        sensitive_headers = {'host', 'connection', 'proxy'}
        return {k: v for k, v in v.items() if k.lower() not in sensitive_headers}

    class Config:
        json_schema_extra = {
            "example": {
                "service": "api",
                "path": "stream/create",
                "method": "POST",
                "headers": {
                    "Content-Type": "application/json",
                    "Authorization": "Bearer token"
                },
                "query_params": {
                    "name": "测试",
                    "url": "rtsp://example.com/stream",
                    "description": "测试",
                    "group_ids": [1, 2, 3]
                },
                "body": None
            }
        }

class ProfileUpdate(BaseModel):
    """用户信息更新请求"""
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

"""
数据库模型
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class User(Base):
    """用户模型"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)
    token = Column(String)
    nickname = Column(String, default="MeekYolo")  # 用户昵称
    phone = Column(String, nullable=True)  # 手机号
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class SystemConfig(Base):
    """系统配置"""
    __tablename__ = "system_config"
    
    id = Column(Integer, primary_key=True, index=True)
    device_name = Column(String, default="MeekYolo")  # 设备名称
    device_id = Column(String, unique=True)  # 设备ID
    version = Column(String)  # 系统版本
    last_update = Column(DateTime)  # 最后更新时间
    auto_update = Column(Boolean, default=True)  # 自动更新
    debug_mode = Column(Boolean, default=False)  # 调试模式
    log_level = Column(String, default="INFO")  # 日志级别
    storage_path = Column(String)  # 存储路径
    max_storage_days = Column(Integer, default=30)  # 最大存储天数
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class NetworkConfig(Base):
    """网络配置"""
    __tablename__ = "network_config"
    
    id = Column(Integer, primary_key=True, index=True)
    interface = Column(String)  # 网络接口
    mode = Column(String)  # 网络模式：DHCP/Static
    ip_address = Column(String)  # IP地址
    netmask = Column(String)  # 子网掩码
    gateway = Column(String)  # 网关
    dns_servers = Column(JSON)  # DNS服务器列表
    proxy_enabled = Column(Boolean, default=False)  # 代理开关
    proxy_server = Column(String)  # 代理服务器
    proxy_port = Column(Integer)  # 代理端口
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class CloudConfig(Base):
    """云服务配置"""
    __tablename__ = "cloud_config"
    
    id = Column(Integer, primary_key=True, index=True)
    enabled = Column(Boolean, default=False)  # 云服务开关
    service_type = Column(String)  # 服务类型
    endpoint = Column(String)  # 服务端点
    api_key = Column(String)  # API密钥
    secret_key = Column(String)  # 密钥
    region = Column(String)  # 区域
    bucket = Column(String)  # 存储桶
    sync_interval = Column(Integer, default=3600)  # 同步间隔（秒）
    last_sync = Column(DateTime)  # 最后同步时间
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow) 