"""
视频源路由
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from api_service.models.requests import StreamCreate, StreamUpdate, StreamStatus
from api_service.models.responses import BaseResponse, StreamResponse
from api_service.services.stream import StreamService
from api_service.services.database import get_db
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/streams", tags=["视频源"])
stream_service = StreamService()  # 创建服务实例

@router.post("", response_model=BaseResponse)
async def create_stream(
    data: StreamCreate,
    db: Session = Depends(get_db)
):
    """创建流"""
    try:
        created_stream = stream_service.create_stream(db, data)
        return BaseResponse(
            code=200,
            message="创建成功",
            data=StreamResponse.from_orm(created_stream).dict()
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Create stream failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@router.get("", response_model=BaseResponse,
    description="获取视频源列表",
    responses={
        200: {
            "description": "成功获取视频源列表",
            "content": {
                "application/json": {
                    "example": {
                        "code": 200,
                        "message": "Success",
                        "data": {
                            "total": 1,
                            "items": [{
                                "id": 1,
                                "name": "测试视频源",
                                "url": "rtsp://example.com/stream",
                                "description": "测试用视频源",
                                "status": "active",
                                "error_message": None
                            }]
                        }
                    }
                }
            }
        }
    }
)
async def get_streams(
    skip: int = 0,
    limit: int = 100,
    status: Optional[StreamStatus] = None,
    db: Session = Depends(get_db)
):
    """
    获取视频源列表
    
    可用状态:
    - active: 正在运行
    - inactive: 未运行
    - error: 发生错误
    - connecting: 正在连接
    - disconnected: 连接断开
    - paused: 已暂停
    """
    try:
        streams = stream_service.get_streams(db, skip, limit, status)
        return BaseResponse(
            message="获取成功",
            data={
                "total": len(streams),
                "items": [
                    {
                        "id": s.id,
                        "name": s.name,
                        "url": s.url,
                        "description": s.description,
                        "status": s.status,
                        "error_message": s.error_message
                    } for s in streams
                ]
            }
        )
    except Exception as e:
        logger.error(f"Get streams failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{stream_id}", response_model=BaseResponse)
async def get_stream(stream_id: int, db: Session = Depends(get_db)):
    """获取视频源"""
    try:
        result = stream_service.get_stream(db, stream_id)
        if not result:
            raise HTTPException(status_code=404, detail="Stream not found")
        return BaseResponse(
            code=200,
            message="获取成功",
            data=StreamResponse.from_orm(result).dict()
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Get stream failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@router.put("/{stream_id}", response_model=BaseResponse)
async def update_stream(
    stream_id: int,
    request: StreamUpdate,
    db: Session = Depends(get_db)
):
    """更新视频源"""
    try:
        result = stream_service.update_stream(
            db,
            stream_id,
            request
        )
        if not result:
            raise HTTPException(status_code=404, detail="Stream not found")
        return BaseResponse(
            code=200,
            message="更新成功",
            data=StreamResponse.from_orm(result).dict()
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Update stream failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@router.delete("/{stream_id}", response_model=BaseResponse)
async def delete_stream(stream_id: int, db: Session = Depends(get_db)):
    """删除视频源"""
    try:
        success = stream_service.delete_stream(db, stream_id)
        if not success:
            raise HTTPException(status_code=404, detail="Stream not found")
        return BaseResponse(
            code=200,
            message="删除成功"
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Delete stream failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        ) 