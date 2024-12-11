"""
视频源分组 CRUD 操作
"""
from sqlalchemy.orm import Session
from typing import List, Optional
from api_service.models.database import StreamGroup, Stream

def create_group(db: Session, name: str, description: str = None) -> StreamGroup:
    """创建分组"""
    group = StreamGroup(name=name, description=description)
    db.add(group)
    db.commit()
    db.refresh(group)
    return group

def get_group(db: Session, group_id: int) -> Optional[StreamGroup]:
    """获取分组"""
    return db.query(StreamGroup).filter(StreamGroup.id == group_id).first()

def get_groups(db: Session, skip: int = 0, limit: int = 100) -> List[StreamGroup]:
    """获取分组列表"""
    return db.query(StreamGroup).offset(skip).limit(limit).all()

def update_group(db: Session, group_id: int, name: str = None, description: str = None) -> Optional[StreamGroup]:
    """更新分组"""
    group = get_group(db, group_id)
    if group:
        if name:
            group.name = name
        if description:
            group.description = description
        db.commit()
        db.refresh(group)
    return group

def delete_group(db: Session, group_id: int) -> bool:
    """删除分组"""
    group = get_group(db, group_id)
    if group:
        db.delete(group)
        db.commit()
        return True
    return False 