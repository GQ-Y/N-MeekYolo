from typing import List, Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session
from models.database import Stream, StreamGroup
from models.requests import (
    CreateStreamRequest,
    UpdateStreamRequest
)
from shared.utils.logger import setup_logger
from core.config import settings

logger = setup_logger(__name__)

class StreamService:
    def create_stream(self, db: Session, stream_data: CreateStreamRequest) -> Stream:
        """创建流"""
        try:
            # 检查URL是否已存在
            existing_stream = db.query(Stream).filter(Stream.url == stream_data.url).first()
            if existing_stream:
                raise HTTPException(
                    status_code=409,
                    detail=f"Stream with URL '{stream_data.url}' already exists"
                )
            
            # 创建流对象
            stream = Stream(
                name=stream_data.name,
                url=stream_data.url,
                description=stream_data.description
            )
            
            # 处理分组关联
            if stream_data.group_ids:
                # 如果指定了分组，添加分组关联
                groups = db.query(StreamGroup).filter(
                    StreamGroup.id.in_(stream_data.group_ids)
                ).all()
                stream.groups.extend(groups)
            else:
                # 如果没有指定分组，关联到默认分组
                default_group = db.query(StreamGroup).filter(
                    StreamGroup.name == settings.DEFAULT_GROUP.name
                ).first()
                
                if not default_group:
                    # 如果默认分组不存在(异常情况),创建默认分组
                    default_group = StreamGroup(
                        name=settings.DEFAULT_GROUP.name,
                        description=settings.DEFAULT_GROUP.description
                    )
                    db.add(default_group)
                    db.flush()  # 获取分组ID
                    
                stream.groups.append(default_group)
                logger.info(f"Associated stream with default group: {default_group.name}")
            
            # 保存到数据库
            db.add(stream)
            db.commit()
            db.refresh(stream)
            
            return stream
            
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Database error in create stream: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create stream: {str(e)}"
            )

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
                
            try:
                # 先检查是否有关联的任务
                logger.info(f"正在检查流 {stream_id} 是否有关联的任务...")
                associated_tasks = stream.tasks
                
                if associated_tasks:
                    logger.info(f"流 {stream_id} 有 {len(associated_tasks)} 个关联任务，解除关联...")
                    # 解除与任务的关联
                    for task in associated_tasks:
                        # 从task.streams中移除此stream
                        task.streams.remove(stream)
                    
                    # 提交更改，以确保任务关联已更新
                    db.commit()
                    logger.info(f"已解除流 {stream_id} 与任务的关联")
                
                # 删除流
                logger.info(f"正在删除流 {stream_id}...")
                db.delete(stream)
                db.commit()
                logger.info(f"流 {stream_id} 删除成功")
                return True
                
            except Exception as e:
                db.rollback()
                logger.error(f"删除流失败: {str(e)}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"删除失败: {str(e)}"
                )
                
        except Exception as e:
            logger.error(f"获取流信息失败: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"删除失败: {str(e)}"
            )