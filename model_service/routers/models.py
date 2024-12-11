"""
模型路由
处理模型管理相关的请求
"""
from fastapi import APIRouter, File, UploadFile, Form, HTTPException, Depends
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from shared.utils.logger import setup_logger
from model_service.models.models import ModelInfo
from model_service.models.schemas import BaseResponse, ModelResponse, ModelListResponse
from model_service.manager.model_manager import ModelManager
from model_service.services.model import ModelService
from model_service.services.database import get_db

logger = setup_logger(__name__)
router = APIRouter()
model_manager = ModelManager()
model_service = ModelService()

@router.post("/upload", response_model=ModelResponse)
async def upload_model(
    files: List[UploadFile] = File(...),
    name: str = Form(...),
    code: str = Form(...),
    version: str = Form("1.0.0"),
    author: str = Form(""),
    description: str = Form("")
):
    """上传模型文件"""
    try:
        model_info = ModelInfo(
            name=name,
            code=code,
            version=version,
            author=author,
            description=description
        )
        result = await model_manager.upload_model(files, model_info)
        return ModelResponse(data=model_info)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"模型上传失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/list", response_model=ModelListResponse)
async def list_models(skip: int = 0, limit: int = 10):
    """获取模型列表"""
    try:
        models = await model_manager.list_models(skip, limit)
        return ModelListResponse(data=models)
    except Exception as e:
        logger.error(f"获取模型列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{model_code}", response_model=ModelResponse)
async def get_model(model_code: str):
    """获取模型信息"""
    try:
        model = await model_manager.get_model_info(model_code)
        if not model:
            raise HTTPException(status_code=404, detail=f"模型不存在: {model_code}")
        return ModelResponse(data=model)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取模型信息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{model_code}", response_model=BaseResponse)
async def delete_model(model_code: str):
    """删除模型"""
    try:
        result = await model_manager.delete_model(model_code)
        if not result:
            raise HTTPException(status_code=404, detail=f"模型不存在: {model_code}")
        return BaseResponse(
            message="模型已删除",
            data={"code": model_code}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除模型失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{model_code}/sync", response_model=BaseResponse, summary="同步模型")
async def sync_model(
    model_code: str,
    db: Session = Depends(get_db)
):
    """
    从云市场同步模型
    
    参数:
    - model_code: 模型代码
    
    返回:
    - 同步结果
    """
    try:
        result = await model_service.sync_model(db, model_code)
        return BaseResponse(data=result)
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to sync model: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))