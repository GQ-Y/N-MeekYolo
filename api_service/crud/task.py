"""
任务 CRUD 操作
"""
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from api_service.models.database import Task, Stream, Model, Callback

def create_task(
    db: Session,
    name: str,
    stream_ids: List[int],
    model_ids: List[int],
    callback_ids: List[int] = None,
    callback_interval: int = 1
) -> Task:
    """创建任务"""
    task = Task(
        name=name,
        callback_interval=callback_interval
    )
    
    # 添加视频源关联
    streams = db.query(Stream).filter(Stream.id.in_(stream_ids)).all()
    task.streams.extend(streams)
    
    # 添加模型关联
    models = db.query(Model).filter(Model.id.in_(model_ids)).all()
    task.models.extend(models)
    
    # 添加回调服务关联
    if callback_ids:
        callbacks = db.query(Callback).filter(Callback.id.in_(callback_ids)).all()
        task.callbacks.extend(callbacks)
    
    db.add(task)
    db.commit()
    db.refresh(task)
    return task

def get_task(db: Session, task_id: int) -> Optional[Task]:
    """获取任务"""
    return db.query(Task).filter(Task.id == task_id).first()

def get_tasks(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    status: str = None
) -> List[Task]:
    """获取任务列表"""
    query = db.query(Task)
    if status:
        query = query.filter(Task.status == status)
    return query.offset(skip).limit(limit).all()

def update_task_status(
    db: Session,
    task_id: int,
    status: str,
    error_message: str = None
) -> Optional[Task]:
    """更新任务状态"""
    task = get_task(db, task_id)
    if task:
        task.status = status
        if error_message:
            task.error_message = error_message
            
        # 更新时间戳
        if status == 'running':
            task.started_at = datetime.utcnow()
        elif status in ['completed', 'error']:
            task.completed_at = datetime.utcnow()
            
        db.commit()
        db.refresh(task)
    return task

def update_task(
    db: Session,
    task_id: int,
    name: str = None,
    stream_ids: List[int] = None,
    model_ids: List[int] = None,
    callback_ids: List[int] = None,
    callback_interval: int = None
) -> Optional[Task]:
    """更新任务"""
    task = get_task(db, task_id)
    if task:
        if name:
            task.name = name
        if callback_interval is not None:
            task.callback_interval = callback_interval
            
        # 更新视频源关联
        if stream_ids is not None:
            streams = db.query(Stream).filter(Stream.id.in_(stream_ids)).all()
            task.streams = streams
            
        # 更新模型关联
        if model_ids is not None:
            models = db.query(Model).filter(Model.id.in_(model_ids)).all()
            task.models = models
            
        # 更新回调服务关联
        if callback_ids is not None:
            callbacks = db.query(Callback).filter(Callback.id.in_(callback_ids)).all()
            task.callbacks = callbacks
            
        db.commit()
        db.refresh(task)
    return task

def delete_task(db: Session, task_id: int) -> bool:
    """删除任务"""
    task = get_task(db, task_id)
    if task:
        db.delete(task)
        db.commit()
        return True
    return False 