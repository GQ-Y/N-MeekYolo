"""
模型路由
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from api_service.models.responses import BaseResponse, ModelResponse
from api_service.services.model import ModelService
from api_service.services.database import get_db
from api_service.models.database import Model
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/v1/model", tags=["模型"])
model_service = ModelService()

@router.post("/list", response_model=BaseResponse)
async def get_models(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """获取模型列表"""
    try:
        # 如果model_service可用,同步最新数据
        service_available = await model_service.check_model_service()
        if service_available:
            try:
                models = await model_service.sync_models(db)
            except Exception as e:
                logger.error(f"Failed to sync models from model service: {str(e)}")
                # 如果同步失败，降级使用本地数据
                models = db.query(Model).offset(skip).limit(limit).all()
        else:
            # 服务不可用时使用本地数据
            logger.warning("Model service is not available, using local data")
            models = db.query(Model).offset(skip).limit(limit).all()
            
        return BaseResponse(
            data={
                "total": len(models),
                "items": [
                    {
                        "id": model.id,
                        "code": model.code,
                        "name": model.name,
                        "description": model.description,
                        "path": model.path
                    } for model in models
                ]
            }
        )
    except Exception as e:
        logger.error(f"Get models failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/detail/code", response_model=BaseResponse)
async def get_model_by_code(
    code: str,
    db: Session = Depends(get_db)
):
    """通过代码获取模型"""
    try:
        model = await model_service.get_model_by_code(db, code)
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")
            
        return BaseResponse(
            data={
                "id": model.id,
                "code": model.code,
                "name": model.name,
                "description": model.description,
                "path": model.path
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get model by code failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/detail", response_model=BaseResponse)
async def get_model(
    model_id: int,
    db: Session = Depends(get_db)
):
    """通过ID获取模型"""
    try:
        model = await model_service.get_model(db, model_id)
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")
            
        return BaseResponse(
            data={
                "id": model.id,
                "code": model.code,
                "name": model.name,
                "description": model.description,
                "path": model.path
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get model failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 