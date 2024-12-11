"""
云服务配置模块
"""
from pydantic_settings import BaseSettings
from typing import Dict, Any, Optional, List
from pydantic import BaseModel
import yaml
import os

class DatabaseConfig(BaseModel):
    """数据库配置"""
    url: str = "sqlite:///data/cloud_market.db"

class StorageConfig(BaseModel):
    """存储配置"""
    base_dir: str = "store"
    max_size: int = 1024 * 1024 * 1024  # 1GB
    allowed_formats: list = [".pt", ".pth", ".onnx", ".yaml"]

class ServiceConfig(BaseModel):
    """服务配置"""
    host: str = "0.0.0.0"
    port: int = 8004

class LoggingConfig(BaseModel):
    """日志配置"""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

class AnalysisConfig(BaseModel):
    """分析配置"""
    confidence: float = 0.5
    iou: float = 0.45
    max_det: int = 300
    device: str = "auto"

class OutputConfig(BaseModel):
    """输出配置"""
    save_dir: str = "results"
    save_img: bool = True
    save_txt: bool = False

class ServicesConfig(BaseModel):
    """服��配置组"""
    model: Dict[str, Any]
    analysis: Dict[str, Any]
    api: Dict[str, Any]

class AppSettings(BaseModel):
    """应用配置"""
    title: str = "Cloud Service"
    version: str = "1.0.0"
    description: str = "云服务"
    base_url: str = "http://localhost:8004"

class CloudSettings(BaseSettings):
    """云服务配置"""
    
    PROJECT_NAME: str = "MeekYolo Cloud Service"
    VERSION: str = "1.0.0"
    
    # 服务配置
    SERVICE: ServiceConfig = ServiceConfig()
    SERVICES: Optional[ServicesConfig] = None
    
    # 存储配置
    STORAGE: StorageConfig = StorageConfig()
    
    # 数据库配置
    DATABASE: DatabaseConfig = DatabaseConfig()
    
    # 日志配置
    LOGGING: Optional[LoggingConfig] = None
    
    # 分析配置
    ANALYSIS: Optional[AnalysisConfig] = None
    
    # 输出配置
    OUTPUT: Optional[OutputConfig] = None
    
    # 应用配置 - 使用默认值
    APP: AppSettings = AppSettings()
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"  # 允许额外字段

    @classmethod
    def load_from_yaml(cls):
        """从YAML文件加载配置"""
        # 获取配置文件路径
        config_path = os.getenv("CONFIG_PATH", "config/config.yaml")
        
        # 读取配置文件
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config_dict = yaml.safe_load(f)
                return cls(**config_dict)
        return cls()

# 导出配置实例
settings = CloudSettings.load_from_yaml() 