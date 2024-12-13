"""
任务CRUD操作
"""
from datetime import datetime
from sqlalchemy.orm import Session
from analysis_service.models.database import Task
from shared.utils.logger import setup_logger
from typing import Dict, Any
import uuid

logger = setup_logger(__name__)

def create_task(
    db: Session,
    task_id: str = None,
    model_code: str = None,
    stream_url: str = None,
    callback_urls: str = None,
    output_url: str = None
) -> Task:
    """创建任务"""
    # 如果没有提供task_id,生成一个新的
    if task_id is None:
        task_id = str(uuid.uuid4())
        
    task = Task(
        id=task_id,
        model_code=model_code,
        stream_url=stream_url,
        callback_urls=callback_urls,
        output_url=output_url
    )
    
    db.add(task)
    db.commit()
    db.refresh(task)
    
    return task

def update_task_status(db: Session, task_id: str, status: int) -> Task:
    """更新任务状态"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if task:
        task.status = status
        if status == 0:  # 停止
            task.stop_time = datetime.now()
            if task.start_time:
                duration = (task.stop_time - task.start_time).total_seconds() / 60
                task.duration = duration
        db.commit()
    return task

def get_task(db: Session, task_id: str) -> Task:
    """获取任务"""
    return db.query(Task).filter(Task.id == task_id).first() 