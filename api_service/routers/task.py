"""
任务路由模块

提供分析任务的管理接口，支持：
- 创建任务：创建新的分析任务
- 查询任务：获取任务列表和详情
- 更新任务：修改任务配置
- 删除任务：移除不需要的任务
- 任务控制：启动、停止和监控任务执行
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from api_service.models.requests import TaskCreate, TaskUpdate, TaskStatusUpdate
from api_service.models.responses import BaseResponse, TaskResponse
from api_service.crud import task
from api_service.services.database import get_db
from shared.utils.logger import setup_logger
from api_service.services.task_controller import TaskController
from api_service.models.database import Task, SubTask, Node

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/v1/tasks", tags=["任务"])
task_controller = TaskController()

@router.post("/create", response_model=BaseResponse)
async def create_task(
    request: Request,
    task_data: TaskCreate,
    db: Session = Depends(get_db)
):
    """创建任务"""
    try:
        result = task.create_task(
            db,
            task_data.name,
            task_data.stream_ids,
            task_data.model_ids,
            task_data.callback_ids,
            task_data.callback_interval,
            task_data.enable_callback,
            task_data.save_result,
            task_data.config,
            task_data.node_id
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
            "callback_ids": [callback.id for callback in result.callbacks],
            "enable_callback": result.enable_callback if hasattr(result, 'enable_callback') else True,
            "save_result": result.save_result if hasattr(result, 'save_result') else False,
            "config": result.config if hasattr(result, 'config') else {},
            "node_id": result.node_id if hasattr(result, 'node_id') else None
        }
        
        return BaseResponse(
            path=str(request.url),
            message="创建成功",
            data=response_data
        )
    except Exception as e:
        logger.error(f"Create task failed: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/list", response_model=BaseResponse)
async def get_tasks(
    request: Request,
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取任务列表"""
    try:
        tasks = task.get_tasks(db, skip, limit, status)
        return BaseResponse(
            path=str(request.url),
            message="获取成功",
            data={
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
            }
        )
    except Exception as e:
        logger.error(f"Get tasks failed: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/detail", response_model=BaseResponse)
async def get_task(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db)
):
    """获取任务详情"""
    try:
        result = task.get_task(db, task_id)
        if not result:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="Task not found"
            )
            
        # 构造基本响应数据
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
        
        # 若任务为运行状态，添加子任务详情
        if result.status == "running":
            # 获取子任务列表
            sub_tasks = db.query(SubTask).filter(SubTask.task_id == task_id).all()
            
            # 构造子任务数据
            sub_tasks_data = []
            for sub_task in sub_tasks:
                # 获取节点信息
                node = None
                if result.node_id:
                    node = db.query(Node).filter(Node.id == result.node_id).first()
                
                sub_task_data = {
                    "id": sub_task.id,
                    "analysis_task_id": sub_task.analysis_task_id,
                    "status": sub_task.status,
                    "stream_id": sub_task.stream_id,
                    "model_id": sub_task.model_id,
                    "started_at": sub_task.started_at,
                    "completed_at": sub_task.completed_at,
                    "node_id": result.node_id,
                    "node_info": {
                        "id": node.id,
                        "ip": node.ip,
                        "port": node.port,
                        "status": node.service_status
                    } if node else None
                }
                sub_tasks_data.append(sub_task_data)
            
            # 添加子任务数据到响应
            response_data["sub_tasks"] = sub_tasks_data
            
            # 添加节点信息
            if result.node_id and result.node:
                response_data["node"] = {
                    "id": result.node.id,
                    "ip": result.node.ip,
                    "port": result.node.port,
                    "status": result.node.service_status
                }
        
        return BaseResponse(
            path=str(request.url),
            message="获取成功",
            data=response_data
        )
    except Exception as e:
        logger.error(f"Get task failed: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/update", response_model=BaseResponse)
async def update_task(
    request: Request,
    task_data: TaskUpdate,
    db: Session = Depends(get_db)
):
    """更新任务"""
    try:
        result = task.update_task(
            db,
            task_data.id,
            name=task_data.name,
            stream_ids=task_data.stream_ids,
            model_ids=task_data.model_ids,
            callback_ids=task_data.callback_ids,
            callback_interval=task_data.callback_interval,
            enable_callback=task_data.enable_callback,
            save_result=task_data.save_result,
            config=task_data.config,
            node_id=task_data.node_id
        )
        if not result:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="Task not found"
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
            "callback_ids": [callback.id for callback in result.callbacks],
            "enable_callback": result.enable_callback if hasattr(result, 'enable_callback') else True,
            "save_result": result.save_result if hasattr(result, 'save_result') else False,
            "config": result.config if hasattr(result, 'config') else {},
            "node_id": result.node_id if hasattr(result, 'node_id') else None
        }
        
        return BaseResponse(
            path=str(request.url),
            message="更新成功",
            data=response_data
        )
    except Exception as e:
        logger.error(f"Update task failed: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/status/update", response_model=BaseResponse)
async def update_task_status(
    request: Request,
    status_data: TaskStatusUpdate,
    db: Session = Depends(get_db)
):
    """更新任务状态"""
    try:
        result = task.update_task_status(
            db,
            status_data.task_id,
            status=status_data.status,
            error_message=status_data.error_message
        )
        if not result:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="Task not found"
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
        
        return BaseResponse(
            path=str(request.url),
            message="状态更新成功",
            data=response_data
        )
    except Exception as e:
        logger.error(f"Update task status failed: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/delete", response_model=BaseResponse)
async def delete_task(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db)
):
    """删除任务"""
    try:
        success = task.delete_task(db, task_id)
        if not success:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="Task not found"
            )
        return BaseResponse(
            path=str(request.url),
            message="删除成功"
        )
    except Exception as e:
        logger.error(f"Delete task failed: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/start", response_model=BaseResponse)
async def start_task(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db)
):
    """启动任务"""
    try:
        success = await task_controller.start_task(db, task_id)
        if not success:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=400,
                message="Failed to start task"
            )
            
        # 获取更新后的任务信息
        task_info = db.query(Task).filter(Task.id == task_id).first()
        if not task_info:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="Task not found"
            )
            
        return BaseResponse(
            path=str(request.url),
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
    except Exception as e:
        logger.error(f"Start task failed: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/stop", response_model=BaseResponse)
async def stop_task(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db)
):
    """停止任务"""
    try:
        success = await task_controller.stop_task(db, task_id)
        if not success:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=400,
                message="Failed to stop task"
            )
            
        return BaseResponse(
            path=str(request.url),
            message="任务停止成功",
            data={"task_id": task_id}
        )
    except Exception as e:
        logger.error(f"Stop task failed: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        ) 