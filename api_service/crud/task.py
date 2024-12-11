"""
任务 CRUD 操作
"""
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import datetime
from api_service.models.database import Task, Stream, Model, Callback

def create_task(
    db: Session,
    name: str,
    stream_ids: List[int],
    model_ids: List[int],
    callback_ids: List[int],
    callback_interval: int = 1
) -> Task:
    """创建任务"""
    # 获取关联对象
    streams = db.query(Stream).filter(Stream.id.in_(stream_ids)).all()
    models = db.query(Model).filter(Model.id.in_(model_ids)).all()
    callbacks = db.query(Callback).filter(Callback.id.in_(callback_ids)).all()
    
    # 创建任务
    task = Task(
        name=name,
        callback_interval=callback_interval,
        streams=streams,
        models=models,
        callbacks=callbacks
    )
    
    db.add(task)
    db.commit()
    db.refresh(task)
    return task

def get_task(db: Session, task_id: int) -> Optional[Task]:
    """获取任务详情"""
    return db.query(Task)\
        .options(
            joinedload(Task.streams),
            joinedload(Task.models),
            joinedload(Task.callbacks)
        )\
        .filter(Task.id == task_id)\
        .first()

def get_tasks(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None
) -> List[Task]:
    """获取任务列表"""
    query = db.query(Task)\
        .options(
            joinedload(Task.streams),
            joinedload(Task.models),
            joinedload(Task.callbacks)
        )
    
    if status:
        query = query.filter(Task.status == status)
    
    return query.offset(skip).limit(limit).all()

def update_task_status(
    db: Session,
    task_id: int,
    status: str,
    error_message: Optional[str] = None
) -> Optional[Task]:
    """更新任务状态"""
    task = db.query(Task)\
        .options(
            joinedload(Task.streams),
            joinedload(Task.models),
            joinedload(Task.callbacks)
        )\
        .filter(Task.id == task_id)\
        .first()
        
    if task:
        task.status = status
        if error_message is not None:
            task.error_message = error_message
            
        # 更新相关时间戳
        if status == "running":
            task.started_at = datetime.now()
        elif status in ["completed", "failed", "stopped"]:
            task.completed_at = datetime.now()
            
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
    # 使用 joinedload 获取任务及其关联数据
    task = db.query(Task)\
        .options(
            joinedload(Task.streams),
            joinedload(Task.models),
            joinedload(Task.callbacks)
        )\
        .filter(Task.id == task_id)\
        .first()
        
    if task:
        if name:
            task.name = name
        if callback_interval is not None:
            task.callback_interval = callback_interval
            
        try:
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
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update task relationships: {str(e)}")
            raise
            
    return None

def delete_task(db: Session, task_id: int) -> bool:
    """删除任务"""
    task = get_task(db, task_id)
    if task:
        db.delete(task)
        db.commit()
        return True
    return False 