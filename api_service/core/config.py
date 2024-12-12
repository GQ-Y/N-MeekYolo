"""
配置模块
"""
from typing import Dict, List, Optional, ClassVar
from pydantic_settings import BaseSettings
from pydantic import BaseModel
import os

class ServiceConfig(BaseModel):
    """服务配置"""
    host: str
    port: int

class ServicesConfig(BaseModel):
    """所有服务配置"""
    model: ServiceConfig = ServiceConfig(
        host="localhost",
        port=8003
    )
    analysis: ServiceConfig
    api: ServiceConfig
    gateway: ServiceConfig
    cloud: ServiceConfig

class StorageConfig(BaseModel):
    """存储配置"""
    base_dir: str
    model_dir: str
    temp_dir: str
    max_size: int
    allowed_formats: List[str]

class AnalysisConfig(BaseModel):
    """分析配置"""
    confidence: float
    iou: float
    max_det: int
    device: str

class OutputConfig(BaseModel):
    """输出配置"""
    save_dir: str
    save_img: bool
    save_txt: bool

class LoggingConfig(BaseModel):
    """日志配置"""
    level: str
    format: str

class Settings(BaseSettings):
    """应用配置"""
    PROJECT_NAME: str = "MeekYolo Service"
    VERSION: str = "1.0.0"
    
    # 数据库配置 - 使用相对路径 api_service 的路径
    DATABASE_DIR: str = "data"  # api_service/data 目录
    DATABASE_NAME: str = "api_service.db"
    
    # 默认分组配置 - 添加 ClassVar 类型注解
    DEFAULT_GROUP: ClassVar[Dict[str, str]] = {
        "name": "默认分组",
        "description": "系统默认分组"
    }
    
    @property
    def DATABASE_URL(self) -> str:
        # 获取 api_service 目录的绝对路径
        api_service_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # 构建数据库目录的绝对路径
        db_dir = os.path.join(api_service_dir, self.DATABASE_DIR)
        # 确保数据目录存在
        os.makedirs(db_dir, exist_ok=True)
        # 构建数据库文件的绝对路径
        db_path = os.path.join(db_dir, self.DATABASE_NAME)
        return f"sqlite:///{db_path}"
    
    # 其他配置
    SERVICES: ServicesConfig
    STORAGE: StorageConfig
    ANALYSIS: AnalysisConfig
    OUTPUT: OutputConfig
    LOGGING: LoggingConfig

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

# 加载配置
def load_config() -> Settings:
    """加载配置"""
    import os
    import yaml
    
    # 获取配置文件路径
    config_path = os.getenv("CONFIG_PATH", "config/config.yaml")
    
    # 读取配置文件
    with open(config_path, "r", encoding="utf-8") as f:
        config_dict = yaml.safe_load(f)
    
    # 创建配置对象
    return Settings(**config_dict)

# 导出配置实例
settings = load_config() 