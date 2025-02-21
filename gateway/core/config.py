"""
网关服务配置
"""
from pydantic_settings import BaseSettings
from typing import Dict, Any
from pydantic import BaseModel
import os
import yaml
import logging

logger = logging.getLogger(__name__)

class GatewayServiceConfig(BaseSettings):
    """网关服务配置"""
    
    # 基础信息
    PROJECT_NAME: str = "MeekYolo Gateway"
    VERSION: str = "1.0.0"
    
    # 服务配置
    class ServiceConfig(BaseModel):
        host: str = "0.0.0.0"
        port: int = 8000
    
    # 服务发现配置
    class DiscoveryConfig(BaseModel):
        interval: int = 30  # 服务发现间隔(秒)
        timeout: int = 5    # 请求超时时间(秒)
        retry: int = 3      # 重试次数
    
    # 服务列表配置
    class ServicesConfig(BaseModel):
        api: Dict[str, Any] = {
            "url": "http://localhost:8001",
            "description": "API服务"
        }
        analysis: Dict[str, Any] = {
            "url": "http://localhost:8002",
            "description": "分析服务"
        }
        model: Dict[str, Any] = {
            "url": "http://localhost:8003",
            "description": "模型服务"
        }
        cloud: Dict[str, Any] = {
            "url": "http://localhost:8004",
            "description": "云服务"
        }
    
    # 配置项
    SERVICE: ServiceConfig = ServiceConfig()
    DISCOVERY: DiscoveryConfig = DiscoveryConfig()
    SERVICES: ServicesConfig = ServicesConfig()
    
    class Config:
        env_file = ".env"
        case_sensitive = True
    
    @classmethod
    def load_config(cls) -> "GatewayServiceConfig":
        """加载配置"""
        try:
            config = {}
            
            # 获取配置文件路径
            if "CONFIG_PATH" in os.environ:
                config_path = os.environ["CONFIG_PATH"]
            else:
                # 使用默认配置文件路径
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
    settings = GatewayServiceConfig.load_config()
    logger.debug(f"Settings loaded successfully: {settings}")
except Exception as e:
    logger.error(f"Failed to load config: {str(e)}")
    raise 