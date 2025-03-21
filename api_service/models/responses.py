"""
响应数据模型
"""
from typing import Dict, Optional, List, Any
from pydantic import BaseModel, Field
from datetime import datetime
from api_service.models.requests import StreamStatus

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
    """视频源响应"""
    id: int
    name: str
    url: str
    description: Optional[str] = None
    status: int = Field(default=0, description="状态: 0-离线, 1-在线")
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, obj):
        # 确保status是整数，处理可能的字符串值
        if hasattr(obj, 'status'):
            try:
                if isinstance(obj.status, str):
                    # 处理字符串状态
                    status_map = {
                        'active': 1,
                        'online': 1,
                        'inactive': 0,
                        'offline': 0
                    }
                    obj.status = status_map.get(obj.status.lower(), 0)
                else:
                    # 确保是整数
                    obj.status = int(obj.status)
            except (ValueError, TypeError):
                obj.status = 0  # 默认离线
        return super().from_orm(obj)

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
    
    # 关联数据 - 只存储ID
    stream_ids: List[int] = Field(default_factory=list)  # 改名以更清晰
    model_ids: List[int] = Field(default_factory=list)   # 改名以更清晰
    callback_ids: List[int] = Field(default_factory=list) # 改名以更清晰

    class Config:
        from_attributes = True
        
        # 添加别名映射，使其能正确从数据库模型转换
        alias_generator = lambda x: x.replace('_ids', 's')

class ResponseModel(BaseModel):
    """通用响应模型"""
    code: int = 200
    message: str = "success"
    data: Optional[Dict[str, Any]] = None