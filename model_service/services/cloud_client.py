"""
云服务客户端
"""
import aiohttp
from typing import Dict, Any
from sqlalchemy.orm import Session
from model_service.core.config import settings
from model_service.services.base import get_api_key
from shared.utils.logger import setup_logger
import os

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
        """同步模型"""
        try:
            # 获取API密钥
            api_key = await get_api_key(db)
            if not api_key:
                raise ValueError("No valid API key found")
            
            # 调用云服务API
            url = f"{self.base_url}{self.api_prefix}/models/{model_code}/sync"
            headers = {"x-api-key": api_key}
            
            logger.info(f"Syncing model {model_code} from cloud service: {url}")
            
            async with aiohttp.ClientSession() as session:
                # 1. 获取模型信息
                async with session.post(url, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Failed to sync model. Status: {response.status}, Response: {error_text}")
                        raise Exception(f"Failed to sync model: {response.status}")
                    
                    result = await response.json()
                    download_url = result["data"]["download_url"]
                    logger.info(f"Model sync successful, download URL: {download_url}")
                    
                    # 2. 下载模型文件
                    async with session.get(download_url, headers=headers) as download_response:
                        if download_response.status != 200:
                            error_text = await download_response.text()
                            logger.error(f"Failed to download model. Status: {download_response.status}, Response: {error_text}")
                            raise Exception(f"Failed to download model: {download_response.status}")
                        
                        # 3. 保存模型文件
                        model_dir = os.path.join(settings.STORAGE.base_dir, model_code)
                        os.makedirs(model_dir, exist_ok=True)
                        file_path = os.path.join(model_dir, f"{model_code}.zip")
                        
                        with open(file_path, "wb") as f:
                            while True:
                                chunk = await download_response.content.read(8192)
                                if not chunk:
                                    break
                                f.write(chunk)
                        
                        logger.info(f"Model file saved to: {file_path}")
                        
                        # 4. 解压模型文件
                        import zipfile
                        with zipfile.ZipFile(file_path, "r") as zip_ref:
                            zip_ref.extractall(model_dir)
                        
                        logger.info(f"Model file extracted to: {model_dir}")
                        
                        return result["data"]
                    
        except Exception as e:
            logger.error(f"Failed to sync model {model_code}: {str(e)}")
            raise