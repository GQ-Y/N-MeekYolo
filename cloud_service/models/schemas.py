"""
数据模型
"""
from typing import Dict, Optional, List
from pydantic import BaseModel, EmailStr
from datetime import datetime

# 基础响应
class BaseResponse(BaseModel):
    """基础响应"""
    code: int = 200
    message: str = "success"
    data: Optional[Dict] = None

# 云模型
class CloudModelCreate(BaseModel):
    """创建云模型请求"""
    code: str
    version: str
    name: str
    description: str
    author: str
    nc: int
    names: Dict[int, str]

class CloudModelUpdate(BaseModel):
    """更新云模型请求"""
    version: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    author: Optional[str] = None
    nc: Optional[int] = None
    names: Optional[Dict[int, str]] = None
    status: Optional[bool] = None

class CloudModelResponse(BaseModel):
    """云模型响应"""
    id: int
    code: str
    version: str
    name: str
    description: str
    author: str
    file_path: str
    status: bool
    nc: int
    names: Dict[int, str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# API密钥
class ApiKeyCreate(BaseModel):
    """创建API密钥请求"""
    name: str
    phone: str
    email: EmailStr

class ApiKeyResponse(BaseModel):
    """API密钥响应"""
    id: int
    key: str
    name: str
    phone: str
    email: str
    status: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ApiKeyUpdate(BaseModel):
    """更新API密钥请求"""
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    status: Optional[bool] = None

    class Config:
        from_attributes = True 