"""
模型服务
"""
import os
import shutil
import httpx
import zipfile
from typing import Optional, Tuple, Dict
from sqlalchemy.orm import Session
from model_service.core.config import settings
from model_service.services.cloud_client import CloudClient
from model_service.services.base import get_api_key
from shared.utils.logger import setup_logger
from model_service.models.models import ModelInfo

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
    
    async def download_model(self, download_url: str, api_key: str) -> Tuple[Optional[str], Optional[str]]:
        """
        下载模型文件
        
        Args:
            download_url: 下载地址
            api_key: API密钥
            
        Returns:
            Tuple[Optional[str], Optional[str]]: (临时文件路径, 错误信息)
        """
        temp_file = os.path.join(self.temp_dir, "temp_model.zip")
        try:
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
            return temp_file, None
            
        except Exception as e:
            if os.path.exists(temp_file):
                os.remove(temp_file)
            error_msg = f"下载模型文件失败: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
    
    def extract_model(self, zip_file: str, model_code: str) -> Optional[str]:
        """
        解压模型文件
        
        Args:
            zip_file: 压缩文件路径
            model_code: 模型代码
            
        Returns:
            Optional[str]: 错误信息
        """
        model_dir = os.path.join(self.base_dir, model_code)
        try:
            # 清理现有目录
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
                
            # 验证必要的文件
            required_files = ["best.pt", "data.yaml"]
            missing_files = []
            for file in required_files:
                file_path = os.path.join(model_dir, file)
                if not os.path.exists(file_path):
                    missing_files.append(file)
                    
            if missing_files:
                error_msg = f"模型包缺少必要文件: {', '.join(missing_files)}"
                logger.error(error_msg)
                return error_msg
                
            logger.info(f"Model extracted to {model_dir}")
            logger.info(f"Extracted files: {os.listdir(model_dir)}")
            return None
            
        except Exception as e:
            error_msg = f"解压模型文件失败: {str(e)}"
            logger.error(error_msg)
            return error_msg
        finally:
            # 清理临时文件
            if os.path.exists(zip_file):
                os.remove(zip_file)
    
    async def sync_model(self, db: Session, model_code: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        同步模型
        
        Args:
            db: 数据库会话
            model_code: 模型代码
            
        Returns:
            Tuple[Optional[Dict], Optional[str]]: (同步结果, 错误信息)
        """
        try:
            # 获取API密钥
            api_key, error = await get_api_key(db)
            if error:
                return None, error
            
            # 调用云服务API同步模型
            result, error = await self.cloud_client.sync_model(db, model_code)
            if error:
                return None, error
            
            # 获取下载地址
            download_url = result.get("download_url")
            if not download_url:
                return None, "未获取到模型下载地址"
            
            # 下载模型文件
            temp_file, error = await self.download_model(download_url, api_key)
            if error:
                return None, error
            
            # 解压模型文件
            error = self.extract_model(temp_file, model_code)
            if error:
                return None, error
            
            # 验证模型文件
            model_dir = os.path.join(self.base_dir, model_code)
            model_file = os.path.join(model_dir, "best.pt")
            if not os.path.exists(model_file):
                return None, f"模型文件不存在: {model_file}"
            
            logger.info(f"Successfully synced model {model_code}")
            return result, None
            
        except Exception as e:
            # 清理失败的同步
            model_dir = os.path.join(self.base_dir, model_code)
            if os.path.exists(model_dir):
                shutil.rmtree(model_dir)
            error_msg = f"同步模型失败: {str(e)}"
            logger.error(error_msg)
            return None, error_msg

    async def get_model_by_code(self, db: Session, code: str) -> Tuple[Optional[ModelInfo], Optional[str]]:
        """
        通过代码获取模型
        
        Args:
            db: 数据库会话
            code: 模型代码
            
        Returns:
            Tuple[Optional[ModelInfo], Optional[str]]: (模型信息, 错误信息)
        """
        try:
            # 从数据库中获取模型信息
            model = db.query(ModelInfo).filter(ModelInfo.code == code).first()
            if not model:
                error_msg = f"模型 {code} 不存在"
                logger.error(error_msg)
                return None, error_msg
            
            logger.info(f"Found model: {model.code}")
            return model, None
            
        except Exception as e:
            error_msg = f"获取模型信息失败: {str(e)}"
            logger.error(error_msg)
            return None, error_msg