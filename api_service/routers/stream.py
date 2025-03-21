"""
视频源路由
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from api_service.models.requests import StreamCreate, StreamUpdate, StreamStatus
from api_service.models.responses import BaseResponse, StreamResponse
from api_service.models.database import Stream  # 添加Stream模型导入
from api_service.services.stream import StreamService
from api_service.services.database import get_db
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/streams", tags=["视频源"])
stream_service = StreamService()  # 创建服务实例

@router.post("", response_model=BaseResponse)
async def create_stream(
    data: StreamCreate,
    db: Session = Depends(get_db)
):
    """创建流"""
    try:
        created_stream = stream_service.create_stream(db, data)
        return BaseResponse(
            code=200,
            message="创建成功",
            data=StreamResponse.from_orm(created_stream).dict()
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Create stream failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@router.get("", response_model=BaseResponse)
async def get_streams(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """获取视频源列表"""
    try:
        # 强制刷新会话
        db.expire_all()
        
        # 获取总数
        total = db.query(Stream).count()
        
        # 获取分页数据
        streams = db.query(Stream).offset(skip).limit(limit).all()
        
        # 添加状态验证日志
        online_count = db.query(Stream).filter(Stream.status == StreamStatus.ONLINE).count()
        offline_count = db.query(Stream).filter(Stream.status == StreamStatus.OFFLINE).count()
        
        logger.info(
            f"视频源状态统计:\n"
            f"- 总数: {total}\n"
            f"- 在线: {online_count}\n"
            f"- 离线: {offline_count}\n"
        )
        
        # 构造响应数据
        stream_list = []
        for stream in streams:
            try:
                stream_data = StreamResponse.from_orm(stream).dict()
                # 添加单个视频源状态日志
                logger.debug(
                    f"视频源 {stream.id} ({stream.name}) "
                    f"状态值: {stream_data['status']}, "
                    f"状态: {'在线' if stream_data['status'] == StreamStatus.ONLINE else '离线'}"
                )
                stream_list.append(stream_data)
            except Exception as e:
                logger.error(f"处理视频源 {stream.id} 数据时出错: {str(e)}")
                # 创建一个带有默认状态的响应
                stream_data = {
                    "id": stream.id,
                    "name": stream.name,
                    "url": stream.url,
                    "description": stream.description,
                    "status": StreamStatus.OFFLINE,  # 默认离线
                    "error_message": str(e),
                    "created_at": stream.created_at,
                    "updated_at": stream.updated_at
                }
                stream_list.append(stream_data)
        
        return BaseResponse(
            code=200,
            message="获取成功",
            data={
                "total": total,
                "items": stream_list
            }
        )
    except Exception as e:
        logger.error(f"获取视频源列表失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@router.get("/{stream_id}", response_model=BaseResponse)
async def get_stream(stream_id: int, db: Session = Depends(get_db)):
    """获取视频源"""
    try:
        result = stream_service.get_stream(db, stream_id)
        if not result:
            raise HTTPException(status_code=404, detail="Stream not found")
        return BaseResponse(
            code=200,
            message="获取成功",
            data=StreamResponse.from_orm(result).dict()
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Get stream failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@router.put("/{stream_id}", response_model=BaseResponse)
async def update_stream(
    stream_id: int,
    request: StreamUpdate,
    db: Session = Depends(get_db)
):
    """更新视频源"""
    try:
        result = stream_service.update_stream(
            db,
            stream_id,
            request
        )
        if not result:
            raise HTTPException(status_code=404, detail="Stream not found")
        return BaseResponse(
            code=200,
            message="更新成功",
            data=StreamResponse.from_orm(result).dict()
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Update stream failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@router.delete("/{stream_id}", response_model=BaseResponse)
async def delete_stream(stream_id: int, db: Session = Depends(get_db)):
    """删除视频源"""
    try:
        success = stream_service.delete_stream(db, stream_id)
        if not success:
            raise HTTPException(status_code=404, detail="Stream not found")
        return BaseResponse(
            code=200,
            message="删除成功"
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Delete stream failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        ) 