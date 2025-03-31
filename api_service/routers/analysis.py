"""
分析路由
"""
from fastapi import APIRouter, HTTPException
from typing import List
from api_service.models.requests import ImageAnalysisRequest, VideoAnalysisRequest, StreamAnalysisRequest
from api_service.models.responses import BaseResponse
from api_service.services.analysis import AnalysisService
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/v1/analysis", tags=["分析"])

analysis_service = AnalysisService()

@router.post("/image/analyze", response_model=BaseResponse)
async def analyze_image(request: ImageAnalysisRequest):
    """图片分析"""
    try:
        task_id = await analysis_service.analyze_image(
            request.model_code,
            request.image_urls,
            request.callback_url,
            request.is_base64
        )
        return BaseResponse(data={"task_id": task_id})
    except Exception as e:
        logger.error(f"Image analysis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/video/analyze", response_model=BaseResponse)
async def analyze_video(request: VideoAnalysisRequest):
    """视频分析"""
    try:
        task_id = await analysis_service.analyze_video(
            request.model_code,
            request.video_url,
            request.callback_url
        )
        return BaseResponse(data={"task_id": task_id})
    except Exception as e:
        logger.error(f"Video analysis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stream/analyze", response_model=BaseResponse)
async def analyze_stream(request: StreamAnalysisRequest):
    """流分析"""
    try:
        task_id = await analysis_service.analyze_stream(
            request.model_code,
            request.stream_url,
            request.callback_url,
            request.output_url,
            request.callback_interval
        )
        return BaseResponse(data={"task_id": task_id})
    except Exception as e:
        logger.error(f"Stream analysis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/task/stop", response_model=BaseResponse)
async def stop_analysis(task_id: str):
    """停止分析任务"""
    try:
        await analysis_service.stop_task(task_id)
        return BaseResponse(message="Task stopped successfully")
    except Exception as e:
        logger.error(f"Stop task failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 