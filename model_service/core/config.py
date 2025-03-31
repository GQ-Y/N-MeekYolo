"""
配置模块
"""
from pydantic_settings import BaseSettings
from typing import Dict, List, Optional
from pydantic import BaseModel
import os
import yaml
import logging

logger = logging.getLogger(__name__)

class ModelServiceConfig(BaseSettings):
    """模型服务配置"""
    
    # 基础信息
    PROJECT_NAME: str = "MeekYolo Model Service"
    VERSION: str = "1.0.0"
    
    # CORS配置
    ALLOWED_HOSTS: List[str] = ["*"]
    CORS_ORIGINS: List[str] = ["*"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]
    
    # 服务配置
    class ServiceConfig(BaseModel):
        host: str = "0.0.0.0"
        port: int = 8003
    
    # 存储配置
    class StorageConfig(BaseModel):
        base_dir: str = "models"
        max_size: int = 1024 * 1024 * 1024  # 1GB
        allowed_formats: List[str] = [".pt", ".pth", ".onnx", ".yaml"]
    
    # 数据库配置
    class DatabaseConfig(BaseModel):
        url: str = "sqlite:///data/model_service.db"
    
    # 日志配置
    class LoggingConfig(BaseModel):
        level: str = "INFO"
        format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # 云服务配置
    class CloudConfig(BaseModel):
        url: str = "http://localhost:8004"  # 云服务地址
        api_prefix: str = "/api/v1"         # API前缀
    
    # 配置项
    SERVICE: ServiceConfig = ServiceConfig()
    STORAGE: StorageConfig = StorageConfig()
    DATABASE: DatabaseConfig = DatabaseConfig()
    LOGGING: LoggingConfig = LoggingConfig()
    CLOUD: CloudConfig = CloudConfig()
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"
    
    @classmethod
    def load_config(cls) -> "ModelServiceConfig":
        """加载配置"""
        try:
            # 加载配置
            config = {}
            
            # 获取配置文件路径
            # 1. 优先使用环境变量
            # 2. 如果没有环境变量，使用相对于当前文件的路径
            if "CONFIG_PATH" in os.environ:
                config_path = os.environ["CONFIG_PATH"]
            else:
                # 获取当前文件所在目录
                current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                config_path = os.path.join(current_dir, "config", "config.yaml")
            
            logger.debug(f"Loading config from: {config_path}")
            
            if os.path.exists(config_path):
                logger.debug(f"Config file exists: {config_path}")
                with open(config_path, "r", encoding="utf-8") as f:
                    config.update(yaml.safe_load(f))
                    logger.debug(f"Loaded config: {config}")
            else:
                logger.warning(f"Config file not found: {config_path}, using default values")
            
            return cls(**config)
        except Exception as e:
            logger.error(f"Failed to load config: {str(e)}")
            raise

# 加载配置
try:
    settings = ModelServiceConfig.load_config()
    logger.debug(f"Settings loaded successfully: {settings}")
except Exception as e:
    logger.error(f"Failed to load config: {str(e)}")
    raise 