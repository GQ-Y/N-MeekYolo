"""
模型CRUD操作
"""
import os
import yaml
from typing import List, Optional
from sqlalchemy.orm import Session
from api_service.models.database import Model
from api_service.core.config import settings
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

def scan_models(db: Session) -> List[Model]:
    """扫描模型目录并同步到数据库"""
    try:
        # 获取项目根目录
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
        # 获取模型目录的绝对路径
        model_dir = os.path.join(project_root, settings.STORAGE.base_dir)
        
        logger.info(f"Scanning models in directory: {model_dir}")
        
        if not os.path.exists(model_dir):
            logger.warning(f"Model directory not found: {model_dir}")
            return []

        # 扫描模型文件
        models = []
        for root, _, files in os.walk(model_dir):
            # 查找data.yaml和best.pt文件
            if "data.yaml" in files and "best.pt" in files:
                data_path = os.path.join(root, "data.yaml")
                weight_path = os.path.join(root, "best.pt")
                
                try:
                    # 读取模型配置
                    with open(data_path, "r", encoding="utf-8") as f:
                        config = yaml.safe_load(f)
                    
                    # 获取相对路径
                    rel_path = os.path.relpath(root, model_dir)
                    
                    # 从配置中获取模型代码
                    code = config.get("code")
                    if not code:
                        # 如果配置中没有code，使用目录名
                        code = os.path.basename(root)
                        logger.warning(f"No code found in {data_path}, using directory name: {code}")
                    
                    logger.info(f"Found model: {code} at {rel_path}")
                    
                    # 检查数据库中是否存在
                    model = get_model_by_code(db, code)
                    if not model:
                        # 创建新模型记录
                        model = Model(
                            code=code,
                            name=config.get("name", code),
                            path=rel_path,
                            description=config.get("description", f"Model from {rel_path}")
                        )
                        db.add(model)
                        logger.info(f"Added new model to database: {code}")
                    else:
                        # 更新现有记录
                        model.name = config.get("name", code)
                        model.description = config.get("description", f"Model from {rel_path}")
                        logger.info(f"Updated existing model in database: {code}")
                    
                    models.append(model)
                except Exception as e:
                    logger.error(f"Failed to load model config {data_path}: {str(e)}")
                    continue
        
        # 提交更改
        db.commit()
        logger.info(f"Successfully scanned {len(models)} models")
        return models
    except Exception as e:
        logger.error(f"Scan models failed: {str(e)}")
        db.rollback()
        return []

def get_models(db: Session, skip: int = 0, limit: int = 100) -> List[Model]:
    """获取模型列表"""
    # 先扫描模型目录
    scan_models(db)
    # 然后返回数据库中的记录
    return db.query(Model).offset(skip).limit(limit).all()

def get_model(db: Session, model_id: int) -> Optional[Model]:
    """获取模型"""
    return db.query(Model).filter(Model.id == model_id).first()

def get_model_by_code(db: Session, code: str) -> Optional[Model]:
    """通过代码获取模型"""
    return db.query(Model).filter(Model.code == code).first()

def create_model(
    db: Session,
    code: str,
    name: str,
    path: str,
    description: Optional[str] = None
) -> Model:
    """创建模型"""
    model = Model(
        code=code,
        name=name,
        path=path,
        description=description
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return model

def update_model(
    db: Session,
    model_id: int,
    code: Optional[str] = None,
    name: Optional[str] = None,
    path: Optional[str] = None,
    description: Optional[str] = None
) -> Optional[Model]:
    """更新模型"""
    model = get_model(db, model_id)
    if not model:
        return None
    
    if code is not None:
        model.code = code
    if name is not None:
        model.name = name
    if path is not None:
        model.path = path
    if description is not None:
        model.description = description
    
    db.commit()
    db.refresh(model)
    return model

def delete_model(db: Session, model_id: int) -> bool:
    """删除模型"""
    model = get_model(db, model_id)
    if not model:
        return False
    
    db.delete(model)
    db.commit()
    return True 