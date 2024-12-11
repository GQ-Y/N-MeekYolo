"""
分析路由
处理分析请求
"""
from fastapi import APIRouter, HTTPException
from typing import List
from pydantic import BaseModel
from analysis_service.core.detector import YOLODetector
from analysis_service.models.responses import (
    ImageAnalysisResponse,
    VideoAnalysisResponse,
    StreamAnalysisResponse
)
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter()
detector = YOLODetector()

class ImageAnalysisRequest(BaseModel):
    """图片分析请求"""
    model_code: str
    image_urls: List[str]
    callback_url: str = None
    is_base64: bool = False

class VideoAnalysisRequest(BaseModel):
    """视频分析请求"""
    model_code: str
    video_url: str
    callback_url: str = None

class StreamAnalysisRequest(BaseModel):
    """流分析请求"""
    model_code: str
    stream_url: str
    callback_url: str = None
    output_url: str = None
    callback_interval: int = 1

@router.post("/image", response_model=ImageAnalysisResponse)
async def analyze_image(request: ImageAnalysisRequest):
    """分析图片"""
    try:
        result = await detector.detect_images(
            request.model_code,
            request.image_urls,
            request.callback_url,
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

@router.post("/stream", response_model=StreamAnalysisResponse)
async def analyze_stream(request: StreamAnalysisRequest):
    """分析RTSP流"""
    try:
        task = await detector.start_stream_analysis(
            request.model_code,
            request.stream_url,
            request.callback_url,
            request.output_url,
            request.callback_interval
        )
        return StreamAnalysisResponse(**task)
    except Exception as e:
        logger.error(f"Stream analysis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stream/{task_id}/stop")
async def stop_stream_analysis(task_id: str):
    """停止流分析"""
    try:
        result = await detector.stop_stream_analysis(task_id)
        return StreamAnalysisResponse(**result)
    except Exception as e:
        logger.error(f"Stop stream analysis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 