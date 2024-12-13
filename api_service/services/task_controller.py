"""
任务控制服务
"""
import httpx
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from api_service.models.database import Task, Stream, Model, SubTask
from api_service.core.config import settings
from shared.utils.logger import setup_logger
from api_service.models.requests import StreamStatus
from datetime import datetime
from api_service.services.analysis import AnalysisService  # 添加导入

logger = setup_logger(__name__)

class TaskController:
    """任务控制器"""
    
    def __init__(self):
        self.analysis_url = f"http://{settings.SERVICES.analysis.host}:{settings.SERVICES.analysis.port}"
        self.analysis_service = AnalysisService()  # 初始化分析服务
        
    def _get_callback_urls(self, callbacks) -> str:
        """获取回调URL列表"""
        # 获取 api_service 回调地址
        api_callback_url = f"http://{settings.SERVICES.api.host}:{settings.SERVICES.api.port}/api/v1/callbacks/analysis/callback"
        
        # 构造回调URL列表
        callback_urls = []
        if callbacks:
            callback_urls.extend([cb.url for cb in callbacks])
        callback_urls.append(api_callback_url)
        
        # 转换为分号分隔的字符串
        return ";".join(callback_urls)
    
    async def start_analysis_task(self, task: Task, stream: Stream, model: Model, callback_urls: List[str]) -> bool:
        """
        已废弃,使用start_task替代
        """
        logger.warning("This method is deprecated, use start_task instead")
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
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                return False
            
            # 更新任务状态
            task.status = "starting"
            task.started_at = datetime.now()
            
            # 为每个视频源和模型组合创建子任务
            for stream in task.streams:
                for model in task.models:
                    try:
                        # 调用Analysis Service创建分析任务
                        analysis_task_id = await self.analysis_service.analyze_stream(
                            model_code=model.code,
                            stream_url=stream.url,
                            callback_url=self._get_callback_urls(task.callbacks),
                            callback_interval=task.callback_interval
                        )
                        
                        # 创建子任务记录
                        sub_task = SubTask(
                            task_id=task.id,
                            analysis_task_id=analysis_task_id,
                            stream_id=stream.id,
                            model_id=model.id,
                            status="running",
                            started_at=datetime.now()
                        )
                        db.add(sub_task)
                        
                    except Exception as e:
                        logger.error(f"Failed to create sub task: {str(e)}")
                        continue
                        
            # 更新任务状态
            task.status = "running"
            db.commit()
            
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Start task failed: {str(e)}")
            return False
            
    async def stop_task(self, db: Session, task_id: int) -> bool:
        """停止任务"""
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                return False
                
            # 停止所有子任务
            for sub_task in task.sub_tasks:
                if sub_task.status == "running":
                    try:
                        async with httpx.AsyncClient() as client:
                            response = await client.post(
                                f"{self.analysis_url}/analyze/stream/{sub_task.analysis_task_id}/stop"
                            )
                            response.raise_for_status()
                            logger.info(f"Stopped sub task {sub_task.analysis_task_id}")
                    except Exception as e:
                        logger.error(f"Failed to stop sub task {sub_task.analysis_task_id}: {str(e)}")
                        
            # 更新任务状态
            task.status = "stopped"
            task.completed_at = datetime.now()
            db.commit()
            
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Stop task failed: {str(e)}")
            return False