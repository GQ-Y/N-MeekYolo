"""
数据模型
"""
from typing import Optional, Any, Dict, List
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from model_service.models.models import ModelInfo, ModelList
import uuid

class StandardResponse(BaseModel):
    """标准响应模型"""
    requestId: str = Field(default_factory=lambda: str(uuid.uuid4()), description="请求ID")
    path: str = Field(..., description="请求路径")
    success: bool = Field(True, description="是否成功")
    message: str = Field("Success", description="响应消息")
    code: int = Field(200, description="状态码")
    data: Optional[Any] = Field(None, description="响应数据")
    timestamp: datetime = Field(default_factory=datetime.now, description="响应时间")

    class Config:
        json_schema_extra = {
            "example": {
                "requestId": "550e8400-e29b-41d4-a716-446655440000",
                "path": "/api/v1/models",
                "success": True,
                "message": "Success",
                "code": 200,
                "data": None,
                "timestamp": 1616633599000
            }
        }

class ModelResponse(StandardResponse):
    """模型响应"""
    pass

class ModelListResponse(StandardResponse):
    """模型列表响应"""
    pass

class KeyCreate(BaseModel):
    """创建密钥请求"""
    name: str = Field(..., description="密钥名称")
    description: Optional[str] = Field(None, description="密钥描述")
    expires_at: Optional[datetime] = Field(None, description="过期时间")

    class Config:
        from_attributes = True

class KeyResponse(StandardResponse):
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