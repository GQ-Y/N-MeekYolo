"""
分析路由
处理分析请求
"""
import os
import json
import uuid
import tempfile
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, File, UploadFile, Form, BackgroundTasks, Request
from pydantic import BaseModel, Field
from analysis_service.core.detector import YOLODetector
from analysis_service.core.queue import TaskQueueManager
from analysis_service.core.resource import ResourceMonitor
from analysis_service.models.responses import (
    ImageAnalysisResponse,
    VideoAnalysisResponse,
    StreamAnalysisResponse,
    BaseApiResponse,
    StreamBatchData,
    ImageAnalysisData,
    VideoAnalysisData,
    ResourceStatusResponse
)
from analysis_service.models.requests import (
    ImageAnalysisRequest,
    VideoAnalysisRequest,
    StreamAnalysisRequest,
    StreamTask
)
from analysis_service.models.database import Task, TaskQueue
from shared.utils.logger import setup_logger
from analysis_service.services.database import get_db_dependency
from analysis_service.crud import task as task_crud
import asyncio
import time
from sqlalchemy.orm import Session
from analysis_service.core.config import settings
from datetime import datetime

logger = setup_logger(__name__)

# 初始化组件
detector = YOLODetector()
resource_monitor = ResourceMonitor()
task_queue = None

router = APIRouter(prefix="/analyze")

# 状态映射
status_map = {
    "waiting": 0,     # 等待中
    "processing": 1,  # 运行中
    "completed": 2,   # 已完成
    "failed": -1      # 失败
}

# 依赖注入函数
async def get_detector() -> YOLODetector:
    """获取检测器实例"""
    return detector

async def get_task_queue(db: Session = Depends(get_db_dependency)) -> TaskQueueManager:
    """获取任务队列管理器"""
    global task_queue
    if task_queue is None:
        task_queue = TaskQueueManager(db)
        await task_queue.start()
    return task_queue

@router.post("/image", response_model=ImageAnalysisResponse, summary="图片分析", description="分析图片中的目标")
async def analyze_image(
    request: Request,
    body: ImageAnalysisRequest,
    detector: YOLODetector = Depends(get_detector)
) -> ImageAnalysisResponse:
    """
    图片分析接口
    
    Args:
        request: FastAPI请求对象
        body: 图片分析请求体
        detector: 检测器实例
    
    Returns:
        ImageAnalysisResponse: 图片分析结果
        
    请求示例:
    ```json
    {
        "model_code": "model-gcc",        // 模型代码
        "task_name": "行人检测-1",        // 任务名称，可选
        "image_urls": [                   // 图片URL列表
            "http://example.com/image.jpg"
        ],
        "callback_urls": "http://callback1,http://callback2",  // 回调地址，多个用逗号分隔，可选
        "enable_callback": true,          // 是否启用回调，默认false
        "is_base64": false,              // 是否返回base64编码的结果图片，默认false
        "save_result": false,            // 是否保存分析结果到本地，默认false
        "config": {                       // 检测配置参数，可选
            "confidence": 0.5,            // 置信度阈值，0-1之间
            "iou": 0.45,                 // IoU阈值，0-1之间
            "classes": [0, 2],           // 需要检测的类别ID列表
            "roi": {                     // 感兴趣区域，坐标为相对值(0-1)
                "x1": 0.1,              // 左上角x坐标
                "y1": 0.1,              // 左上角y坐标
                "x2": 0.9,              // 右下角x坐标
                "y2": 0.9               // 右下角y坐标
            },
            "imgsz": 640,               // 输入图片大小
            "nested_detection": true     // 是否启用嵌套检测
        }
    }
    ```
    """
    try:
        # 记录请求参数
        logger.info(f"收到图片分析请求:")
        logger.info(f"- 模型代码: {body.model_code}")
        logger.info(f"- 任务名称: {body.task_name}")
        logger.info(f"- 图片数量: {len(body.image_urls)}")
        logger.info(f"- 检测配置: {body.config}")
        logger.info(f"- 是否返回base64: {body.is_base64}")
        logger.info(f"- 是否保存结果: {body.save_result}")
        
        # 生成任务ID
        task_id = f"img_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        result = await detector.detect_images(
            body.model_code,
            body.image_urls,
            body.callback_urls,
            body.is_base64,
            config=body.config.dict() if body.config else None,
            task_name=body.task_name,
            enable_callback=body.enable_callback,
            save_result=body.save_result
        )
        
        # 记录检测结果
        logger.info(f"检测完成:")
        logger.info(f"- 检测到目标数量: {len(result.get('detections', []))}")
        logger.info(f"- 处理时长: {result.get('analysis_duration', 0):.3f}秒")
        if result.get('saved_paths'):
            logger.info(f"- 保存路径: {result['saved_paths']}")
        
        # 构建响应数据
        analysis_data = ImageAnalysisData(
            task_id=task_id,
            task_name=result.get('task_name'),
            image_url=body.image_urls[0],
            saved_path=result.get('saved_path'),
            objects=result.get('detections', []),
            result_image=result.get('result_image') if body.is_base64 else None,
            start_time=result.get('start_time'),
            end_time=result.get('end_time'),
            analysis_duration=result.get('analysis_duration')
        )
        
        # 构建标准响应
        return ImageAnalysisResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=True,
            message="图片分析成功",
            code=200,
            data=analysis_data
        )
        
    except Exception as e:
        logger.error(f"图片分析失败: {str(e)}", exc_info=True)
        return ImageAnalysisResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=False,
            message=f"图片分析失败: {str(e)}",
            code=500,
            data=None
        )

@router.post("/video", response_model=VideoAnalysisResponse, summary="视频分析", description="分析视频中的目标")
async def analyze_video(
    request: Request,
    body: VideoAnalysisRequest,
    background_tasks: BackgroundTasks,
    detector: YOLODetector = Depends(get_detector)
) -> VideoAnalysisResponse:
    """
    视频分析接口
    
    Args:
        request: FastAPI请求对象
        body: 视频分析请求体
        background_tasks: 后台任务
        detector: 检测器实例
    
    Returns:
        VideoAnalysisResponse: 视频分析结果
        
    请求示例:
    ```json
    {
        "model_code": "model-gcc",        // 模型代码
        "task_name": "视频分析-1",        // 任务名称，可选
        "video_url": "http://example.com/video.mp4",  // 视频URL
        "callback_urls": "http://callback1,http://callback2",  // 回调地址，多个用逗号分隔，可选
        "enable_callback": true,          // 是否启用回调，默认true
        "save_result": false,            // 是否保存分析结果到本地，默认false
        "config": {                      // 检测配置参数，可选
            "confidence": 0.5,           // 置信度阈值，0-1之间
            "iou": 0.45,                // IoU阈值，0-1之间
            "classes": [0, 2],          // 需要检测的类别ID列表
            "roi": {                    // 感兴趣区域，坐标为相对值(0-1)
                "x1": 0.1,             // 左上角x坐标
                "y1": 0.1,             // 左上角y坐标
                "x2": 0.9,             // 右下角x坐标
                "y2": 0.9              // 右下角y坐标
            },
            "imgsz": 640,              // 输入图片大小
            "nested_detection": true    // 是否启用嵌套检测
        }
    }
    ```
    """
    try:
        # 生成任务ID
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        # 启动视频分析任务
        task = await detector.start_video_analysis(
            task_id=task_id,
            model_code=body.model_code,
            video_url=body.video_url,
            callback_urls=body.callback_urls,
            config=body.config,
            task_name=body.task_name,
            enable_callback=body.enable_callback,
            save_result=body.save_result
        )
        
        # 构建响应数据
        analysis_data = VideoAnalysisData(
            task_id=task['task_id'],
            task_name=task['task_name'],
            status=status_map.get(task.get('status', 'processing'), 1),  # 默认为运行中
            video_url=task['video_url'],
            saved_path=task['saved_path'],
            start_time=task['start_time'],
            end_time=task['end_time'],
            analysis_duration=task['analysis_duration'],
            progress=task.get('progress', 0.0),
            total_frames=task.get('total_frames', 0),
            processed_frames=task.get('processed_frames', 0)
        )
        
        # 构建标准响应
        return VideoAnalysisResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=True,
            message="视频分析任务已启动",
            code=200,
            data=analysis_data
        )
        
    except Exception as e:
        logger.error(f"视频分析失败: {str(e)}", exc_info=True)
        return VideoAnalysisResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=False,
            message=f"视频分析失败: {str(e)}",
            code=500,
            data=None
        )

@router.post("/stream", response_model=StreamAnalysisResponse, summary="流分析", description="分析视频流中的目标")
async def analyze_stream(
    request: Request,
    body: StreamAnalysisRequest,
    queue: TaskQueueManager = Depends(get_task_queue),
    db: Session = Depends(get_db_dependency)
) -> StreamAnalysisResponse:
    """
    流分析接口
    
    Args:
        request: FastAPI请求对象
        body: 流分析请求体
        queue: 任务队列管理器
        db: 数据库会话
    
    Returns:
        StreamAnalysisResponse: 流分析结果
        
    请求示例:
    ```json
    {
        "tasks": [                       // 任务列表
            {
                "model_code": "model-gcc",  // 模型代码
                "task_name": "流分析-1",    // 任务名称，可选
                "stream_url": "rtsp://example.com/stream1",  // 视频流URL
                "output_url": "rtmp://example.com/output1",  // 输出流URL，可选
                "config": {               // 检测配置参数，可选
                    "confidence": 0.5,    // 置信度阈值，0-1之间
                    "iou": 0.45,         // IoU阈值，0-1之间
                    "classes": [0, 2]     // 需要检测的类别ID列表
                }
            }
        ],
        "callback_urls": "http://callback1,http://callback2",  // 回调地址，多个用逗号分隔，可选
        "analyze_interval": 1.0,         // 分析间隔（秒），可选
        "alarm_interval": 5.0,          // 报警间隔（秒），可选
        "push_interval": 1.0,           // 推送间隔（秒），可选
        "random_interval": [0.5, 2.0],  // 随机间隔范围（秒），可选
        "enable_callback": true,        // 是否启用回调，默认true
        "save_result": false           // 是否保存分析结果到本地，默认false
    }
    ```
    """
    try:
        # 检查资源是否足够
        if not resource_monitor.has_available_resource():
            return StreamAnalysisResponse(
                requestId=str(uuid.uuid4()),
                path=str(request.url.path),
                success=False,
                message="资源不足，请稍后再试",
                code=503,
                data=None
            )
            
        # 记录请求参数
        logger.info(f"收到流分析请求:")
        logger.info(f"- 任务数量: {len(body.tasks)}")
        logger.info(f"- 分析间隔: {body.analyze_interval}秒")
        logger.info(f"- 报警间隔: {body.alarm_interval}秒")
        logger.info(f"- 推送间隔: {body.push_interval}秒")
        logger.info(f"- 是否启用回调: {body.enable_callback}")
        logger.info(f"- 是否保存结果: {body.save_result}")
            
        # 生成父任务ID
        parent_task_id = str(uuid.uuid4())
        
        # 从配置获取默认值
        default_analyze_interval = settings.ANALYSIS.analyze_interval
        default_alarm_interval = settings.ANALYSIS.alarm_interval
        default_random_interval = tuple(settings.ANALYSIS.random_interval)
        default_push_interval = settings.ANALYSIS.push_interval
        
        # 使用请求参数覆盖默认值
        analyze_interval = body.analyze_interval or default_analyze_interval
        alarm_interval = body.alarm_interval or default_alarm_interval
        random_interval = body.random_interval or default_random_interval
        push_interval = body.push_interval or default_push_interval
        
        # 创建子任务
        sub_tasks = []
        queue_tasks = []
        
        for task in body.tasks:
            logger.info(f"处理子任务:")
            logger.info(f"- 模型代码: {task.model_code}")
            logger.info(f"- 任务名称: {task.task_name}")
            logger.info(f"- 流地址: {task.stream_url}")
            logger.info(f"- 输出地址: {task.output_url}")
            
            sub_task = task_crud.create_task(
                db=db,
                task_id=None,
                model_code=task.model_code,
                stream_url=task.stream_url,
                output_url=task.output_url,
                callback_urls=body.callback_urls,
                task_name=task.task_name
            )
            sub_tasks.append(sub_task)
            
            # 将任务加入队列
            queue_task = await queue.add_task(
                task=sub_task,
                parent_task_id=parent_task_id,
                analyze_interval=analyze_interval,
                alarm_interval=alarm_interval,
                random_interval=random_interval,
                push_interval=push_interval,
                config=task.config.dict() if task.config else None,
                task_name=task.task_name,
                enable_callback=body.enable_callback,
                save_result=body.save_result
            )
            queue_tasks.append(queue_task)
            
        # 构建响应数据
        stream_data = StreamBatchData(
            batch_id=parent_task_id,
            task_id=queue_tasks[0].id if queue_tasks else None,
            frame_id=0,
            timestamp=time.time(),
            objects=[],
            image_url=None
        )
        
        logger.info(f"流分析任务已创建:")
        logger.info(f"- 父任务ID: {parent_task_id}")
        logger.info(f"- 子任务数量: {len(sub_tasks)}")
        
        # 构建标准响应
        return StreamAnalysisResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=True,
            message="流分析任务已创建",
            code=200,
            data=stream_data
        )
        
    except Exception as e:
        logger.error(f"创建流分析任务失败: {str(e)}", exc_info=True)
        return StreamAnalysisResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=False,
            message=f"创建流分析任务失败: {str(e)}",
            code=500,
            data=None
        )

class StopStreamRequest(BaseModel):
    """停止流分析请求"""
    task_id: str = Field(..., description="任务ID")

@router.post("/stream/stop", response_model=BaseApiResponse, summary="停止流分析", description="停止指定的流分析任务")
async def stop_stream_analysis(
    request: Request,
    body: StopStreamRequest,
    queue: TaskQueueManager = Depends(get_task_queue),
    db: Session = Depends(get_db_dependency)
) -> BaseApiResponse:
    """
    停止流分析任务
    
    Args:
        request: FastAPI请求对象
        body: 停止流分析请求体
        queue: 任务队列管理器
        db: 数据库会话
    
    Returns:
        BaseApiResponse: 停止结果
        
    请求示例:
    ```json
    {
        "task_id": "550e8400-e29b-41d4-a716-446655440000"  // 任务ID
    }
    ```
    """
    try:
        # 1. 查找并锁定任务记录
        task = db.query(TaskQueue).with_for_update().filter(
            TaskQueue.id == body.task_id
        ).first()
        
        if not task:
            return BaseApiResponse(
                requestId=str(uuid.uuid4()),
                path=str(request.url.path),
                success=False,
                message=f"任务 {body.task_id} 不存在",
                code=404,
                data=None
            )

        # 2. 停止任务进程
        try:
            logger.info(f"正在停止任务进程: {body.task_id}")
            stop_result = await queue.cancel_task(body.task_id)
            logger.info(f"停止任务进程结果: {stop_result}")
            
            # 等待任务真正停止
            for _ in range(10):  # 最多等待5秒
                if not await queue.is_task_running(body.task_id):
                    break
                await asyncio.sleep(0.5)
                
        except Exception as e:
            logger.error(f"停止任务进程失败: {str(e)}", exc_info=True)
            return BaseApiResponse(
                requestId=str(uuid.uuid4()),
                path=str(request.url.path),
                success=False,
                message=f"停止任务进程失败: {str(e)}",
                code=500,
                data=None
            )

        # 3. 获取父任务ID
        parent_task_id = task.parent_task_id

        try:
            # 4. 删除当前子任务
            logger.info(f"删除子任务: {body.task_id}")
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

            return BaseApiResponse(
                requestId=str(uuid.uuid4()),
                path=str(request.url.path),
                success=True,
                message="任务已停止并删除",
                code=200,
                data={
                    "task_id": body.task_id,
                    "parent_task_id": parent_task_id,
                    "parent_deleted": parent_task_id and not remaining_sub_tasks
                }
            )

        except Exception as e:
            db.rollback()
            logger.error(f"删除任务记录失败: {str(e)}", exc_info=True)
            return BaseApiResponse(
                requestId=str(uuid.uuid4()),
                path=str(request.url.path),
                success=False,
                message=f"删除任务记录失败: {str(e)}",
                code=500,
                data=None
            )

    except Exception as e:
        logger.error(f"停止任务失败: {str(e)}", exc_info=True)
        return BaseApiResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=False,
            message=f"停止任务失败: {str(e)}",
            code=500,
            data=None
        )

class StreamStatusRequest(BaseModel):
    """流状态查询请求"""
    task_id: str = Field(..., description="任务ID")

@router.post("/stream/status", response_model=BaseApiResponse, summary="获取流状态", description="获取指定流分析任务的状态")
async def get_stream_status(
    request: Request,
    body: StreamStatusRequest,
    queue: TaskQueueManager = Depends(get_task_queue)
) -> BaseApiResponse:
    """
    获取流分析状态
    
    Args:
        request: FastAPI请求对象
        body: 流状态查询请求体
        queue: 任务队列管理器
    
    Returns:
        BaseApiResponse: 流分析状态
        
    请求示例:
    ```json
    {
        "task_id": "550e8400-e29b-41d4-a716-446655440000"  // 任务ID
    }
    ```
    """
    try:
        status = await queue.get_task_status(body.task_id)
        return BaseApiResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=True,
            message="获取状态成功",
            code=200,
            data=status
        )
    except Exception as e:
        logger.error(f"获取任务状态失败: {str(e)}")
        return BaseApiResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=False,
            message=f"获取任务状态失败: {str(e)}",
            code=500,
            data=None
        )

@router.post("/resource", response_model=ResourceStatusResponse, summary="获取资源状态", description="获取系统资源使用状况")
async def get_resource_status(request: Request) -> ResourceStatusResponse:
    """
    获取资源状态
    
    Args:
        request: FastAPI请求对象
    
    Returns:
        ResourceStatusResponse: 资源使用状况
    """
    try:
        status = resource_monitor.get_resource_usage()
        return ResourceStatusResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=True,
            message="获取资源状态成功",
            code=200,
            data=status
        )
    except Exception as e:
        logger.error(f"获取资源状态失败: {str(e)}")
        return ResourceStatusResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=False,
            message=f"获取资源状态失败: {str(e)}",
            code=500,
            data=None
        )

# 添加新的请求模型
class VideoStatusRequest(BaseModel):
    """视频状态查询请求"""
    task_id: str = Field(..., description="任务ID")

@router.post("/video/status", response_model=VideoAnalysisResponse, summary="获取视频状态", description="获取指定视频分析任务的状态")
async def get_video_status(
    request: Request,
    body: VideoStatusRequest
) -> VideoAnalysisResponse:
    """
    获取视频分析任务状态
    
    Args:
        request: FastAPI请求对象
        body: 视频状态查询请求体
    
    Returns:
        VideoAnalysisResponse: 视频分析状态
        
    请求示例:
    ```json
    {
        "task_id": "550e8400-e29b-41d4-a716-446655440000"  // 任务ID
    }
    ```
    """
    try:
        # 获取任务状态
        task = await detector.get_video_task_status(body.task_id)
        if not task:
            return VideoAnalysisResponse(
                requestId=str(uuid.uuid4()),
                path=str(request.url.path),
                success=False,
                message=f"任务 {body.task_id} 不存在",
                code=404,
                data=None
            )
            
        # 将字符串状态转换为数字状态
        status = status_map.get(task.get('status', 'processing'), 1)  # 默认为运行中
        
        # 构建响应数据
        analysis_data = VideoAnalysisData(
            task_id=body.task_id,
            task_name=task.get('task_name'),
            status=status,
            video_url=task.get('video_url'),
            saved_path=task.get('saved_path'),
            start_time=task.get('start_time'),
            end_time=task.get('end_time'),
            analysis_duration=task.get('analysis_duration'),
            progress=task.get('progress'),
            total_frames=task.get('total_frames'),
            processed_frames=task.get('processed_frames')
        )
        
        return VideoAnalysisResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=True,
            message="获取任务状态成功",
            code=200,
            data=analysis_data
        )
        
    except Exception as e:
        logger.error(f"获取视频分析任务状态失败: {str(e)}", exc_info=True)
        return VideoAnalysisResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=False,
            message=f"获取任务状态失败: {str(e)}",
            code=500,
            data=None
        )

class VideoStopRequest(BaseModel):
    """停止视频分析任务请求"""
    task_id: str = Field(..., description="任务ID")

@router.post("/video/stop", response_model=BaseApiResponse, summary="停止视频分析", description="停止指定的视频分析任务")
async def stop_video_analysis(
    request: Request,
    body: VideoStopRequest
) -> BaseApiResponse:
    """
    停止视频分析任务
    
    Args:
        request: FastAPI请求对象
        body: 停止视频分析请求体
    
    Returns:
        BaseApiResponse: 停止结果
        
    请求示例:
    ```json
    {
        "task_id": "550e8400-e29b-41d4-a716-446655440000"  // 任务ID
    }
    ```
    """
    try:
        # 停止任务
        result = await detector.stop_video_task(body.task_id)
        if not result:
            return BaseApiResponse(
                requestId=str(uuid.uuid4()),
                path=str(request.url.path),
                success=False,
                message=f"任务 {body.task_id} 不存在",
                code=404,
                data=None
            )
            
        return BaseApiResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=True,
            message="任务已停止",
            code=200,
            data={
                "task_id": body.task_id
            }
        )
        
    except Exception as e:
        logger.error(f"停止视频分析任务失败: {str(e)}", exc_info=True)
        return BaseApiResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=False,
            message=f"停止任务失败: {str(e)}",
            code=500,
            data=None
        )