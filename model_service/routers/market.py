"""
市场路由
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from model_service.models.schemas import StandardResponse
from model_service.services.market import MarketService
from model_service.services.database import get_db
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter()
market_service = MarketService()

@router.post("/sync", response_model=StandardResponse, summary="同步市场模型")
async def sync_market(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    同步云市场模型
    
    返回:
    - 同步结果
    """
    try:
        result = await market_service.sync_models(db)
        return StandardResponse(
            path=str(request.url),
            data=result
        )
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to sync market: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/models", response_model=StandardResponse)
async def get_market_models(
    request: Request,
    skip: int = 0,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """获取市场模型列表"""
    try:
        models = await market_service.get_models(db, skip, limit)
        return StandardResponse(
            path=str(request.url),
            data=models
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 