"""
响应数据模型
"""
from typing import Dict, Optional, List, Any, TypeVar, Generic
from pydantic import BaseModel, Field
from datetime import datetime
from api_service.models.requests import StreamStatus
import uuid
import time

T = TypeVar('T')

class BaseResponse(BaseModel, Generic[T]):
    """标准响应模型"""
    requestId: str = Field(default_factory=lambda: str(uuid.uuid4()), description="请求ID")
    path: str = Field("", description="请求路径")
    success: bool = Field(True, description="是否成功")
    message: str = Field("Success", description="响应消息")
    code: int = Field(200, description="状态码")
    data: Optional[T] = Field(None, description="响应数据")
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000), description="时间戳")

    class Config:
        json_schema_extra = {
            "example": {
                "requestId": "550e8400-e29b-41d4-a716-446655440000",
                "path": "/api/v1/stream/list",
                "success": True,
                "message": "Success",
                "code": 200,
                "data": {
                    "total": 1,
                    "items": [
                        {
                            "id": 1,
                            "name": "测试视频源",
                            "status": "online"
                        }
                    ]
                },
                "timestamp": 1616633599000
            }
        }

class NodeBase(BaseModel):
    """节点基础模型"""
    ip: str = Field(..., description="节点IP地址")
    port: str = Field(..., description="节点端口")
    service_name: str = Field(..., description="服务名称")

class NodeCreate(NodeBase):
    """节点创建模型"""
    pass

class NodeUpdate(NodeBase):
    """节点更新模型"""
    ip: Optional[str] = Field(None, description="节点IP地址")
    port: Optional[str] = Field(None, description="节点端口")
    service_name: Optional[str] = Field(None, description="服务名称")
    service_status: Optional[str] = Field(None, description="服务状态")

class NodeStatusUpdate(BaseModel):
    """节点状态更新模型"""
    node_id: int = Field(..., description="节点ID")
    service_status: str = Field(..., description="服务状态")

class NodeTaskCountsUpdate(BaseModel):
    """节点任务数量更新模型"""
    node_id: int = Field(..., description="节点ID")
    image_task_count: int = Field(0, description="图像任务数量")
    video_task_count: int = Field(0, description="视频任务数量")
    stream_task_count: int = Field(0, description="流任务数量")

class NodeResponse(NodeBase):
    """节点响应模型"""
    id: int = Field(..., description="节点ID")
    service_status: str = Field(..., description="服务状态")
    image_task_count: int = Field(0, description="图像任务数量")
    video_task_count: int = Field(0, description="视频任务数量")
    stream_task_count: int = Field(0, description="流任务数量")
    is_active: bool = Field(True, description="是否激活")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    last_heartbeat: Optional[datetime] = Field(None, description="最后心跳时间")

    class Config:
        from_attributes = True

class NodeListResponse(BaseResponse[List[NodeResponse]]):
    """节点列表响应"""
    data: List[NodeResponse] = Field(default_factory=list, description="节点列表")

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
    groups: List[Dict[str, Any]] = Field(default_factory=list, description="所属分组列表")
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, obj):
        if isinstance(obj, dict):
            # 如果是字典，直接使用
            return cls(**obj)
            
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
                
        # 处理分组信息
        groups_data = []
        if hasattr(obj, 'groups'):
            for group in obj.groups:
                if hasattr(group, 'id') and hasattr(group, 'name'):
                    groups_data.append({"id": group.id, "name": group.name})
                elif isinstance(group, dict) and 'id' in group and 'name' in group:
                    groups_data.append(group)
                    
        # 创建响应数据
        data = {
            "id": obj.id,
            "name": obj.name,
            "url": obj.url,
            "description": obj.description,
            "status": obj.status,
            "error_message": obj.error_message if hasattr(obj, 'error_message') else None,
            "groups": groups_data,
            "created_at": obj.created_at,
            "updated_at": obj.updated_at
        }
        
        return cls(**data)

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