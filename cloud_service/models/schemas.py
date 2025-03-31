"""
数据模型
"""
from typing import Dict, Optional, List, Any
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from uuid import UUID, uuid4

# 标准响应
class StandardResponse(BaseModel):
    """标准响应模型"""
    requestId: str = Field(default_factory=lambda: str(uuid4()), description="请求ID")
    path: str = Field(default="", description="请求路径")
    success: bool = Field(default=True, description="请求是否成功")
    message: str = Field(default="success", description="响应消息")
    code: int = Field(default=200, description="HTTP状态码")
    data: Optional[Any] = Field(default=None, description="响应数据")
    timestamp: datetime = Field(default_factory=datetime.now, description="响应时间")

# 云模型
class CloudModelCreate(BaseModel):
    """创建云模型请求"""
    code: str = Field(..., description="模型代码", min_length=1)
    version: str = Field(..., description="模型版本", min_length=1)
    name: str = Field(..., description="模型名称", min_length=1)
    description: str = Field(..., description="模型描述")
    author: str = Field(..., description="作者")
    nc: int = Field(..., description="类别数量", gt=0)
    names: Dict[int, str] = Field(..., description="类别名称映射")

class CloudModelUpdate(BaseModel):
    """更新云模型请求"""
    version: Optional[str] = Field(None, description="模型版本")
    name: Optional[str] = Field(None, description="模型名称")
    description: Optional[str] = Field(None, description="模型描述")
    author: Optional[str] = Field(None, description="作者")
    nc: Optional[int] = Field(None, description="类别数量", gt=0)
    names: Optional[Dict[int, str]] = Field(None, description="类别名称映射")
    status: Optional[bool] = Field(None, description="模型状态")

class CloudModelResponse(BaseModel):
    """云模型响应"""
    id: int = Field(..., description="模型ID")
    code: str = Field(..., description="模型代码")
    version: str = Field(..., description="模型版本")
    name: str = Field(..., description="模型名称")
    description: str = Field(..., description="模型描述")
    author: str = Field(..., description="作者")
    file_path: str = Field(..., description="文件路径")
    status: bool = Field(..., description="模型状态")
    nc: int = Field(..., description="类别数量")
    names: Dict[int, str] = Field(..., description="类别名称映射")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    class Config:
        from_attributes = True

# API密钥
class ApiKeyCreate(BaseModel):
    """创建API密钥请求"""
    name: str = Field(..., description="密钥名称", min_length=1)
    phone: str = Field(..., description="联系电话", min_length=11, max_length=11)
    email: EmailStr = Field(..., description="电子邮箱")

class ApiKeyResponse(BaseModel):
    """API密钥响应"""
    id: int = Field(..., description="密钥ID")
    key: str = Field(..., description="密钥值")
    name: str = Field(..., description="密钥名称")
    phone: str = Field(..., description="联系电话")
    email: str = Field(..., description="电子邮箱")
    status: bool = Field(..., description="密钥状态")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    class Config:
        from_attributes = True

class ApiKeyUpdate(BaseModel):
    """更新API密钥请求"""
    name: Optional[str] = Field(None, description="密钥名称")
    phone: Optional[str] = Field(None, description="联系电话", min_length=11, max_length=11)
    email: Optional[EmailStr] = Field(None, description="电子邮箱")
    status: Optional[bool] = Field(None, description="密钥状态")

    class Config:
        from_attributes = True 