"""
模型路由
处理模型管理相关的请求
"""
from fastapi import APIRouter, File, UploadFile, Form, HTTPException, Depends, Request, Body, Query
from fastapi.responses import FileResponse
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from shared.utils.logger import setup_logger
from model_service.models.models import ModelInfo
from model_service.models.schemas import StandardResponse, ModelResponse, ModelListResponse
from model_service.manager.model_manager import ModelManager
from model_service.services.model import ModelService
from model_service.services.database import get_db
import os
from model_service.core.config import settings

# 设置文件大小限制 (100MB)
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB in bytes
ALLOWED_EXTENSIONS = {'.pt', '.pth', '.onnx', '.yaml', '.yml'}

logger = setup_logger(__name__)
router = APIRouter()
model_manager = ModelManager()
model_service = ModelService()

def validate_file(file: UploadFile) -> None:
    """验证上传文件"""
    # 检查文件大小
    file.file.seek(0, 2)  # 移动到文件末尾
    size = file.file.tell()  # 获取文件大小
    file.file.seek(0)  # 重置文件指针
    
    if size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"文件大小超过限制 (最大 {MAX_FILE_SIZE/1024/1024}MB)"
        )
    
    # 检查文件扩展名
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型 {ext}，允许的类型: {', '.join(ALLOWED_EXTENSIONS)}"
        )

@router.post("/upload", response_model=ModelResponse)
async def upload_model(
    request: Request,
    files: List[UploadFile] = File(..., description="模型文件列表，支持 .pt、.pth、.onnx、.yaml 格式"),
    name: str = Form(..., description="模型名称"),
    code: str = Form(..., description="模型代码，唯一标识符"),
    version: str = Form("1.0.0", description="模型版本号"),
    author: str = Form("", description="模型作者"),
    description: str = Form("", description="模型描述")
):
    """
    上传模型文件
    
    支持上传以下格式的文件：
    - .pt/.pth: PyTorch 模型文件
    - .onnx: ONNX 模型文件
    - .yaml: 模型配置文件
    
    文件大小限制：100MB
    """
    try:
        # 验证所有文件
        for file in files:
            validate_file(file)
            
        model_info = ModelInfo(
            name=name,
            code=code,
            version=version,
            author=author,
            description=description
        )
        result = await model_manager.upload_model(files, model_info)
        return ModelResponse(
            path=str(request.url),
            data=model_info
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"模型上传失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/list", response_model=ModelListResponse)
async def list_models(
    request: Request,
    skip: int = 0,
    limit: int = 10
):
    """
    获取模型列表
    
    参数：
    - skip: 跳过的记录数，用于分页
    - limit: 返回的记录数，用于分页
    
    返回：
    - 模型列表，包含基本信息
    """
    try:
        models = await model_manager.list_models(skip, limit)
        return ModelListResponse(
            path=str(request.url),
            data=models
        )
    except Exception as e:
        logger.error(f"获取模型列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/detail", response_model=ModelResponse)
async def get_model(
    request: Request,
    model_code: str = Query(..., description="模型代码，唯一标识符")
):
    """
    获取模型详细信息
    
    参数：
    - model_code: 模型代码，唯一标识符
    
    返回：
    - 模型详细信息，包含所有字段
    """
    try:
        model = await model_manager.get_model_info(model_code)
        if not model:
            raise HTTPException(status_code=404, detail=f"模型不存在: {model_code}")
        return ModelResponse(
            path=str(request.url),
            data=model
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取模型信息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/delete", response_model=StandardResponse)
async def delete_model(
    request: Request,
    model_code: str = Body(..., embed=True, description="要删除的模型代码")
):
    """
    删除模型
    
    参数：
    - model_code: 要删除的模型代码
    
    返回：
    - 删除结果
    """
    try:
        result = await model_manager.delete_model(model_code)
        if not result:
            raise HTTPException(status_code=404, detail=f"模型不存在: {model_code}")
        return StandardResponse(
            path=str(request.url),
            message="模型已删除",
            data={"code": model_code}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除模型失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sync", response_model=StandardResponse)
async def sync_model(
    request: Request,
    model_code: str = Body(..., embed=True, description="要同步的模型代码"),
    db: Session = Depends(get_db)
):
    """
    从云市场同步模型
    
    参数：
    - model_code: 要同步的模型代码
    
    返回：
    - 同步结果
    """
    try:
        result, error = await model_service.sync_model(db, model_code)
        if error:
            raise HTTPException(status_code=400, detail=error)
            
        return StandardResponse(
            path=str(request.url),
            data=result
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"同步模型失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/available", response_model=ModelListResponse)
async def get_available_models(
    request: Request,
    skip: int = Query(0, description="分页起始位置"),
    limit: int = Query(10, description="每页数量"),
    db: Session = Depends(get_db)
):
    """
    获取可用模型列表
    
    参数：
    - skip: 分页起始位置
    - limit: 每页数量
    
    返回：
    - 可用模型列表
    """
    try:
        result, error = await model_service.cloud_client.get_available_models(db, skip, limit)
        if error:
            raise HTTPException(status_code=400, detail=error)
            
        return ModelListResponse(
            path=str(request.url),
            data=result
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取可用模型列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/detail", response_model=ModelResponse)
async def get_model_detail(
    request: Request,
    code: str = Query(..., description="模型代码"),
    db: Session = Depends(get_db)
):
    """
    获取模型详细信息
    
    参数：
    - code: 模型代码
    
    返回：
    - 模型详细信息
    """
    try:
        # 先查询本地数据库
        model, error = await model_service.get_model_by_code(db, code)
        if model:
            return ModelResponse(
                path=str(request.url),
                data=model
            )
            
        # 如果本地没有，从云服务获取
        result, error = await model_service.cloud_client.get_model_info(db, code)
        if error:
            raise HTTPException(status_code=404, detail=error)
            
        return ModelResponse(
            path=str(request.url),
            data=result
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取模型详情失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/download", response_class=FileResponse)
async def download_model(
    request: Request,
    code: str = Query(..., description="要下载的模型代码"),
    db: Session = Depends(get_db)
):
    """
    下载模型文件
    
    参数：
    - code: 要下载的模型代码
    
    返回：
    - 模型文件（.pt 格式）
    """
    try:
        # 检查本地是否存在模型文件
        base_dir = os.path.join(settings.STORAGE.base_dir, code)
        model_file = os.path.join(base_dir, "best.pt")
        
        if not os.path.exists(model_file):
            # 如果本地不存在，尝试同步
            result, error = await model_service.sync_model(db, code)
            if error:
                raise HTTPException(status_code=404, detail=error)
        
        # 返回模型文件
        return FileResponse(
            model_file,
            filename=f"{code}.pt",
            media_type="application/octet-stream"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"下载模型失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))