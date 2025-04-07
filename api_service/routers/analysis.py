"""
分析路由模块

提供目标检测分析的管理接口，支持：
- 图片分析：支持单张或多张图片的目标检测分析
- 视频分析：支持视频文件的目标检测分析
- 流分析：支持实时视频流的目标检测分析
- 任务管理：支持停止正在进行的分析任务
"""
from fastapi import APIRouter, Request, Depends
from typing import List, Dict, Any
from models.requests import ImageAnalysisRequest, VideoAnalysisRequest, StreamAnalysisRequest
from models.responses import BaseResponse
from services.analysis_client import AnalysisClient
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/v1/analysis", tags=["分析"])

# 依赖注入函数，从请求状态中获取分析服务客户端
def get_analysis_client(request: Request) -> AnalysisClient:
    return request.state.analysis_client

@router.post("/image/analyze", response_model=BaseResponse, summary="图片分析")
async def analyze_image(
    request: Request,
    analysis_request: ImageAnalysisRequest,
    analysis_client: AnalysisClient = Depends(get_analysis_client)
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
        result = await analysis_client.analyze_image(
            model_code=analysis_request.model_code,
            image_urls=analysis_request.image_urls,
            config=analysis_request.config,
            task_name=analysis_request.task_name,
            callback_urls=analysis_request.callback_url,
            enable_callback=True if analysis_request.callback_url else False,
            save_result=analysis_request.save_result,
            is_base64=analysis_request.is_base64
        )
        
        # 使用返回的结果构建响应
        return BaseResponse(
            requestId=result.get("requestId", ""),
            path=str(request.url),
            success=result.get("success", True),
            message=result.get("message", "分析任务创建成功"),
            code=result.get("code", 200),
            data=result.get("data", {"task_id": ""}),
            timestamp=result.get("timestamp", 0)
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
    analysis_request: VideoAnalysisRequest,
    analysis_client: AnalysisClient = Depends(get_analysis_client)
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
        result = await analysis_client.analyze_video(
            model_code=analysis_request.model_code,
            video_url=analysis_request.video_url,
            config=analysis_request.config,
            task_name=analysis_request.task_name,
            callback_urls=analysis_request.callback_url,
            enable_callback=True if analysis_request.callback_url else False,
            save_result=analysis_request.save_result
        )
        
        # 使用返回的结果构建响应
        return BaseResponse(
            requestId=result.get("requestId", ""),
            path=str(request.url),
            success=result.get("success", True),
            message=result.get("message", "分析任务创建成功"),
            code=result.get("code", 200),
            data=result.get("data", {"task_id": ""}),
            timestamp=result.get("timestamp", 0)
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
    analysis_request: StreamAnalysisRequest,
    analysis_client: AnalysisClient = Depends(get_analysis_client)
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
        # 构建配置
        config = analysis_request.config or {}
        if analysis_request.callback_interval:
            config["callback_interval"] = analysis_request.callback_interval
        if analysis_request.output_url:
            config["output_url"] = analysis_request.output_url
        
        result = await analysis_client.analyze_stream(
            model_code=analysis_request.model_code,
            stream_url=analysis_request.stream_url,
            config=config,
            task_name=analysis_request.task_name,
            callback_urls=analysis_request.callback_url,
            enable_callback=True if analysis_request.callback_url else False,
            save_result=analysis_request.save_result,
            task_id=analysis_request.task_id
        )
        
        # 使用返回的结果构建响应
        return BaseResponse(
            requestId=result.get("requestId", ""),
            path=str(request.url),
            success=result.get("success", True),
            message=result.get("message", "分析任务创建成功"),
            code=result.get("code", 200),
            data=result.get("data", {"task_id": ""}),
            timestamp=result.get("timestamp", 0)
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
    task_id: str,
    analysis_client: AnalysisClient = Depends(get_analysis_client)
):
    """
    停止指定的分析任务
    
    参数:
    - task_id: 要停止的分析任务ID
    
    返回:
    - 操作结果
    """
    try:
        result = await analysis_client.stop_task(task_id)
        
        # 使用返回的结果构建响应
        return BaseResponse(
            requestId=result.get("requestId", ""),
            path=str(request.url),
            success=result.get("success", True),
            message=result.get("message", "任务已停止"),
            code=result.get("code", 200),
            data=result.get("data", None),
            timestamp=result.get("timestamp", 0)
        )
    except Exception as e:
        logger.error(f"停止分析任务失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )
        
@router.post("/resource", response_model=BaseResponse, summary="获取资源状态")
async def get_resource_status(
    request: Request,
    analysis_client: AnalysisClient = Depends(get_analysis_client)
):
    """
    获取分析服务的资源状态
    
    返回:
    - 资源状态信息
    """
    try:
        result = await analysis_client.get_resource_status()
        
        # 使用返回的结果构建响应
        return BaseResponse(
            requestId=result.get("requestId", ""),
            path=str(request.url),
            success=result.get("success", True),
            message=result.get("message", "资源状态获取成功"),
            code=result.get("code", 200),
            data=result.get("data", {}),
            timestamp=result.get("timestamp", 0)
        )
    except Exception as e:
        logger.error(f"获取资源状态失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        ) 