"""
回调服务路由
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from api_service.models.requests import CallbackCreate, CallbackUpdate, StreamStatus
from api_service.models.responses import BaseResponse, CallbackResponse
from api_service.models.database import Stream, SubTask
from api_service.crud import callback
from api_service.services.database import get_db
from shared.utils.logger import setup_logger
from datetime import datetime

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/v1/callback", tags=["回调服务"])

@router.post("/create", response_model=BaseResponse)
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

@router.post("/list", response_model=BaseResponse)
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

@router.post("/detail", response_model=BaseResponse)
async def get_callback(
    callback_id: int,
    db: Session = Depends(get_db)
):
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

@router.post("/update", response_model=BaseResponse)
async def update_callback(
    request: CallbackUpdate,
    db: Session = Depends(get_db)
):
    """更新回调服务"""
    try:
        result = callback.update_callback(
            db,
            request.id,  # 从请求体获取ID
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

@router.post("/delete", response_model=BaseResponse)
async def delete_callback(
    callback_id: int,
    db: Session = Depends(get_db)
):
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

@router.post("/analysis/notify", response_model=BaseResponse)
async def analysis_callback(
    callback_data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """接收分析服务回调"""
    try:
        logger.info(f"Received analysis callback: {callback_data}")
        
        # 获取任务ID和状态
        analysis_task_id = callback_data.get("task_id")
        status = callback_data.get("status")
        
        if not analysis_task_id or not status:
            raise HTTPException(status_code=400, detail="Invalid callback data")
            
        # 查找对应的子任务
        sub_task = db.query(SubTask).filter(
            SubTask.analysis_task_id == analysis_task_id
        ).first()
        
        if not sub_task:
            logger.warning(f"Sub task not found for analysis_task_id: {analysis_task_id}")
            return BaseResponse(message="Sub task not found")
            
        # 更新子任务状态
        sub_task.status = status
        if status == "stopped":
            sub_task.completed_at = datetime.now()
            
            # 更新关联的视频源状态
            stream = sub_task.stream
            if stream:
                stream.status = StreamStatus.DISCONNECTED
                stream.updated_at = datetime.now()
                logger.info(f"Updated stream {stream.id} status to disconnected")
                
        db.commit()
        return BaseResponse(message="Callback processed successfully")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Process analysis callback failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 