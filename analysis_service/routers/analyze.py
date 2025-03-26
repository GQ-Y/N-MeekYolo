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
from fastapi import APIRouter, HTTPException, Depends, File, UploadFile, Form, BackgroundTasks
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
from analysis_service.models.requests import (
    ImageAnalysisRequest,
    VideoAnalysisRequest,
    StreamAnalysisRequest,
    StreamTask
)
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

@router.post("/image", response_model=ImageAnalysisResponse)
async def analyze_image(request: ImageAnalysisRequest):
    """分析图片
    
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
    
    响应示例:
    ```json
    {
        "image_url": "http://example.com/image.jpg",  // 原始图片URL
        "task_name": "行人检测-1",                    // 任务名称
        "detections": [                              // 检测结果列表
            {
                "track_id": null,                    // 跟踪ID（图片检测时为null）
                "class_name": "person",              // 类别名称
                "confidence": 0.95,                  // 置信度
                "bbox": {                           // 边界框坐标
                    "x1": 100,                      // 左上角x坐标
                    "y1": 200,                      // 左上角y坐标
                    "x2": 300,                      // 右下角x坐标
                    "y2": 400                       // 右下角y坐标
                },
                "children": []                      // 嵌套检测的子目标列表
            }
        ],
        "result_image": "base64...",               // base64编码的结果图片（当is_base64=true时）
        "saved_path": "/path/to/saved/result.jpg",  // 保存路径
        "start_time": 1648123456.789,             // 开始时间戳
        "end_time": 1648123457.123,               // 结束时间戳
        "analysis_duration": 0.334                 // 分析耗时（秒）
    }
    ```
    """
    try:
        # 记录请求参数
        logger.info(f"收到图片分析请求:")
        logger.info(f"- 模型代码: {request.model_code}")
        logger.info(f"- 任务名称: {request.task_name}")
        logger.info(f"- 图片数量: {len(request.image_urls)}")
        logger.info(f"- 检测配置: {request.config}")
        logger.info(f"- 是否返回base64: {request.is_base64}")
        logger.info(f"- 是否保存结果: {request.save_result}")
        
        result = await detector.detect_images(
            request.model_code,
            request.image_urls,
            request.callback_urls,
            request.is_base64,
            config=request.config.dict() if request.config else None,
            task_name=request.task_name,
            enable_callback=request.enable_callback,
            save_result=request.save_result
        )
        
        # 记录检测结果
        logger.info(f"检测完成:")
        logger.info(f"- 检测到目标数量: {len(result.get('detections', []))}")
        logger.info(f"- 处理时长: {result.get('analysis_duration', 0):.3f}秒")
        if result.get('saved_paths'):
            logger.info(f"- 保存路径: {result['saved_paths']}")
        
        # 构建响应
        response = ImageAnalysisResponse(
            image_url=request.image_urls[0],
            task_name=result.get('task_name'),
            detections=result.get('detections', []),
            result_image=result.get('result_image'),
            saved_path=result.get('saved_path'),
            start_time=result.get('start_time'),
            end_time=result.get('end_time'),
            analysis_duration=result.get('analysis_duration')
        )
        
        return response
        
    except Exception as e:
        logger.error(f"图片分析失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/video/url", response_model=VideoAnalysisResponse)
async def analyze_video_url(
    request: VideoAnalysisRequest,
    background_tasks: BackgroundTasks,
    detector: YOLODetector = Depends(get_detector)
) -> VideoAnalysisResponse:
    """分析视频
    
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
    
    响应示例:
    ```json
    {
        "task_id": "task_20240326_123456_abcd1234",
        "task_name": "视频分析-1",
        "status": 1,  // 0:等待中 1:运行中 2:已完成 -1:失败
        "video_url": "http://example.com/video.mp4",
        "saved_path": "results/20240326/video_analysis_1.mp4",
        "start_time": 1648123456.789,
        "end_time": null,
        "analysis_duration": null,
        "progress": 0.0,
        "total_frames": 0,
        "processed_frames": 0
    }
    ```
    """
    try:
        # 生成任务ID
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        # 启动视频分析任务
        task = await detector.start_video_analysis(
            task_id=task_id,
            model_code=request.model_code,
            video_url=request.video_url,
            callback_urls=request.callback_urls,
            config=request.config,
            task_name=request.task_name,
            enable_callback=request.enable_callback,
            save_result=request.save_result
        )
        
        # 构建响应
        return VideoAnalysisResponse(
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
        
    except Exception as e:
        logger.error(f"视频分析失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"视频分析失败: {str(e)}"
        )

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
            
        # 记录请求参数
        logger.info(f"收到流分析请求:")
        logger.info(f"- 任务数量: {len(request.tasks)}")
        logger.info(f"- 分析间隔: {request.analyze_interval}秒")
        logger.info(f"- 报警间隔: {request.alarm_interval}秒")
        logger.info(f"- 推送间隔: {request.push_interval}秒")
        logger.info(f"- 是否启用回调: {request.enable_callback}")
        logger.info(f"- 是否保存结果: {request.save_result}")
            
        # 生成父任务ID
        parent_task_id = str(uuid.uuid4())
        
        # 从配置获取默认值
        default_analyze_interval = settings.ANALYSIS.analyze_interval
        default_alarm_interval = settings.ANALYSIS.alarm_interval
        default_random_interval = tuple(settings.ANALYSIS.random_interval)
        default_push_interval = settings.ANALYSIS.push_interval
        
        # 使用请求参数覆盖默认值
        analyze_interval = request.analyze_interval or default_analyze_interval
        alarm_interval = request.alarm_interval or default_alarm_interval
        random_interval = request.random_interval or default_random_interval
        push_interval = request.push_interval or default_push_interval
        
        # 创建子任务
        sub_tasks = []
        queue_tasks = []
        
        for task in request.tasks:
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
                callback_urls=request.callback_urls,
                task_name=task.task_name
            )
            sub_tasks.append(sub_task)
            
            # 将任务加入队列,传递所有参数
            queue_task = await queue.add_task(
                task=sub_task,
                parent_task_id=parent_task_id,
                analyze_interval=analyze_interval,
                alarm_interval=alarm_interval,
                random_interval=random_interval,
                push_interval=push_interval,
                config=task.config.dict() if task.config else None,
                task_name=task.task_name,
                enable_callback=request.enable_callback,
                save_result=request.save_result  # 添加保存结果参数
            )
            queue_tasks.append(queue_task)
            
        # 构建子任务信息列表
        sub_task_infos = [
            SubTaskInfo(
                task_id=qt.id,
                task_name=st.task_name,
                status=0,
                stream_url=st.stream_url,
                output_url=st.output_url,
                saved_path=None  # 初始时保存路径为空
            )
            for qt, st in zip(queue_tasks, sub_tasks)
        ]
        
        # 构建响应数据
        response_data = StreamBatchResponse(
            parent_task_id=parent_task_id,
            sub_tasks=sub_task_infos
        )
        
        logger.info(f"流分析任务已创建:")
        logger.info(f"- 父任务ID: {parent_task_id}")
        logger.info(f"- 子任务数量: {len(sub_tasks)}")
        
        return StreamResponse(
            code=200,
            message="Stream analysis tasks queued",
            data=response_data
        )
        
    except Exception as e:
        logger.error(f"创建流分析任务失败: {str(e)}", exc_info=True)
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

# 添加新的请求模型
class VideoStatusRequest(BaseModel):
    """视频状态查询请求"""
    task_id: str = Field(..., description="任务ID")

@router.post("/video/status", response_model=VideoAnalysisResponse)
async def get_video_status(request: VideoStatusRequest):
    """获取视频分析任务状态
    
    请求示例:
    ```json
    {
        "task_id": "550e8400-e29b-41d4-a716-446655440000"
    }
    ```
    
    响应示例:
    ```json
    {
        "task_id": "550e8400-e29b-41d4-a716-446655440000",
        "task_name": "视频分析-1",
        "status": 1,  # 0:等待中 1:运行中 2:已完成 -1:失败
        "video_url": "http://example.com/video.mp4",
        "saved_path": "results/20240326/video_analysis_1.mp4",
        "start_time": 1648123456.789,
        "end_time": 1648123556.789,
        "analysis_duration": 100.0,
        "progress": 45.5,  # 处理进度（0-100）
        "total_frames": 1000,  # 总帧数
        "processed_frames": 455  # 已处理帧数
    }
    ```
    """
    try:
        # 获取任务状态
        task = await detector.get_video_task_status(request.task_id)
        if not task:
            raise HTTPException(
                status_code=404,
                detail=f"任务 {request.task_id} 不存在"
            )
            
        # 将字符串状态转换为数字状态
        status_map = {
            "waiting": 0,
            "processing": 1,
            "completed": 2,
            "failed": -1
        }
        status = status_map.get(task.get('status', 'processing'), 1)  # 默认为运行中
        
        return VideoAnalysisResponse(
            task_id=request.task_id,
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
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取视频分析任务状态失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"获取任务状态失败: {str(e)}"
        )

class VideoStopRequest(BaseModel):
    """停止视频分析任务请求"""
    task_id: str = Field(..., description="任务ID")

@router.post("/video/stop", response_model=BaseResponse)
async def stop_video_analysis(request: VideoStopRequest):
    """停止视频分析任务
    
    请求示例:
    ```json
    {
        "task_id": "550e8400-e29b-41d4-a716-446655440000"
    }
    ```
    
    响应示例:
    ```json
    {
        "code": 200,
        "message": "任务已停止",
        "data": {
            "task_id": "550e8400-e29b-41d4-a716-446655440000"
        }
    }
    ```
    """
    try:
        # 停止任务
        result = await detector.stop_video_task(request.task_id)
        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"任务 {request.task_id} 不存在"
            )
            
        return {
            "code": 200,
            "message": "任务已停止",
            "data": {
                "task_id": request.task_id
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"停止视频分析任务失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"停止任务失败: {str(e)}"
        )