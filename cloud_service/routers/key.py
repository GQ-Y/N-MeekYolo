"""
API密钥路由
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from cloud_service.models.schemas import (
    StandardResponse,
    ApiKeyCreate,
    ApiKeyUpdate,
    ApiKeyResponse
)
from cloud_service.services.key import KeyService
from cloud_service.services.database import get_db
from shared.utils.logger import setup_logger
from uuid import uuid4

logger = setup_logger(__name__)
router = APIRouter(prefix="/keys", tags=["API密钥"])
key_service = KeyService()

@router.post("", response_model=StandardResponse)
async def create_key(
    request: Request,
    data: ApiKeyCreate = Depends(),
    db: Session = Depends(get_db)
):
    """
    创建API密钥
    
    参数：
    - data: API密钥创建参数
        - name: 密钥名称
        - description: 密钥描述
        - expires_at: 过期时间
    
    返回：
    - 创建成功的API密钥信息
    """
    try:
        key = await key_service.create_key(db, data)
        return StandardResponse(
            requestId=str(uuid4()),
            path=str(request.url),
            message="API密钥创建成功",
            data=ApiKeyResponse.from_orm(key).model_dump()
        )
    except Exception as e:
        logger.error(f"创建API密钥失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("", response_model=StandardResponse)
async def get_key(
    request: Request,
    key_id: int = Query(..., description="API密钥ID", gt=0),
    db: Session = Depends(get_db)
):
    """
    获取API密钥
    
    参数：
    - key_id: API密钥ID，必须大于0
    
    返回：
    - API密钥详细信息
    """
    key = await key_service.get_key(db, key_id)
    if not key:
        raise HTTPException(status_code=404, detail="API密钥不存在")
    return StandardResponse(
        requestId=str(uuid4()),
        path=str(request.url),
        data=ApiKeyResponse.from_orm(key).model_dump()
    )

@router.put("", response_model=StandardResponse)
async def update_key(
    request: Request,
    key_id: int = Query(..., description="API密钥ID", gt=0),
    data: ApiKeyUpdate = Depends(),
    db: Session = Depends(get_db)
):
    """
    更新API密钥
    
    参数：
    - key_id: API密钥ID，必须大于0
    - data: API密钥更新参数
        - name: 密钥名称
        - description: 密钥描述
        - expires_at: 过期时间
    
    返回：
    - 更新后的API密钥信息
    """
    try:
        key = await key_service.update_key(db, key_id, data)
        if not key:
            raise HTTPException(status_code=404, detail="API密钥不存在")
        return StandardResponse(
            requestId=str(uuid4()),
            path=str(request.url),
            message="API密钥更新成功",
            data=ApiKeyResponse.from_orm(key).model_dump()
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新API密钥失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("", response_model=StandardResponse)
async def delete_key(
    request: Request,
    key_id: int = Query(..., description="API密钥ID", gt=0),
    db: Session = Depends(get_db)
):
    """
    删除API密钥
    
    参数：
    - key_id: API密钥ID，必须大于0
    
    返回：
    - 删除结果
    """
    try:
        if not await key_service.delete_key(db, key_id):
            raise HTTPException(status_code=404, detail="API密钥不存在")
        return StandardResponse(
            requestId=str(uuid4()),
            path=str(request.url),
            message="API密钥删除成功"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除API密钥失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 