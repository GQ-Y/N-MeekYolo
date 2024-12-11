"""
配置
"""
import os
from pydantic_settings import BaseSettings
from pydantic import BaseModel

class DatabaseConfig(BaseModel):
    """数据库配置"""
    url: str = "sqlite:///data/model_service.db"

class MarketConfig(BaseModel):
    """市场配置"""
    base_url: str = "http://localhost:8004"

class Settings(BaseSettings):
    """配置"""
    
    PROJECT_NAME: str = "Model Service"
    VERSION: str = "1.0.0"
    
    # 组件配置
    DATABASE: DatabaseConfig = DatabaseConfig()
    MARKET: MarketConfig = MarketConfig()
    
    class Config:
        env_file = ".env"

settings = Settings() 