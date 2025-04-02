"""
分析路由模块
处理视觉分析请求，包括图片分析、视频分析和流分析
"""
import os
import json
import uuid
import tempfile
from pathlib import Path
from typing import List, Optional, Union
from fastapi import APIRouter, HTTPException, Depends, File, UploadFile, Form, BackgroundTasks, Request
from pydantic import BaseModel, Field, validator
from core.detector import YOLODetector
from core.redis_manager import RedisManager
from core.task_queue import TaskQueue, TaskStatus
from core.resource import ResourceMonitor
from core.models import (
    StandardResponse,
    AnalysisType,
    AnalysisStatus,
    DetectionResult,
    SegmentationResult,
    TrackingResult,
    CrossCameraResult
)
from core.exceptions import (
    InvalidInputException,
    ModelLoadException,
    ProcessingException,
    ResourceNotFoundException
)
from models.responses import (
    ImageAnalysisResponse,
    VideoAnalysisResponse,
    StreamAnalysisResponse,
    BaseApiResponse,
    StreamBatchData,
    ImageAnalysisData,
    VideoAnalysisData,
    ResourceStatusResponse
)
from models.requests import (
    ImageAnalysisRequest,
    VideoAnalysisRequest,
    StreamAnalysisRequest,
    StreamTask,
    TaskStatusRequest
)
from shared.utils.logger import setup_logger
from core.config import settings
from datetime import datetime
import base64
import re

logger = setup_logger(__name__)

# 初始化组件
detector = YOLODetector()
resource_monitor = ResourceMonitor()
redis_manager = RedisManager()
task_queue = TaskQueue()

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
    
    model_config = {"protected_namespaces": ()}

class ImageAnalysisRequest(BaseAnalysisRequest):
    """图片分析请求"""
    image_urls: List[str] = Field(..., description="图片URL列表，支持以下格式：\n- HTTP/HTTPS URL\n- Base64编码的图片数据（以 'data:image/' 开头）\n- Blob URL（以 'blob:' 开头）")
    is_base64: bool = Field(False, description="是否返回base64编码的结果图片")

    @validator('image_urls')
    def validate_image_urls(cls, v):
        for url in v:
            # 检查是否是有效的 HTTP/HTTPS URL
            if url.startswith(('http://', 'https://')):
                continue
            # 检查是否是有效的 Base64 图片数据
            elif url.startswith('data:image/'):
                try:
                    # 提取实际的 base64 数据
                    base64_data = url.split(',')[1]
                    base64.b64decode(base64_data)
                except:
                    raise ValueError(f"Invalid base64 image data: {url[:50]}...")
            # 检查是否是有效的 Blob URL
            elif url.startswith('blob:'):
                if not re.match(r'^blob:(http[s]?://[^/]+/[a-f0-9-]+)$', url):
                    raise ValueError(f"Invalid blob URL: {url}")
            else:
                raise ValueError(f"Unsupported image URL format: {url}")
        return v

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

async def get_redis() -> RedisManager:
    """获取Redis管理器实例"""
    return redis_manager

async def get_task_queue() -> TaskQueue:
    """获取任务队列实例"""
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
        result = await detector.start_video_analysis(
            task_id=task_id,
            model_code=body.model_code,
            video_url=body.video_url,
            callback_urls=body.callback_urls,
            config=body.config,
            task_name=body.task_name,
            enable_callback=body.enable_callback,
            save_result=body.save_result
        )
        
        # 记录结果
        logger.info(f"视频分析任务已启动: task_id={task_id}")
        
        return StandardResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=True,
            message="视频分析任务已启动",
            code=200,
            data={
                "task_id": task_id,
                "task_name": body.task_name,
                "status": result.get("status", TaskStatus.PROCESSING),
                "video_url": body.video_url,
                "start_time": result.get("start_time"),
                "progress": result.get("progress", 0)
            }
        )
        
    except Exception as e:
        logger.error(f"启动视频分析任务失败: {str(e)}", exc_info=True)
        if isinstance(e, (InvalidInputException, ModelLoadException, ProcessingException)):
            raise
        raise ProcessingException(f"启动视频分析任务失败: {str(e)}")

@router.post(
    "/task/status",
    response_model=StandardResponse,
    summary="获取任务状态",
    description="获取分析任务的状态信息"
)
async def get_task_status(
    request: Request,
    body: TaskStatusRequest,
    task_queue: TaskQueue = Depends(get_task_queue)
) -> StandardResponse:
    """获取任务状态"""
    try:
        # 获取任务信息
        task_info = await task_queue.get_task(body.task_id)
        if not task_info:
            raise ResourceNotFoundException(f"任务 {body.task_id} 不存在")
            
        return StandardResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=True,
            message="获取任务状态成功",
            code=200,
            data=task_info
        )
        
    except Exception as e:
        logger.error(f"获取任务状态失败: {str(e)}", exc_info=True)
        if isinstance(e, ResourceNotFoundException):
            raise
        raise ProcessingException(f"获取任务状态失败: {str(e)}")

@router.post("/task/stop", response_model=StandardResponse, summary="停止任务", description="停止指定的任务")
async def stop_task(
    request: Request,
    body: TaskStatusRequest,
    detector: YOLODetector = Depends(get_detector)
) -> StandardResponse:
    """停止任务"""
    try:
        # 获取任务信息
        task_info = await detector._get_task_info(body.task_id)
        if not task_info:
            raise ResourceNotFoundException(f"任务 {body.task_id} 不存在")
            
        # 更新任务状态为停止中
        task_info["status"] = TaskStatus.STOPPING
        await detector._update_task_info(body.task_id, task_info)
        await detector.task_queue.update_task_status(body.task_id, TaskStatus.STOPPING, task_info)
        
        return StandardResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=True,
            message="任务已开始停止",
            code=200,
            data={
                "task_id": body.task_id,
                "status": TaskStatus.STOPPING
            }
        )
        
    except Exception as e:
        logger.error(f"停止任务失败: {str(e)}", exc_info=True)
        if isinstance(e, ResourceNotFoundException):
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

@router.post(
    "/video/status",
    response_model=StandardResponse,
    summary="获取视频状态",
    description="获取指定视频分析任务的状态"
)
async def get_video_status(
    request: Request,
    body: TaskStatusRequest,
    detector: YOLODetector = Depends(get_detector)
) -> StandardResponse:
    """获取视频分析任务状态"""
    try:
        # 获取任务状态
        status_info = await detector.get_video_task_status(body.task_id)
        if not status_info:
            raise ResourceNotFoundException(f"任务 {body.task_id} 不存在")
            
        return StandardResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=True,
            message="获取任务状态成功",
            code=200,
            data=status_info
        )
        
    except Exception as e:
        logger.error(f"获取任务状态失败: {str(e)}", exc_info=True)
        if isinstance(e, ResourceNotFoundException):
            raise
        raise ProcessingException(f"获取任务状态失败: {str(e)}")

@router.post(
    "/stream",
    response_model=StandardResponse,
    summary="流分析",
    description="""
    分析视频流中的目标
    
    支持以下格式:
    - RTSP流 (rtsp://)
    - RTMP流 (rtmp://)
    - HTTP流 (http://, https://)
    
    支持以下功能:
    - 目标检测
    - 实例分割
    - 目标跟踪
    
    请求示例:
    ```json
    {
        "model_code": "yolov8",
        "task_name": "流分析-1",
        "stream_url": "rtsp://example.com/stream",
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
    background_tasks: BackgroundTasks,
    detector: YOLODetector = Depends(get_detector)
) -> StandardResponse:
    """流分析接口"""
    try:
        # 记录请求参数
        logger.info(f"收到流分析请求: {json.dumps(body.dict(), ensure_ascii=False)}")
        
        # 生成任务ID
        task_id = f"str_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        # 启动流分析任务
        result = await detector.start_stream_analysis(
            task_id=task_id,
            model_code=body.model_code,
            stream_url=body.stream_url,
            callback_urls=body.callback_urls,
            config=body.config,
            task_name=body.task_name,
            enable_callback=body.enable_callback,
            save_result=body.save_result
        )
        
        # 记录结果
        logger.info(f"流分析任务已启动: task_id={task_id}")
        
        return StandardResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=True,
            message="流分析任务已启动",
            code=200,
            data={
                "task_id": task_id,
                "task_name": body.task_name,
                "status": result.get("status", TaskStatus.PROCESSING),
                "stream_url": body.stream_url,
                "start_time": result.get("start_time"),
                "progress": result.get("progress", 0)
            }
        )
        
    except Exception as e:
        logger.error(f"启动流分析任务失败: {str(e)}", exc_info=True)
        if isinstance(e, (InvalidInputException, ModelLoadException, ProcessingException)):
            raise
        raise ProcessingException(f"启动流分析任务失败: {str(e)}")

@router.post(
    "/stream/status",
    response_model=StandardResponse,
    summary="获取流状态",
    description="获取指定流分析任务的状态"
)
async def get_stream_status(
    request: Request,
    body: TaskStatusRequest,
    detector: YOLODetector = Depends(get_detector)
) -> StandardResponse:
    """获取流分析任务状态"""
    try:
        # 获取任务状态
        status_info = await detector.get_video_task_status(body.task_id)
        if not status_info:
            raise ResourceNotFoundException(f"任务 {body.task_id} 不存在")
            
        return StandardResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=True,
            message="获取任务状态成功",
            code=200,
            data=status_info
        )
        
    except Exception as e:
        logger.error(f"获取任务状态失败: {str(e)}", exc_info=True)
        if isinstance(e, ResourceNotFoundException):
            raise
        raise ProcessingException(f"获取任务状态失败: {str(e)}")