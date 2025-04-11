"""
流分组服务
"""
from typing import List, Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session
from models.database import StreamGroup, Stream
from models.requests import StreamGroupCreate, StreamGroupUpdate
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class StreamGroupService:
    """流分组服务"""
    
    async def create_stream_group(
        self,
        db: Session,
        data: StreamGroupCreate
    ) -> StreamGroup:
        """创建流分组"""
        try:
            # 检查名称是否已存在
            existing = db.query(StreamGroup).filter(
                StreamGroup.name == data.name
            ).first()
            if existing:
                logger.warning(f"Attempt to create duplicate stream group: {data.name}")
                raise HTTPException(
                    status_code=400,
                    detail=f"流分组名称 '{data.name}' 已存在"
                )
            
            # 创建新分组
            group = StreamGroup(
                name=data.name,
                description=data.description
            )
            
            logger.info(f"Creating new stream group: {data.name}")
            
            db.add(group)
            db.commit()
            db.refresh(group)
            
            logger.info(f"Successfully created stream group with id: {group.id}")
            
            return group
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Database error in create stream group: {str(e)}", exc_info=True)
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"数据库错误: {str(e)}"
            )
    
    async def get_stream_groups(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100
    ) -> List[StreamGroup]:
        """获取流分组列表"""
        try:
            return db.query(StreamGroup).offset(skip).limit(limit).all()
        except Exception as e:
            logger.error(f"Get stream groups failed: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def get_stream_group(
        self,
        db: Session,
        group_id: int
    ) -> Optional[StreamGroup]:
        """获取流分组"""
        try:
            group = db.query(StreamGroup).filter(
                StreamGroup.id == group_id
            ).first()
            if not group:
                raise HTTPException(
                    status_code=404,
                    detail="Stream group not found"
                )
            return group
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Get stream group failed: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def update_stream_group(
        self,
        db: Session,
        group_id: int,
        data: StreamGroupUpdate
    ) -> Optional[StreamGroup]:
        """更新流分组"""
        try:
            group = await self.get_stream_group(db, group_id)
            
            # 检查新名称是否已存在
            if data.name and data.name != group.name:
                existing = db.query(StreamGroup).filter(
                    StreamGroup.name == data.name
                ).first()
                if existing:
                    raise HTTPException(
                        status_code=400,
                        detail="Stream group name already exists"
                    )
            
            # 更新字段
            for field, value in data.dict(exclude_unset=True).items():
                setattr(group, field, value)
            
            db.commit()
            db.refresh(group)
            return group
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Update stream group failed: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def delete_stream_group(
        self,
        db: Session,
        group_id: int
    ) -> bool:
        """删除流分组"""
        try:
            # 检查是否为默认分组
            if group_id == 0:
                raise HTTPException(
                    status_code=403,
                    detail="默认分组不允许删除"
                )
                
            group = await self.get_stream_group(db, group_id)
            
            # 再次检查是否为默认分组（通过名称）
            if group.name == "默认分组":
                raise HTTPException(
                    status_code=403,
                    detail="默认分组不允许删除"
                )
            
            db.delete(group)
            db.commit()
            return True
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"删除分组失败: {str(e)}"
            )
    
    async def add_stream_to_group(
        self,
        db: Session,
        group_id: int,
        stream_id: int
    ) -> StreamGroup:
        """添加流到分组"""
        try:
            group = await self.get_stream_group(db, group_id)
            stream = db.query(Stream).filter(Stream.id == stream_id).first()
            if not stream:
                raise HTTPException(
                    status_code=404,
                    detail="Stream not found"
                )
            
            group.streams.append(stream)
            db.commit()
            db.refresh(group)
            return group
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Add stream to group failed: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def remove_stream_from_group(
        self,
        db: Session,
        group_id: int,
        stream_id: int
    ) -> StreamGroup:
        """从分组移除流"""
        try:
            group = await self.get_stream_group(db, group_id)
            stream = db.query(Stream).filter(Stream.id == stream_id).first()
            if not stream:
                raise HTTPException(
                    status_code=404,
                    detail="Stream not found"
                )
            
            group.streams.remove(stream)
            db.commit()
            db.refresh(group)
            return group
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Remove stream from group failed: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))