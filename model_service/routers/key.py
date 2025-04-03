"""
密钥路由
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Body
from sqlalchemy.orm import Session
from models.schemas import StandardResponse, KeyCreate, KeyResponse, KeyUpdate
from services.key import KeyService
from services.database import get_db
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter()
key_service = KeyService()

@router.post("", response_model=StandardResponse)
async def create_key(
    request: Request,
    key_data: KeyCreate,
    db: Session = Depends(get_db)
):
    """
    注册密钥
    
    参数：
    - name: 密钥名称，不能为空
    - phone: 手机号，11位数字
    - email: 邮箱地址
    
    返回：
    - 注册的密钥信息
    """
    try:
        key = await key_service.create_key(db, key_data)
        return StandardResponse(
            path=str(request.url),
            message="密钥注册成功",
            data=KeyResponse.model_validate(key)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"注册密钥失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/current", response_model=StandardResponse)
async def get_current_key(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    获取当前密钥
    
    返回：
    - 当前密钥信息
    """
    try:
        key = await key_service.get_key(db)
        if not key:
            raise HTTPException(status_code=404, detail="未找到有效的密钥")
        return StandardResponse(
            path=str(request.url),
            data=KeyResponse.model_validate(key)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取当前密钥失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("", response_model=StandardResponse)
async def update_key(
    request: Request,
    key_data: KeyUpdate,
    db: Session = Depends(get_db)
):
    """
    更新密钥信息
    
    参数：
    - name: 密钥名称（可选）
    - phone: 手机号，11位数字（可选）
    - email: 邮箱地址（可选）
    - status: 密钥状态（可选）
    
    返回：
    - 更新后的密钥信息
    """
    try:
        key = await key_service.update_key(db, key_data)
        return StandardResponse(
            path=str(request.url),
            message="密钥更新成功",
            data=KeyResponse.model_validate(key)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新密钥失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 