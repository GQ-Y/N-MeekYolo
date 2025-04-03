"""
模型存储管理器
负责模型文件的存储和管理
"""
import os
import shutil
import yaml
from typing import Dict, Any, List, Optional
from datetime import datetime
from shared.utils.logger import setup_logger
from core.config import settings

logger = setup_logger(__name__)

class ModelStorage:
    """模型存储管理器"""
    
    def __init__(self):
        self.base_dir = settings.STORAGE["base_dir"]
        self.temp_dir = settings.STORAGE["temp_dir"]
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)
        
    async def save_model(self, model_code: str, files: List[Any]) -> Dict[str, Any]:
        """
        保存模型文件
        
        Args:
            model_code: 模型编码
            files: 模型文件列表
            
        Returns:
            Dict: 模型信息
        """
        model_dir = os.path.join(self.base_dir, model_code)
        os.makedirs(model_dir, exist_ok=True)
        
        try:
            saved_files = []
            for file in files:
                # 检查文件���式
                if not any(file.filename.endswith(fmt) 
                          for fmt in settings.STORAGE["allowed_formats"]):
                    raise ValueError(f"Unsupported file format: {file.filename}")
                    
                # 保存文件
                file_path = os.path.join(model_dir, file.filename)
                with open(file_path, "wb") as f:
                    shutil.copyfileobj(file.file, f)
                saved_files.append(file.filename)
                
            # 创建或更新配置文件
            config = {
                "code": model_code,
                "files": saved_files,
                "update_time": datetime.now().isoformat()
            }
            
            config_path = os.path.join(model_dir, "config.yaml")
            with open(config_path, "w") as f:
                yaml.dump(config, f)
                
            return config
            
        except Exception as e:
            # 清理失败的文件
            shutil.rmtree(model_dir, ignore_errors=True)
            raise
            
    async def get_model_info(self, model_code: str) -> Optional[Dict[str, Any]]:
        """获取模型信息"""
        config_path = os.path.join(self.base_dir, model_code, "config.yaml")
        if not os.path.exists(config_path):
            return None
            
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
            
    async def list_models(self, skip: int = 0, limit: int = 10) -> List[Dict[str, Any]]:
        """获取模型列表"""
        models = []
        for model_code in os.listdir(self.base_dir):
            model_info = await self.get_model_info(model_code)
            if model_info:
                models.append(model_info)
                
        # 分页
        return models[skip:skip + limit]
        
    async def delete_model(self, model_code: str) -> bool:
        """删除模型"""
        model_dir = os.path.join(self.base_dir, model_code)
        if os.path.exists(model_dir):
            shutil.rmtree(model_dir)
            return True
        return False 