"""
视频流分组的数据库操作
"""
from sqlalchemy.orm import Session
from typing import List, Optional
from api_service.models.database import StreamGroup, Stream

def create_stream_group(
    db: Session,
    name: str,
    description: Optional[str] = None
) -> StreamGroup:
    """创建视频流分组"""
    group = StreamGroup(
        name=name,
        description=description
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return group

def get_stream_groups(
    db: Session,
    skip: int = 0,
    limit: int = 100
) -> List[StreamGroup]:
    """获取视频流分组列表"""
    return db.query(StreamGroup).offset(skip).limit(limit).all()

def get_stream_group(
    db: Session,
    group_id: int
) -> Optional[StreamGroup]:
    """获取视频流分组详情"""
    return db.query(StreamGroup).filter(StreamGroup.id == group_id).first()

def update_stream_group(
    db: Session,
    group_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None
) -> Optional[StreamGroup]:
    """更新视频流分组"""
    group = get_stream_group(db, group_id)
    if not group:
        return None
        
    if name is not None:
        group.name = name
    if description is not None:
        group.description = description
        
    db.commit()
    db.refresh(group)
    return group

def delete_stream_group(
    db: Session,
    group_id: int
) -> bool:
    """删除视频流分组"""
    group = get_stream_group(db, group_id)
    if not group:
        return False
        
    db.delete(group)
    db.commit()
    return True

def add_stream_to_group(
    db: Session,
    group_id: int,
    stream_id: int
) -> Optional[StreamGroup]:
    """向分组添加视频流"""
    group = get_stream_group(db, group_id)
    if not group:
        return None
        
    stream = db.query(Stream).filter(Stream.id == stream_id).first()
    if not stream:
        return None
        
    group.streams.append(stream)
    db.commit()
    db.refresh(group)
    return group

def remove_stream_from_group(
    db: Session,
    group_id: int,
    stream_id: int
) -> bool:
    """从分组移除视频流"""
    group = get_stream_group(db, group_id)
    if not group:
        return False
        
    stream = db.query(Stream).filter(Stream.id == stream_id).first()
    if not stream or stream not in group.streams:
        return False
        
    group.streams.remove(stream)
    db.commit()
    return True 