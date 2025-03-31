"""
配置模块
"""
from pydantic_settings import BaseSettings
from typing import Dict, List, Optional
from pydantic import BaseModel
import os
import yaml

class CloudServiceConfig(BaseSettings):
    """云服务配置"""
    
    # 基础信息
    PROJECT_NAME: str = "MeekYolo Cloud Service"
    VERSION: str = "1.0.0"
    
    # 存储配置
    class StorageConfig(BaseModel):
        base_dir: str = "models"
        max_size: int = 1024 * 1024 * 1024  # 1GB
        allowed_formats: List[str] = [".pt", ".pth", ".onnx", ".yaml"]
    
    # 数据库配置
    class DatabaseConfig(BaseModel):
        url: str = "sqlite:///data/cloud_service.db"
    
    # 服务配置
    class ServiceConfig(BaseModel):
        host: str = "0.0.0.0"
        port: int = 8004
        base_url: str = "http://cloud-service:8004"
        debug: bool = False
    
    # 日志配置
    class LoggingConfig(BaseModel):
        level: str = "INFO"
        format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # CORS配置
    class CORSConfig(BaseModel):
        allow_origins: List[str] = ["*"]
        allow_methods: List[str] = ["*"]
        allow_headers: List[str] = ["*"]
        allow_credentials: bool = True
    
    # 安全配置
    class SecurityConfig(BaseModel):
        allowed_hosts: List[str] = ["*"]
        api_key_header: str = "X-API-Key"
        rate_limit: str = "5/minute"
        ssl_enabled: bool = False
        ssl_cert_file: Optional[str] = None
        ssl_key_file: Optional[str] = None
    
    # 配置项
    SERVICE: ServiceConfig = ServiceConfig()
    STORAGE: StorageConfig = StorageConfig()
    DATABASE: DatabaseConfig = DatabaseConfig()
    LOGGING: LoggingConfig = LoggingConfig()
    CORS: CORSConfig = CORSConfig()
    SECURITY: SecurityConfig = SecurityConfig()
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        # 允许额外字段
        extra = "ignore"  # 忽略配置文件中的额外字段
    
    def get_model_dir(self, model_code: str) -> str:
        """获取模型目录"""
        base_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            self.STORAGE.base_dir
        )
        return os.path.join(base_dir, model_code)
    
    @classmethod
    def load_config(cls) -> "CloudServiceConfig":
        """加载配置"""
        # 加载配置
        config = {}
        
        # 从配置文件加载
        config_path = os.getenv("CONFIG_PATH", "cloud_service/config/config.yaml")
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config.update(yaml.safe_load(f))
        
        return cls(**config)

# 加载配置
try:
    settings = CloudServiceConfig.load_config()
except Exception as e:
    import logging
    logging.error(f"Failed to load config: {str(e)}")
    raise