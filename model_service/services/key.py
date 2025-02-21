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
from datetime import datetime

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
            # 获取现有密钥
            key = db.query(MarketKey).first()
            
            # 调用云服务
            cloud_client = CloudClient()
            if key:
                # 更新密钥
                result = await cloud_client.update_key(key.cloud_id, data.model_dump())
            else:
                # 创建新密钥
                result = await cloud_client.create_key(data.model_dump())
            
            # 保存到数据库
            if key:
                key.name = result["name"]
                key.phone = result["phone"]
                key.email = result["email"]
                key.key = result["key"]
                key.updated_at = datetime.now()
            else:
                key = MarketKey(
                    cloud_id=result["id"],
                    key=result["key"],
                    name=result["name"],
                    phone=result["phone"],
                    email=result["email"]
                )
                db.add(key)
            
            db.commit()
            db.refresh(key)
            return key
            
        except Exception as e:
            logger.error(f"Failed to create/update key: {str(e)}")
            raise