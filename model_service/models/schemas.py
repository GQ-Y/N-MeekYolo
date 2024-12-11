"""
数据模型
"""
from typing import Optional, Any, Dict, List
from pydantic import BaseModel, EmailStr
from datetime import datetime
from model_service.models.models import ModelInfo, ModelList

class BaseResponse(BaseModel):
    """基础响应"""
    code: int = 200
    message: str = "success"
    data: Optional[Any] = None

class ModelResponse(BaseModel):
    """模型响应"""
    code: int = 200
    message: str = "success"
    data: Optional[ModelInfo] = None

class ModelListResponse(BaseModel):
    """模型列表响应"""
    code: int = 200
    message: str = "success"
    data: ModelList

class KeyCreate(BaseModel):
    """创建密钥"""
    name: str
    phone: str
    email: EmailStr

class KeyResponse(BaseModel):
    """密钥响应"""
    id: int
    key: str
    name: str
    phone: str
    email: str
    status: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True 