#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Body, Query, BackgroundTasks
from pydantic import BaseModel

from services.mqtt.mqtt_task_manager import get_mqtt_task_manager, MQTTTaskManager
from services.task.task_priority_manager import get_task_priority_manager
from services.core.smart_task_scheduler import get_smart_task_scheduler

router = APIRouter(
    prefix="/api/mqtt/tasks",
    tags=["MQTT任务管理"]
)

# 模型定义
class TaskRequest(BaseModel):
    task_id: str
    subtask_id: str
    priority: Optional[int] = 1
    wait: Optional[bool] = False

class RetryRequest(BaseModel):
    subtask_id: str
    priority: Optional[int] = None

class CancelRequest(BaseModel):
    subtask_id: str

class TaskStatusResponse(BaseModel):
    task_id: str
    subtask_id: str
    status: int
    status_text: str
    is_pending: bool
    error_message: Optional[str] = None
    progress: Optional[float] = 0
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    node_info: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    priority: Optional[int] = None
    attempts: Optional[int] = None

class QueueStatusResponse(BaseModel):
    total_tasks: int
    queues: Dict[str, int]
    oldest_task_age: Optional[float] = None
    newest_task_age: Optional[float] = None

class SchedulerStatusResponse(BaseModel):
    nodes_count: int
    top_nodes: List[Dict[str, Any]]
    task_types: List[str]
    last_sync: float
    queue_status: QueueStatusResponse

# 路由定义
@router.post("/dispatch", response_model=Dict[str, Any])
async def dispatch_task(
    request: TaskRequest,
    task_manager: MQTTTaskManager = Depends(get_mqtt_task_manager)
):
    """
    分发任务到MQTT节点
    
    参数:
    - task_id: 任务ID
    - subtask_id: 子任务ID
    - priority: 优先级 (0=低, 1=正常, 2=高, 3=紧急)
    - wait: 是否等待任务分发完成
    """
    success, result = await task_manager.dispatch_task(
        request.task_id, 
        request.subtask_id, 
        request.priority, 
        request.wait
    )
    
    if not success and "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
        
    return result

@router.post("/retry", response_model=Dict[str, Any])
async def retry_task(
    request: RetryRequest,
    task_manager: MQTTTaskManager = Depends(get_mqtt_task_manager)
):
    """
    重试失败的任务
    
    参数:
    - subtask_id: 子任务ID
    - priority: 新的优先级 (可选)
    """
    success, result = await task_manager.retry_failed_task(
        request.subtask_id,
        request.priority
    )
    
    if not success and "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
        
    return result

@router.post("/cancel", response_model=Dict[str, Any])
async def cancel_task(
    request: CancelRequest,
    task_manager: MQTTTaskManager = Depends(get_mqtt_task_manager)
):
    """
    取消待处理或正在运行的任务
    
    参数:
    - subtask_id: 子任务ID
    """
    success, result = await task_manager.cancel_task(request.subtask_id)
    
    if not success and "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
        
    return result

@router.get("/status/{task_id}/{subtask_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    subtask_id: str,
    task_manager: MQTTTaskManager = Depends(get_mqtt_task_manager)
):
    """
    获取任务状态
    
    参数:
    - task_id: 任务ID
    - subtask_id: 子任务ID
    """
    result = await task_manager.get_task_status(task_id, subtask_id)
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
        
    return result

@router.get("/queue/status", response_model=QueueStatusResponse)
async def get_queue_status(
    priority_manager = Depends(get_task_priority_manager)
):
    """
    获取任务队列状态
    """
    return await priority_manager.get_queue_status()

@router.get("/scheduler/status", response_model=SchedulerStatusResponse)
async def get_scheduler_status(
    task_scheduler = Depends(get_smart_task_scheduler)
):
    """
    获取任务调度器状态
    """
    return await task_scheduler.get_scheduler_status()

@router.post("/scheduler/sync-nodes", response_model=Dict[str, Any])
async def sync_nodes(
    task_scheduler = Depends(get_smart_task_scheduler)
):
    """
    强制同步节点信息
    """
    await task_scheduler.sync_nodes_from_db(force=True)
    return {"success": True, "message": "节点信息已同步"}

@router.post("/process-pending", response_model=Dict[str, Any])
async def process_pending_tasks(
    batch_size: int = Query(10, description="一次处理的最大任务数量"),
    task_manager: MQTTTaskManager = Depends(get_mqtt_task_manager)
):
    """
    手动处理等待中的任务
    
    参数:
    - batch_size: 一次处理的最大任务数量
    """
    processed = await task_manager._process_pending_tasks(batch_size)
    return {
        "success": True, 
        "processed_count": processed,
        "message": f"已处理 {processed} 个待处理任务"
    } 