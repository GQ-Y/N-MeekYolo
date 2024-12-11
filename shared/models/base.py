"""
基础数据模型
"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class BaseResponse(BaseModel):
    """基础响应模型"""
    status: str = "success"
    message: Optional[str] = None
    data: Optional[dict] = None

class ServiceInfo(BaseModel):
    """服务信息模型"""
    name: str = Field(..., description="服务名称")
    host: str = Field(..., description="服务主机")
    port: int = Field(..., description="服务端口")
    status: str = Field("healthy", description="服务状态")
    last_check: datetime = Field(default_factory=datetime.now) 