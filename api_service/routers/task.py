"""
任务路由模块

提供分析任务的管理接口，支持：
- 创建任务：创建新的分析任务
- 查询任务：获取任务列表和详情
- 更新任务：修改任务配置
- 删除任务：移除不需要的任务
- 任务控制：启动、停止和监控任务执行
"""
from fastapi import APIRouter, Depends, Body, Request, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from models.responses import BaseResponse, TaskDetailResponse, SubTaskResponse
from models.requests import TaskCreate, TaskUpdate
from services.database import get_db
from crud import task as task_crud
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/v1/tasks", tags=["任务管理"])

@router.post("/create", response_model=BaseResponse, summary="创建任务")
async def create_task(
    request: Request,
    task_data: TaskCreate,
    db: Session = Depends(get_db)
):
    """
    创建任务
    
    参数:
    - name: 任务名称
    - save_result: 是否保存结果
    - tasks: 子任务配置列表，每个子任务包含流ID和模型配置列表
    
    请求示例:
    ```json
    {
        "name": "多摄像头行人检测",
        "save_result": true,
        "tasks": [
            {
                "stream_id": 1,
                "stream_name": "前门摄像头",
                "models": [
                    {
                        "model_id": 2,
                        "config": {
                            "confidence": 0.5,
                            "iou": 0.45,
                            "classes": [0, 1, 2],
                            "roi_type": 1,
                            "roi": {
                                "x1": 0.1,
                                "y1": 0.1,
                                "x2": 0.9,
                                "y2": 0.9
                            },
                            "imgsz": 640,
                            "nested_detection": true,
                            "analysis_type": "detection",
                            "callback": {
                                "enabled": true,
                                "url": "http://example.com/callback",
                                "interval": 5
                            }
                        }
                    }
                ]
            },
            {
                "stream_id": 2,
                "stream_name": "后门摄像头",
                "models": [
                    {
                        "model_id": 2,
                        "config": {
                            "confidence": 0.4,
                            "iou": 0.4,
                            "classes": [0, 1, 2], 
                            "roi_type": 2,
                            "roi": {
                                "points": [
                                    [0.1, 0.1],
                                    [0.9, 0.1],
                                    [0.9, 0.9],
                                    [0.1, 0.9]
                                ]
                            },
                            "analysis_type": "tracking",
                            "callback": {
                                "enabled": true
                            }
                        }
                    },
                    {
                        "model_id": 3,
                        "config": {
                            "confidence": 0.6,
                            "analysis_type": "counting",
                            "roi_type": 3,
                            "roi": {
                                "points": [
                                    [0.2, 0.5],
                                    [0.8, 0.5]
                                ]
                            }
                        }
                    }
                ]
            }
        ]
    }
    ```
    
    返回:
    - 创建的任务ID和基本信息
    """
    try:
        new_task = task_crud.create_task(db, task_data)
        
        return BaseResponse(
            path=str(request.url),
            message="创建成功",
            data={
                "id": new_task.id,
                "name": new_task.name,
                "status": new_task.status,
                "save_result": new_task.save_result,
                "total_subtasks": new_task.total_subtasks,
                "created_at": new_task.created_at
            }
        )
    except Exception as e:
        logger.error(f"创建任务失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/list", response_model=BaseResponse, summary="获取任务列表")
async def get_tasks(
    request: Request,
    skip: int = 0,
    limit: int = 10,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    获取任务列表
    
    参数:
    - skip: 跳过的记录数
    - limit: 返回的最大记录数
    - status: 任务状态过滤
    
    返回:
    - 任务列表和总数
    """
    try:
        tasks = task_crud.get_tasks(db, skip, limit, status, include_subtasks=False)
        total = db.query(task_crud.Task).count()
        
        # 转换为响应格式
        task_list = []
        for t in tasks:
            task_list.append({
                "id": t.id,
                "name": t.name,
                "status": t.status,
                "save_result": t.save_result,
                "active_subtasks": t.active_subtasks,
                "total_subtasks": t.total_subtasks,
                "created_at": t.created_at,
                "updated_at": t.updated_at,
                "started_at": t.started_at,
                "completed_at": t.completed_at,
                "error_message": t.error_message
            })
        
        return BaseResponse(
            path=str(request.url),
            message="获取成功",
            data={
                "total": total,
                "items": task_list
            }
        )
    except Exception as e:
        logger.error(f"获取任务列表失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/detail", response_model=BaseResponse, summary="获取任务详情")
async def get_task(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db)
):
    """
    获取任务详情
    
    参数:
    - task_id: 任务ID
    
    返回:
    - 任务详细信息，包括子任务列表
    """
    try:
        task_obj = task_crud.get_task(db, task_id, include_subtasks=True)
        if not task_obj:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="任务不存在"
            )
        
        # 准备子任务响应
        subtasks = []
        for st in task_obj.sub_tasks:
            # 获取流和模型信息
            stream_name = st.stream.name if st.stream else None
            model_name = st.model.name if st.model else None
            
            node_info = None
            if st.node:
                node_info = {
                    "id": st.node.id,
                    "ip": st.node.ip,
                    "port": st.node.port,
                    "service_name": st.node.service_name,
                    "service_status": st.node.service_status
                }
            
            subtasks.append({
                "id": st.id,
                "task_id": st.task_id,
                "stream_id": st.stream_id,
                "model_id": st.model_id,
                "status": st.status,
                "error_message": st.error_message,
                "created_at": st.created_at,
                "updated_at": st.updated_at,
                "started_at": st.started_at,
                "completed_at": st.completed_at,
                "config": st.config,
                "enable_callback": st.enable_callback,
                "callback_url": st.callback_url,
                "roi_type": st.roi_type,
                "analysis_type": st.analysis_type,
                "node_id": st.node_id,
                "analysis_task_id": st.analysis_task_id,
                "stream_name": stream_name,
                "model_name": model_name,
                "node_info": node_info
            })
        
        # 组装任务详情响应
        task_detail = {
            "id": task_obj.id,
            "name": task_obj.name,
            "status": task_obj.status,
            "error_message": task_obj.error_message,
            "save_result": task_obj.save_result,
            "created_at": task_obj.created_at,
            "updated_at": task_obj.updated_at,
            "started_at": task_obj.started_at,
            "completed_at": task_obj.completed_at,
            "active_subtasks": task_obj.active_subtasks,
            "total_subtasks": task_obj.total_subtasks,
            "sub_tasks": subtasks
        }
        
        return BaseResponse(
            path=str(request.url),
            message="获取成功",
            data=task_detail
        )
    except Exception as e:
        logger.error(f"获取任务详情失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/update", response_model=BaseResponse, summary="更新任务")
async def update_task(
    request: Request,
    task_data: TaskUpdate,
    db: Session = Depends(get_db)
):
    """
    更新任务基本信息
    
    参数:
    - id: 任务ID
    - name: 任务名称 (可选)
    - save_result: 是否保存结果 (可选)
    
    返回:
    - 更新后的任务基本信息
    """
    try:
        updated_task = task_crud.update_task(db, task_data.id, task_data)
        if not updated_task:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="任务不存在"
            )
        
        return BaseResponse(
            path=str(request.url),
            message="更新成功",
            data={
                "id": updated_task.id,
                "name": updated_task.name,
                "status": updated_task.status,
                "save_result": updated_task.save_result,
                "active_subtasks": updated_task.active_subtasks,
                "total_subtasks": updated_task.total_subtasks,
                "updated_at": updated_task.updated_at
            }
        )
    except Exception as e:
        logger.error(f"更新任务失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/delete", response_model=BaseResponse, summary="删除任务")
async def delete_task(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db)
):
    """
    删除任务
    
    参数:
    - task_id: 任务ID
    
    返回:
    - 删除操作结果
    """
    try:
        result = task_crud.delete_task(db, task_id)
        if not result:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="任务不存在或无法删除运行中的任务"
            )
        
        return BaseResponse(
            path=str(request.url),
            message="删除成功"
        )
    except Exception as e:
        logger.error(f"删除任务失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/start", response_model=BaseResponse, summary="启动任务")
async def start_task(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db)
):
    """
    启动任务
    
    参数:
    - task_id: 任务ID
    
    返回:
    - 启动操作结果
    """
    try:
        success, message = await task_crud.start_task(db, task_id)
        
        return BaseResponse(
            path=str(request.url),
            success=success,
            message=message
        )
    except Exception as e:
        logger.error(f"启动任务失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/stop", response_model=BaseResponse, summary="停止任务")
async def stop_task(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db)
):
    """
    停止任务
    
    参数:
    - task_id: 任务ID
    
    返回:
    - 停止操作结果
    """
    try:
        success, message = await task_crud.stop_task(db, task_id)
        
        return BaseResponse(
            path=str(request.url),
            success=success,
            message=message
        )
    except Exception as e:
        logger.error(f"停止任务失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        ) 