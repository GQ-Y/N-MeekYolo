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
    Response,
    Query,
    Request
)
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
import yaml
import os
from typing import List, Optional
from models.schemas import (
    StandardResponse,
    CloudModelCreate,
    CloudModelUpdate,
    CloudModelResponse
)
from models.database import CloudModel
from services.model import ModelService
from services.key import KeyService
from services.database import get_db
from core.config import settings
from datetime import datetime
from shared.utils.logger import setup_logger
from uuid import uuid4
import io
import zipfile

router = APIRouter(prefix="/models", tags=["模型"])
model_service = ModelService()
key_service = KeyService()
logger = setup_logger(__name__)

# 验证API密钥
async def verify_api_key(
    x_api_key: str = Header(..., description="API密钥"),
    db: Session = Depends(get_db)
) -> bool:
    """验证API密钥"""
    try:
        if not await key_service.get_key_by_value(db, x_api_key):
            raise HTTPException(
                status_code=401,
                detail="无效的API密钥"
            )
        return True
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"验证API密钥失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="验证API密钥时发生错误"
        )

async def validate_model_files(model_file: UploadFile, config_file: UploadFile):
    """验证模型文件"""
    try:
        # 检查模型文件扩展名
        if not model_file.filename.endswith('.pt'):
            raise HTTPException(
                status_code=400,
                detail="模型文件必须是.pt格式"
            )
        
        # 检查配置文件扩展名
        if not config_file.filename.endswith('.yaml'):
            raise HTTPException(
                status_code=400,
                detail="配置文件必须是.yaml格式"
            )
    except Exception as e:
        logger.error(f"验证模型文件失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="验证模型文件时发生错误"
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
                    detail=f"配置文件缺少必要字段: {field}"
                )
        
        return config_data
    except yaml.YAMLError as e:
        logger.error(f"解析YAML文件失败: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"无效的YAML格式: {str(e)}"
        )
    except Exception as e:
        logger.error(f"解析配置文件失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"解析配置文件时发生错误: {str(e)}"
        )

# 模型管理API
@router.post("", response_model=StandardResponse)
async def create_model(
    request: Request,
    model_file: UploadFile = File(..., description="模型文件(.pt)"),
    config_file: UploadFile = File(..., description="配置文件(.yaml)"),
    db: Session = Depends(get_db)
):
    """
    创建模型
    
    参数：
    - model_file: 模型文件(.pt格式)
    - config_file: 配置文件(.yaml格式)
    
    配置文件格式示例：
    ```yaml
    code: yolov8n
    version: "1.0"
    name: YOLOv8n
    description: YOLOv8 Nano Model
    author: Ultralytics
    nc: 80
    names:
      0: person
      1: bicycle
      # ...其他类别
    ```
    
    返回：
    - 创建成功的模型信息
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
        return StandardResponse(
            requestId=str(uuid4()),
            path=str(request.url),
            message="模型创建成功",
            data=CloudModelResponse.from_orm(model).model_dump()
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建模型失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("", response_model=StandardResponse)
async def get_models(
    request: Request,
    skip: int = Query(0, description="分页起始位置", ge=0),
    limit: int = Query(100, description="每页数量", gt=0, le=1000),
    db: Session = Depends(get_db)
):
    """
    获取模型列表
    
    参数：
    - skip: 分页起始位置，必须大于等于0
    - limit: 每页数量，必须大于0且小于等于1000
    
    返回：
    - 模型列表及总数
    """
    try:
        models = await model_service.get_available_models(db, skip, limit)
        return StandardResponse(
            requestId=str(uuid4()),
            path=str(request.url),
            data={
                "total": len(models),
                "items": [CloudModelResponse.from_orm(m).model_dump() for m in models]
            }
        )
    except Exception as e:
        logger.error(f"获取模型列表失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="获取模型列表失败"
        )

@router.get("/available", response_model=StandardResponse)
async def get_available_models(
    request: Request,
    skip: int = Query(0, description="分页起始位置", ge=0),
    limit: int = Query(100, description="每页数量", gt=0, le=1000),
    db: Session = Depends(get_db),
    _: bool = Depends(verify_api_key)
):
    """
    获取可用模型列表(需要API密钥)
    
    参数：
    - skip: 分页起始位置，必须大于等于0
    - limit: 每页数量，必须大于0且小于等于1000
    
    返回：
    - 可用模型列表及总数
    """
    try:
        models = await model_service.get_available_models(db, skip, limit)
        return StandardResponse(
            requestId=str(uuid4()),
            path=str(request.url),
            data={
                "total": len(models),
                "items": [CloudModelResponse.from_orm(m).model_dump() for m in models]
            }
        )
    except Exception as e:
        logger.error(f"获取可用模型列表失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="获取可用模型列表失败"
        )

@router.get("/detail", response_model=StandardResponse)
async def get_model_by_code(
    request: Request,
    code: str = Query(..., description="模型代码", min_length=1),
    db: Session = Depends(get_db)
):
    """
    通过代码获取模型
    
    参数：
    - code: 模型代码，不能为空
    
    返回：
    - 模型详细信息
    """
    try:
        model = db.query(CloudModel).filter(CloudModel.code == code).first()
        if not model:
            raise HTTPException(status_code=404, detail="模型不存在")
        return StandardResponse(
            requestId=str(uuid4()),
            path=str(request.url),
            data=CloudModelResponse.from_orm(model).model_dump()
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取模型失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="获取模型失败"
        )

@router.get("/info", response_model=StandardResponse)
async def get_model(
    request: Request,
    model_id: int = Query(..., description="模型ID", gt=0),
    db: Session = Depends(get_db)
):
    """
    获取模型详情
    
    参数：
    - model_id: 模型ID，必须大于0
    
    返回：
    - 模型详细信息
    """
    try:
        model = await model_service.get_model(db, model_id)
        if not model:
            raise HTTPException(status_code=404, detail="模型不存在")
        return StandardResponse(
            requestId=str(uuid4()),
            path=str(request.url),
            data=CloudModelResponse.from_orm(model).model_dump()
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取模型详情失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="获取模型详情失败"
        )

@router.post("/sync", response_model=StandardResponse)
async def sync_model(
    request: Request,
    code: str = Query(..., description="模型代码", min_length=1),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """
    同步模型
    
    参数：
    - code: 模型代码，不能为空
    
    返回：
    - 同步结果，包含下载URL
    """
    try:
        # 检查模型是否存在
        model = db.query(CloudModel).filter(CloudModel.code == code).first()
        if not model:
            logger.error(f"模型不存在: {code}")
            raise HTTPException(status_code=404, detail=f"模型 {code} 不存在")
        
        logger.info(f"找到模型: {model.code} ({model.name})")
        
        # 构建下载URL
        download_url = f"{settings.SERVICE.base_url}/api/v1/models/download?code={code}"
        logger.info(f"模型下载URL: {download_url}")
        
        # 返回同步结果
        return StandardResponse(
            requestId=str(uuid4()),
            path=str(request.url),
            message="模型同步成功",
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
        logger.error(f"同步模型失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"同步模型失败: {str(e)}"
        )

@router.get("/download", response_class=FileResponse)
async def download_model(
    request: Request,
    code: str = Query(..., description="模型代码", min_length=1),
    db: Session = Depends(get_db)
):
    """
    下载模型文件
    
    参数：
    - code: 模型代码，不能为空
    
    返回：
    - 包含模型文件(.pt)和配置文件(.yaml)的zip压缩包
    """
    try:
        logger.info(f"开始处理模型下载请求: {code}")
        
        # 检查模型是否存在
        model = db.query(CloudModel).filter(CloudModel.code == code).first()
        if not model:
            logger.error(f"模型未找到: {code}")
            raise HTTPException(status_code=404, detail="模型不存在")
        
        logger.info(f"找到模型: {model.code} (版本: {model.version})")
        
        # 获取zip文件路径
        zip_path = model.file_path
        logger.info(f"模型zip文件路径: {zip_path}")
        
        if not os.path.exists(zip_path):
            logger.error(f"模型zip文件不存在: {zip_path}")
            raise HTTPException(status_code=404, detail="模型文件不存在")
        
        logger.info(f"准备返回zip文件: {zip_path}")
        
        return FileResponse(
            zip_path,
            media_type="application/zip",
            filename=f"{model.code}_v{model.version}.zip"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"下载模型失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"下载模型失败: {str(e)}"
        ) 