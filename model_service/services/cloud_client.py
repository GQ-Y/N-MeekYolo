"""
云服务客户端
"""
import aiohttp
from typing import Dict, Any
from sqlalchemy.orm import Session
from model_service.core.config import settings
from model_service.services.base import get_api_key
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class CloudClient:
    """云服务客户端"""
    
    def __init__(self):
        self.base_url = settings.CLOUD.url
        self.api_prefix = settings.CLOUD.api_prefix
    
    def _get_api_url(self, path: str) -> str:
        """获取完整的API URL"""
        return f"{self.base_url}{self.api_prefix}{path}"
    
    async def create_key(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建密钥"""
        try:
            url = self._get_api_url("/keys")
            logger.info(f"Creating key at: {url}")
            logger.info(f"Request data: {data}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"Key created successfully: {result}")
                        return result["data"]
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to create key. Status: {response.status}, Response: {error_text}")
                        raise Exception(f"Failed to create key: {response.status}")
                        
        except Exception as e:
            logger.error(f"Failed to create key: {str(e)}")
            raise
    
    async def update_key(self, key_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """更新密钥"""
        try:
            url = self._get_api_url(f"/keys/{key_id}")
            logger.info(f"Updating key at: {url}")
            logger.info(f"Request data: {data}")
            
            async with aiohttp.ClientSession() as session:
                async with session.put(url, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"Key updated successfully: {result}")
                        return result["data"]
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to update key. Status: {response.status}, Response: {error_text}")
                        raise Exception(f"Failed to update key: {response.status}")
                        
        except Exception as e:
            logger.error(f"Failed to update key: {str(e)}")
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
            async with aiohttp.ClientSession() as session:
                response = await session.post(
                    f"{self.base_url}/api/v1/models/{model_code}/sync",
                    headers={"x-api-key": api_key}
                )
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"Successfully synced model: {model_code}")
                    return result["data"]
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to sync model {model_code}. Status: {response.status}, Response: {error_text}")
                    raise Exception(f"Failed to sync model: {response.status}")
        except Exception as e:
            logger.error(f"Failed to sync model {model_code}: {str(e)}")
            raise