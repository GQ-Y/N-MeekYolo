"""
资源监控模块
"""
import psutil
import torch
from typing import Dict
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class ResourceMonitor:
    """资源监控"""
    
    def __init__(self):
        self.cpu_threshold = 0.9
        self.memory_threshold = 0.9
        self.gpu_memory_threshold = 0.9
        
    def get_resource_usage(self) -> Dict:
        """获取资源使用情况"""
        try:
            cpu_percent = psutil.cpu_percent() / 100
            memory = psutil.virtual_memory()
            memory_percent = memory.percent / 100
            
            gpu_memory_percent = 0
            if torch.cuda.is_available():
                gpu_memory = torch.cuda.memory_allocated()
                gpu_memory_total = torch.cuda.get_device_properties(0).total_memory
                gpu_memory_percent = gpu_memory / gpu_memory_total
                
            return {
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent,
                "gpu_memory_percent": gpu_memory_percent
            }
            
        except Exception as e:
            logger.error(f"Get resource usage error: {str(e)}")
            return {
                "cpu_percent": 1,
                "memory_percent": 1,
                "gpu_memory_percent": 1
            }
            
    def has_available_resource(self) -> bool:
        """检查是否有可用资源"""
        usage = self.get_resource_usage()
        
        if usage["cpu_percent"] > self.cpu_threshold:
            logger.warning("CPU usage exceeds threshold")
            return False
            
        if usage["memory_percent"] > self.memory_threshold:
            logger.warning("Memory usage exceeds threshold")
            return False
            
        if torch.cuda.is_available() and usage["gpu_memory_percent"] > self.gpu_memory_threshold:
            logger.warning("GPU memory usage exceeds threshold")
            return False            
        return True 
