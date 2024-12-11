"""
响应数据模型
"""
from typing import Dict, Optional, List, Any
from pydantic import BaseModel
from datetime import datetime

class BaseResponse(BaseModel):
    """基础响应"""
    code: int = 200
    message: str = "success"
    data: Optional[Dict] = None

class StreamGroupResponse(BaseModel):
    """流分组响应"""
    id: int
    name: str
    description: Optional[str] = None
    streams: List[int] = []  # 修改为 int 类型列表,存储 stream id
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class StreamResponse(BaseModel):
    """流响应模型"""
    id: int
    name: str
    url: str
    description: Optional[str] = None
    status: str = "inactive"
    error_message: Optional[str] = None
    
    class Config:
        from_attributes = True

class CreateStreamResponse(BaseModel):
    """创建流响应"""
    code: int = 200
    message: str = "创建成功"
    data: StreamResponse

class ModelResponse(BaseModel):
    """模型响应"""
    id: int
    name: str
    description: Optional[str] = None
    type: str
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ModelListResponse(BaseResponse):
    """模型列表响应"""
    data: List[ModelResponse] = []

class CallbackResponse(BaseModel):
    """回调服务响应"""
    id: int
    name: str
    url: str
    description: Optional[str] = None
    headers: Optional[Dict] = None
    retry_count: int = 3
    retry_interval: int = 1
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class TaskResponse(BaseModel):
    """任务响应"""
    id: int
    name: str
    status: str
    error_message: Optional[str] = None
    callback_interval: int = 1
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # 关联数据
    streams: List[int] = []  # 流ID列表
    models: List[int] = []   # 模型ID列表
    callbacks: List[int] = [] # 回调服务ID列表

    class Config:
        from_attributes = True

class ResponseModel(BaseModel):
    """通用响应模型"""
    code: int = 200
    message: str = "success"
    data: Optional[Dict[str, Any]] = None