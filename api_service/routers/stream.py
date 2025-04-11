"""
视频流路由模块

提供视频流的管理接口，支持：
- 创建视频流：添加新的视频流
- 查询视频流：获取视频流列表和详情
- 更新视频流：修改视频流配置
- 删除视频流：移除不需要的视频流
- 状态管理：控制视频流的启动和停止
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session, joinedload
from typing import Optional
from models.requests import StreamCreate, StreamUpdate, StreamStatus
from models.responses import BaseResponse, StreamResponse
from models.database import Stream
from services.stream.stream import StreamService
from services.core.database import get_db
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/v1/streams", tags=["视频流"])

stream_service = StreamService()

@router.post("/list", response_model=BaseResponse, summary="获取视频流列表")
async def get_streams(
    request: Request,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    获取视频流列表，支持分页查询
    
    参数:
    - skip: 跳过的记录数
    - limit: 返回的最大记录数
    
    返回:
    - total: 总记录数
    - items: 视频流列表
    """
    try:
        # 强制刷新会话
        db.expire_all()
        
        # 获取总数和分页数据
        total = db.query(Stream).count()
        streams = db.query(Stream).options(joinedload(Stream.groups)).offset(skip).limit(limit).all()
        
        # 统计在线状态
        online_count = db.query(Stream).filter(Stream.status == StreamStatus.ONLINE).count()
        offline_count = db.query(Stream).filter(Stream.status == StreamStatus.OFFLINE).count()
        
        logger.info(
            f"视频流状态统计:\n"
            f"- 总数: {total}\n"
            f"- 在线: {online_count}\n"
            f"- 离线: {offline_count}\n"
        )
        
        # 构造响应数据
        stream_list = []
        for stream in streams:
            try:
                stream_data = StreamResponse.from_orm(stream)
                logger.debug(
                    f"视频流 {stream.id} ({stream.name}) "
                    f"状态值: {stream_data.status}, "
                    f"状态: {'在线' if stream_data.status == StreamStatus.ONLINE else '离线'}, "
                    f"分组数: {len(stream_data.groups)}"
                )
                stream_list.append(stream_data.dict())
            except Exception as e:
                logger.error(f"处理视频流 {stream.id} 数据时出错: {str(e)}")
                # 创建一个新的 StreamResponse 对象
                error_response = StreamResponse(
                    id=stream.id,
                    name=stream.name,
                    url=stream.url,
                    description=stream.description,
                    status=StreamStatus.OFFLINE,
                    error_message=str(e),
                    groups=[],
                    created_at=stream.created_at,
                    updated_at=stream.updated_at
                )
                stream_list.append(error_response.dict())
        
        return BaseResponse(
            path=str(request.url),
            message="获取成功",
            data={
                "total": total,
                "items": stream_list
            }
        )
    except Exception as e:
        logger.error(f"获取视频流列表失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/create", response_model=BaseResponse, summary="创建视频流")
async def create_stream(
    request: Request,
    data: StreamCreate,
    db: Session = Depends(get_db)
):
    """
    创建新的视频流
    
    参数:
    - name: 视频流名称
    - url: 视频流地址
    - description: 视频流描述(可选)
    
    返回:
    - 创建的视频流信息
    """
    try:
        created_stream = stream_service.create_stream(db, data)
        return BaseResponse(
            path=str(request.url),
            message="创建成功",
            data=StreamResponse.from_orm(created_stream).dict()
        )
    except Exception as e:
        logger.error(f"创建视频流失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/detail", response_model=BaseResponse, summary="获取视频流详情")
async def get_stream(
    request: Request,
    stream_id: int,
    db: Session = Depends(get_db)
):
    """
    获取指定视频流的详细信息
    
    参数:
    - stream_id: 视频流ID
    
    返回:
    - 视频流详细信息
    """
    try:
        result = stream_service.get_stream(db, stream_id)
        if not result:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="视频流不存在"
            )
        return BaseResponse(
            path=str(request.url),
            message="获取成功",
            data=StreamResponse.from_orm(result).dict()
        )
    except Exception as e:
        logger.error(f"获取视频流详情失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/update", response_model=BaseResponse, summary="更新视频流")
async def update_stream(
    request: Request,
    stream_data: StreamUpdate,
    db: Session = Depends(get_db)
):
    """
    更新指定视频流的信息
    
    参数:
    - id: 视频流ID
    - name: 新的视频流名称(可选)
    - url: 新的视频流地址(可选)
    - description: 新的视频流描述(可选)
    
    返回:
    - 更新后的视频流信息
    """
    try:
        result = stream_service.update_stream(
            db,
            stream_data.id,
            stream_data
        )
        if not result:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="视频流不存在"
            )
        return BaseResponse(
            path=str(request.url),
            message="更新成功",
            data=StreamResponse.from_orm(result).dict()
        )
    except Exception as e:
        logger.error(f"更新视频流失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/delete", response_model=BaseResponse, summary="删除视频流")
async def delete_stream(
    request: Request,
    stream_id: int,
    db: Session = Depends(get_db)
):
    """
    删除指定的视频流
    
    参数:
    - stream_id: 视频流ID
    
    返回:
    - 删除操作的结果
    """
    try:
        success = stream_service.delete_stream(db, stream_id)
        if not success:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="视频流不存在"
            )
        return BaseResponse(
            path=str(request.url),
            message="删除成功"
        )
    except Exception as e:
        logger.error(f"删除视频流失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        ) 