"""
模型服务
"""
import os
import shutil
import httpx
import zipfile
from sqlalchemy.orm import Session
from model_service.core.config import settings
from model_service.services.cloud_client import CloudClient
from model_service.services.base import get_api_key
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class ModelService:
    """模型服务"""
    
    def __init__(self):
        self.cloud_client = CloudClient()
        # 使用 model_service 目录下的 store 目录
        self.base_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "store")
        self.temp_dir = os.path.join(self.base_dir, "temp")
        
        # 创建必要的目录
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)
        
        logger.info(f"Model base directory: {self.base_dir}")
        logger.info(f"Model temp directory: {self.temp_dir}")
    
    async def download_model(self, download_url: str, api_key: str) -> str:
        """
        下载模型文件
        
        Args:
            download_url: 下载地址
            api_key: API密钥
            
        Returns:
            str: 临时文件路径
        """
        try:
            # 创建临时文件
            temp_file = os.path.join(self.temp_dir, "temp_model.zip")
            
            # 下载文件
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    download_url,
                    headers={"x-api-key": api_key}
                )
                response.raise_for_status()
                
                # 保存文件
                with open(temp_file, "wb") as f:
                    f.write(response.content)
                    
            logger.info(f"Model file downloaded to {temp_file}")
            return temp_file
            
        except Exception as e:
            if os.path.exists(temp_file):
                os.remove(temp_file)
            logger.error(f"Failed to download model: {str(e)}")
            raise
    
    def extract_model(self, zip_file: str, model_code: str):
        """
        解压模型文件
        
        Args:
            zip_file: 压缩文件路径
            model_code: 模型代码
        """
        try:
            # 创建模型目录
            model_dir = os.path.join(self.base_dir, model_code)
            if os.path.exists(model_dir):
                shutil.rmtree(model_dir)
            os.makedirs(model_dir)
            
            # 解压文件
            with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                # 获取压缩包内的文件列表
                file_list = zip_ref.namelist()
                logger.info(f"Files in zip: {file_list}")
                
                # 解压所有文件
                zip_ref.extractall(model_dir)
                
            # 验证必要的文件是否存在
            required_files = ["best.pt", "data.yaml"]
            for file in required_files:
                file_path = os.path.join(model_dir, file)
                if not os.path.exists(file_path):
                    raise ValueError(f"Required file {file} not found in model package")
                
            logger.info(f"Model extracted to {model_dir}")
            logger.info(f"Extracted files: {os.listdir(model_dir)}")
            
        except Exception as e:
            if os.path.exists(model_dir):
                shutil.rmtree(model_dir)
            logger.error(f"Failed to extract model: {str(e)}")
            raise
        finally:
            # 清理临时文件
            if os.path.exists(zip_file):
                os.remove(zip_file)
    
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
            
            # 调用云市场API同步模型
            result = await self.cloud_client.sync_model(db, model_code)
            
            # 下载模型文件
            temp_file = await self.download_model(result["download_url"], api_key)
            
            # 解压模型文件
            self.extract_model(temp_file, model_code)
            
            # 验证模型文件
            model_dir = os.path.join(self.base_dir, model_code)
            model_file = os.path.join(model_dir, "best.pt")
            if not os.path.exists(model_file):
                raise ValueError(f"Model file not found at {model_file}")
            
            logger.info(f"Successfully synced model {model_code}")
            return result
            
        except Exception as e:
            # 清理失败的同步
            model_dir = os.path.join(self.base_dir, model_code)
            if os.path.exists(model_dir):
                shutil.rmtree(model_dir)
            logger.error(f"Failed to sync model {model_code}: {str(e)}")
            raise