"""
API密钥路由
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from cloud_service.models.schemas import (
    BaseResponse,
    ApiKeyCreate,
    ApiKeyUpdate,
    ApiKeyResponse
)
from cloud_service.services.key import KeyService
from cloud_service.services.database import get_db

router = APIRouter(prefix="/keys", tags=["API密钥"])
key_service = KeyService()

@router.post("", response_model=BaseResponse)
async def create_key(
    data: ApiKeyCreate,
    db: Session = Depends(get_db)
):
    """创建API密钥"""
    try:
        key = await key_service.create_key(db, data)
        return BaseResponse(data=ApiKeyResponse.from_orm(key).model_dump())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{key_id}", response_model=BaseResponse)
async def get_key(key_id: int, db: Session = Depends(get_db)):
    """获取API密钥"""
    key = await key_service.get_key(db, key_id)
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    return BaseResponse(data=ApiKeyResponse.from_orm(key).model_dump())

@router.put("/{key_id}", response_model=BaseResponse)
async def update_key(
    key_id: int,
    data: ApiKeyUpdate,
    db: Session = Depends(get_db)
):
    """更新API密钥"""
    key = await key_service.update_key(db, key_id, data)
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    return BaseResponse(data=ApiKeyResponse.from_orm(key).model_dump())

@router.delete("/{key_id}", response_model=BaseResponse)
async def delete_key(key_id: int, db: Session = Depends(get_db)):
    """删除API密钥"""
    if not await key_service.delete_key(db, key_id):
        raise HTTPException(status_code=404, detail="API key not found")
    return BaseResponse(message="API key deleted successfully") 