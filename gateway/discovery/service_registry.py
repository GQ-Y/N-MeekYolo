"""
服务注册中心
管理服务的注册、注销和健康检查
"""
from typing import Dict, Optional
import asyncio
from datetime import datetime
from shared.utils.logger import setup_logger
from shared.models.base import ServiceInfo
from shared.utils.discovery import ServiceDiscovery

logger = setup_logger(__name__)

class ServiceRegistry:
    """服务注册中心"""
    
    def __init__(self):
        self.services: Dict[str, ServiceInfo] = {}
        self.discovery = ServiceDiscovery()
        self.health_check_interval = 30  # 健康检查间隔(秒)
        
    async def register_service(self, service_info: ServiceInfo) -> bool:
        """注册服务"""
        try:
            self.services[service_info.name] = service_info
            logger.info(f"Service registered: {service_info.name}")
            return True
        except Exception as e:
            logger.error(f"Failed to register service {service_info.name}: {str(e)}")
            return False
            
    async def deregister_service(self, service_name: str) -> bool:
        """注销服务"""
        try:
            if service_name in self.services:
                del self.services[service_name]
                logger.info(f"Service deregistered: {service_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to deregister service {service_name}: {str(e)}")
            return False
            
    async def get_service(self, service_name: str) -> Optional[ServiceInfo]:
        """获取服务信息"""
        return self.services.get(service_name)
        
    async def start_health_check(self):
        """启动健康检查循环"""
        while True:
            try:
                for service_name in list(self.services.keys()):
                    is_healthy = await self.discovery.check_service_health(service_name)
                    if not is_healthy:
                        logger.warning(f"Service {service_name} is unhealthy")
                        self.services[service_name].status = "unhealthy"
                    else:
                        self.services[service_name].status = "healthy"
                        
            except Exception as e:
                logger.error(f"Health check error: {str(e)}")
                
            await asyncio.sleep(self.health_check_interval)

# 创建全局服务注册中心实例
service_registry = ServiceRegistry() 