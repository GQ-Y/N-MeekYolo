"""
视频流播放路由

提供视频流播放功能，支持将RTSP/RTMP流转换为HLS协议以便在Web浏览器中播放
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from typing import Optional
from models.responses import BaseResponse
from services.database import get_db
from services.stream_player import StreamPlayerService
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/v1/stream-player", tags=["视频流播放"])

# 创建服务实例
stream_player_service = StreamPlayerService()

@router.post("/play", response_model=BaseResponse, summary="获取视频流播放地址")
async def get_playable_url(
    request: Request,
    stream_id: int,
    db: Session = Depends(get_db)
):
    """
    获取视频流的可播放地址，自动将RTSP/RTMP流转换为HLS格式
    
    参数:
    - stream_id: 视频流ID
    
    返回:
    - original_url: 原始视频流地址
    - playable_url: 可播放的视频流地址（HLS格式）
    - protocol: 播放协议
    - converted: 是否进行了转换
    """
    try:
        result = await stream_player_service.get_playable_url(db, stream_id)
        return BaseResponse(
            path=str(request.url),
            message="获取播放地址成功",
            data=result
        )
    except Exception as e:
        logger.error(f"获取视频流播放地址失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/stop", response_model=BaseResponse, summary="停止视频流转换")
async def stop_conversion(
    request: Request,
    stream_id: int
):
    """
    停止指定视频流的转换进程
    
    参数:
    - stream_id: 视频流ID
    
    返回:
    - 操作结果
    """
    try:
        stream_player_service._stop_conversion(stream_id)
        return BaseResponse(
            path=str(request.url),
            message="停止转换成功",
            data={"stream_id": stream_id}
        )
    except Exception as e:
        logger.error(f"停止视频流转换失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        ) 