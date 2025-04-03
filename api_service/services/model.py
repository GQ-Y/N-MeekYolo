"""
模型服务
"""
import httpx
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from core.config import settings
from models.database import Model
from shared.utils.logger import setup_logger
from sqlalchemy.sql import text

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
                
                # 获取模型服务返回的模型代码列表
                remote_model_codes = [item["code"] for item in data.get("data", {}).get("items", [])]
                
                # 获取本地数据库中的所有模型
                local_models = db.query(Model).all()
                local_model_codes = {model.code: model for model in local_models}
                
                # 处理需要更新或添加的模型
                updated_models = []
                for item in data.get("data", {}).get("items", []):
                    code = item["code"]
                    
                    if code in local_model_codes:
                        # 更新已有模型
                        model = local_model_codes[code]
                        model.name = item["name"]
                        model.path = item.get("path", "")
                        model.description = item.get("description", "")
                        model.nc = item.get("nc", 0)
                        model.names = item.get("names", {})
                        model.version = item.get("version", "1.0.0")
                        model.author = item.get("author", "")
                        updated_models.append(model)
                        logger.info(f"更新模型: {code}")
                    else:
                        # 添加新模型
                        model = Model(
                            code=code,
                            name=item["name"],
                            path=item.get("path", ""),
                            description=item.get("description", ""),
                            nc=item.get("nc", 0),
                            names=item.get("names", {}),
                            version=item.get("version", "1.0.0"),
                            author=item.get("author", "")
                        )
                        db.add(model)
                        updated_models.append(model)
                        logger.info(f"添加新模型: {code}")
                
                # 删除不再存在的模型
                # 找出不再远程存在但本地存在的模型代码
                deleted_codes = set(local_model_codes.keys()) - set(remote_model_codes)
                
                # 检查这些模型是否有被任务引用
                for code in deleted_codes:
                    model = local_model_codes[code]
                    
                    # 检查是否有任务引用了这个模型
                    # 使用 SQL 查询检查是否存在引用
                    has_references = db.execute(text("""
                        SELECT 1 FROM task_model_association WHERE model_id = :model_id
                        UNION ALL
                        SELECT 1 FROM sub_tasks WHERE model_id = :model_id
                        LIMIT 1
                    """), {"model_id": model.id}).scalar() is not None
                    
                    if not has_references:
                        # 如果没有引用，可以安全删除
                        db.delete(model)
                        logger.info(f"删除模型: {code}")
                    else:
                        # 如果有引用，将模型保留在列表中
                        logger.warning(f"模型 {code} 被任务引用，无法删除")
                        updated_models.append(model)
                
                # 提交更改
                db.commit()
                
                return updated_models
                
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
                    nc=data.get("nc", 0),
                    names=data.get("names", {}),
                    version=data.get("version", "1.0.0"),
                    author=data.get("author", "")
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