"""
流分组路由
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from api_service.models.responses import BaseResponse, StreamGroupResponse
from api_service.models.requests import StreamGroupCreate, StreamGroupUpdate
from api_service.services.stream_group import StreamGroupService
from api_service.services.database import get_db
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/stream-groups", tags=["流分组"])
stream_group_service = StreamGroupService()

@router.post("", response_model=BaseResponse)
async def create_stream_group(
    data: StreamGroupCreate,
    db: Session = Depends(get_db)
):
    """创建流分组"""
    try:
        group = await stream_group_service.create_stream_group(db, data)
        
        # 添加详细日志
        logger.info(f"Successfully created stream group: {group.name}")
        
        # 构造响应数据
        response_data = {
            "id": group.id,
            "name": group.name,
            "description": group.description,
            "created_at": group.created_at,
            "updated_at": group.updated_at
        }
        
        return BaseResponse(
            code=200,
            message="创建成功",
            data=response_data
        )
    except HTTPException as e:
        logger.error(f"Business error in create stream group: {e.detail}")
        return BaseResponse(
            code=e.status_code,
            message=e.detail,
            data=None
        )
    except Exception as e:
        logger.error(f"Create stream group failed: {str(e)}", exc_info=True)
        return BaseResponse(
            code=500,
            message=f"创建失败: {str(e)}",
            data=None
        )

@router.get("", response_model=List[StreamGroupResponse])
async def get_stream_groups(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """获取流分组列表"""
    try:
        groups = await stream_group_service.get_stream_groups(db, skip=skip, limit=limit)
        
        response_data = []
        for group in groups:
            stream_ids = []
            if group.streams:
                stream_ids = [str(stream.id) for stream in group.streams]
                
            group_dict = {
                "id": str(group.id),
                "name": group.name,
                "description": group.description,
                "streams": stream_ids,
                "created_at": group.created_at,
                "updated_at": group.updated_at
            }
            
            logger.debug(f"Converting group to dict: {group_dict}")
            response_data.append(StreamGroupResponse(**group_dict))
            
        return response_data

    except Exception as e:
        logger.error(f"Get stream groups failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"获取失败: {str(e)}"
        ) 