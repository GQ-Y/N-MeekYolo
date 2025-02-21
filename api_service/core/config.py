"""
API服务配置
"""
from pydantic_settings import BaseSettings
from typing import Dict, Any, Optional
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
        url: str = "http://analysis-service:8002"
        api_prefix: str = "/api/v1"
    
    # 模型服务配置
    class ModelServiceConfig(BaseModel):
        url: str = "http://model-service:8003"
        api_prefix: str = "/api/v1"
    
    # 数据库配置
    class DatabaseConfig(BaseModel):
        url: str = "sqlite:///data/api_service.db"
        dir: str = "data"
        name: str = "api_service.db"
    
    # 默认分组配置
    class DefaultGroupConfig(BaseModel):
        name: str = "默认分组"
        description: str = "系统默认分组"
    
    # 服务发现配置
    class DiscoveryConfig(BaseModel):
        interval: int = 30
        timeout: int = 5
        retry: int = 3
    
    # 服务列表配置
    class ServicesConfig(BaseModel):
        api: Dict[str, Any] = {
            "url": "http://api-service:8001",
            "description": "API服务"
        }
        analysis: Dict[str, Any] = {
            "url": "http://analysis-service:8002",
            "description": "分析服务"
        }
        model: Dict[str, Any] = {
            "url": "http://model-service:8003",
            "description": "模型服务"
        }
        cloud: Dict[str, Any] = {
            "url": "http://cloud-service:8004",
            "description": "云服务"
        }
    
    # 配置项
    SERVICE: ServiceConfig = ServiceConfig()
    ANALYSIS_SERVICE: AnalysisServiceConfig = AnalysisServiceConfig()
    MODEL_SERVICE: ModelServiceConfig = ModelServiceConfig()
    DATABASE: DatabaseConfig = DatabaseConfig()
    DEFAULT_GROUP: DefaultGroupConfig = DefaultGroupConfig()
    DISCOVERY: DiscoveryConfig = DiscoveryConfig()
    SERVICES: ServicesConfig = ServicesConfig()
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        # 允许额外字段
        extra = "allow"  # 允许配置文件中的额外字段
    
    @classmethod
    def load_config(cls) -> "APIServiceConfig":
        """加载配置"""
        try:
            config = {}
            
            # 获取配置文件路径
            if "CONFIG_PATH" in os.environ:
                config_path = os.environ["CONFIG_PATH"]
            else:
                config_path = "/app/config/config.yaml"
            
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