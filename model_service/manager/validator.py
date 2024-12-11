"""
模型验证器
负责模型文件和参数的验证
"""
import os
import yaml
from typing import Dict, Any, List, Tuple
from shared.utils.logger import setup_logger
from model_service.core.config import settings

logger = setup_logger(__name__)

class ModelValidator:
    """模型验证器"""
    
    def __init__(self):
        self.required_files = ['best.pt', 'data.yaml']
        self.allowed_formats = settings.STORAGE["allowed_formats"]
        
    async def validate_files(self, files: List[Any]) -> Tuple[bool, str, List[str]]:
        """
        验证上传的文件
        
        Args:
            files: 上传的文件列表
            
        Returns:
            Tuple[bool, str, List[str]]: (是否有效, 错误信息, 有效文件列表)
        """
        if not files:
            return False, "没有上传任何文件", []
            
        # 检查文件格式
        valid_files = []
        for file in files:
            if not file or not file.filename:
                continue
                
            if not any(file.filename.endswith(fmt) for fmt in self.allowed_formats):
                return False, f"不支持的文件格式: {file.filename}", []
                
            valid_files.append(file.filename)
            
        if not valid_files:
            return False, "没有有效的文件", []
            
        # 检查必需文件
        has_pt = any(f.endswith('.pt') for f in valid_files)
        has_yaml = any(f.endswith('.yaml') for f in valid_files)
        
        missing = []
        if not has_pt:
            missing.append(".pt模型文件")
        if not has_yaml:
            missing.append("YAML配置文件")
            
        if missing:
            return False, f"缺少必需的文件: {', '.join(missing)}", valid_files
            
        return True, "", valid_files
        
    async def validate_config(self, data_yaml_path: str) -> Tuple[bool, str, Dict[str, Any]]:
        """
        验证模型配置
        
        Args:
            data_yaml_path: data.yaml文件路径
            
        Returns:
            Tuple[bool, str, Dict]: (是否有效, 错误信息, 配置数据)
        """
        try:
            if not os.path.exists(data_yaml_path):
                return False, "配置文件不存在", {}
                
            with open(data_yaml_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                
            # 检查必需字段
            required_fields = ['nc', 'names']
            missing = [field for field in required_fields if field not in config]
            if missing:
                return False, f"配置缺少必需字段: {', '.join(missing)}", config
                
            # 验证类别数量和名称
            if not isinstance(config['nc'], int) or config['nc'] <= 0:
                return False, "无效的类别数量", config
                
            if not isinstance(config['names'], dict) or len(config['names']) != config['nc']:
                return False, "类别名称配置无效", config
                
            return True, "", config
            
        except Exception as e:
            logger.error(f"验证配置失败: {str(e)}")
            return False, f"验证配置失败: {str(e)}", {} 