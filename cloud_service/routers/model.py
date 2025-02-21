"""
模型路由
"""
from fastapi import (
    APIRouter, 
    Depends, 
    HTTPException, 
    File, 
    UploadFile, 
    Form,
    Header,
    Response
)
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
import yaml
import os
from typing import List, Optional
from cloud_service.models.schemas import (
    BaseResponse,
    CloudModelCreate,
    CloudModelUpdate,
    CloudModelResponse
)
from cloud_service.models.database import CloudModel
from cloud_service.services.model import ModelService
from cloud_service.services.key import KeyService
from cloud_service.services.database import get_db
from cloud_service.core.config import settings
from datetime import datetime
import logging

router = APIRouter(prefix="/models", tags=["模型"])
model_service = ModelService()
key_service = KeyService()
logger = logging.getLogger(__name__)

# 验证API密钥
async def verify_api_key(
    x_api_key: str = Header(..., description="API密钥"),
    db: Session = Depends(get_db)
) -> bool:
    """验证API密钥"""
    if not await key_service.get_key_by_value(db, x_api_key):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    return True

async def validate_model_files(model_file: UploadFile, config_file: UploadFile):
    """验证模型文件"""
    # 检查模型文件扩展名
    if not model_file.filename.endswith('.pt'):
        raise HTTPException(
            status_code=400,
            detail="Model file must be a .pt file"
        )
    
    # 检查配置文件扩展名
    if not config_file.filename.endswith('.yaml'):
        raise HTTPException(
            status_code=400,
            detail="Config file must be a .yaml file"
        )

async def parse_model_config(config_file: UploadFile) -> dict:
    """解析模型配置文件"""
    try:
        config_content = await config_file.read()
        config_data = yaml.safe_load(config_content)
        
        # 验证必要字段
        required_fields = ['code', 'version', 'name', 'description', 'author', 'nc', 'names']
        for field in required_fields:
            if field not in config_data:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required field: {field} in config file"
                )
        
        return config_data
    except yaml.YAMLError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid YAML format: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error parsing config file: {str(e)}"
        )

# 模型管理API
@router.post("", response_model=BaseResponse)
async def create_model(
    model_file: UploadFile = File(..., description="模型文件(.pt)"),
    config_file: UploadFile = File(..., description="配置文件(.yaml)"),
    db: Session = Depends(get_db)
):
    """创建模型
    
    传模型需要提供两个文件：
    1. 模型文件(.pt)
    2. 配置文件(.yaml)
    
    配置文件格式示例：    ```yaml
    code: yolov8n
    version: "1.0"
    name: YOLOv8n
    description: YOLOv8 Nano Model
    author: Ultralytics
    nc: 80
    names:
      0: person
      1: bicycle
      # ...其他类别    ```
    """
    try:
        # 验证文件
        await validate_model_files(model_file, config_file)
        
        # 解析配置文件
        config_data = await parse_model_config(config_file)
        
        # 创建请求对象
        data = CloudModelCreate(**config_data)
        
        # 创建模型
        model = await model_service.create_model(db, model_file, data)
        return BaseResponse(data=CloudModelResponse.from_orm(model).model_dump())
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("", response_model=BaseResponse)
async def get_models(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """获取模型列表"""
    models = await model_service.get_available_models(db, skip, limit)
    return BaseResponse(data={
        "total": len(models),
        "items": [CloudModelResponse.from_orm(m).model_dump() for m in models]
    })

# 其他服务API - 需要API密钥
@router.get("/available", response_model=BaseResponse)
async def get_available_models(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_api_key)
):
    """获取可用模型列表(需要API密钥)"""
    models = await model_service.get_available_models(db, skip, limit)
    return BaseResponse(data={
        "total": len(models),
        "items": [CloudModelResponse.from_orm(m).model_dump() for m in models]
    })

@router.get("/code/{code}", response_model=BaseResponse)
async def get_model_by_code(code: str, db: Session = Depends(get_db)):
    """通过代码获取模型"""
    model = db.query(CloudModel).filter(CloudModel.code == code).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return BaseResponse(data=CloudModelResponse.from_orm(model).model_dump())

@router.get("/{model_id}", response_model=BaseResponse)
async def get_model(model_id: int, db: Session = Depends(get_db)):
    """获取模型详情"""
    model = await model_service.get_model(db, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return BaseResponse(data=CloudModelResponse.from_orm(model).model_dump())

@router.post("/{code}/sync", response_model=BaseResponse)
async def sync_model(
    code: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """同步模型"""
    try:
        # 检查模型是否存在
        model = db.query(CloudModel).filter(CloudModel.code == code).first()
        if not model:
            logger.error(f"Model {code} not found in database")
            raise HTTPException(status_code=404, detail=f"Model {code} not found")
        
        logger.info(f"Found model: {model.code} ({model.name})")
        
        # 构建下载URL
        download_url = f"{settings.SERVICE.base_url}/api/v1/models/{code}/download"
        logger.info(f"Model download URL: {download_url}")
        
        # 返回同步结果
        return BaseResponse(
            message="Model synced successfully",
            data={
                "code": code,
                "name": model.name,
                "version": model.version,
                "download_url": download_url,
                "synced_at": datetime.now().isoformat()
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to sync model: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{code}/download", response_class=FileResponse)
async def download_model(
    code: str,
    db: Session = Depends(get_db)
):
    """下载模型文件"""
    try:
        # 检查模型是否存在
        model = db.query(CloudModel).filter(CloudModel.code == code).first()
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")
        
        # 构建文件路径
        file_path = os.path.join(settings.STORAGE.base_dir, code, "best.pt")
        
        logger.info(f"Downloading model from: {file_path}")
        
        if not os.path.exists(file_path):
            logger.error(f"Model file not found: {file_path}")
            raise HTTPException(status_code=404, detail="Model file not found")
        
        return FileResponse(
            file_path,
            filename=f"{code}.pt",
            media_type="application/octet-stream"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download model: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 