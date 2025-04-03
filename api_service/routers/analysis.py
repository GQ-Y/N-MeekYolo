"""
分析路由模块

提供目标检测分析的管理接口，支持：
- 图片分析：支持单张或多张图片的目标检测分析
- 视频分析：支持视频文件的目标检测分析
- 流分析：支持实时视频流的目标检测分析
- 任务管理：支持停止正在进行的分析任务
"""
from fastapi import APIRouter, Request
from typing import List, Dict, Any
from models.requests import ImageAnalysisRequest, VideoAnalysisRequest, StreamAnalysisRequest
from models.responses import BaseResponse
from services.analysis import AnalysisService
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/v1/analysis", tags=["分析"])

analysis_service = AnalysisService()

@router.post("/image/analyze", response_model=BaseResponse, summary="图片分析")
async def analyze_image(
    request: Request,
    analysis_request: ImageAnalysisRequest
):
    """
    对图片进行目标检测分析
    
    参数:
    - model_code: 使用的模型代码
    - image_urls: 待分析的图片URL列表
    - callback_url: 分析结果回调地址
    - is_base64: 图片是否为base64编码
    
    返回:
    - task_id: 分析任务ID，用于后续查询或停止任务
    """
    try:
        task_id = await analysis_service.analyze_image(
            analysis_request.model_code,
            analysis_request.image_urls,
            analysis_request.callback_url,
            analysis_request.is_base64
        )
        return BaseResponse(
            path=str(request.url),
            message="分析任务创建成功",
            data={"task_id": task_id}
        )
    except Exception as e:
        logger.error(f"图片分析任务创建失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/video/analyze", response_model=BaseResponse, summary="视频分析")
async def analyze_video(
    request: Request,
    analysis_request: VideoAnalysisRequest
):
    """
    对视频文件进行目标检测分析
    
    参数:
    - model_code: 使用的模型代码
    - video_url: 待分析的视频URL
    - callback_url: 分析结果回调地址
    
    返回:
    - task_id: 分析任务ID，用于后续查询或停止任务
    """
    try:
        task_id = await analysis_service.analyze_video(
            analysis_request.model_code,
            analysis_request.video_url,
            analysis_request.callback_url
        )
        return BaseResponse(
            path=str(request.url),
            message="分析任务创建成功",
            data={"task_id": task_id}
        )
    except Exception as e:
        logger.error(f"视频分析任务创建失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/stream/analyze", response_model=BaseResponse, summary="流分析")
async def analyze_stream(
    request: Request,
    analysis_request: StreamAnalysisRequest
):
    """
    对实时视频流进行目标检测分析
    
    参数:
    - model_code: 使用的模型代码
    - stream_url: 待分析的视频流URL
    - callback_url: 分析结果回调地址
    - output_url: 分析结果输出流地址(可选)
    - callback_interval: 回调间隔时间(秒)
    
    返回:
    - task_id: 分析任务ID，用于后续查询或停止任务
    """
    try:
        task_id = await analysis_service.analyze_stream(
            analysis_request.model_code,
            analysis_request.stream_url,
            analysis_request.callback_url,
            analysis_request.output_url,
            analysis_request.callback_interval
        )
        return BaseResponse(
            path=str(request.url),
            message="分析任务创建成功",
            data={"task_id": task_id}
        )
    except Exception as e:
        logger.error(f"视频流分析任务创建失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/task/stop", response_model=BaseResponse, summary="停止分析任务")
async def stop_analysis(
    request: Request,
    task_id: str
):
    """
    停止指定的分析任务
    
    参数:
    - task_id: 要停止的分析任务ID
    
    返回:
    - 操作结果
    """
    try:
        await analysis_service.stop_task(task_id)
        return BaseResponse(
            path=str(request.url),
            message="任务已停止"
        )
    except Exception as e:
        logger.error(f"停止分析任务失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        ) 