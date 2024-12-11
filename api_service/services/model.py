"""
模型服务
"""
import httpx
from typing import Optional, Dict, List
from sqlalchemy.orm import Session
from api_service.models.database import Model
from api_service.core.config import settings
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class ModelService:
    """模型服务"""
    
    def __init__(self):
        self.model_service_url = f"http://{settings.SERVICES.model.host}:{settings.SERVICES.model.port}"
    
    async def check_model_service(self) -> bool:
        """检查模型服务是否可用"""
        try:
            logger.info(f"Checking model service at: {self.model_service_url}")
            async with httpx.AsyncClient(timeout=5.0) as client:
                # 使用 list API 进行检查，因为根路由可能不存在
                response = await client.get(f"{self.model_service_url}/api/v1/models/list")
                if response.status_code == 200:
                    logger.info("Model service is available")
                    return True
                logger.warning(f"Model service returned status code: {response.status_code}")
                return False
        except Exception as e:
            logger.warning(f"Model service is not available: {str(e)}")
            return False
    
    async def sync_models(self, db: Session) -> List[Model]:
        """同步模型列表"""
        try:
            # 调用model_service获取模型列表
            async with httpx.AsyncClient(timeout=10.0) as client:
                logger.info(f"Fetching models from: {self.model_service_url}/api/v1/models/list")
                response = await client.get(
                    f"{self.model_service_url}/api/v1/models/list"
                )
                response.raise_for_status()
                data = response.json()
                
                if not data.get("data") or not data["data"].get("items"):
                    logger.warning("No models data received from model service")
                    return []
                
                # 更新本地数据库
                models = []
                for item in data["data"]["items"]:
                    try:
                        model = db.query(Model).filter(Model.code == item["code"]).first()
                        if not model:
                            model = Model(
                                code=item["code"],
                                name=item["name"],
                                description=item.get("description", ""),
                                path=item.get("path", "")
                            )
                            db.add(model)
                            logger.info(f"Created new model: {item['code']}")
                        else:
                            model.name = item["name"]
                            model.description = item.get("description", "")
                            model.path = item.get("path", "")
                            logger.info(f"Updated existing model: {item['code']}")
                        models.append(model)
                    except Exception as e:
                        logger.error(f"Failed to process model {item.get('code')}: {str(e)}")
                        continue
                
                db.commit()
                logger.info(f"Successfully synced {len(models)} models")
                return models
                
        except Exception as e:
            logger.error(f"Failed to sync models: {str(e)}")
            db.rollback()
            raise
    
    async def get_model_by_code(self, db: Session, code: str) -> Optional[Model]:
        """通过代码获取模型"""
        try:
            # 先检查本地数据库
            model = db.query(Model).filter(Model.code == code).first()
            
            # 如果model_service可用,从远程获取最新数据
            if await self.check_model_service():
                try:
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        response = await client.get(
                            f"{self.model_service_url}/api/v1/models/code/{code}"
                        )
                        if response.status_code == 200:
                            data = response.json()
                            if not data.get("data"):
                                logger.warning(f"No data received for model code: {code}")
                                return model
                            
                            model_data = data["data"]
                            # 更新或创建模型
                            if not model:
                                model = Model(
                                    code=model_data["code"],
                                    name=model_data["name"],
                                    description=model_data.get("description"),
                                    path=model_data.get("path", "")
                                )
                                db.add(model)
                            else:
                                model.name = model_data["name"]
                                model.description = model_data.get("description")
                                model.path = model_data.get("path", "")
                            db.commit()
                except Exception as e:
                    logger.error(f"Failed to get model from service: {str(e)}")
                    # 发生错误时返回本地数据
                    return model
            else:
                logger.warning(f"Model service not available, using local data for code: {code}")
            
            return model
            
        except Exception as e:
            logger.error(f"Failed to get model by code: {str(e)}")
            return model  # 返回本地数据
    
    async def get_model(self, db: Session, model_id: int) -> Optional[Model]:
        """通过ID���取模型"""
        try:
            model = db.query(Model).filter(Model.id == model_id).first()
            if not model:
                return None
            
            # 如果找到模型且model_service可用，尝试通过code更新
            if model and await self.check_model_service():
                try:
                    updated_model = await self.get_model_by_code(db, model.code)
                    if updated_model:
                        return updated_model
                except Exception as e:
                    logger.error(f"Failed to update model from service: {str(e)}")
                
            return model
            
        except Exception as e:
            logger.error(f"Failed to get model by id: {str(e)}")
            return None