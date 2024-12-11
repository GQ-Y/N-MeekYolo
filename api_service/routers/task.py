"""
任务路由
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from api_service.models.requests import TaskCreate, TaskUpdate, TaskStatusUpdate
from api_service.models.responses import BaseResponse, TaskResponse
from api_service.crud import task
from api_service.services.database import get_db
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/tasks", tags=["任务"])

@router.post("", response_model=BaseResponse)
async def create_task(request: TaskCreate, db: Session = Depends(get_db)):
    """创建任务"""
    try:
        result = task.create_task(
            db,
            request.name,
            request.stream_ids,
            request.model_ids,
            request.callback_ids,
            request.callback_interval
        )
        return BaseResponse(data=TaskResponse.from_orm(result).dict())
    except Exception as e:
        logger.error(f"Create task failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("", response_model=BaseResponse)
async def get_tasks(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取任务列表"""
    try:
        tasks = task.get_tasks(db, skip, limit, status)
        return BaseResponse(data={
            "total": len(tasks),
            "items": [TaskResponse.from_orm(t).dict() for t in tasks]
        })
    except Exception as e:
        logger.error(f"Get tasks failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{task_id}", response_model=BaseResponse)
async def get_task(task_id: int, db: Session = Depends(get_db)):
    """获取任务"""
    try:
        result = task.get_task(db, task_id)
        if not result:
            raise HTTPException(status_code=404, detail="Task not found")
        return BaseResponse(data=TaskResponse.from_orm(result).dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get task failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{task_id}", response_model=BaseResponse)
async def update_task(
    task_id: int,
    request: TaskUpdate,
    db: Session = Depends(get_db)
):
    """更新任务"""
    try:
        result = task.update_task(
            db,
            task_id,
            request.name,
            request.stream_ids,
            request.model_ids,
            request.callback_ids,
            request.callback_interval
        )
        if not result:
            raise HTTPException(status_code=404, detail="Task not found")
        return BaseResponse(data=TaskResponse.from_orm(result).dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update task failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{task_id}/status", response_model=BaseResponse)
async def update_task_status(
    task_id: int,
    request: TaskStatusUpdate,
    db: Session = Depends(get_db)
):
    """更新任务状态"""
    try:
        result = task.update_task_status(
            db,
            task_id,
            request.status,
            request.error_message
        )
        if not result:
            raise HTTPException(status_code=404, detail="Task not found")
        return BaseResponse(data=TaskResponse.from_orm(result).dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update task status failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{task_id}", response_model=BaseResponse)
async def delete_task(task_id: int, db: Session = Depends(get_db)):
    """删除任务"""
    try:
        success = task.delete_task(db, task_id)
        if not success:
            raise HTTPException(status_code=404, detail="Task not found")
        return BaseResponse(message="Task deleted successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete task failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 