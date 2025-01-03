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
from cloud_service.services.model import ModelService
from cloud_service.services.key import KeyService
from cloud_service.services.database import get_db
from cloud_service.core.config import settings

router = APIRouter(prefix="/models", tags=["模型"])
model_service = ModelService()
key_service = KeyService()

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
    model = await model_service.get_model_by_code(db, code)
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
    _: bool = Depends(verify_api_key)
):
    """同步模型(需要API密钥)"""
    model = await model_service.get_model_by_code(db, code)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    # 构建下载URL
    download_url = f"{settings.APP.base_url}/api/v1/models/{code}/download"
    
    # 返回模型信息
    return BaseResponse(data={
        "code": model.code,
        "file_path": model.file_path,
        "download_url": download_url
    })

@router.get("/{code}/download")
async def download_model(
    code: str,
    db: Session = Depends(get_db),
    range: Optional[str] = Header(None)
):
    """下载模型文件
    
    支持:
    1. 直接下载
    2. 断点续传
    3. 分块下载
    """
    # 获取模型信息
    model = await model_service.get_model_by_code(db, code)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    # 检查模型状态
    if not model.status:
        raise HTTPException(status_code=403, detail="Model is not available")
    
    # 构建完整的文件路径 - 包含模型代码子目录
    base_dir = os.path.join("/app", "models")
    model_dir = os.path.join(base_dir, code)  # 添加模型代码作为子目录
    file_name = f"{code}.zip"
    file_path = os.path.join(model_dir, file_name)
    
    print(f"Model code: {code}")                         # 打印模型代码
    print(f"Model file_path from DB: {model.file_path}") # 打印数据库中的路径
    print(f"Base directory: {base_dir}")                 # 打印基础目录
    print(f"Model directory: {model_dir}")              # 打印模型目录
    print(f"File name: {file_name}")                    # 打印文件名
    print(f"Full file path: {file_path}")               # 打印完整文件路径
    print(f"File exists: {os.path.exists(file_path)}")  # 打印文件是否存在
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Model file not found")
    
    # 获取文件信息
    file_size = os.path.getsize(file_path)
    
    # 处理断点续传
    if range:
        try:
            start_bytes = int(range.replace("bytes=", "").split("-")[0])
            end_bytes = file_size - 1
            
            # 创建文件流
            async def file_stream():
                with open(file_path, "rb") as f:
                    f.seek(start_bytes)
                    while True:
                        chunk = f.read(8192)  # 8KB chunks
                        if not chunk:
                            break
                        yield chunk
            
            # 返回部分内容
            headers = {
                "Content-Range": f"bytes {start_bytes}-{end_bytes}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Disposition": f'attachment; filename="{file_name}"',
                "Content-Type": "application/zip",
            }
            return StreamingResponse(
                file_stream(),
                status_code=206,
                headers=headers
            )
            
        except (IndexError, ValueError):
            pass  # 如果解析失败，回退到普通下载
    
    # 普通下载
    return FileResponse(
        file_path,
        filename=file_name,
        media_type="application/zip",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size)
        }
    ) 