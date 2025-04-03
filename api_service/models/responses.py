"""
响应数据模型
"""
from typing import Dict, Optional, List, Any, TypeVar, Generic, Union
from pydantic import BaseModel, Field
from datetime import datetime
from models.requests import StreamStatus
import uuid
import time

T = TypeVar('T')

class BaseResponse(BaseModel, Generic[T]):
    """标准响应模型"""
    requestId: str = Field(default_factory=lambda: str(uuid.uuid4()), description="请求ID")
    path: str = Field("", description="请求路径")
    success: bool = Field(True, description="是否成功")
    message: str = Field("操作成功", description="响应消息")
    code: int = Field(200, description="状态码")
    data: Optional[T] = Field(None, description="响应数据")
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000), description="时间戳")

    model_config = {
        "json_schema_extra": {
            "example": {
                "requestId": "550e8400-e29b-41d4-a716-446655440000",
                "path": "/api/v1/stream/list",
                "success": True,
                "message": "操作成功",
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
    }

class NodeBase(BaseModel):
    """节点基础模型"""
    ip: str = Field(..., description="节点IP地址")
    port: str = Field(..., description="节点端口")
    service_name: str = Field(..., description="服务名称")
    weight: int = Field(1, description="负载均衡权重")
    max_tasks: int = Field(10, description="最大任务数量")

class NodeCreate(BaseModel):
    """节点创建请求模型"""
    ip: str = Field(..., description="节点IP地址")
    port: str = Field(..., description="节点端口")
    service_name: str = Field(..., description="服务名称")
    weight: int = Field(1, description="负载均衡权重")
    max_tasks: int = Field(10, description="最大任务数量")
    node_type: str = Field("edge", description="节点类型：edge(边缘节点)、cluster(集群节点)")
    service_type: int = Field(1, description="服务类型：1-分析服务、2-模型服务、3-云服务")
    compute_type: str = Field("cpu", description="计算类型：cpu(CPU计算边缘节点)、camera(摄像头边缘节点)、gpu(GPU计算边缘节点)、elastic(弹性集群节点)")

class NodeUpdate(BaseModel):
    """节点更新请求模型"""
    ip: Optional[str] = Field(None, description="节点IP地址")
    port: Optional[str] = Field(None, description="节点端口")
    service_name: Optional[str] = Field(None, description="服务名称")
    service_status: Optional[str] = Field(None, description="服务状态")
    weight: Optional[int] = Field(None, description="负载均衡权重")
    max_tasks: Optional[int] = Field(None, description="最大任务数量")
    node_type: Optional[str] = Field(None, description="节点类型：edge(边缘节点)、cluster(集群节点)")
    service_type: Optional[int] = Field(None, description="服务类型：1-分析服务、2-模型服务、3-云服务")
    compute_type: Optional[str] = Field(None, description="计算类型：cpu(CPU计算边缘节点)、camera(摄像头边缘节点)、gpu(GPU计算边缘节点)、elastic(弹性集群节点)")
    memory_usage: Optional[float] = Field(None, description="内存占用率")
    gpu_memory_usage: Optional[float] = Field(None, description="GPU显存占用率")

class NodeStatusUpdate(BaseModel):
    """节点状态更新请求模型"""
    node_id: int = Field(..., description="节点ID")
    service_status: str = Field(..., description="服务状态")
    memory_usage: Optional[float] = Field(None, description="内存占用率")
    gpu_memory_usage: Optional[float] = Field(None, description="GPU显存占用率")

class NodeTaskCountsUpdate(BaseModel):
    """节点任务数量更新请求模型"""
    node_id: int = Field(..., description="节点ID")
    image_task_count: int = Field(0, description="图像任务数量")
    video_task_count: int = Field(0, description="视频任务数量")
    stream_task_count: int = Field(0, description="流任务数量")

class NodeResponse(BaseModel):
    """节点响应模型"""
    id: int = Field(..., description="节点ID")
    ip: str = Field(..., description="节点IP地址")
    port: str = Field(..., description="节点端口")
    service_name: str = Field(..., description="服务名称")
    service_status: str = Field(..., description="服务状态")
    image_task_count: int = Field(0, description="图像任务数量")
    video_task_count: int = Field(0, description="视频任务数量")
    stream_task_count: int = Field(0, description="流任务数量")
    weight: int = Field(1, description="负载均衡权重")
    max_tasks: int = Field(10, description="最大任务数量")
    is_active: bool = Field(True, description="是否激活")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    last_heartbeat: Optional[datetime] = Field(None, description="最后心跳时间")
    node_type: str = Field("edge", description="节点类型：edge(边缘节点)、cluster(集群节点)")
    service_type: int = Field(1, description="服务类型：1-分析服务、2-模型服务、3-云服务")
    compute_type: str = Field("cpu", description="计算类型：cpu(CPU计算边缘节点)、camera(摄像头边缘节点)、gpu(GPU计算边缘节点)、elastic(弹性集群节点)")
    memory_usage: float = Field(0, description="内存占用率")
    gpu_memory_usage: float = Field(0, description="GPU显存占用率")
    total_tasks: int = Field(0, description="总任务数量")

    model_config = {
        "from_attributes": True
    }
    
    def get_total_tasks(self) -> int:
        """获取总任务数量"""
        return self.image_task_count + self.video_task_count + self.stream_task_count
    
    # 模型方法，用于自定义序列化
    def model_dump(self, **kwargs):
        data = super().model_dump(**kwargs)
        data["total_tasks"] = self.get_total_tasks()
        return data

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

    model_config = {
        "from_attributes": True
    }

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
    
    model_config = {
        "from_attributes": True
    }

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

    model_config = {
        "from_attributes": True
    }

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

    model_config = {
        "from_attributes": True
    }

class TaskResponse(BaseModel):
    """任务响应"""
    id: int
    name: str
    status: str
    error_message: Optional[str] = None
    callback_interval: int = 1
    enable_callback: bool = Field(True, description="是否启用回调")
    save_result: bool = Field(False, description="是否保存结果")
    config: Dict[str, Any] = Field(default_factory=dict, description="任务配置")
    node_id: Optional[int] = Field(None, description="节点ID")
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # 关联数据 - 只存储ID
    stream_ids: List[int] = Field(default_factory=list)  # 改名以更清晰
    model_ids: List[int] = Field(default_factory=list)   # 改名以更清晰
    callback_ids: List[int] = Field(default_factory=list) # 改名以更清晰

    model_config = {
        "protected_namespaces": (),
        "from_attributes": True,
        "alias_generator": lambda x: x.replace('_ids', 's')
    }

class ResponseModel(BaseModel):
    """通用响应模型"""
    code: int = 200
    message: str = "success"
    data: Optional[Dict[str, Any]] = None

class SubTaskResponse(BaseModel):
    """子任务响应模型"""
    id: int
    task_id: int
    stream_id: int
    model_id: int
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    enable_callback: bool = False
    callback_url: Optional[str] = None
    roi_type: int = 0
    analysis_type: str = "detection"
    node_id: Optional[int] = None
    analysis_task_id: Optional[str] = None
    
    # 关联信息
    stream_name: Optional[str] = None
    model_name: Optional[str] = None
    node_info: Optional[Dict[str, Any]] = None
    
    class Config:
        orm_mode = True

class TaskDetailResponse(BaseModel):
    """任务详情响应模型"""
    id: int
    name: str
    status: str
    error_message: Optional[str] = None
    save_result: bool = False
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    active_subtasks: int
    total_subtasks: int
    
    # 子任务列表
    sub_tasks: List[SubTaskResponse] = []
    
    class Config:
        orm_mode = True