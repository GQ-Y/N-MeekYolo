"""
基础服务
"""
from typing import Optional
from sqlalchemy.orm import Session
from model_service.models.database import MarketKey
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

async def get_key(db: Session) -> Optional[MarketKey]:
    """获取密钥"""
    return db.query(MarketKey).first()

async def get_api_key(db: Session) -> Optional[str]:
    """获取API密钥"""
    key = await get_key(db)
    if not key or not key.status:
        return None
    return key.key 