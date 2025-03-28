"""
分析路由模块
处理视觉分析请求，包括图片分析、视频分析和流分析
"""
import os
import json
import uuid
import tempfile
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, File, UploadFile, Form, BackgroundTasks, Request
from pydantic import BaseModel, Field
from analysis_service.core.detector import YOLODetector
from analysis_service.core.queue import TaskQueueManager
from analysis_service.core.resource import ResourceMonitor
from analysis_service.core.models import (
    StandardResponse,
    AnalysisType,
    AnalysisStatus,
    DetectionResult,
    SegmentationResult,
    TrackingResult,
    CrossCameraResult
)
from analysis_service.core.exceptions import (
    InvalidInputException,
    ModelLoadException,
    ProcessingException,
    ResourceNotFoundException
)
from analysis_service.models.responses import (
    ImageAnalysisResponse,
    VideoAnalysisResponse,
    StreamAnalysisResponse,
    BaseApiResponse,
    StreamBatchData,
    ImageAnalysisData,
    VideoAnalysisData,
    ResourceStatusResponse
)
from analysis_service.models.requests import (
    ImageAnalysisRequest,
    VideoAnalysisRequest,
    StreamAnalysisRequest,
    StreamTask
)
from analysis_service.models.database import Task, TaskQueue
from shared.utils.logger import setup_logger
from analysis_service.services.database import get_db_dependency
from analysis_service.crud import task as task_crud
import asyncio
import time
from sqlalchemy.orm import Session
from analysis_service.core.config import settings
from datetime import datetime

logger = setup_logger(__name__)

# 初始化组件
detector = YOLODetector()
resource_monitor = ResourceMonitor()
task_queue = None

# 创建路由器
router = APIRouter(
    tags=["视觉分析"],
    responses={
        400: {"model": StandardResponse, "description": "请求参数错误"},
        401: {"model": StandardResponse, "description": "未授权访问"},
        403: {"model": StandardResponse, "description": "禁止访问"},
        404: {"model": StandardResponse, "description": "资源未找到"},
        500: {"model": StandardResponse, "description": "服务器内部错误"}
    }
)

# 状态映射
status_map = {
    "waiting": 0,     # 等待中
    "processing": 1,  # 运行中
    "completed": 2,   # 已完成
    "failed": -1      # 失败
}

# 基础请求模型
class BaseAnalysisRequest(BaseModel):
    """基础分析请求模型"""
    model_code: str = Field(..., description="模型代码")
    task_name: Optional[str] = Field(None, description="任务名称")
    callback_urls: Optional[str] = Field(None, description="回调地址，多个用逗号分隔")
    enable_callback: bool = Field(False, description="是否启用回调")
    save_result: bool = Field(False, description="是否保存结果")
    config: Optional[dict] = Field(None, description="分析配置")

class ImageAnalysisRequest(BaseAnalysisRequest):
    """图片分析请求"""
    image_urls: List[str] = Field(..., description="图片URL列表")
    is_base64: bool = Field(False, description="是否返回base64编码的结果图片")

class VideoAnalysisRequest(BaseAnalysisRequest):
    """视频分析请求"""
    video_url: str = Field(..., description="视频URL")

class StreamAnalysisRequest(BaseAnalysisRequest):
    """流分析请求"""
    stream_url: str = Field(..., description="流URL")
    analysis_type: AnalysisType = Field(..., description="分析类型")

class TaskStatusRequest(BaseModel):
    """任务状态查询请求"""
    task_id: str = Field(..., description="任务ID")

# 依赖注入函数
async def get_detector() -> YOLODetector:
    """获取检测器实例"""
    return detector

async def get_task_queue(db: Session = Depends(get_db_dependency)) -> TaskQueueManager:
    """获取任务队列管理器"""
    global task_queue
    if task_queue is None:
        task_queue = TaskQueueManager(db)
        await task_queue.start()
    return task_queue

@router.post(
    "/image",
    response_model=StandardResponse,
    summary="图片分析",
    description="""
    分析图片中的目标
    
    支持以下功能:
    - 目标检测
    - 实例分割
    - 目标跟踪
    
    请求示例:
    ```json
    {
        "model_code": "yolov8",
        "task_name": "行人检测-1",
        "image_urls": [
            "http://example.com/image.jpg"
        ],
        "callback_urls": "http://callback1,http://callback2",
        "enable_callback": true,
        "is_base64": false,
        "save_result": false,
        "config": {
            "confidence": 0.5,
            "iou": 0.45,
            "classes": [0, 2],
            "roi": {
                "x1": 0.1,
                "y1": 0.1,
                "x2": 0.9,
                "y2": 0.9
            },
            "imgsz": 640,
            "nested_detection": true
        }
    }
    ```
    """
)
async def analyze_image(
    request: Request,
    body: ImageAnalysisRequest,
    detector: YOLODetector = Depends(get_detector)
) -> StandardResponse:
    """图片分析接口"""
    try:
        # 记录请求参数
        logger.info(f"收到图片分析请求: {json.dumps(body.dict(), ensure_ascii=False)}")
        
        # 生成任务ID
        task_id = f"img_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        # 执行分析
        result = await detector.detect_images(
            body.model_code,
            body.image_urls,
            body.callback_urls,
            body.is_base64,
            config=body.config,
            task_name=body.task_name,
            enable_callback=body.enable_callback,
            save_result=body.save_result
        )
        
        # 记录结果
        logger.info(f"图片分析完成: task_id={task_id}, objects={len(result.get('detections', []))}")
        
        return StandardResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=True,
            message="图片分析成功",
            code=200,
            data={
                "task_id": task_id,
                "task_name": result.get("task_name"),
                "status": AnalysisStatus.COMPLETED,
                "image_url": body.image_urls[0],
                "saved_path": result.get("saved_path"),
                "objects": result.get("detections", []),
                "result_image": result.get("result_image") if body.is_base64 else None,
                "start_time": result.get("start_time"),
                "end_time": result.get("end_time"),
                "analysis_duration": result.get("analysis_duration")
            }
        )
        
    except Exception as e:
        logger.error(f"图片分析失败: {str(e)}", exc_info=True)
        if isinstance(e, (InvalidInputException, ModelLoadException, ProcessingException)):
            raise
        raise ProcessingException(f"图片分析失败: {str(e)}")

@router.post(
    "/video",
    response_model=StandardResponse,
    summary="视频分析",
    description="""
    分析视频中的目标
    
    支持以下功能:
    - 目标检测
    - 实例分割
    - 目标跟踪
    
    请求示例:
    ```json
    {
        "model_code": "yolov8",
        "task_name": "视频分析-1",
        "video_url": "http://example.com/video.mp4",
        "callback_urls": "http://callback1,http://callback2",
        "enable_callback": true,
        "save_result": false,
        "config": {
            "confidence": 0.5,
            "iou": 0.45,
            "classes": [0, 2],
            "roi": {
                "x1": 0.1,
                "y1": 0.1,
                "x2": 0.9,
                "y2": 0.9
            },
            "imgsz": 640,
            "nested_detection": true
        }
    }
    ```
    """
)
async def analyze_video(
    request: Request,
    body: VideoAnalysisRequest,
    background_tasks: BackgroundTasks,
    detector: YOLODetector = Depends(get_detector)
) -> StandardResponse:
    """视频分析接口"""
    try:
        # 记录请求参数
        logger.info(f"收到视频分析请求: {json.dumps(body.dict(), ensure_ascii=False)}")
        
        # 生成任务ID
        task_id = f"vid_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        # 启动视频分析任务
        task = await detector.start_video_analysis(
            task_id=task_id,
            model_code=body.model_code,
            video_url=body.video_url,
            callback_urls=body.callback_urls,
            config=body.config,
            task_name=body.task_name,
            enable_callback=body.enable_callback,
            save_result=body.save_result
        )
        
        # 记录任务信息
        logger.info(f"视频分析任务已启动: task_id={task_id}")
        
        return StandardResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=True,
            message="视频分析任务已启动",
            code=200,
            data={
                "task_id": task["task_id"],
                "task_name": task["task_name"],
                "status": AnalysisStatus.PROCESSING,
                "video_url": task["video_url"],
                "saved_path": task["saved_path"],
                "start_time": task["start_time"]
            }
        )
        
    except Exception as e:
        logger.error(f"视频分析任务启动失败: {str(e)}", exc_info=True)
        if isinstance(e, (InvalidInputException, ModelLoadException, ProcessingException)):
            raise
        raise ProcessingException(f"视频分析任务启动失败: {str(e)}")

@router.post(
    "/stream",
    response_model=StandardResponse,
    summary="流分析",
    description="""
    分析视频流中的目标
    
    支持以下功能:
    - 目标检测
    - 实例分割
    - 目标跟踪
    - 跨摄像头跟踪
    
    请求示例:
    ```json
    {
        "model_code": "yolov8",
        "task_name": "流分析-1",
        "stream_url": "rtsp://example.com/stream",
        "analysis_type": "detection",
        "callback_urls": "http://callback1,http://callback2",
        "enable_callback": true,
        "save_result": false,
        "config": {
            "confidence": 0.5,
            "iou": 0.45,
            "classes": [0, 2],
            "roi": {
                "x1": 0.1,
                "y1": 0.1,
                "x2": 0.9,
                "y2": 0.9
            },
            "imgsz": 640,
            "nested_detection": true
        }
    }
    ```
    """
)
async def analyze_stream(
    request: Request,
    body: StreamAnalysisRequest,
    queue: TaskQueueManager = Depends(get_task_queue)
) -> StandardResponse:
    """流分析接口"""
    try:
        # 记录请求参数
        logger.info(f"收到流分析请求: {json.dumps(body.dict(), ensure_ascii=False)}")
        
        # 生成任务ID
        task_id = f"str_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        # 创建流分析任务
        task = await queue.create_stream_task(
            task_id=task_id,
            model_code=body.model_code,
            stream_url=body.stream_url,
            analysis_type=body.analysis_type,
            callback_urls=body.callback_urls,
            config=body.config,
            task_name=body.task_name,
            enable_callback=body.enable_callback,
            save_result=body.save_result
        )
        
        # 记录任务信息
        logger.info(f"流分析任务已创建: task_id={task_id}")
        
        return StandardResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=True,
            message="流分析任务已创建",
            code=200,
            data={
                "task_id": task.task_id,
                "task_name": task.task_name,
                "status": AnalysisStatus.PENDING,
                "stream_url": task.stream_url,
                "analysis_type": task.analysis_type,
                "create_time": task.create_time
            }
        )
        
    except Exception as e:
        logger.error(f"流分析任务创建失败: {str(e)}", exc_info=True)
        if isinstance(e, (InvalidInputException, ModelLoadException, ProcessingException)):
            raise
        raise ProcessingException(f"流分析任务创建失败: {str(e)}")

@router.post(
    "/task/status",
    response_model=StandardResponse,
    summary="获取任务状态",
    description="获取分析任务的状态信息"
)
async def get_task_status(
    request: Request,
    body: TaskStatusRequest,
    queue: TaskQueueManager = Depends(get_task_queue)
) -> StandardResponse:
    """获取任务状态"""
    try:
        # 获取任务状态
        task = await queue.get_task_status(body.task_id)
        if not task:
            raise ResourceNotFoundException(f"任务不存在: {body.task_id}")
            
        return StandardResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=True,
            message="获取任务状态成功",
            code=200,
            data=task
        )
        
    except Exception as e:
        logger.error(f"获取任务状态失败: {str(e)}", exc_info=True)
        if isinstance(e, (ResourceNotFoundException,)):
            raise
        raise ProcessingException(f"获取任务状态失败: {str(e)}")

@router.post(
    "/task/stop",
    response_model=StandardResponse,
    summary="停止任务",
    description="停止指定的分析任务"
)
async def stop_task(
    request: Request,
    body: TaskStatusRequest,
    queue: TaskQueueManager = Depends(get_task_queue)
) -> StandardResponse:
    """停止任务"""
    try:
        # 停止任务
        result = await queue.stop_task(body.task_id)
        if not result:
            raise ResourceNotFoundException(f"任务不存在: {body.task_id}")
            
        return StandardResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=True,
            message="停止任务成功",
            code=200,
            data={"task_id": body.task_id}
        )
        
    except Exception as e:
        logger.error(f"停止任务失败: {str(e)}", exc_info=True)
        if isinstance(e, (ResourceNotFoundException,)):
            raise
        raise ProcessingException(f"停止任务失败: {str(e)}")

@router.post(
    "/resource",
    response_model=StandardResponse,
    summary="获取资源状态",
    description="获取系统资源使用状况"
)
async def get_resource_status(request: Request) -> StandardResponse:
    """获取资源状态"""
    try:
        # 获取资源状态
        status = resource_monitor.get_status()
        
        return StandardResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=True,
            message="获取资源状态成功",
            code=200,
            data=status
        )
        
    except Exception as e:
        logger.error(f"获取资源状态失败: {str(e)}", exc_info=True)
        raise ProcessingException(f"获取资源状态失败: {str(e)}")

# 添加新的请求模型
class VideoStatusRequest(BaseModel):
    """视频状态查询请求"""
    task_id: str = Field(..., description="任务ID")

@router.post("/video/status", response_model=VideoAnalysisResponse, summary="获取视频状态", description="获取指定视频分析任务的状态")
async def get_video_status(
    request: Request,
    body: VideoStatusRequest
) -> VideoAnalysisResponse:
    """
    获取视频分析任务状态
    
    Args:
        request: FastAPI请求对象
        body: 视频状态查询请求体
    
    Returns:
        VideoAnalysisResponse: 视频分析状态
        
    请求示例:
    ```json
    {
        "task_id": "550e8400-e29b-41d4-a716-446655440000"  // 任务ID
    }
    ```
    """
    try:
        # 获取任务状态
        task = await detector.get_video_task_status(body.task_id)
        if not task:
            return VideoAnalysisResponse(
                requestId=str(uuid.uuid4()),
                path=str(request.url.path),
                success=False,
                message=f"任务 {body.task_id} 不存在",
                code=404,
                data=None
            )
            
        # 将字符串状态转换为数字状态
        status = status_map.get(task.get('status', 'processing'), 1)  # 默认为运行中
        
        # 构建响应数据
        analysis_data = VideoAnalysisData(
            task_id=body.task_id,
            task_name=task.get('task_name'),
            status=status,
            video_url=task.get('video_url'),
            saved_path=task.get('saved_path'),
            start_time=task.get('start_time'),
            end_time=task.get('end_time'),
            analysis_duration=task.get('analysis_duration'),
            progress=task.get('progress'),
            total_frames=task.get('total_frames'),
            processed_frames=task.get('processed_frames')
        )
        
        return VideoAnalysisResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=True,
            message="获取任务状态成功",
            code=200,
            data=analysis_data
        )
        
    except Exception as e:
        logger.error(f"获取视频分析任务状态失败: {str(e)}", exc_info=True)
        return VideoAnalysisResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=False,
            message=f"获取任务状态失败: {str(e)}",
            code=500,
            data=None
        )

class VideoStopRequest(BaseModel):
    """停止视频分析任务请求"""
    task_id: str = Field(..., description="任务ID")

@router.post("/video/stop", response_model=BaseApiResponse, summary="停止视频分析", description="停止指定的视频分析任务")
async def stop_video_analysis(
    request: Request,
    body: VideoStopRequest
) -> BaseApiResponse:
    """
    停止视频分析任务
    
    Args:
        request: FastAPI请求对象
        body: 停止视频分析请求体
    
    Returns:
        BaseApiResponse: 停止结果
        
    请求示例:
    ```json
    {
        "task_id": "550e8400-e29b-41d4-a716-446655440000"  // 任务ID
    }
    ```
    """
    try:
        # 停止任务
        result = await detector.stop_video_task(body.task_id)
        if not result:
            return BaseApiResponse(
                requestId=str(uuid.uuid4()),
                path=str(request.url.path),
                success=False,
                message=f"任务 {body.task_id} 不存在",
                code=404,
                data=None
            )
            
        return BaseApiResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=True,
            message="任务已停止",
            code=200,
            data={
                "task_id": body.task_id
            }
        )
        
    except Exception as e:
        logger.error(f"停止视频分析任务失败: {str(e)}", exc_info=True)
        return BaseApiResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=False,
            message=f"停止任务失败: {str(e)}",
            code=500,
            data=None
        )