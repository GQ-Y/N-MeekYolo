"""
数据模型
"""
from typing import Optional, Any, Dict, List
from pydantic import BaseModel, EmailStr, Field, constr
from datetime import datetime
from models.models import ModelInfo, ModelList
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
    name: str = Field(..., min_length=1, description="密钥名称")
    phone: constr(min_length=11, max_length=11) = Field(..., description="手机号")
    email: EmailStr = Field(..., description="邮箱")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "name": "测试密钥",
                "phone": "13800138000",
                "email": "test@example.com"
            }
        }

class KeyUpdate(BaseModel):
    """更新密钥请求"""
    name: Optional[str] = Field(None, min_length=1, description="密钥名称")
    phone: Optional[constr(min_length=11, max_length=11)] = Field(None, description="手机号")
    email: Optional[EmailStr] = Field(None, description="邮箱")
    status: Optional[bool] = Field(None, description="状态")

    class Config:
        from_attributes = True

class KeyResponse(BaseModel):
    """密钥响应"""
    id: int = Field(..., description="密钥ID")
    cloud_id: int = Field(..., description="云服务密钥ID")
    key: str = Field(..., description="API密钥")
    name: str = Field(..., description="密钥名称")
    phone: str = Field(..., description="手机号")
    email: str = Field(..., description="邮箱")
    status: bool = Field(..., description="状态")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "cloud_id": 100,
                "key": "sk-xxxxxxxxxxxxxxxx",
                "name": "测试密钥",
                "phone": "13800138000",
                "email": "test@example.com",
                "status": True,
                "created_at": "2024-03-31T00:00:00Z",
                "updated_at": None
            }
        } 