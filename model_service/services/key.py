"""
密钥服务
"""
from typing import Optional
from sqlalchemy.orm import Session
from model_service.models.database import MarketKey
from model_service.models.schemas import KeyCreate
from model_service.services.cloud_client import CloudClient
from model_service.services.base import get_key
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class KeyService:
    """密钥服务"""
    
    def __init__(self):
        self.cloud_client = CloudClient()
    
    async def get_key(self, db: Session) -> Optional[MarketKey]:
        """获取密钥"""
        return await get_key(db)
    
    async def create_or_update_key(self, db: Session, data: KeyCreate) -> MarketKey:
        """创建或更新密钥"""
        try:
            # 查找现有密钥
            existing_key = await self.get_key(db)
            
            if existing_key:
                # 更新云市场密钥
                cloud_key = await self.cloud_client.update_key(
                    existing_key.cloud_id,
                    {
                        "name": data.name,
                        "phone": data.phone,
                        "email": data.email,
                        "status": existing_key.status
                    }
                )
                
                # 更新本地密钥
                existing_key.key = cloud_key["key"]
                existing_key.name = data.name
                existing_key.phone = data.phone
                existing_key.email = data.email
                db.commit()
                db.refresh(existing_key)
                logger.info(f"Updated key for user: {data.name}")
                return existing_key
            else:
                # 创建云市场密钥
                cloud_key = await self.cloud_client.create_key(data.model_dump())
                
                # 创建本地密钥
                market_key = MarketKey(
                    cloud_id=cloud_key["id"],
                    key=cloud_key["key"],
                    name=data.name,
                    phone=data.phone,
                    email=data.email,
                    status=True
                )
                db.add(market_key)
                db.commit()
                db.refresh(market_key)
                logger.info(f"Created new key for user: {data.name}")
                return market_key
                
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create/update key: {str(e)}")
            raise