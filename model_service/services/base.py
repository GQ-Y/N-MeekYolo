"""
基础服务
"""
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from model_service.models.database import MarketKey
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

async def get_key(db: Session) -> Optional[MarketKey]:
    """获取密钥"""
    try:
        return db.query(MarketKey).filter(
            MarketKey.status == True,
            MarketKey.key.isnot(None),
            MarketKey.cloud_id.isnot(None)
        ).first()
    except Exception as e:
        logger.error(f"获取密钥失败: {str(e)}")
        return None

async def get_api_key(db: Session) -> Tuple[Optional[str], Optional[str]]:
    """
    获取有效的API密钥
    
    Returns:
        Tuple[Optional[str], Optional[str]]: (api_key, error_message)
    """
    try:
        key = await get_key(db)
        
        if not key:
            return None, "没有找到有效的API密钥"
            
        if not key.status:
            return None, "API密钥已禁用"
            
        if not key.cloud_id:
            return None, "API密钥未在云服务注册"
            
        return key.key, None
        
    except Exception as e:
        logger.error(f"获取API密钥失败: {str(e)}")
        return None, f"获取API密钥失败: {str(e)}"

async def invalidate_key(db: Session, key: str) -> bool:
    """
    将密钥标记为无效
    
    Args:
        db: 数据库会话
        key: API密钥
        
    Returns:
        bool: 是否成功标记为无效
    """
    try:
        result = db.query(MarketKey).filter(
            MarketKey.key == key
        ).update({
            MarketKey.status: False
        })
        db.commit()
        return result > 0
    except Exception as e:
        logger.error(f"标记密钥无效失败: {str(e)}")
        db.rollback()
        return False 