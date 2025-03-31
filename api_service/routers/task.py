"""
任务路由
"""
from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session
from typing import List, Optional
from api_service.models.requests import TaskCreate, TaskUpdate, TaskStatusUpdate
from api_service.models.responses import BaseResponse, TaskResponse
from api_service.crud import task
from api_service.services.database import get_db
from shared.utils.logger import setup_logger
from api_service.services.task_controller import TaskController
from api_service.models.database import Task

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/v1/task", tags=["任务"])
task_controller = TaskController()

@router.post("/create", response_model=BaseResponse)
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
        
        # 构造响应数据
        response_data = {
            "id": result.id,
            "name": result.name,
            "status": result.status,
            "error_message": result.error_message,
            "callback_interval": result.callback_interval,
            "created_at": result.created_at,
            "updated_at": result.updated_at,
            "started_at": result.started_at,
            "completed_at": result.completed_at,
            "stream_ids": [stream.id for stream in result.streams],
            "model_ids": [model.id for model in result.models],
            "callback_ids": [callback.id for callback in result.callbacks]
        }
        
        return BaseResponse(data=response_data)
    except Exception as e:
        logger.error(f"Create task failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/list", response_model=BaseResponse)
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
            "items": [
                {
                    "id": t.id,
                    "name": t.name,
                    "status": t.status,
                    "error_message": t.error_message,
                    "callback_interval": t.callback_interval,
                    "created_at": t.created_at,
                    "updated_at": t.updated_at,
                    "started_at": t.started_at,
                    "completed_at": t.completed_at,
                    "stream_ids": [s.id for s in t.streams],
                    "model_ids": [m.id for m in t.models],
                    "callback_ids": [c.id for c in t.callbacks]
                } for t in tasks
            ]
        })
    except Exception as e:
        logger.error(f"Get tasks failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/detail", response_model=BaseResponse)
async def get_task(
    task_id: int,
    db: Session = Depends(get_db)
):
    """获取任务详情"""
    try:
        result = task.get_task(db, task_id)
        if not result:
            raise HTTPException(status_code=404, detail="Task not found")
            
        return BaseResponse(data={
            "id": result.id,
            "name": result.name,
            "status": result.status,
            "error_message": result.error_message,
            "callback_interval": result.callback_interval,
            "created_at": result.created_at,
            "updated_at": result.updated_at,
            "started_at": result.started_at,
            "completed_at": result.completed_at,
            "stream_ids": [stream.id for stream in result.streams],
            "model_ids": [model.id for model in result.models],
            "callback_ids": [callback.id for callback in result.callbacks]
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get task failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/update", response_model=BaseResponse)
async def update_task(
    request: TaskUpdate,
    db: Session = Depends(get_db)
):
    """更新任务"""
    try:
        result = task.update_task(
            db,
            request.id,  # 从请求体获取ID
            name=request.name,
            stream_ids=request.stream_ids,
            model_ids=request.model_ids,
            callback_ids=request.callback_ids,
            callback_interval=request.callback_interval
        )
        if not result:
            raise HTTPException(status_code=404, detail="Task not found")
            
        # 构造响应数据
        response_data = {
            "id": result.id,
            "name": result.name,
            "status": result.status,
            "error_message": result.error_message,
            "callback_interval": result.callback_interval,
            "created_at": result.created_at,
            "updated_at": result.updated_at,
            "started_at": result.started_at,
            "completed_at": result.completed_at,
            "stream_ids": [stream.id for stream in result.streams],
            "model_ids": [model.id for model in result.models],
            "callback_ids": [callback.id for callback in result.callbacks]
        }
        
        return BaseResponse(data=response_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update task failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/status/update", response_model=BaseResponse)
async def update_task_status(
    request: TaskStatusUpdate,
    db: Session = Depends(get_db)
):
    """
    更新任务状态
    
    可用状态:
    - created: 任务已创建
    - pending: 等待执行
    - running: 正在执行
    - completed: 执行完成
    - failed: 执行失败
    - stopped: 已停止
    - paused: 已暂停
    """
    try:
        result = task.update_task_status(
            db,
            request.task_id,  # 从请求体获取ID
            status=request.status,
            error_message=request.error_message
        )
        if not result:
            raise HTTPException(status_code=404, detail="Task not found")
            
        # 构造响应数据
        response_data = {
            "id": result.id,
            "name": result.name,
            "status": result.status,
            "error_message": result.error_message,
            "callback_interval": result.callback_interval,
            "created_at": result.created_at,
            "updated_at": result.updated_at,
            "started_at": result.started_at,
            "completed_at": result.completed_at,
            "stream_ids": [stream.id for stream in result.streams],
            "model_ids": [model.id for model in result.models],
            "callback_ids": [callback.id for callback in result.callbacks]
        }
        
        return BaseResponse(data=response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update task status failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/delete", response_model=BaseResponse)
async def delete_task(
    task_id: int,
    db: Session = Depends(get_db)
):
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

@router.post("/start", response_model=BaseResponse)
async def start_task(
    task_id: int,
    db: Session = Depends(get_db)
):
    """启动任务"""
    try:
        success = await task_controller.start_task(db, task_id)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to start task")
            
        # 获取更新后的任务信息
        task_info = db.query(Task).filter(Task.id == task_id).first()
        if not task_info:
            raise HTTPException(status_code=404, detail="Task not found")
            
        return BaseResponse(
            message="任务启动成功",
            data={
                "task_id": task_id,
                "status": task_info.status,
                "started_at": task_info.started_at,
                "streams": [
                    {
                        "id": stream.id,
                        "status": stream.status
                    } for stream in task_info.streams
                ]
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Start task failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stop", response_model=BaseResponse)
async def stop_task(
    task_id: int,
    db: Session = Depends(get_db)
):
    """
    停止任务
    
    优雅地停止所有分析线程，并更新任务状态。
    停止过程会：
    1. 将任务状态设置为停止中
    2. 通知所有分析线程停止运行
    3. 等待线程完成当前处理
    4. 释放所有资源
    5. 更新任务状态为已停止
    
    注意：
    - 任务必须处于运行中状态
    - 会等待所有线程正常结束(最多等待10秒)
    - 如果超时，会强制结束线程
    """
    try:
        success = await task_controller.stop_task(db, task_id)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to stop task")
            
        return BaseResponse(
            message="任务停止成功",
            data={"task_id": task_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Stop task failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 