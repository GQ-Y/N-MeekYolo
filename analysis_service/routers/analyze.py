"""
分析路由
处理分析请求
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from pydantic import BaseModel
from analysis_service.core.detector import YOLODetector
from analysis_service.core.queue import TaskQueueManager
from analysis_service.core.resource import ResourceMonitor
from analysis_service.models.responses import (
    ImageAnalysisResponse,
    VideoAnalysisResponse,
    StreamAnalysisResponse,
    BaseResponse,
    StreamResponse
)
from shared.utils.logger import setup_logger
from analysis_service.services.database import get_db_dependency
from analysis_service.crud import task as task_crud
import asyncio
import time
from sqlalchemy.orm import Session

logger = setup_logger(__name__)

# 初始化组件
detector = YOLODetector()
resource_monitor = ResourceMonitor()
task_queue = None

router = APIRouter(prefix="/analyze")

# 依赖注入
async def get_task_queue(db: Session = Depends(get_db_dependency)) -> TaskQueueManager:
    global task_queue
    if task_queue is None:
        task_queue = TaskQueueManager(db)
        await task_queue.start()
    return task_queue

class ImageAnalysisRequest(BaseModel):
    """图片分析请求"""
    model_code: str
    image_urls: List[str]
    callback_urls: str = None
    is_base64: bool = False

class VideoAnalysisRequest(BaseModel):
    """视频分析请求"""
    model_code: str
    video_url: str
    callback_urls: str = None

class StreamAnalysisRequest(BaseModel):
    """流分析请求"""
    model_code: str
    stream_url: str
    callback_urls: str
    output_url: Optional[str] = None
    callback_interval: int = 1

@router.post("/image", response_model=ImageAnalysisResponse)
async def analyze_image(request: ImageAnalysisRequest):
    """分析图片"""
    try:
        result = await detector.detect_images(
            request.model_code,
            request.image_urls,
            request.callback_urls,
            request.is_base64
        )
        logger.info(f"Detection result: {result}")
        response = ImageAnalysisResponse(
            image_url=request.image_urls[0],
            detections=result.get('detections', []),
            result_image=result.get('result_image')
        )
        return response
    except Exception as e:
        logger.error(f"Image analysis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/video", response_model=VideoAnalysisResponse)
async def analyze_video(request: VideoAnalysisRequest):
    """分析视频"""
    try:
        task = await detector.start_video_analysis(
            request.model_code,
            request.video_url
        )
        return VideoAnalysisResponse(**task)
    except Exception as e:
        logger.error(f"Video analysis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stream", response_model=StreamResponse)
async def analyze_stream(
    request: StreamAnalysisRequest,
    queue: TaskQueueManager = Depends(get_task_queue),
    db: Session = Depends(get_db_dependency)
) -> StreamResponse:
    """处理流分析请求"""
    try:
        # 检查资源是否足够
        if not resource_monitor.has_available_resource():
            raise HTTPException(
                status_code=503,
                detail="资源不足,请稍后重试"
            )
            
        # 创建任务记录
        task = task_crud.create_task(
            db=db,
            task_id=None,  # 由TaskQueue生成ID
            model_code=request.model_code,
            stream_url=request.stream_url,
            callback_urls=request.callback_urls,
            output_url=request.output_url
        )
        
        # 加入任务队列
        queue_task = await queue.add_task(task)
        
        return StreamResponse(
            code=200,
            message="Stream analysis task queued",
            data={
                "task_id": queue_task.id,
                "status": "queued",
                "stream_url": request.stream_url,
                "output_url": request.output_url
            }
        )
        
    except Exception as e:
        logger.error(f"Queue stream analysis task failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@router.post("/stream/{task_id}/stop")
async def stop_stream_analysis(
    task_id: str,
    queue: TaskQueueManager = Depends(get_task_queue)
):
    """停止流分析"""
    try:
        await queue.cancel_task(task_id)
        return {
            "code": 200,
            "message": "Task cancelled successfully",
            "data": {"task_id": task_id}
        }
    except Exception as e:
        logger.error(f"Cancel task failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stream/{task_id}/status", response_model=BaseResponse)
async def get_stream_status(
    task_id: str,
    queue: TaskQueueManager = Depends(get_task_queue)
):
    """获取流分析状态"""
    try:
        status = await queue.get_task_status(task_id)
        return {
            "code": 200,
            "message": "success",
            "data": status
        }
    except Exception as e:
        logger.error(f"Get task status failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/resource", response_model=BaseResponse)
async def get_resource_status():
    """获取资源状态"""
    try:
        status = resource_monitor.get_resource_usage()
        return {
            "code": 200,
            "message": "success",
            "data": status
        }
    except Exception as e:
        logger.error(f"Get resource status failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))