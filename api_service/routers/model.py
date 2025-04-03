"""
模型路由模块

提供目标检测模型的管理接口，支持：
- 模型列表：获取所有可用的目标检测模型
- 模型详情：通过ID或代码获取模型详细信息
- 模型同步：自动同步远程模型服务的最新模型数据

本模块支持服务降级，当远程模型服务不可用时，会自动降级使用本地数据。
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from typing import List
from models.responses import BaseResponse, ModelResponse
from services.model import ModelService
from services.database import get_db
from models.database import Model
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/v1/models", tags=["模型"])
model_service = ModelService()

@router.post("/list", response_model=BaseResponse, summary="获取模型列表")
async def get_models(
    request: Request,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    获取模型列表
    
    参数:
    - skip: 跳过的记录数
    - limit: 返回的最大记录数
    
    返回:
    - models: 模型列表，包含所有模型信息（id、code、name、description、path、nc、names、version、author）
    - total: 总记录数
    
    说明:
    - 优先从远程模型服务同步最新数据
    - 如果远程服务不可用或同步失败，将使用本地数据
    """
    try:
        # 如果model_service可用,同步最新数据
        service_available = await model_service.check_model_service()
        if service_available:
            try:
                models = await model_service.sync_models(db)
            except Exception as e:
                logger.error(f"从模型服务同步数据失败: {str(e)}")
                # 如果同步失败，降级使用本地数据
                models = db.query(Model).offset(skip).limit(limit).all()
        else:
            # 服务不可用时使用本地数据
            logger.warning("模型服务不可用，使用本地数据")
            models = db.query(Model).offset(skip).limit(limit).all()
        
        total = db.query(Model).count()    
        
        return BaseResponse(
            path=str(request.url),
            message="获取成功",
            data={
                "total": total,
                "models": [
                    {
                        "id": model.id,
                        "code": model.code,
                        "name": model.name,
                        "description": model.description,
                        "path": model.path,
                        "nc": model.nc,
                        "names": model.names,
                        "version": model.version,
                        "author": model.author,
                        "created_at": model.created_at,
                        "updated_at": model.updated_at
                    } for model in models
                ]
            }
        )
    except Exception as e:
        logger.error(f"获取模型列表失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/detail/code", response_model=BaseResponse, summary="通过代码获取模型")
async def get_model_by_code(
    request: Request,
    code: str,
    db: Session = Depends(get_db)
):
    """
    通过模型代码获取模型详细信息
    
    参数:
    - code: 模型代码，唯一标识一个模型
    
    返回:
    - 模型的详细信息，包括ID、代码、名称、描述、路径、检测类别数量、类别名称映射、版本和作者
    """
    try:
        model = await model_service.get_model_by_code(db, code)
        if not model:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="模型不存在"
            )
            
        return BaseResponse(
            path=str(request.url),
            message="获取成功",
            data={
                "id": model.id,
                "code": model.code,
                "name": model.name,
                "description": model.description,
                "path": model.path,
                "nc": model.nc,
                "names": model.names,
                "version": model.version,
                "author": model.author,
                "created_at": model.created_at,
                "updated_at": model.updated_at
            }
        )
    except Exception as e:
        logger.error(f"通过代码获取模型失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/detail", response_model=BaseResponse, summary="通过ID获取模型")
async def get_model(
    request: Request,
    model_id: int,
    db: Session = Depends(get_db)
):
    """
    通过模型ID获取模型详细信息
    
    参数:
    - model_id: 模型ID
    
    返回:
    - 模型的详细信息，包括ID、代码、名称、描述、路径、检测类别数量、类别名称映射、版本和作者
    """
    try:
        model = await model_service.get_model(db, model_id)
        if not model:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="模型不存在"
            )
            
        return BaseResponse(
            path=str(request.url),
            message="获取成功",
            data={
                "id": model.id,
                "code": model.code,
                "name": model.name,
                "description": model.description,
                "path": model.path,
                "nc": model.nc,
                "names": model.names,
                "version": model.version,
                "author": model.author,
                "created_at": model.created_at,
                "updated_at": model.updated_at
            }
        )
    except Exception as e:
        logger.error(f"通过ID获取模型失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        ) 