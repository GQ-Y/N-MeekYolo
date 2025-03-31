"""
密钥路由
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Body, Query
from sqlalchemy.orm import Session
from model_service.models.schemas import StandardResponse, KeyCreate, KeyResponse, KeyUpdate
from model_service.services.key import KeyService
from model_service.services.database import get_db
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
    创建密钥
    
    参数：
    - name: 密钥名称，不能为空
    - phone: 手机号，11位数字
    - email: 邮箱地址
    
    返回：
    - 创建的密钥信息
    """
    try:
        key = await key_service.create_key(db, key_data)
        return StandardResponse(
            path=str(request.url),
            message="密钥创建成功",
            data=KeyResponse.model_validate(key)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建密钥失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("", response_model=StandardResponse)
async def get_keys(
    request: Request,
    skip: int = Query(0, ge=0, description="跳过的记录数，用于分页"),
    limit: int = Query(10, gt=0, le=100, description="返回的记录数，用于分页"),
    db: Session = Depends(get_db)
):
    """
    获取密钥列表
    
    参数：
    - skip: 跳过的记录数，用于分页，必须大于等于0
    - limit: 返回的记录数，用于分页，必须大于0且小于等于100
    
    返回：
    - 密钥列表
    """
    try:
        keys = await key_service.get_keys(db, skip, limit)
        return StandardResponse(
            path=str(request.url),
            data=[KeyResponse.model_validate(key) for key in keys]
        )
    except Exception as e:
        logger.error(f"获取密钥列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/detail", response_model=StandardResponse)
async def get_key(
    request: Request,
    key_id: int = Query(..., gt=0, description="密钥ID"),
    db: Session = Depends(get_db)
):
    """
    获取密钥详情
    
    参数：
    - key_id: 密钥ID，必须大于0
    
    返回：
    - 密钥详细信息
    """
    try:
        key = await key_service.get_key(db, key_id)
        if not key:
            raise HTTPException(status_code=404, detail=f"密钥不存在: {key_id}")
        return StandardResponse(
            path=str(request.url),
            data=KeyResponse.model_validate(key)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取密钥详情失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("", response_model=StandardResponse)
async def delete_key(
    request: Request,
    key_id: int = Query(..., gt=0, description="要删除的密钥ID"),
    db: Session = Depends(get_db)
):
    """
    删除密钥
    
    参数：
    - key_id: 要删除的密钥ID，必须大于0
    
    返回：
    - 删除结果
    """
    try:
        result = await key_service.delete_key(db, key_id)
        if not result:
            raise HTTPException(status_code=404, detail=f"密钥不存在: {key_id}")
        return StandardResponse(
            path=str(request.url),
            message="密钥删除成功",
            data={"id": key_id}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除密钥失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 