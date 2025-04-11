"""
视频流分组路由模块

提供视频流分组的管理接口，支持：
- 创建分组：创建新的视频流分组
- 查询分组：获取分组列表和详情
- 更新分组：修改分组信息
- 删除分组：移除不需要的分组
- 分组管理：添加或移除分组中的视频流
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from typing import Optional
from models.requests import StreamGroupCreate, StreamGroupUpdate
from models.responses import BaseResponse
from services.stream.stream_group import StreamGroupService
from services.core.database import get_db
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/v1/stream-groups", tags=["视频流分组"])

stream_group_service = StreamGroupService()

@router.post("/list", response_model=BaseResponse, summary="获取视频流分组列表")
async def get_stream_groups(
    request: Request,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    获取视频流分组列表，支持分页查询
    
    参数:
    - skip: 跳过的记录数
    - limit: 返回的最大记录数
    
    返回:
    - total: 总记录数
    - items: 分组列表，包含每个分组的基本信息和关联的视频流数量
    """
    try:
        groups = await stream_group_service.get_stream_groups(db, skip, limit)
        return BaseResponse(
            path=str(request.url),
            message="获取成功",
            data={
                "total": len(groups),
                "items": [
                    {
                        "id": group.id,
                        "name": group.name,
                        "description": group.description,
                        "cameras": [
                            {
                                "id": stream.id,
                                "name": stream.name,
                                "url": stream.url,
                                "status": stream.status,
                                "error_message": stream.error_message
                            } for stream in group.streams
                        ],
                        "created_at": group.created_at,
                        "updated_at": group.updated_at
                    } for group in groups
                ]
            }
        )
    except Exception as e:
        logger.error(f"获取视频流分组列表失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/create", response_model=BaseResponse, summary="创建视频流分组")
async def create_stream_group(
    request: Request,
    group_data: StreamGroupCreate,
    db: Session = Depends(get_db)
):
    """
    创建新的视频流分组
    
    参数:
    - name: 分组名称
    - description: 分组描述(可选)
    
    返回:
    - 创建的分组信息
    """
    try:
        result = await stream_group_service.create_stream_group(db, group_data)
        return BaseResponse(
            path=str(request.url),
            message="创建成功",
            data={
                "id": result.id,
                "name": result.name,
                "description": result.description,
                "created_at": result.created_at,
                "updated_at": result.updated_at
            }
        )
    except Exception as e:
        logger.error(f"创建视频流分组失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/detail", response_model=BaseResponse, summary="获取视频流分组详情")
async def get_stream_group(
    request: Request,
    group_id: int,
    db: Session = Depends(get_db)
):
    """
    获取指定视频流分组的详细信息
    
    参数:
    - group_id: 分组ID
    
    返回:
    - 分组详细信息，包含关联的视频流列表
    """
    try:
        result = await stream_group_service.get_stream_group(db, group_id)
        if not result:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="分组不存在"
            )
            
        return BaseResponse(
            path=str(request.url),
            message="获取成功",
            data={
                "id": result.id,
                "name": result.name,
                "description": result.description,
                "streams": [
                    {
                        "id": stream.id,
                        "name": stream.name,
                        "url": stream.url,
                        "status": stream.status
                    } for stream in result.streams
                ],
                "created_at": result.created_at,
                "updated_at": result.updated_at
            }
        )
    except Exception as e:
        logger.error(f"获取视频流分组详情失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/update", response_model=BaseResponse, summary="更新视频流分组")
async def update_stream_group(
    request: Request,
    group_data: StreamGroupUpdate,
    db: Session = Depends(get_db)
):
    """
    更新指定视频流分组的信息
    
    参数:
    - id: 分组ID
    - name: 新的分组名称(可选)
    - description: 新的分组描述(可选)
    
    返回:
    - 更新后的分组信息
    """
    try:
        result = await stream_group_service.update_stream_group(
            db,
            group_data.id,  # 从请求体中获取分组ID
            group_data
        )
        if not result:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="分组不存在"
            )
            
        return BaseResponse(
            path=str(request.url),
            message="更新成功",
            data={
                "id": result.id,
                "name": result.name,
                "description": result.description,
                "created_at": result.created_at,
                "updated_at": result.updated_at
            }
        )
    except Exception as e:
        logger.error(f"更新视频流分组失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/delete", response_model=BaseResponse, summary="删除视频流分组")
async def delete_stream_group(
    request: Request,
    group_id: int,
    db: Session = Depends(get_db)
):
    """
    删除指定的视频流分组
    
    参数:
    - group_id: 分组ID
    
    返回:
    - 删除操作的结果
    """
    try:
        success = await stream_group_service.delete_stream_group(db, group_id)
        if not success:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="分组不存在"
            )
        return BaseResponse(
            path=str(request.url),
            message="删除成功"
        )
    except Exception as e:
        logger.error(f"删除视频流分组失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/streams/add", response_model=BaseResponse, summary="添加视频流到分组")
async def add_stream_to_group(
    request: Request,
    group_id: int,
    stream_id: int,
    db: Session = Depends(get_db)
):
    """
    向指定分组添加视频流
    
    参数:
    - group_id: 分组ID
    - stream_id: 视频流ID
    
    返回:
    - 操作结果
    """
    try:
        result = await stream_group_service.add_stream_to_group(db, group_id, stream_id)
        if not result:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="分组或视频流不存在"
            )
        return BaseResponse(
            path=str(request.url),
            message="添加成功"
        )
    except Exception as e:
        logger.error(f"添加视频流到分组失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/streams/remove", response_model=BaseResponse, summary="从分组移除视频流")
async def remove_stream_from_group(
    request: Request,
    group_id: int,
    stream_id: int,
    db: Session = Depends(get_db)
):
    """
    从指定分组移除视频流
    
    参数:
    - group_id: 分组ID
    - stream_id: 视频流ID
    
    返回:
    - 操作结果
    """
    try:
        success = await stream_group_service.remove_stream_from_group(db, group_id, stream_id)
        if not success:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="分组或视频流不存在"
            )
        return BaseResponse(
            path=str(request.url),
            message="移除成功"
        )
    except Exception as e:
        logger.error(f"从分组移除视频流失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        ) 