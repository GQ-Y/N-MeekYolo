"""
请求数据模型
"""
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
from enum import Enum, IntEnum

# 分析请求模型
class AnalysisRequest(BaseModel):
    """分析请求基础模型"""
    model_code: str
    callback_url: Optional[str] = None

class ImageAnalysisRequest(AnalysisRequest):
    """图片分析请求"""
    image_urls: List[str]
    is_base64: bool = False

class VideoAnalysisRequest(AnalysisRequest):
    """视频分析请求"""
    video_url: str
    callback_url: str = None

class StreamAnalysisRequest(AnalysisRequest):
    """流分析请求"""
    stream_url: str
    callback_url: str = None
    output_url: str = None
    callback_interval: int = 1

# 视频源分组请求模型
class StreamGroupCreate(BaseModel):
    """创建流分组请求"""
    name: str
    description: Optional[str] = None

class StreamGroupUpdate(BaseModel):
    """更新流分组请求"""
    id: int = Field(..., description="分组ID")
    name: Optional[str] = Field(None, description="分组名称")
    description: Optional[str] = Field(None, description="分组描述")

# 视频源请求模型
class StreamCreate(BaseModel):
    """创建视频源请求"""
    name: str = Field(..., description="视频源名称")
    url: str = Field(..., description="视频源URL")
    description: Optional[str] = Field(None, description="视频源描述")
    group_ids: Optional[List[int]] = Field(None, description="分组ID列表")

class StreamStatus(IntEnum):
    """视频源状态"""
    OFFLINE = 0  # 离线
    ONLINE = 1   # 在线

class StreamUpdate(BaseModel):
    """更新视频源请求"""
    id: int = Field(..., description="视频源ID")
    name: Optional[str] = Field(None, description="视频源名称")
    url: Optional[str] = Field(None, description="视频源URL")
    description: Optional[str] = Field(None, description="视频源描述")
    status: Optional[StreamStatus] = Field(None, description="视频源状态")
    error_message: Optional[str] = Field(None, description="错误信息")
    group_ids: Optional[List[int]] = Field(None, description="分组ID列表")

# 模型请求模型
class ModelCreate(BaseModel):
    """创建模型请求"""
    code: str = Field(..., description="模型代码")
    name: str = Field(..., description="模型名称")
    path: str = Field(..., description="模型路径")
    description: Optional[str] = Field(None, description="模型描述")

class ModelUpdate(BaseModel):
    """更新模型请求"""
    code: Optional[str] = Field(None, description="模型代码")
    name: Optional[str] = Field(None, description="模型名称")
    path: Optional[str] = Field(None, description="模型路径")
    description: Optional[str] = Field(None, description="模型描述")

# 回调服务请求模型
class CallbackCreate(BaseModel):
    """创建回调服务请求"""
    name: str = Field(..., description="回调服务名称")
    url: str = Field(..., description="回调URL")
    description: Optional[str] = Field(None, description="回调服务描述")
    headers: Optional[Dict] = Field(None, description="自定义请求头")
    method: str = Field('POST', description="请求方法(GET/POST)")
    body_template: Optional[Dict] = Field(None, description="请求体模板")
    retry_count: Optional[int] = Field(3, description="重试次数")
    retry_interval: Optional[int] = Field(1, description="重试间隔(秒)")

class CallbackUpdate(BaseModel):
    """更新回调服务请求"""
    name: Optional[str] = Field(None, description="回调服务名称")
    url: Optional[str] = Field(None, description="回调URL")
    description: Optional[str] = Field(None, description="回调服务描述")
    headers: Optional[Dict] = Field(None, description="自定义请求头")
    method: Optional[str] = Field(None, description="请求方法(GET/POST)")
    body_template: Optional[Dict] = Field(None, description="请求体模板")
    retry_count: Optional[int] = Field(None, description="重试次数")
    retry_interval: Optional[int] = Field(None, description="重试间隔(秒)")

# 任务请求模型
class TaskCreate(BaseModel):
    """创建任务请求"""
    name: str = Field(..., description="任务名称")
    stream_ids: List[int] = Field(..., description="视频源ID列表")
    model_ids: List[int] = Field(..., description="模型ID列表")
    callback_ids: Optional[List[int]] = Field(None, description="回调服务ID列表")
    callback_interval: Optional[int] = Field(1, description="回调间隔(秒)")

class TaskUpdate(BaseModel):
    """更新任务请求"""
    name: Optional[str] = Field(None, description="任务名称")
    stream_ids: Optional[List[int]] = Field(None, description="视频源ID列表")
    model_ids: Optional[List[int]] = Field(None, description="模型ID列表")
    callback_ids: Optional[List[int]] = Field(None, description="回调服务ID列表")
    callback_interval: Optional[int] = Field(None, description="回调间隔(秒)")

class TaskStatus(str, Enum):
    """任务状态枚举"""
    CREATED = "created"      # 已创建
    STARTING = "starting"    # 正在启动
    RUNNING = "running"      # 运行中
    STOPPING = "stopping"    # 正在停止
    STOPPED = "stopped"      # 已停止
    ERROR = "error"         # 错误

class TaskStatusUpdate(BaseModel):
    """任务状态更新请求"""
    status: TaskStatus
    error_message: Optional[str] = None

class CreateStreamRequest(BaseModel):
    """创建流请求"""
    name: str
    url: str
    description: Optional[str] = None
    group_ids: Optional[List[int]] = None

class UpdateStreamRequest(BaseModel):
    """更新流请求"""
    name: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None
    status: Optional[int] = None
    group_ids: Optional[List[int]] = None

class CreateStreamGroupRequest(BaseModel):
    """创建流分组请求"""
    name: str
    description: Optional[str] = None

class UpdateStreamGroupRequest(BaseModel):
    """更新流分组请求"""
    name: Optional[str] = None
    description: Optional[str] = None

class CreateModelRequest(BaseModel):
    """创建模型请求"""
    name: str
    type: str
    description: Optional[str] = None

class UpdateModelRequest(BaseModel):
    """更新模型请求"""
    name: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None

class CreateCallbackRequest(BaseModel):
    """创建回调服务请求"""
    name: str
    url: str
    description: Optional[str] = None
    headers: Optional[dict] = None
    retry_count: Optional[int] = 3
    retry_interval: Optional[int] = 1

class UpdateCallbackRequest(BaseModel):
    """更新回调服务请求"""
    name: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None
    headers: Optional[dict] = None
    retry_count: Optional[int] = None
    retry_interval: Optional[int] = None

class CreateTaskRequest(BaseModel):
    """创建任务请求"""
    name: str
    stream_ids: List[int]
    model_ids: List[int]
    callback_ids: Optional[List[int]] = None
    callback_interval: Optional[int] = 1

class UpdateTaskRequest(BaseModel):
    """更新任务请求"""
    name: Optional[str] = None
    stream_ids: Optional[List[int]] = None
    model_ids: Optional[List[int]] = None
    callback_ids: Optional[List[int]] = None
    callback_interval: Optional[int] = None
    status: Optional[str] = None

class AnalysisCreate(BaseModel):
    """创建分析服务请求"""
    name: str
    description: Optional[str] = None
    model_id: int
    stream_id: int
    callback_id: Optional[int] = None
    config: Optional[Dict[str, Any]] = None

class AnalysisUpdate(BaseModel):
    """更新分析服务请求"""
    id: int
    name: Optional[str] = None
    description: Optional[str] = None
    model_id: Optional[int] = None
    stream_id: Optional[int] = None
    callback_id: Optional[int] = None
    config: Optional[Dict[str, Any]] = None 