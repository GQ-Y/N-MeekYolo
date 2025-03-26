"""
分析服务响应模型
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class BaseResponse(BaseModel):
    """基础响应模型"""
    code: int = 200
    message: str = "success"
    data: Optional[Dict[str, Any]] = None

class SubTaskInfo(BaseModel):
    """子任务信息"""
    task_id: str
    status: int  # 修改为整数类型，与数据库一致: 0:等待中 1:运行中 2:已完成 -1:失败
    stream_url: str
    output_url: Optional[str] = None

class StreamBatchResponse(BaseModel):
    """批量流分析响应数据"""
    parent_task_id: str
    sub_tasks: List[SubTaskInfo]

class StreamResponse(BaseResponse):
    """流分析响应"""
    data: Optional[StreamBatchResponse] = None

class DetectionResponse(BaseResponse):
    """检测响应"""
    data: Dict[str, Any] = {
        "detections": List[Dict[str, Any]],
        "result_image": Optional[str]
    }

class TaskStatusResponse(BaseResponse):
    """任务状态响应"""
    data: Dict[str, Any] = {
        "task_id": str,
        "status": str,
        "message": Optional[str]
    }

class HealthResponse(BaseResponse):
    """健康检查响应"""
    data: Dict[str, Any] = {
        "status": str,
        "version": str
    }

class DetectionResult(BaseModel):
    """检测结果"""
    track_id: Optional[int] = None
    class_name: str
    confidence: float
    bbox: Dict[str, float]  # x1, y1, x2, y2 使用浮点数以保持精度
    children: Optional[List['DetectionResult']] = []  # 嵌套检测结果

class ImageAnalysisResponse(BaseModel):
    """图片分析响应"""
    image_url: str
    task_name: Optional[str] = None
    detections: List[DetectionResult]
    result_image: Optional[str] = None  # base64编码的结果图片
    saved_path: Optional[str] = None    # 保存的结果图片路径（相对于项目根目录）
    start_time: Optional[float] = None  # 开始时间戳
    end_time: Optional[float] = None    # 结束时间戳
    analysis_duration: Optional[float] = None  # 分析耗时(秒)

class VideoAnalysisResponse(BaseModel):
    """视频分析响应"""
    task_id: str = Field(
        ...,  # 必填字段
        description="任务ID",
        example="task_20240315_123456"
    )
    task_name: Optional[str] = Field(
        None,
        description="任务名称",
        example="视频分析-1"
    )
    status: int = Field(
        1,  # 默认为运行中状态
        description="任务状态：0-等待中，1-运行中，2-已完成，-1-失败",
        example=1
    )
    video_url: Optional[str] = Field(
        None,
        description="视频URL",
        example="http://example.com/video.mp4"
    )
    saved_path: Optional[str] = Field(
        None,
        description="保存的结果视频路径（相对于项目根目录）",
        example="results/20240315/video_analysis_123456.mp4"
    )
    start_time: Optional[float] = Field(
        None,
        description="开始时间戳",
        example=1647321456.789
    )
    end_time: Optional[float] = Field(
        None,
        description="结束时间戳",
        example=1647321556.789
    )
    analysis_duration: Optional[float] = Field(
        None,
        description="分析耗时(秒)",
        example=100.0
    )
    progress: Optional[float] = Field(
        0.0,
        description="处理进度（0-100）",
        ge=0.0,
        le=100.0,
        example=45.5
    )
    total_frames: Optional[int] = Field(
        0,
        description="总帧数",
        ge=0,
        example=1000
    )
    processed_frames: Optional[int] = Field(
        0,
        description="已处理帧数",
        ge=0,
        example=455
    )

class StreamAnalysisResponse(BaseModel):
    """流分析响应"""
    task_id: str
    task_name: Optional[str] = None
    status: str
    stream_url: str
    saved_path: Optional[str] = None  # 保存的结果视频/图片路径
    last_frame: Optional[str] = None  # 最新帧的时间戳
    detections: Optional[List[DetectionResult]] = None
    result_frame: Optional[str] = None  # base64编码的最新结果帧 