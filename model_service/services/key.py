"""
密钥服务
"""
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException
from model_service.models.database import MarketKey
from model_service.models.schemas import KeyCreate, KeyUpdate
from model_service.services.cloud_client import CloudClient
from model_service.services.base import get_key
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class KeyService:
    """密钥服务"""
    
    def __init__(self):
        self.cloud_client = CloudClient()
    
    async def get_key(self, db: Session) -> Optional[MarketKey]:
        """
        获取当前可用的密钥
        
        Args:
            db: 数据库会话
            
        Returns:
            Optional[MarketKey]: 密钥信息
        """
        return await get_key(db)
    
    async def create_key(self, db: Session, data: KeyCreate) -> MarketKey:
        """
        注册密钥
        
        Args:
            db: 数据库会话
            data: 密钥创建参数
            
        Returns:
            MarketKey: 创建的密钥信息
        """
        try:
            # 检查是否已存在激活的密钥
            existing_key = await self.get_key(db)
            if existing_key and existing_key.status:
                raise HTTPException(
                    status_code=400,
                    detail="已存在激活的密钥，请先禁用当前密钥"
                )
            
            # 调用云服务注册密钥
            result, error = await self.cloud_client._make_request(
                "POST",
                "/api/v1/keys",
                db,
                params={  # 所有参数都在query中
                    "name": data.name,
                    "phone": data.phone,
                    "email": data.email
                }
            )
            
            if error:
                raise HTTPException(status_code=400, detail=error)
            
            # 保存到数据库
            try:
                key = MarketKey(
                    cloud_id=result["data"]["id"],
                    key=result["data"]["key"],
                    name=data.name,
                    phone=data.phone,
                    email=data.email,
                    status=True
                )
                db.add(key)
                db.commit()
                db.refresh(key)
                return key
                
            except Exception as e:
                logger.error(f"数据库操作失败: {str(e)}")
                db.rollback()
                raise HTTPException(status_code=500, detail="数据库操作失败")
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"注册密钥失败: {str(e)}")
            raise HTTPException(status_code=500, detail="注册密钥失败")
    
    async def update_key(self, db: Session, data: KeyUpdate) -> MarketKey:
        """
        更新密钥信息
        
        Args:
            db: 数据库会话
            data: 密钥更新参数
            
        Returns:
            MarketKey: 更新后的密钥信息
            
        Raises:
            HTTPException: 当密钥不存在时
        """
        try:
            key = await self.get_key(db)
            if not key:
                raise HTTPException(status_code=404, detail="密钥不存在")
            
            # 准备更新参数
            update_params: Dict[str, Any] = {"key_id": key.cloud_id}
            if data.name is not None:
                update_params["name"] = data.name
            if data.phone is not None:
                update_params["phone"] = data.phone
            if data.email is not None:
                update_params["email"] = data.email
            if data.status is not None:
                update_params["status"] = str(data.status).lower()  # 将布尔值转换为字符串
            
            # 调用云服务更新密钥
            result, error = await self.cloud_client._make_request(
                "PUT",
                "/api/v1/keys",
                db,
                params=update_params  # 所有参数都在query中
            )
            
            if error:
                raise HTTPException(status_code=400, detail=error)
            
            # 更新本地数据库
            try:
                if data.name is not None:
                    key.name = data.name
                if data.phone is not None:
                    key.phone = data.phone
                if data.email is not None:
                    key.email = data.email
                if data.status is not None:
                    key.status = data.status
                    
                db.commit()
                db.refresh(key)
                return key
                
            except Exception as e:
                logger.error(f"数据库操作失败: {str(e)}")
                db.rollback()
                raise HTTPException(status_code=500, detail="数据库操作失败")
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"更新密钥失败: {str(e)}")
            raise HTTPException(status_code=500, detail="更新密钥失败")