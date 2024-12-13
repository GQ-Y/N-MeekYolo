"""
分析服务配置
"""
from shared.config.settings import Settings
from typing import Dict, Any

class AnalysisSettings(Settings):
    """分析服务配置"""
    
    PROJECT_NAME: str = "MeekYolo Analysis Service"
    
    # 模型配置
    MODEL: Dict[str, Any] = {
        "default_model": "/models/yolo/yolov11.pt",  # 默认模型路径
        "store_dir": "/store"  # model_service的模型存储目录
    }
    
    # 服务配置
    SERVICES: Dict[str, Dict[str, Any]] = {
        "model": {
            "host": "localhost",
            "port": 8003
        }
    }
    
    # 分析配置
    ANALYSIS: Dict[str, Any] = {
        "confidence": 0.5,     # 置信度阈值
        "iou": 0.45,          # IOU阈值
        "max_det": 300,       # 最大检测数量
        "device": "auto"      # 设备选择 (auto/cpu/cuda)
    }
    
    # RTSP配置
    RTSP: Dict[str, Any] = {
        "timeout": 5,         # 连接超时时间
        "retry_interval": 5,  # 重试间隔
        "max_retries": 3     # 最大重试次数
    }
    
    # 输出配置
    OUTPUT: Dict[str, Any] = {
        "save_dir": "results",  # 结果保存目录
        "save_txt": False,      # 是否保存文本结果
        "save_img": True,      # 是否保存图片结果
        "return_base64": True  # 是否在回调中返回base64图片
    }

    class Config:
        env_file = ".env"
        extra = "allow"

settings = AnalysisSettings.load_from_yaml() 