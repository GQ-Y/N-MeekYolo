"""
模型服务
"""
import httpx
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from core.config import settings
from models.database import Model, Node
from shared.utils.logger import setup_logger
from sqlalchemy.sql import text

logger = setup_logger(__name__)

class ModelService:
    """模型服务"""
    
    def __init__(self):
        # 不再直接从配置中获取URL，而是动态从节点获取
        self.api_prefix = settings.MODEL_SERVICE.api_prefix
    
    def _get_api_url(self, path: str, base_url: str = None) -> str:
        """获取完整的API URL"""
        if not base_url:
            # 如果没有提供基础URL，尝试从节点获取
            base_url = self._get_model_service_url()
            if not base_url:
                logger.error("无法获取模型服务URL，服务不可用")
                raise ValueError("模型服务不可用，无法获取服务URL")
        return f"{base_url}{self.api_prefix}{path}"
    
    def _get_model_service_url(self) -> Optional[str]:
        """从节点表中获取模型服务URL"""
        from core.database import SessionLocal
        
        db = SessionLocal()
        try:
            # 查询类型为模型服务(2)的在线节点
            node = db.query(Node).filter(
                Node.service_type == 2,  # 模型服务
                Node.service_status == "online",
                Node.is_active == True
            ).first()
            
            if node:
                return f"http://{node.ip}:{node.port}"
            else:
                logger.warning("未找到可用的模型服务节点")
                return None
        except Exception as e:
            logger.error(f"查询模型服务节点失败: {str(e)}")
            return None
        finally:
            db.close()
    
    async def check_model_service(self) -> bool:
        """检查模型服务是否可用"""
        try:
            # 获取模型服务URL
            base_url = self._get_model_service_url()
            if not base_url:
                logger.error("未找到模型服务节点，服务不可用")
                return False
                
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{base_url}/health")
                return response.status_code == 200
        except Exception as e:
            logger.error(f"检查模型服务失败: {str(e)}")
            return False
    
    async def sync_models(self, db: Session) -> List[Model]:
        """同步模型列表"""
        try:
            # 检查模型服务是否可用
            if not await self.check_model_service():
                logger.warning("模型服务不可用，使用本地数据")
                return db.query(Model).all()
                
            base_url = self._get_model_service_url()
            if not base_url:
                logger.warning("模型服务不可用，使用本地数据")
                return db.query(Model).all()
                
            async with httpx.AsyncClient() as client:
                # 使用新的 list 接口，注意这里改为 GET 请求
                response = await client.get(self._get_api_url("/models/list", base_url))
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
                        # 版本和作者是可选字段，更新时直接设置
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
            logger.error(f"同步模型失败: {str(e)}")
            db.rollback()
            # 返回现有模型列表而不抛出异常，确保任务状态保持不变
            return db.query(Model).all()
    
    async def get_model(self, db: Session, model_id: int) -> Optional[Model]:
        """获取模型
        
        先尝试从本地数据库获取模型，如果没有找到则尝试从模型服务获取
        """
        # 先尝试从本地数据库获取
        model = db.query(Model).filter(Model.id == model_id).first()
        if model:
            logger.info(f"从本地数据库找到模型 ID={model_id}, code={model.code}")
            return model
        
        # 检查模型服务是否可用
        if not await self.check_model_service():
            logger.warning(f"模型服务不可用，无法获取模型ID {model_id}")
            return None
        
        base_url = self._get_model_service_url()
        if not base_url:
            logger.warning(f"未找到模型服务节点，无法获取模型ID {model_id}")
            return None
        
        try:
            # 尝试从模型服务获取模型详情
            async with httpx.AsyncClient() as client:
                # 使用模型详情接口
                response = await client.get(
                    self._get_api_url("/models/detail", base_url),
                    params={"id": model_id}
                )
                
                if response.status_code == 404:
                    logger.warning(f"模型服务中不存在模型ID {model_id}")
                    return None
                
                response.raise_for_status()
                data = response.json()
                
                if not data.get("success", False):
                    logger.warning(f"获取模型ID {model_id} 失败：{data.get('message')}")
                    return None
                
                model_data = data.get("data", {})
                if not model_data:
                    logger.warning(f"获取的模型ID {model_id} 数据为空")
                    return None
                
                # 创建新模型记录
                model = Model(
                    id=model_id,  # 保持ID一致
                    code=model_data.get("code", f"model_{model_id}"),  # 如果没有code，使用默认值
                    name=model_data.get("name", f"Model {model_id}"),  # 如果没有name，使用默认值
                    path=model_data.get("path", ""),
                    description=model_data.get("description", ""),
                    nc=model_data.get("nc", 0),
                    names=model_data.get("names", {}),
                    version=model_data.get("version", "1.0.0"),
                    author=model_data.get("author", "")
                )
                
                # 保存到数据库
                db.add(model)
                try:
                    db.commit()
                    db.refresh(model)
                    logger.info(f"成功从模型服务获取并保存模型 ID={model_id}, code={model.code}")
                    return model
                except Exception as e:
                    db.rollback()
                    logger.error(f"保存模型 ID={model_id} 到数据库失败: {str(e)}")
                    return None
        except Exception as e:
            logger.error(f"从模型服务获取模型 ID={model_id} 失败: {str(e)}")
            return None
    
    async def get_model_by_code(self, db: Session, code: str) -> Optional[Model]:
        """通过代码获取模型"""
        try:
            # 先从本地数据库获取
            model = db.query(Model).filter(Model.code == code).first()
            if model:
                return model
            
            # 检查模型服务是否可用
            if not await self.check_model_service():
                logger.warning("模型服务不可用，无法获取模型信息")
                return None
                
            base_url = self._get_model_service_url()
            if not base_url:
                logger.warning("模型服务不可用，无法获取模型信息")
                return None
            
            # 如果本地没有，从模型服务获取
            async with httpx.AsyncClient() as client:
                # 使用新的 detail 接口
                response = await client.get(
                    self._get_api_url("/models/detail", base_url),
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
            logger.error(f"通过代码获取模型失败: {str(e)}")
            db.rollback()
            return None