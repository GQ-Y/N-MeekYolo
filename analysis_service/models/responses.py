"""
分析服务响应模型
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class BaseResponse(BaseModel):
    """基础响应模型"""
    code: int = 200
    message: str = "success"
    data: Optional[Dict[str, Any]] = None

class DetectionResponse(BaseResponse):
    """检测响应"""
    data: Dict[str, Any] = {
        "detections": List[Dict[str, Any]],
        "result_image": Optional[str]
    }

class StreamResponse(BaseResponse):
    """流分析响应"""
    class DataModel(BaseModel):
        task_id: str
        status: str
        stream_url: str
        output_url: Optional[str] = None
        
    data: Optional[DataModel] = None

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
    bbox: Dict[str, int]  # x1, y1, x2, y2, width, height

class ImageAnalysisResponse(BaseModel):
    """图片分析响应"""
    image_url: str
    detections: List[DetectionResult]
    result_image: Optional[str] = None  # base64编码的结果图片

class VideoAnalysisResponse(BaseModel):
    """视频分析响应"""
    task_id: str
    status: str
    progress: float = 0.0
    detections: Optional[List[DetectionResult]] = None
    result_video: Optional[str] = None  # 结果视频的URL

class StreamAnalysisResponse(BaseModel):
    """流分析响应"""
    task_id: str
    status: str
    last_frame: Optional[str] = None  # 最新帧的时间戳
    detections: Optional[List[DetectionResult]] = None
    result_frame: Optional[str] = None  # base64编码的最新结果帧 