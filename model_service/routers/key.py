"""
密钥路由
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from model_service.models.schemas import KeyCreate, KeyResponse, BaseResponse
from model_service.services.key import KeyService
from model_service.services.database import get_db
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter()
key_service = KeyService()

@router.post("", response_model=BaseResponse, summary="创建或更新密钥")
async def create_or_update_key(
    data: KeyCreate,
    db: Session = Depends(get_db)
):
    """
    创建或更新云市场API密钥
    
    参数:
    - name: 用户名称
    - phone: 手机号
    - email: 邮箱地址
    
    返回:
    - 密钥信息
    """
    try:
        key = await key_service.create_or_update_key(db, data)
        return BaseResponse(data=KeyResponse.from_orm(key).model_dump())
    except Exception as e:
        logger.error(f"Failed to create/update key: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("", response_model=BaseResponse, summary="获取密钥")
async def get_key(db: Session = Depends(get_db)):
    """
    获取当前密钥
    
    返回:
    - 密钥信息
    """
    try:
        key = await key_service.get_key(db)
        if not key:
            raise HTTPException(status_code=404, detail="No key found")
        return BaseResponse(data=KeyResponse.from_orm(key).model_dump())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get key: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 