from typing import List, Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session
from api_service.models.database import Stream, StreamGroup
from api_service.models.requests import (
    CreateStreamRequest,
    UpdateStreamRequest
)
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class StreamService:
    def create_stream(self, db: Session, stream_data: CreateStreamRequest) -> Stream:
        """创建流"""
        try:
            # 创建流对象
            stream = Stream(
                name=stream_data.name,
                url=stream_data.url,
                description=stream_data.description
            )
            
            # 如果指定了分组，添加分组关联
            if stream_data.group_ids:
                groups = db.query(StreamGroup).filter(
                    StreamGroup.id.in_(stream_data.group_ids)
                ).all()
                stream.groups.extend(groups)
            
            # 保存到数据库
            db.add(stream)
            db.commit()
            db.refresh(stream)
            
            return stream
            
        except Exception as e:
            db.rollback()
            logger.error(f"Database error in create stream: {str(e)}", exc_info=True)
            raise

    def get_streams(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        group_id: Optional[int] = None,
        status: Optional[str] = None
    ) -> List[Stream]:
        """获取流列表"""
        try:
            query = db.query(Stream)
            
            # 按分组过滤
            if group_id is not None:
                query = query.filter(Stream.groups.any(StreamGroup.id == group_id))
            
            # 按状态过滤
            if status and status.lower() != 'all':
                query = query.filter(Stream.status == status)
            
            # 分页
            streams = query.offset(skip).limit(limit).all()
            return streams
            
        except Exception as e:
            logger.error(f"Get streams failed: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"获取失败: {str(e)}"
            )
            
    def get_stream(self, db: Session, stream_id: int) -> Optional[Stream]:
        """获取单个流"""
        try:
            stream = db.query(Stream).filter(Stream.id == stream_id).first()
            return stream
        except Exception as e:
            logger.error(f"Get stream failed: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"获取失败: {str(e)}"
            )
            
    def update_stream(
        self,
        db: Session,
        stream_id: int,
        data: UpdateStreamRequest
    ) -> Optional[Stream]:
        """更新流"""
        try:
            stream = db.query(Stream).filter(Stream.id == stream_id).first()
            if not stream:
                return None
                
            # 更新基本信息
            for key, value in data.dict(exclude_unset=True).items():
                if key != "group_ids":
                    setattr(stream, key, value)
            
            # 更新分组关系
            if data.group_ids is not None:
                # 清除现有关系
                stream.groups = []
                # 添加新关系
                for group_id in data.group_ids:
                    group = db.query(StreamGroup).filter(StreamGroup.id == group_id).first()
                    if not group:
                        raise HTTPException(
                            status_code=404,
                            detail=f"分组 ID {group_id} 不存在"
                        )
                    stream.groups.append(group)
            
            db.commit()
            db.refresh(stream)
            return stream
            
        except HTTPException as e:
            db.rollback()
            raise e
        except Exception as e:
            db.rollback()
            logger.error(f"Update stream failed: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"更新失败: {str(e)}"
            )
            
    def delete_stream(self, db: Session, stream_id: int) -> bool:
        """删除流"""
        try:
            stream = db.query(Stream).filter(Stream.id == stream_id).first()
            if not stream:
                return False
                
            db.delete(stream)
            db.commit()
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Delete stream failed: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"删除失败: {str(e)}"
            )