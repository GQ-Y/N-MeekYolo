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
        self.cpu_threshold = 0.95
        self.memory_threshold = 0.95
        self.gpu_memory_threshold = 0.95
        
    def get_resource_usage(self) -> Dict:
        """获取资源使用情况"""
        try:
            cpu_percent = sum(psutil.cpu_percent(interval=0.1, percpu=True)) / psutil.cpu_count() / 100
            
            memory = psutil.virtual_memory()
            memory_percent = memory.percent / 100
            
            gpu_memory_percent = 0
            if torch.cuda.is_available():
                gpu_memory = torch.cuda.memory_allocated()
                gpu_memory_total = torch.cuda.get_device_properties(0).total_memory
                gpu_memory_percent = gpu_memory / gpu_memory_total
                
            logger.debug(f"资源使用情况:")
            logger.debug(f"  - CPU: {cpu_percent*100:.1f}%")
            logger.debug(f"  - 内存: {memory_percent*100:.1f}%")
            logger.debug(f"  - GPU内存: {gpu_memory_percent*100:.1f}%")
                
            return {
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent,
                "gpu_memory_percent": gpu_memory_percent
            }
            
        except Exception as e:
            logger.error(f"获取资源使用情况失败: {str(e)}", exc_info=True)
            return {
                "cpu_percent": 1,
                "memory_percent": 1,
                "gpu_memory_percent": 1
            }
            
    def has_available_resource(self) -> bool:
        """检查是否有可用资源"""
        usage = self.get_resource_usage()
        
        if usage["cpu_percent"] > self.cpu_threshold:
            logger.warning(f"CPU使用率超过阈值: {usage['cpu_percent']*100:.1f}% > {self.cpu_threshold*100}%")
            return False
            
        if usage["memory_percent"] > self.memory_threshold:
            logger.warning(f"内存使用率超过阈值: {usage['memory_percent']*100:.1f}% > {self.memory_threshold*100}%")
            return False
            
        if torch.cuda.is_available() and usage["gpu_memory_percent"] > self.gpu_memory_threshold:
            logger.warning(f"GPU内存使用率超过阈值: {usage['gpu_memory_percent']*100:.1f}% > {self.gpu_memory_threshold*100}%")
            return False
            
        logger.info("资源检查通过")
        return True
