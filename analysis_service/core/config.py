"""
分析服务配置
"""
from pydantic_settings import BaseSettings
from typing import Dict, Any, List
from pydantic import BaseModel
import os
import yaml
import logging

logger = logging.getLogger(__name__)

class AnalysisServiceConfig(BaseSettings):
    """分析服务配置"""
    
    # 基础信息
    PROJECT_NAME: str = "MeekYolo Analysis Service"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"  # 环境: development, production, testing
    DEBUG: bool = True  # 调试模式
    
    # CORS配置
    CORS_ORIGINS: List[str] = ["*"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]
    
    # 服务配置
    class ServiceConfig(BaseModel):
        host: str = "0.0.0.0"
        port: int = 8002
    
    # 模型服务配置
    class ModelServiceConfig(BaseModel):
        url: str = "http://model-service:8003"
        api_prefix: str = "/api/v1"
    
    # 分析配置
    class AnalysisConfig(BaseModel):
        confidence: float = 0.1
        iou: float = 0.45
        max_det: int = 300
        device: str = "auto"
        analyze_interval: int = 1
        alarm_interval: int = 60
        random_interval: List[int] = [0, 0]
        push_interval: int = 5
    
    # 存储配置
    class StorageConfig(BaseModel):
        base_dir: str = "data"
        model_dir: str = "models"
        temp_dir: str = "temp"
        max_size: int = 1073741824  # 1GB
    
    # 输出配置
    class OutputConfig(BaseModel):
        save_dir: str = "results"
        save_txt: bool = False
        save_img: bool = True
        return_base64: bool = True
    
    # 服务发现配置
    class DiscoveryConfig(BaseModel):
        interval: int = 30
        timeout: int = 5
        retry: int = 3
    
    # 服务配置
    class ServicesConfig(BaseModel):
        host: str = "0.0.0.0"
        port: int = 8002
    
    # 配置实例
    SERVICE: ServiceConfig = ServiceConfig()
    MODEL_SERVICE: ModelServiceConfig = ModelServiceConfig()
    ANALYSIS: AnalysisConfig = AnalysisConfig()
    STORAGE: StorageConfig = StorageConfig()
    OUTPUT: OutputConfig = OutputConfig()
    DISCOVERY: DiscoveryConfig = DiscoveryConfig()
    SERVICES: ServicesConfig = ServicesConfig()
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"  # 允许额外的字段
    
    @classmethod
    def load_config(cls) -> "AnalysisServiceConfig":
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
                    config_content = f.read()
                    logger.debug(f"Config content:\n{config_content}")
                    config.update(yaml.safe_load(config_content))
            else:
                logger.warning(f"Config file not found: {config_path}, using default values")
            
            logger.debug(f"Final config dict: {config}")
            return cls(**config)
            
        except Exception as e:
            logger.error(f"Failed to load config: {str(e)}")
            raise

# 加载配置
try:
    settings = AnalysisServiceConfig.load_config()
    logger.debug(f"Settings loaded successfully: {settings}")
except Exception as e:
    logger.error(f"Failed to load config: {str(e)}")
    raise 