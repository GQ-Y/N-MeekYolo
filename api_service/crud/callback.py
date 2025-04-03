"""
回调服务 CRUD 操作
"""
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from models.database import Callback

def create_callback(
    db: Session,
    name: str,
    url: str,
    description: str = None,
    headers: Dict = None,
    method: str = 'POST',
    body_template: Dict = None,
    retry_count: int = 3,
    retry_interval: int = 1
) -> Callback:
    """创建回调服务"""
    callback = Callback(
        name=name,
        url=url,
        description=description,
        headers=headers,
        method=method,
        body_template=body_template,
        retry_count=retry_count,
        retry_interval=retry_interval
    )
    db.add(callback)
    db.commit()
    db.refresh(callback)
    return callback

def get_callback(db: Session, callback_id: int) -> Optional[Callback]:
    """获取回调服务"""
    return db.query(Callback).filter(Callback.id == callback_id).first()

def get_callbacks(db: Session, skip: int = 0, limit: int = 100) -> List[Callback]:
    """获取回调服务列表"""
    return db.query(Callback).offset(skip).limit(limit).all()

def update_callback(
    db: Session,
    callback_id: int,
    name: str = None,
    url: str = None,
    description: str = None,
    headers: Dict = None,
    method: str = None,
    body_template: Dict = None,
    retry_count: int = None,
    retry_interval: int = None
) -> Optional[Callback]:
    """更新回调服务"""
    callback = get_callback(db, callback_id)
    if callback:
        if name:
            callback.name = name
        if url:
            callback.url = url
        if description:
            callback.description = description
        if headers is not None:
            callback.headers = headers
        if method:
            callback.method = method
        if body_template is not None:
            callback.body_template = body_template
        if retry_count is not None:
            callback.retry_count = retry_count
        if retry_interval is not None:
            callback.retry_interval = retry_interval
        db.commit()
        db.refresh(callback)
    return callback

def delete_callback(db: Session, callback_id: int) -> bool:
    """删除回调服务"""
    callback = get_callback(db, callback_id)
    if callback:
        db.delete(callback)
        db.commit()
        return True
    return False 