"""
市场路由
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Query, Body
from sqlalchemy.orm import Session
from model_service.models.schemas import StandardResponse
from model_service.services.market import MarketService
from model_service.services.database import get_db
from shared.utils.logger import setup_logger
from typing import Optional
from pydantic import BaseModel
import json

logger = setup_logger(__name__)

router = APIRouter(
    prefix="/sync",  # 只定义子路径，让 app.py 管理完整前缀
    tags=["模型市场"]  # 使用中文标签，与 app.py 中的注册保持一致
)
market_service = MarketService()

class ModelSyncRequest(BaseModel):
    """模型同步请求"""
    model_code: str

@router.post("/sync")
async def sync_market(
    request: Request,
    code: Optional[str] = Query(None, description="模型代码（查询参数）"),
    body: Optional[ModelSyncRequest] = Body(None, description="请求体参数"),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """
    同步指定的模型
    
    参数：
    - code: 模型代码（查询参数）
    - body: 请求体参数，包含model_code
    
    返回：
    - 同步结果
    """
    try:
        
        # 优先使用查询参数中的code，如果没有则使用请求体中的model_code
        final_code = code
        if not final_code and body:
            final_code = body.model_code
            logger.info(f"使用请求体中的model_code: {final_code}")
        elif final_code:
            logger.info(f"使用查询参数中的code: {final_code}")
            
        if not final_code:
            error_msg = "请提供模型代码，可以通过查询参数code或请求体model_code提供"
            logger.error(error_msg)
            return StandardResponse(
                code=400,
                path=str(request.url),
                message=error_msg,
                data=None
            )
        
        # 调用服务执行同步
        result = await market_service.sync_model(db, final_code)
        
        # 返回成功响应
        response = StandardResponse(
            code=200,
            path=str(request.url),
            message=result.get("message", "同步成功"),
            data=result
        )
        return response
        
    except HTTPException as e:
        # 返回HTTP异常响应
        error_response = StandardResponse(
            code=e.status_code,
            path=str(request.url),
            message=str(e.detail),
            data=None
        )
        return error_response
        
    except Exception as e:
        # 返回未预期的异常响应
        error_msg = f"同步失败: {str(e)}"
        error_response = StandardResponse(
            code=500,
            path=str(request.url),
            message=error_msg,
            data=None
        )
        return error_response

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
            code=200,
            path=str(request.url),
            message="获取模型列表成功",
            data=models
        )
    except Exception as e:
        return StandardResponse(
            code=500,
            path=str(request.url),
            message=str(e),
            data=None
        ) 