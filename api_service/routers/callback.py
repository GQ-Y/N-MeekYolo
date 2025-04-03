"""
回调路由模块

提供回调配置的管理接口，支持：
- 创建回调：配置新的回调接口
- 查询回调：获取回调配置列表和详情
- 更新回调：修改现有回调配置
- 删除回调：移除不需要的回调配置

回调配置用于在分析任务完成时，将结果推送到指定的接口。
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from models.requests import CallbackCreate, CallbackUpdate, CreateCallbackRequest, UpdateCallbackRequest
from models.responses import BaseResponse
from crud import callback
from services.database import get_db
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/v1/callbacks", tags=["回调"])

@router.post("/create", response_model=BaseResponse, summary="创建回调配置")
async def create_callback(
    request: Request,
    callback_data: CallbackCreate,
    db: Session = Depends(get_db)
):
    """
    创建新的回调配置
    
    参数:
    - name: 回调配置名称
    - url: 回调接口地址
    - headers: 请求头配置(可选)
    - method: 请求方法(GET/POST)
    - body_template: 请求体模板(可选)
    - retry_count: 重试次数(可选，默认3)
    - retry_interval: 重试间隔(秒)(可选，默认1)
    
    返回:
    - 创建的回调配置信息
    """
    try:
        result = callback.create_callback(
            db,
            callback_data.name,
            callback_data.url,
            callback_data.description,
            callback_data.headers,
            callback_data.method,
            callback_data.body_template,
            callback_data.retry_count,
            callback_data.retry_interval
        )
        
        return BaseResponse(
            path=str(request.url),
            message="创建成功",
            data={
                "id": result.id,
                "name": result.name,
                "url": result.url,
                "headers": result.headers,
                "method": result.method,
                "body_template": result.body_template,
                "retry_count": result.retry_count,
                "retry_interval": result.retry_interval,
                "created_at": result.created_at,
                "updated_at": result.updated_at
            }
        )
    except Exception as e:
        logger.error(f"创建回调配置失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/list", response_model=BaseResponse, summary="获取回调配置列表")
async def get_callbacks(
    request: Request,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    获取回调配置列表，支持分页查询
    
    参数:
    - skip: 跳过的记录数
    - limit: 返回的最大记录数
    
    返回:
    - total: 总记录数
    - items: 回调配置列表，包含重试次数和重试间隔设置
    """
    try:
        callbacks = callback.get_callbacks(db, skip, limit)
        return BaseResponse(
            path=str(request.url),
            message="获取成功",
            data={
                "total": len(callbacks),
                "items": [
                    {
                        "id": cb.id,
                        "name": cb.name,
                        "url": cb.url,
                        "headers": cb.headers,
                        "method": cb.method,
                        "body_template": cb.body_template,
                        "retry_count": cb.retry_count,
                        "retry_interval": cb.retry_interval,
                        "created_at": cb.created_at,
                        "updated_at": cb.updated_at
                    } for cb in callbacks
                ]
            }
        )
    except Exception as e:
        logger.error(f"获取回调配置列表失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/detail", response_model=BaseResponse, summary="获取回调配置详情")
async def get_callback(
    request: Request,
    callback_id: int,
    db: Session = Depends(get_db)
):
    """
    获取指定回调配置的详细信息
    
    参数:
    - callback_id: 回调配置ID
    
    返回:
    - 回调配置的详细信息，包含重试次数和重试间隔设置
    """
    try:
        result = callback.get_callback(db, callback_id)
        if not result:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="回调配置不存在"
            )
            
        return BaseResponse(
            path=str(request.url),
            message="获取成功",
            data={
                "id": result.id,
                "name": result.name,
                "url": result.url,
                "headers": result.headers,
                "method": result.method,
                "body_template": result.body_template,
                "retry_count": result.retry_count,
                "retry_interval": result.retry_interval,
                "created_at": result.created_at,
                "updated_at": result.updated_at
            }
        )
    except Exception as e:
        logger.error(f"获取回调配置详情失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/update", response_model=BaseResponse, summary="更新回调配置")
async def update_callback(
    request: Request,
    callback_data: UpdateCallbackRequest,
    db: Session = Depends(get_db)
):
    """
    更新指定回调配置的信息
    
    参数:
    - id: 回调配置ID
    - name: 新的配置名称(可选)
    - url: 新的接口地址(可选)
    - headers: 新的请求头配置(可选)
    - method: 新的请求方法(可选)
    - body_template: 新的请求体模板(可选)
    - retry_count: 新的重试次数(可选)
    - retry_interval: 新的重试间隔(可选)
    
    返回:
    - 更新后的回调配置信息
    """
    try:
        result = callback.update_callback(
            db,
            callback_data.id,
            name=callback_data.name,
            url=callback_data.url,
            headers=callback_data.headers,
            method=callback_data.method,
            body_template=callback_data.body_template,
            retry_count=callback_data.retry_count,
            retry_interval=callback_data.retry_interval
        )
        if not result:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="回调配置不存在"
            )
            
        return BaseResponse(
            path=str(request.url),
            message="更新成功",
            data={
                "id": result.id,
                "name": result.name,
                "url": result.url,
                "headers": result.headers,
                "method": result.method,
                "body_template": result.body_template,
                "retry_count": result.retry_count if hasattr(result, 'retry_count') else None,
                "retry_interval": result.retry_interval if hasattr(result, 'retry_interval') else None,
                "created_at": result.created_at,
                "updated_at": result.updated_at
            }
        )
    except Exception as e:
        logger.error(f"更新回调配置失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/delete", response_model=BaseResponse, summary="删除回调配置")
async def delete_callback(
    request: Request,
    callback_id: int,
    db: Session = Depends(get_db)
):
    """
    删除指定的回调配置
    
    参数:
    - callback_id: 回调配置ID
    
    返回:
    - 删除操作的结果
    """
    try:
        success = callback.delete_callback(db, callback_id)
        if not success:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="回调配置不存在"
            )
        return BaseResponse(
            path=str(request.url),
            message="删除成功"
        )
    except Exception as e:
        logger.error(f"删除回调配置失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        ) 