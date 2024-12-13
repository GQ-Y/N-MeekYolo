"""
任务控制服务
"""
import httpx
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from api_service.models.database import Task, Stream, Model
from api_service.core.config import settings
from shared.utils.logger import setup_logger
from api_service.models.requests import StreamStatus
from datetime import datetime

logger = setup_logger(__name__)

class TaskController:
    """任务控制器"""
    
    def __init__(self):
        self.analysis_url = f"http://{settings.SERVICES.analysis.host}:{settings.SERVICES.analysis.port}"
        
    async def start_analysis_task(self, task: Task, stream: Stream, model: Model, callback_urls: List[str]) -> bool:
        """启动分析任务"""
        try:
            # 将回调URL列表转换为分号分隔的字符串
            callback_urls_str = ";".join(callback_urls) if callback_urls else None
            
            # 调用分析服务
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.analysis_url}/analyze/stream",
                    json={
                        "model_code": model.code,
                        "stream_url": stream.url,
                        "callback_urls": callback_urls_str,  # 使用转换后的字符串
                        "output_url": None,  # 可以根据需要设置
                        "callback_interval": task.callback_interval or 1
                    }
                )
                response.raise_for_status()
                
                # 更新任务状态
                task.status = "running"
                task.started_at = datetime.now()
                
                return True
                
        except httpx.HTTPStatusError as e:
            logger.error(f"分析服务HTTP错误: {e.response.status_code} - {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"分析服务调用失败 - 任务:{task.id} 视频源:{stream.id} 模型:{model.id} 错误:{str(e)}")
            return False
            
    async def update_stream_status(self, db: Session, task_id: int, status: StreamStatus):
        """更新任务关联的摄像头状态"""
        try:
            # 获取任务
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                logger.error(f"Task {task_id} not found")
                return False
                
            # 更新所有关联摄像头的状态
            for stream in task.streams:
                stream.status = status
                logger.info(f"Updated stream {stream.id} status to {status}")
                
            db.commit()
            return True
            
        except Exception as e:
            logger.error(f"Failed to update stream status: {str(e)}")
            db.rollback()
            return False
    
    async def start_task(self, db: Session, task_id: int) -> bool:
        """启动任务"""
        try:
            # 获取任务信息
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                logger.error(f"任务不存在: {task_id}")
                return False
                
            # 检查任务状态
            if task.status == "running":
                logger.warning(f"任务已在运行中: {task_id}")
                return False
                
            # 更新任务状态
            task.status = "running"
            task.started_at = datetime.now()
            db.commit()
            
            # 获取 api_service 回调地址
            api_callback_url = f"http://{settings.SERVICES.api.host}:{settings.SERVICES.api.port}/api/v1/callbacks/analysis/callback"
            
            for stream in task.streams:
                for model in task.models:
                    try:
                        # 构造回调URL列表
                        callback_urls = []
                        if task.callbacks:
                            callback_urls.extend([cb.url for cb in task.callbacks])
                        callback_urls.append(api_callback_url)
                        
                        logger.info(f"开始处理 - 任务:{task_id} 视频源:{stream.id} 模型:{model.id}")
                        logger.info(f"视频源URL: {stream.url}")
                        logger.info(f"模型代码: {model.code}")
                        logger.info(f"回调URLs: {callback_urls}")
                        
                        # 启动分析任务
                        success = await self.start_analysis_task(
                            task=task,
                            stream=stream,
                            model=model,
                            callback_urls=callback_urls
                        )
                        
                        if not success:
                            logger.error(f"启动分析任务失败 - 任务:{task_id} 视频源:{stream.id} 模型:{model.id}")
                            continue
                        
                        logger.info(f"分析启动成功 - 任务:{task_id} 视频源:{stream.id} 模型:{model.id}")
                        
                    except Exception as e:
                        logger.error(f"分析服务调用失败 - 任务:{task_id} 视频源:{stream.id} 模型:{model.id} 错误:{str(e)}")
                        continue
            
            # 任务启动成功后,更新摄像头状态为运行中
            if await self.update_stream_status(db, task_id, StreamStatus.ACTIVE):
                logger.info(f"Updated streams status to active for task {task_id}")
            else:
                logger.warning(f"Failed to update streams status for task {task_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"启动任务失败: {str(e)}")
            return False
            
    async def stop_task(self, db: Session, task_id: int) -> bool:
        """停止任务"""
        try:
            # 获取任务信息
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                logger.error(f"任务不存在: {task_id}")
                return False
                
            # 检查任务状态
            if task.status != "running":
                logger.warning(f"任务未在运行: {task_id}")
                return False
                
            # 检查是否有 analysis_task_id
            if not task.analysis_task_id:
                logger.error(f"任务 {task_id} 没有关联的 analysis_task_id")
                return False
                
            # 调用分析服务停止任务
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.analysis_url}/analyze/stream/{task.analysis_task_id}/stop",
                        timeout=30.0
                    )
                    
                    logger.info(f"分析服务停止响应状态码: {response.status_code}")
                    logger.info(f"分析服务停止响应内容: {response.text}")
                    
                    # 检查响应状态
                    response.raise_for_status()
                    
            except Exception as e:
                logger.error(f"调用分析服务停止任务失败: {str(e)}")
                return False
                
            # 更新任务状态
            task.status = "stopped"
            task.completed_at = datetime.now()
            db.commit()
            
            # 更新关联的摄像头状态为未运行
            if await self.update_stream_status(db, task_id, StreamStatus.INACTIVE):
                logger.info(f"Updated streams status to inactive for task {task_id}")
            else:
                logger.warning(f"Failed to update streams status for task {task_id}")
                
            return True
            
        except Exception as e:
            logger.error(f"停止任务失败: {str(e)}")
            return False