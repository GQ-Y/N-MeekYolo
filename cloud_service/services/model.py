"""
模型服务
"""
import os
import shutil
import zipfile
import yaml
from typing import List, Optional
from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from cloud_service.models.database import CloudModel
from cloud_service.models.schemas import CloudModelCreate, CloudModelUpdate
from cloud_service.core.config import settings
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class ModelService:
    """模型服务"""
    
    def __init__(self):
        """初始化"""
        self.store_dir = settings.STORAGE.base_dir
        os.makedirs(self.store_dir, exist_ok=True)
    
    async def create_model(
        self,
        db: Session,
        model_file: UploadFile,
        data: CloudModelCreate
    ) -> CloudModel:
        """创建或更新模型"""
        try:
            # 检查模型是否已存在
            existing_model = await self.get_model_by_code(db, data.code)
            
            # 创建模型目录
            model_dir = os.path.join(self.store_dir, data.code)
            os.makedirs(model_dir, exist_ok=True)
            
            # 保存模型文件
            pt_path = os.path.join(model_dir, "best.pt")
            with open(pt_path, "wb") as f:
                content = await model_file.read()
                f.write(content)
            
            # 生成配置文件
            config = {
                "code": data.code,
                "version": data.version,
                "name": data.name,
                "description": data.description,
                "author": data.author,
                "nc": data.nc,
                "names": data.names,
                "create_time": datetime.utcnow().isoformat(),
                "update_time": datetime.utcnow().isoformat()
            }
            
            yaml_path = os.path.join(model_dir, "data.yaml")
            with open(yaml_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(config, f, allow_unicode=True)
            
            # 创建zip文件
            zip_path = os.path.join(model_dir, f"{data.code}.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.write(pt_path, "best.pt")
                zf.write(yaml_path, "data.yaml")
            
            if existing_model:
                # 更新现有模型
                existing_model.version = data.version
                existing_model.name = data.name
                existing_model.description = data.description
                existing_model.author = data.author
                existing_model.nc = data.nc
                existing_model.names = data.names
                existing_model.file_path = zip_path
                existing_model.status = True
                
                db.commit()
                db.refresh(existing_model)
                return existing_model
            else:
                # 创建新模型
                model = CloudModel(
                    code=data.code,
                    version=data.version,
                    name=data.name,
                    description=data.description,
                    author=data.author,
                    nc=data.nc,
                    names=data.names,
                    file_path=zip_path,
                    status=True
                )
                
                db.add(model)
                db.commit()
                db.refresh(model)
                return model
            
        except Exception as e:
            # 清理已创建的文件
            if 'model_dir' in locals() and os.path.exists(model_dir):
                shutil.rmtree(model_dir)
            raise
    
    async def get_model(self, db: Session, model_id: int) -> Optional[CloudModel]:
        """获取模型"""
        return db.query(CloudModel).filter(CloudModel.id == model_id).first()
    
    async def get_model_by_code(self, db: Session, code: str) -> Optional[CloudModel]:
        """通过代码获取模型"""
        return db.query(CloudModel).filter(CloudModel.code == code).first()
    
    async def get_available_models(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100
    ) -> List[CloudModel]:
        """获取可用模型列表"""
        return db.query(CloudModel).filter(
            CloudModel.status == True
        ).offset(skip).limit(limit).all() 