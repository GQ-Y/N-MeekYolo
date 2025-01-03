"""
分析路由
处理分析请求
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from pydantic import BaseModel, Field
from analysis_service.core.detector import YOLODetector
from analysis_service.core.queue import TaskQueueManager
from analysis_service.core.resource import ResourceMonitor
from analysis_service.models.responses import (
    ImageAnalysisResponse,
    VideoAnalysisResponse,
    StreamAnalysisResponse,
    BaseResponse,
    StreamResponse,
    SubTaskInfo,
    StreamBatchResponse
)
from analysis_service.models.requests import StreamTask
from shared.utils.logger import setup_logger
from analysis_service.services.database import get_db_dependency
from analysis_service.crud import task as task_crud
import asyncio
import time
from sqlalchemy.orm import Session
import uuid
from analysis_service.models.database import TaskQueue, Task  # 添加导入
from sqlalchemy import or_

logger = setup_logger(__name__)

# 初始化组件
detector = YOLODetector()
resource_monitor = ResourceMonitor()
task_queue = None

router = APIRouter(prefix="/analyze")

# 依赖注入
async def get_task_queue(db: Session = Depends(get_db_dependency)) -> TaskQueueManager:
    global task_queue
    if task_queue is None:
        task_queue = TaskQueueManager(db)
        await task_queue.start()
    return task_queue

class ImageAnalysisRequest(BaseModel):
    """图片分析请求"""
    model_code: str
    image_urls: List[str]
    callback_urls: str = None
    is_base64: bool = False

class VideoAnalysisRequest(BaseModel):
    """视频分析请求"""
    model_code: str
    video_url: str
    callback_urls: str = None

class StreamAnalysisRequest(BaseModel):
    """流分析请求"""
    tasks: List[StreamTask] = Field(
        ...,
        description="任务列表",
        min_items=1
    )
    callback_urls: Optional[str] = Field(
        None,
        description="回调地址,多个用逗号分隔",
        example="http://callback1,http://callback2"
    )
    callback_interval: int = Field(
        1,
        description="回调间隔(秒)",
        ge=1
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "callback_interval": 1,
                    "callback_urls": "http://127.0.0.1:8081,http://192.168.1.1:8081",
                    "tasks": [
                        {
                            "model_code": "model-gcc",
                            "stream_url": "rtsp://example.com/stream1"
                        },
                        {
                            "model_code": "model-gcc", 
                            "stream_url": "rtsp://example.com/stream2"
                        }
                    ]
                }
            ]
        }
    }

@router.post("/image", response_model=ImageAnalysisResponse)
async def analyze_image(request: ImageAnalysisRequest):
    """分析图片"""
    try:
        result = await detector.detect_images(
            request.model_code,
            request.image_urls,
            request.callback_urls,
            request.is_base64
        )
        logger.info(f"Detection result: {result}")
        response = ImageAnalysisResponse(
            image_url=request.image_urls[0],
            detections=result.get('detections', []),
            result_image=result.get('result_image')
        )
        return response
    except Exception as e:
        logger.error(f"Image analysis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/video", response_model=VideoAnalysisResponse)
async def analyze_video(request: VideoAnalysisRequest):
    """分析视频"""
    try:
        task = await detector.start_video_analysis(
            request.model_code,
            request.video_url
        )
        return VideoAnalysisResponse(**task)
    except Exception as e:
        logger.error(f"Video analysis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stream", response_model=StreamResponse)
async def analyze_stream(
    request: StreamAnalysisRequest,
    queue: TaskQueueManager = Depends(get_task_queue),
    db: Session = Depends(get_db_dependency)
) -> StreamResponse:
    """处理流分析请求"""
    try:
        # 检查资源是否足够
        if not resource_monitor.has_available_resource():
            raise HTTPException(
                status_code=503,
                detail="资源不足,请稍后再试"
            )
            
        # 生成一个父任务ID但不创建记录
        parent_task_id = str(uuid.uuid4())
        
        # 创建子任务
        sub_tasks = []
        queue_tasks = []
        
        for task in request.tasks:
            sub_task = task_crud.create_task(
                db=db,
                task_id=None,
                model_code=task.model_code,
                stream_url=task.stream_url,
                output_url=task.output_url,
                callback_urls=request.callback_urls
            )
            sub_tasks.append(sub_task)
            
            # 将任务加入队列，使用生成的父任务ID
            queue_task = await queue.add_task(
                task=sub_task,
                parent_task_id=parent_task_id
            )
            queue_tasks.append(queue_task)
            
        # 构建子任务信息列表
        sub_task_infos = [
            SubTaskInfo(
                task_id=qt.id,
                status=0,  # 使用数字状态: 0 表示等待中
                stream_url=st.stream_url,
                output_url=st.output_url
            )
            for qt, st in zip(queue_tasks, sub_tasks)
        ]
        
        # 构建响应数据
        response_data = StreamBatchResponse(
            parent_task_id=parent_task_id,
            sub_tasks=sub_task_infos
        )
        
        return StreamResponse(
            code=200,
            message="Stream analysis tasks queued",
            data=response_data
        )
        
    except Exception as e:
        logger.error(f"Queue stream analysis tasks failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@router.post("/stream/{task_id}/stop")
async def stop_stream_analysis(
    task_id: str,
    queue: TaskQueueManager = Depends(get_task_queue),
    db: Session = Depends(get_db_dependency)
):
    """停止流分析任务"""
    try:
        # 1. 查找并锁定任务记录
        task = db.query(TaskQueue).with_for_update().filter(
            TaskQueue.id == task_id
        ).first()
        
        if not task:
            raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")

        # 2. 停止任务进程
        try:
            logger.info(f"正在停止任务进程: {task_id}")
            stop_result = await queue.cancel_task(task_id)
            logger.info(f"停止任务进程结果: {stop_result}")
            
            # 等待任务真正停止
            for _ in range(10):  # 最多等待5秒
                if not await queue.is_task_running(task_id):
                    break
                await asyncio.sleep(0.5)
                
        except Exception as e:
            logger.error(f"停止任务进程失败: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"停止任务进程失败: {str(e)}")

        # 3. 获取父任务ID
        parent_task_id = task.parent_task_id

        try:
            # 4. 删除当前子任务
            logger.info(f"删除子任务: {task_id}")
            db.delete(task)
            
            # 5. 如果存在父任务，检查是否还有其他子任务
            if parent_task_id:
                remaining_sub_tasks = db.query(TaskQueue).filter(
                    TaskQueue.parent_task_id == parent_task_id
                ).all()
                
                # 如果没有其他子任务，删除父任务
                if not remaining_sub_tasks:
                    logger.info(f"父任务 {parent_task_id} 下没有其他子任务，删除父任务")
                    parent_task = db.query(TaskQueue).filter(
                        TaskQueue.id == parent_task_id
                    ).first()
                    if parent_task:
                        db.delete(parent_task)
                        
                        # 删除关联的主任务记录
                        if parent_task.task_id:
                            db.query(Task).filter(
                                Task.id == parent_task.task_id
                            ).delete()

            # 6. 提交事务
            db.commit()
            logger.info(f"成功删除任务记录")

            return {
                "code": 200,
                "message": "任务已停止并删除",
                "data": {
                    "task_id": task_id,
                    "parent_task_id": parent_task_id,
                    "parent_deleted": parent_task_id and not remaining_sub_tasks
                }
            }

        except Exception as e:
            db.rollback()
            logger.error(f"删除任务记录失败: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"删除任务记录失败: {str(e)}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"停止任务失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"停止任务失败: {str(e)}"
        )

@router.get("/stream/{task_id}/status", response_model=BaseResponse)
async def get_stream_status(
    task_id: str,
    queue: TaskQueueManager = Depends(get_task_queue)
):
    """获取流分析状态"""
    try:
        status = await queue.get_task_status(task_id)
        return {
            "code": 200,
            "message": "success",
            "data": status
        }
    except Exception as e:
        logger.error(f"Get task status failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/resource", response_model=BaseResponse)
async def get_resource_status():
    """获取资源状态"""
    try:
        status = resource_monitor.get_resource_usage()
        return {
            "code": 200,
            "message": "success",
            "data": status
        }
    except Exception as e:
        logger.error(f"Get resource status failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))