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
    
    model_config = {"protected_namespaces": ()}

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
    enable_callback: bool = True
    save_result: bool = False
    config: Optional[Dict[str, Any]] = Field(
        default_factory=lambda: {
            "confidence": 0.5,
            "iou": 0.45,
            "classes": None,
            "roi": None,
            "imgsz": 640,
            "nested_detection": True
        },
        description="任务配置"
    )

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
    id: int = Field(..., description="回调服务ID")
    name: Optional[str] = Field(None, description="回调服务名称")
    url: Optional[str] = Field(None, description="回调URL")
    description: Optional[str] = Field(None, description="回调服务描述")
    headers: Optional[Dict] = Field(None, description="自定义请求头")
    method: Optional[str] = Field(None, description="请求方法(GET/POST)")
    body_template: Optional[Dict] = Field(None, description="请求体模板")
    retry_count: Optional[int] = Field(None, description="重试次数")
    retry_interval: Optional[int] = Field(None, description="重试间隔(秒)")

# 任务请求模型
class TaskModelConfig(BaseModel):
    """任务中的模型配置"""
    model_id: int = Field(..., description="模型ID")
    config: Optional[Dict[str, Any]] = Field(
        default_factory=lambda: {
            "confidence": 0.5,
            "iou": 0.45,
            "classes": [0, 1, 2],
            "roi_type": 1,
            "roi": {
                "x1": 0.1,
                "y1": 0.1,
                "x2": 0.9,
                "y2": 0.9
            },
            "imgsz": 640,
            "nested_detection": True,
            "analysis_type": "detection",
            "callback": {
                "enabled": True,
                "url": "http://example.com/callback",
                "interval": 5
            }
        },
        description="模型配置，包含检测阈值、ROI区域、回调等参数"
    )

class TaskStreamConfig(BaseModel):
    """任务中的视频流配置"""
    stream_id: int = Field(..., description="视频流ID，必须是系统中存在的流ID")
    stream_name: Optional[str] = Field(None, description="视频流自定义名称(用于回调和结果展示)，如不提供将使用系统中的流名称")
    models: List[TaskModelConfig] = Field(..., description="该视频流使用的模型列表及其配置，一个流可以同时配置多个分析模型")

class TaskCreate(BaseModel):
    """创建任务请求"""
    name: str = Field(..., description="任务名称，用于识别和显示任务")
    save_result: bool = Field(False, description="是否保存分析结果数据到服务器")
    save_images: bool = Field(False, description="是否保存分析结果图片到服务器")
    analysis_interval: int = Field(1, description="分析间隔(秒)，控制分析频率")
    specific_node_id: Optional[int] = Field(None, description="指定运行节点ID，如果提供则优先使用该节点")
    tasks: List[TaskStreamConfig] = Field(
        ..., 
        description="子任务配置列表，每个子任务包含一个视频流和多个分析模型的配置"
    )
    
    model_config = {"protected_namespaces": ()}

class TaskUpdate(BaseModel):
    """更新任务请求"""
    id: int = Field(..., description="任务ID")
    name: Optional[str] = Field(None, description="任务名称")
    save_result: Optional[bool] = Field(None, description="是否保存分析结果数据到服务器")
    save_images: Optional[bool] = Field(None, description="是否保存分析结果图片到服务器")
    analysis_interval: Optional[int] = Field(None, description="分析间隔(秒)，控制分析频率")
    specific_node_id: Optional[int] = Field(None, description="指定运行节点ID，如果提供则优先使用该节点")
    tasks: Optional[List[TaskStreamConfig]] = Field(None, description="更新子任务配置")
    
    model_config = {"protected_namespaces": ()}

# 任务状态枚举
class TaskStatus(str, Enum):
    """任务状态枚举"""
    CREATED = "created"      # 已创建
    RUNNING = "running"      # 运行中
    STOPPED = "stopped"      # 已停止
    ERROR = "error"          # 错误
    NO_NODE = "no_node"      # 无可用节点

# 更新子任务状态请求
class SubTaskStatusUpdate(BaseModel):
    """子任务状态更新请求"""
    id: int = Field(..., description="子任务ID")
    status: str = Field(..., description="状态")
    error_message: Optional[str] = Field(None, description="错误信息")

# ROI类型枚举
class RoiType(IntEnum):
    """ROI类型枚举"""
    NONE = 0        # 无ROI
    RECTANGLE = 1   # 矩形
    POLYGON = 2     # 多边形
    LINE = 3        # 线段

# 任务分析类型枚举
class AnalysisType(str, Enum):
    """分析类型枚举"""
    DETECTION = "detection"   # 目标检测
    TRACKING = "tracking"     # 目标跟踪
    COUNTING = "counting"     # 计数

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
    id: int = Field(..., description="回调服务ID")
    name: Optional[str] = Field(None, description="回调服务名称")
    url: Optional[str] = Field(None, description="回调URL")
    description: Optional[str] = Field(None, description="回调服务描述")
    headers: Optional[dict] = Field(None, description="自定义请求头")
    method: Optional[str] = Field(None, description="请求方法(GET/POST)")
    body_template: Optional[dict] = Field(None, description="请求体模板")
    retry_count: Optional[int] = Field(None, description="重试次数")
    retry_interval: Optional[int] = Field(None, description="重试间隔(秒)")

class AnalysisCreate(BaseModel):
    """创建分析服务请求"""
    name: str
    description: Optional[str] = None
    model_id: int
    stream_id: int
    callback_id: Optional[int] = None
    config: Optional[Dict[str, Any]] = None
    
    model_config = {"protected_namespaces": ()}

class AnalysisUpdate(BaseModel):
    """更新分析服务请求"""
    id: int
    name: Optional[str] = None
    description: Optional[str] = None
    model_id: Optional[int] = None
    stream_id: Optional[int] = None
    callback_id: Optional[int] = None
    config: Optional[Dict[str, Any]] = None
    
    model_config = {"protected_namespaces": ()} 