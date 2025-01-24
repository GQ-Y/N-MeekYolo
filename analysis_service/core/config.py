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
    
    # 服务配置
    class ServiceConfig(BaseModel):
        host: str = "0.0.0.0"
        port: int = 8002
    
    # 模型服务配置
    class ModelServiceConfig(BaseModel):
        url: str = "http://localhost:8003"  # 模型服务地址
        api_prefix: str = "/api/v1"         # API前缀
    
    # 分析配置
    class AnalysisConfig(BaseModel):
        confidence: float = 0.8     # 置信度阈值
        iou: float = 0.45          # IOU阈值
        max_det: int = 300         # 最大检测数量
        device: str = "auto"       # 设备选择 (auto/cpu/cuda)
        
        # 新增配置项
        analyze_interval: int = 1   # 分析间隔(秒)
        alarm_interval: int = 60    # 报警间隔(秒)
        random_interval: List[int] = [0, 0]  # 随机间隔范围(秒)
        push_interval: int = 5      # 推送间隔(秒)
    
    # 存储配置
    class StorageConfig(BaseModel):
        base_dir: str = "data"
        model_dir: str = "models"
        temp_dir: str = "temp"
        max_size: int = 1024 * 1024 * 1024  # 1GB
    
    # 输出配置
    class OutputConfig(BaseModel):
        save_dir: str = "results"    # 结果保存目录
        save_txt: bool = False       # 是否保存文本结果
        save_img: bool = True        # 是否保存图片结果
        return_base64: bool = True   # 是否返回base64图片
    
    # 配置项
    SERVICE: ServiceConfig = ServiceConfig()
    MODEL_SERVICE: ModelServiceConfig = ModelServiceConfig()
    ANALYSIS: AnalysisConfig = AnalysisConfig()
    STORAGE: StorageConfig = StorageConfig()
    OUTPUT: OutputConfig = OutputConfig()
    
    class Config:
        env_file = ".env"
        case_sensitive = True
    
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
    settings = AnalysisServiceConfig.load_config()
    logger.debug(f"Settings loaded successfully: {settings}")
except Exception as e:
    logger.error(f"Failed to load config: {str(e)}")
    raise 