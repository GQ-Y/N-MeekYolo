"""
API服务配置
"""
from pydantic_settings import BaseSettings
from typing import Dict, List, Optional
from pydantic import BaseModel
import os
import yaml
import logging

logger = logging.getLogger(__name__)

class APIServiceConfig(BaseSettings):
    """API服务配置"""
    
    # 基础信息
    PROJECT_NAME: str = "MeekYolo API Service"
    VERSION: str = "1.0.0"
    
    # 服务配置
    class ServiceConfig(BaseModel):
        host: str = "0.0.0.0"
        port: int = 8001
    
    # 分析服务配置
    class AnalysisServiceConfig(BaseModel):
        url: str = "http://localhost:8002"  # 分析服务地址
        api_prefix: str = "/api/v1"         # API前缀
    
    # 模型服务配置
    class ModelServiceConfig(BaseModel):
        url: str = "http://localhost:8003"  # 模型服务地址
        api_prefix: str = "/api/v1"         # API前缀
    
    # 数据库配置
    class DatabaseConfig(BaseModel):
        url: str = "sqlite:///data/api_service.db"
        dir: str = "data"
        name: str = "api_service.db"
    
    # 默认分组配置
    class DefaultGroupConfig(BaseModel):
        name: str = "默认分组"
        description: str = "系统默认分组"
    
    # 配置项
    SERVICE: ServiceConfig = ServiceConfig()
    ANALYSIS_SERVICE: AnalysisServiceConfig = AnalysisServiceConfig()
    MODEL_SERVICE: ModelServiceConfig = ModelServiceConfig()
    DATABASE: DatabaseConfig = DatabaseConfig()
    DEFAULT_GROUP: DefaultGroupConfig = DefaultGroupConfig()
    
    class Config:
        env_file = ".env"
        case_sensitive = True
    
    @classmethod
    def load_config(cls) -> "APIServiceConfig":
        """加载配置"""
        try:
            config = {}
            
            # 获取配置文件路径
            if "CONFIG_PATH" in os.environ:
                config_path = os.environ["CONFIG_PATH"]
            else:
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
    settings = APIServiceConfig.load_config()
    logger.debug(f"Settings loaded successfully: {settings}")
except Exception as e:
    logger.error(f"Failed to load config: {str(e)}")
    raise 