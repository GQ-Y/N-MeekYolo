"""
市场服务
"""
import httpx
from sqlalchemy.orm import Session
from model_service.core.config import settings
from model_service.services.key import KeyService
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class MarketService:
    """市场服务"""
    
    def __init__(self):
        self.key_service = KeyService()
        self.base_url = settings.MARKET.base_url
    
    async def sync_models(self, db: Session):
        """同步模型"""
        try:
            # 获取API密钥
            key = await self.key_service.get_key(db)
            if not key:
                raise ValueError("No API key found")
            if not key.status:
                raise ValueError("API key is inactive")
            
            # 调用云市场API
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/models/available",
                    headers={"x-api-key": key.key}
                )
                response.raise_for_status()
                logger.info("Successfully synced models from market")
                return response.json()
                
        except Exception as e:
            logger.error(f"Failed to sync models: {str(e)}")
            raise 