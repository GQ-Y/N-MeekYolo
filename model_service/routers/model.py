"""
模型路由
"""
import os
import yaml
from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from typing import Optional
from model_service.models.requests import ModelUploadRequest
from model_service.models.responses import BaseResponse
from model_service.services.model import ModelService
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/models", tags=["模型"])

@router.post("/upload", response_model=BaseResponse)
async def upload_model(
    model_file: UploadFile = File(...),
    code: str = Form(...),
    version: str = Form(...),
    name: str = Form(...),
    description: str = Form(...),
    author: str = Form(...),
    nc: int = Form(...),
    names: str = Form(...)  # 类别名称映射，JSON字符串
):
    """上传模型"""
    try:
        # 解析类别名称映射
        import json
        names_dict = json.loads(names)
        
        # 创建请求对象
        request = ModelUploadRequest(
            code=code,
            version=version,
            name=name,
            description=description,
            author=author,
            nc=nc,
            names=names_dict
        )
        
        # 保存模型文件
        model_service = ModelService()
        model_dir = await model_service.save_model(model_file, request.code)
        
        # 生成data.yaml配置文件
        config = {
            "code": request.code,
            "version": request.version,
            "name": request.name,
            "description": request.description,
            "author": request.author,
            "create_time": datetime.utcnow().isoformat(),
            "update_time": datetime.utcnow().isoformat(),
            "path": "",
            "train": "images/train",
            "val": "images/val",
            "nc": request.nc,
            "names": request.names
        }
        
        # 保存配置文件
        config_path = os.path.join(model_dir, "data.yaml")
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, allow_unicode=True)
        
        return BaseResponse(
            message="Model uploaded successfully",
            data={
                "code": request.code,
                "path": model_dir
            }
        )
    except Exception as e:
        logger.error(f"Upload model failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 