"""
云市场客户端
"""
import httpx
from sqlalchemy.orm import Session
from model_service.core.config import settings
from model_service.services.base import get_api_key
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class CloudClient:
    """云市场客户端"""
    
    def __init__(self):
        self.base_url = settings.MARKET.base_url
    
    async def create_key(self, data: dict) -> dict:
        """
        创建密钥
        
        Args:
            data: 密钥信息
            
        Returns:
            dict: 创建结果
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/keys",
                    json=data
                )
                response.raise_for_status()
                result = response.json()
                logger.info(f"Successfully created key in cloud market for user: {data['name']}")
                return result["data"]
        except Exception as e:
            logger.error(f"Failed to create key in cloud market: {str(e)}")
            raise

    async def update_key(self, key_id: int, data: dict) -> dict:
        """
        更新密钥
        
        Args:
            key_id: 密钥ID
            data: 密钥信息
            
        Returns:
            dict: 更新结果
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.put(
                    f"{self.base_url}/api/v1/keys/{key_id}",
                    json=data
                )
                response.raise_for_status()
                result = response.json()
                logger.info(f"Successfully updated key in cloud market for user: {data['name']}")
                return result["data"]
        except Exception as e:
            logger.error(f"Failed to update key in cloud market: {str(e)}")
            raise

    async def sync_model(self, db: Session, model_code: str) -> dict:
        """
        同步模型
        
        Args:
            db: 数据库会话
            model_code: 模型代码
            
        Returns:
            dict: 同步结果
        """
        try:
            # 获取API密钥
            api_key = await get_api_key(db)
            if not api_key:
                raise ValueError("No valid API key found")
            
            # 调用云市场API
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/models/{model_code}/sync",
                    headers={"x-api-key": api_key}
                )
                response.raise_for_status()
                result = response.json()
                logger.info(f"Successfully synced model: {model_code}")
                return result["data"]
        except Exception as e:
            logger.error(f"Failed to sync model {model_code}: {str(e)}")
            raise