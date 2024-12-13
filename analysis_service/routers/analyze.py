"""
分析路由
处理分析请求
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from pydantic import BaseModel
from analysis_service.core.detector import YOLODetector
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
logger.info("初始化 YOLODetector...")
detector = YOLODetector()
logger.info("YOLODetector 初始化完成")
router = APIRouter(prefix="/analyze")

# 依赖注入获取检测器实例
def get_detector():
    return detector

# 依赖注入获取数据库会话
def get_db():
    db = get_db_dependency()
    try:
        yield db
    finally:
        db.close()

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
    detector: YOLODetector = Depends(get_detector),
    db: Session = Depends(get_db_dependency)
) -> StreamResponse:
    """处理流分析请求"""
    try:
        # 生成任务ID
        task_id = f"stream_{int(time.time())}"
        
        # 创建任务记录
        task = task_crud.create_task(
            db=db,
            task_id=task_id,
            model_code=request.model_code,
            stream_url=request.stream_url,
            callback_urls=request.callback_urls,
            output_url=request.output_url
        )
        
        # 启动流分析
        result = await detector.start_stream_analysis(
            model_code=request.model_code,
            stream_url=request.stream_url,
            callback_urls=request.callback_urls,
            output_url=request.output_url,
            callback_interval=request.callback_interval
        )
        
        # 更新任务状态为运行中
        task_crud.update_task_status(db, task_id, 1)
        
        return StreamResponse(
            code=200,
            message="Stream analysis started",
            data={
                "task_id": result["task_id"],
                "status": result["status"],
                "stream_url": result["stream_url"],
                "output_url": result["output_url"]
            }
        )
        
    except Exception as e:
        logger.error(f"Start stream analysis failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@router.post("/stream/{task_id}/stop")
async def stop_stream_analysis(task_id: str):
    """停止流分析"""
    try:
        result = await detector.stop_stream_analysis(task_id)
        return StreamAnalysisResponse(**result)
    except Exception as e:
        logger.error(f"Stop stream analysis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stream/{task_id}/status", response_model=BaseResponse)
async def get_stream_status(
    task_id: str,
    db: Session = Depends(get_db)
):
    """获取流分析状态"""
    try:
        task = task_crud.get_task(db, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
            
        return {
            "code": 200,
            "message": "success",
            "data": task.to_dict()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get task status failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 