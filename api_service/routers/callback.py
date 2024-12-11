"""
回调服务路由
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from api_service.models.requests import CallbackCreate, CallbackUpdate
from api_service.models.responses import BaseResponse, CallbackResponse
from api_service.crud import callback
from api_service.services.database import get_db
from shared.utils.logger import setup_logger

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