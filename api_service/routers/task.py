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

logger = setup_logger(__name__)
router = APIRouter(prefix="/tasks", tags=["任务"])
task_controller = TaskController()

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
            # 转换关联对象为ID列表
            "stream_ids": [stream.id for stream in result.streams],
            "model_ids": [model.id for model in result.models],
            "callback_ids": [callback.id for callback in result.callbacks]
        }
        
        return BaseResponse(data=response_data)
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

@router.get("/{task_id}", response_model=BaseResponse)
async def get_task(task_id: int, db: Session = Depends(get_db)):
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
            # 转换关联对象为ID列表
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

@router.put("/{task_id}/status", response_model=BaseResponse, 
    description="更新任务状态",
    responses={
        200: {
            "description": "成功更新任务状态",
            "content": {
                "application/json": {
                    "example": {
                        "code": 200,
                        "message": "Success",
                        "data": {
                            "id": 1,
                            "name": "测试任务",
                            "status": "running",
                            "error_message": None,
                            "created_at": "2024-01-01T00:00:00",
                            "updated_at": "2024-01-01T00:00:00",
                            "stream_ids": [1, 2],
                            "model_ids": [1],
                            "callback_ids": [1]
                        }
                    }
                }
            }
        }
    }
)
async def update_task_status(
    task_id: int,
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
            task_id,
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

@router.post("/{task_id}/start", response_model=BaseResponse,
    description="启动任务",
    responses={
        200: {
            "description": "任务启动成功",
            "content": {
                "application/json": {
                    "example": {
                        "code": 200,
                        "message": "任务启动成功",
                        "data": {
                            "task_id": 1,
                            "status": "running",
                            "started_at": "2024-01-01T00:00:00"
                        }
                    }
                }
            }
        },
        400: {
            "description": "启动失败",
            "content": {
                "application/json": {
                    "example": {
                        "code": 400,
                        "message": "Failed to start task",
                        "detail": "任务已在运行中"
                    }
                }
            }
        }
    }
)
async def start_task(
    task_id: int = Path(..., description="任务ID"),
    db: Session = Depends(get_db)
):
    """
    启动任务
    
    将任务状态更新为运行中，并为每个视频源和模型的组合创建分析线程。
    每个分析线程会：
    1. 连接到视频源
    2. 加载指定的模型
    3. 执行实时分析
    4. 按指定间隔发送回调通知
    
    注意：
    - 任务必须处于已创建或已停止状态
    - 每个视频源会对应多个分析线程(取决于模型数量)
    - 所有分析线程都是独立运行的
    """
    try:
        success = await task_controller.start_task(db, task_id)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to start task")
            
        return BaseResponse(
            message="任务启动成功",
            data={"task_id": task_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Start task failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{task_id}/stop", response_model=BaseResponse,
    description="停止任务",
    responses={
        200: {
            "description": "任务停止成功",
            "content": {
                "application/json": {
                    "example": {
                        "code": 200,
                        "message": "任务停止成功",
                        "data": {
                            "task_id": 1,
                            "status": "stopped",
                            "completed_at": "2024-01-01T00:00:00"
                        }
                    }
                }
            }
        },
        400: {
            "description": "停止失败",
            "content": {
                "application/json": {
                    "example": {
                        "code": 400,
                        "message": "Failed to stop task",
                        "detail": "任务未在运行"
                    }
                }
            }
        }
    }
)
async def stop_task(
    task_id: int = Path(..., description="任务ID"),
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