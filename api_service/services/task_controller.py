"""
任务控制服务
"""
import httpx
from typing import Dict, Any
from sqlalchemy.orm import Session
from api_service.models.database import Task, Stream
from api_service.core.config import settings
from shared.utils.logger import setup_logger
from api_service.models.requests import StreamStatus

logger = setup_logger(__name__)

class TaskController:
    """任务控制器"""
    
    def __init__(self):
        self.analysis_url = f"http://{settings.SERVICES.analysis.host}:{settings.SERVICES.analysis.port}"
        
    async def start_analysis(self, stream_url: str, model_code: str, callback_urls: list) -> Dict[str, Any]:
        """启动分析"""
        try:
            # 构造请求体
            request_data = {
                "model_code": model_code,
                "stream_url": stream_url,
                "callback_urls": callback_urls,
                "callback_interval": 1
            }
            
            logger.info(f"准备调用分析服务，请求URL: {self.analysis_url}/analyze/stream")
            logger.info(f"请求参数: {request_data}")
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.analysis_url}/analyze/stream",
                    json=request_data,
                    timeout=30.0
                )
                
                logger.info(f"分析服务响应状态码: {response.status_code}")
                logger.info(f"分析服务响应内容: {response.text}")
                
                # 检查响应状态
                response.raise_for_status()
                
                # 解析响应
                result = response.json()
                logger.info(f"分析服务返回结果: {result}")
                
                return result
                
        except httpx.HTTPStatusError as e:
            logger.error(f"分析服务HTTP错误: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"调用分析服务失败: {str(e)}")
            raise
            
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
                        callback_urls.append(api_callback_url)  # 添加 api_service 回调
                        
                        logger.info(f"开始处理 - 任务:{task_id} 视频源:{stream.id} 模型:{model.id}")
                        logger.info(f"视频源URL: {stream.url}")
                        logger.info(f"模型代码: {model.code}")
                        logger.info(f"回调URLs: {callback_urls}")
                        
                        # 启动分析
                        result = await self.start_analysis(
                            stream_url=stream.url,
                            model_code=model.code,
                            callback_urls=callback_urls  # 传入回调URL列表
                        )
                        
                        logger.info(f"分析启动成功 - 任务:{task_id} 视频源:{stream.id} 模型:{model.id}")
                        logger.info(f"分析结果: {result}")
                        
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
                
            # 更新任务状态
            task.status = "stopped"
            db.commit()
            
            # TODO: 调用分析服务停止分析
            
            return True
            
        except Exception as e:
            logger.error(f"停止任务失败: {str(e)}")
            return False