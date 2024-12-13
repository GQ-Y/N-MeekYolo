"""
回调服务路由
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from api_service.models.requests import CallbackCreate, CallbackUpdate, StreamStatus
from api_service.models.responses import BaseResponse, CallbackResponse
from api_service.models.database import Stream
from api_service.crud import callback
from api_service.services.database import get_db
from shared.utils.logger import setup_logger
from datetime import datetime

logger = setup_logger(__name__)
router = APIRouter(prefix="/callbacks", tags=["回调服务"])

@router.post("", response_model=BaseResponse)
async def create_callback(request: CallbackCreate, db: Session = Depends(get_db)):
    """创建回调服务"""
    try:
        result = callback.create_callback(
            db,
            request.name,
            request.url,
            request.description,
            request.headers,
            request.retry_count,
            request.retry_interval
        )
        return BaseResponse(data=CallbackResponse.from_orm(result).dict())
    except Exception as e:
        logger.error(f"Create callback failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("", response_model=BaseResponse)
async def get_callbacks(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """获取回调服务列表"""
    try:
        callbacks = callback.get_callbacks(db, skip, limit)
        return BaseResponse(data={
            "total": len(callbacks),
            "items": [CallbackResponse.from_orm(c).dict() for c in callbacks]
        })
    except Exception as e:
        logger.error(f"Get callbacks failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{callback_id}", response_model=BaseResponse)
async def get_callback(callback_id: int, db: Session = Depends(get_db)):
    """获取回调服务"""
    try:
        result = callback.get_callback(db, callback_id)
        if not result:
            raise HTTPException(status_code=404, detail="Callback not found")
        return BaseResponse(data=CallbackResponse.from_orm(result).dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get callback failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{callback_id}", response_model=BaseResponse)
async def update_callback(
    callback_id: int,
    request: CallbackUpdate,
    db: Session = Depends(get_db)
):
    """更新回调服务"""
    try:
        result = callback.update_callback(
            db,
            callback_id,
            request.name,
            request.url,
            request.description,
            request.headers,
            request.retry_count,
            request.retry_interval
        )
        if not result:
            raise HTTPException(status_code=404, detail="Callback not found")
        return BaseResponse(data=CallbackResponse.from_orm(result).dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update callback failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{callback_id}", response_model=BaseResponse)
async def delete_callback(callback_id: int, db: Session = Depends(get_db)):
    """删除回调服务"""
    try:
        success = callback.delete_callback(db, callback_id)
        if not success:
            raise HTTPException(status_code=404, detail="Callback not found")
        return BaseResponse(message="Callback deleted successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete callback failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/analysis/callback", response_model=BaseResponse)
async def analysis_callback(
    callback_data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """接收分析服务回调"""
    try:
        logger.info(f"Received analysis callback: {callback_data}")
        
        # 获取任务ID和状态
        task_id = callback_data.get("task_id")
        status = callback_data.get("status")
        
        if not task_id or not status:
            raise HTTPException(status_code=400, detail="Invalid callback data")
            
        # 如果是停止状态,更新关联视频源状态
        if status == "stopped":
            stream_url = callback_data.get("stream_url")
            if stream_url:
                # 查找对应的视频源
                stream = db.query(Stream).filter(Stream.url == stream_url).first()
                if stream:
                    # 更新状态为断开连接
                    stream.status = StreamStatus.DISCONNECTED
                    stream.updated_at = datetime.now()
                    db.commit()
                    logger.info(f"Updated stream {stream.id} status to disconnected")
                    
        return BaseResponse(message="Callback processed successfully")
        
    except Exception as e:
        logger.error(f"Process analysis callback failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 