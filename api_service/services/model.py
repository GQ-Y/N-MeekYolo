"""
模型服务
"""
import httpx
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from core.config import settings
from models.database import Model
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class ModelService:
    """模型服务"""
    
    def __init__(self):
        # 使用新的配置结构
        self.base_url = settings.MODEL_SERVICE.url
        self.api_prefix = settings.MODEL_SERVICE.api_prefix
    
    def _get_api_url(self, path: str) -> str:
        """获取完整的API URL"""
        return f"{self.base_url}{self.api_prefix}{path}"
    
    async def check_model_service(self) -> bool:
        """检查模型服务是否可用"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Check model service failed: {str(e)}")
            return False
    
    async def sync_models(self, db: Session) -> List[Model]:
        """同步模型列表"""
        try:
            async with httpx.AsyncClient() as client:
                # 使用新的 list 接口，注意这里改为 GET 请求
                response = await client.get(self._get_api_url("/models/list"))
                response.raise_for_status()
                data = response.json()
                
                # 更新本地数据库
                models = []
                for item in data.get("data", {}).get("items", []):
                    model = Model(
                        code=item["code"],
                        name=item["name"],
                        path=item.get("path", ""),  # 可能不存在
                        description=item.get("description", ""),
                        nc=item.get("nc", 0),  # 新增：类别数量
                        names=item.get("names", {})  # 新增：类别名称映射
                    )
                    models.append(model)
                    
                # 保存到数据库
                db.query(Model).delete()
                db.add_all(models)
                db.commit()
                
                return models
                
        except Exception as e:
            logger.error(f"Sync models failed: {str(e)}")
            db.rollback()
            raise
    
    async def get_model(self, db: Session, model_id: int) -> Optional[Model]:
        """获取模型"""
        return db.query(Model).filter(Model.id == model_id).first()
    
    async def get_model_by_code(self, db: Session, code: str) -> Optional[Model]:
        """通过代码获取模型"""
        try:
            # 先从本地数据库获取
            model = db.query(Model).filter(Model.code == code).first()
            if model:
                return model
            
            # 如果本地没有，从模型服务获取
            async with httpx.AsyncClient() as client:
                # 使用新的 detail 接口
                response = await client.get(
                    self._get_api_url("/models/detail"),
                    params={"code": code}
                )
                if response.status_code == 404:
                    return None
                    
                response.raise_for_status()
                data = response.json().get("data", {})
                
                # 创建新模型记录
                model = Model(
                    code=data["code"],
                    name=data["name"],
                    path=data.get("path", ""),
                    description=data.get("description", ""),
                    nc=data.get("nc", 0),  # 新增：类别数量
                    names=data.get("names", {})  # 新增：类别名称映射
                )
                
                # 保存到数据库
                db.add(model)
                db.commit()
                db.refresh(model)
                
                return model
                
        except Exception as e:
            logger.error(f"Get model by code failed: {str(e)}")
            db.rollback()
            return None