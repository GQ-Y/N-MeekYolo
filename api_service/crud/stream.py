"""
视频源 CRUD 操作
"""
from sqlalchemy.orm import Session
from typing import List, Optional
from api_service.models.database import Stream, StreamGroup

def create_stream(
    db: Session, 
    name: str, 
    url: str, 
    description: str = None,
    group_ids: List[int] = None
) -> Stream:
    """创建视频源"""
    stream = Stream(name=name, url=url, description=description)
    
    # 添加分组关联
    if group_ids:
        groups = db.query(StreamGroup).filter(StreamGroup.id.in_(group_ids)).all()
        stream.groups.extend(groups)
    
    db.add(stream)
    db.commit()
    db.refresh(stream)
    return stream

def get_stream(db: Session, stream_id: int) -> Optional[Stream]:
    """获取视频源"""
    return db.query(Stream).filter(Stream.id == stream_id).first()

def get_streams(
    db: Session, 
    skip: int = 0, 
    limit: int = 100,
    group_id: int = None,
    status: str = None
) -> List[Stream]:
    """获取视频源列表"""
    query = db.query(Stream)
    
    # 按分组过滤
    if group_id:
        query = query.filter(Stream.groups.any(StreamGroup.id == group_id))
    
    # 按状态过滤
    if status:
        query = query.filter(Stream.status == status)
        
    return query.offset(skip).limit(limit).all()

def update_stream(
    db: Session,
    stream_id: int,
    name: str = None,
    url: str = None,
    description: str = None,
    status: str = None,
    error_message: str = None,
    group_ids: List[int] = None
) -> Optional[Stream]:
    """更新视频源"""
    stream = get_stream(db, stream_id)
    if stream:
        if name:
            stream.name = name
        if url:
            stream.url = url
        if description:
            stream.description = description
        if status:
            stream.status = status
        if error_message:
            stream.error_message = error_message
            
        # 更新分组关联
        if group_ids is not None:
            groups = db.query(StreamGroup).filter(StreamGroup.id.in_(group_ids)).all()
            stream.groups = groups
            
        db.commit()
        db.refresh(stream)
    return stream

def delete_stream(db: Session, stream_id: int) -> bool:
    """删除视频源"""
    stream = get_stream(db, stream_id)
    if stream:
        db.delete(stream)
        db.commit()
        return True
    return False 