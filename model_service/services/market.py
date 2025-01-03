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
        self.base_url = settings.CLOUD.url
        self.api_prefix = settings.CLOUD.api_prefix
    
    def _get_api_url(self, path: str) -> str:
        """获取完整的API URL"""
        return f"{self.base_url}{self.api_prefix}{path}"
    
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
                    self._get_api_url("/models/available"),
                    headers={"x-api-key": key.key}
                )
                response.raise_for_status()
                logger.info("Successfully synced models from market")
                return response.json()
                
        except Exception as e:
            logger.error(f"Failed to sync models: {str(e)}")
            raise 