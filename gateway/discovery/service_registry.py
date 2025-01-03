"""
服务注册中心
"""
from typing import Dict, Optional, List
import asyncio
import aiohttp
from datetime import datetime
from shared.models.base import ServiceInfo
from gateway.core.config import settings
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class ServiceRegistry:
    """服务注册中心"""
    
    def __init__(self):
        self.services: Dict[str, ServiceInfo] = {}
        self.stats: Dict[str, Dict] = {}
        self.is_running = False
    
    async def discover_services(self):
        """发现服务"""
        # 获取所有服务配置
        services_config = settings.SERVICES.model_dump()
        
        for name, config in services_config.items():
            if not isinstance(config, dict):
                continue
                
            url = config["url"]
            description = config.get("description", "")
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{url}/health",
                        timeout=settings.DISCOVERY.timeout
                    ) as response:
                        if response.status == 200:
                            service = ServiceInfo(
                                name=name,
                                url=url,
                                description=description,
                                status="healthy",
                                started_at=datetime.now()
                            )
                            await self.register_service(service)
                            logger.info(f"Discovered service: {name} at {url}")
                        else:
                            logger.warning(f"Service {name} health check failed: {response.status}")
                            
            except Exception as e:
                logger.error(f"Failed to discover service {name}: {str(e)}")
    
    async def register_service(self, service: ServiceInfo) -> bool:
        """注册服务"""
        try:
            self.services[service.name] = service
            logger.info(f"Registered service: {service.name}")
            return True
        except Exception as e:
            logger.error(f"Failed to register service: {str(e)}")
            return False
    
    async def get_all_services(self) -> List[Dict]:
        """获取所有服务信息"""
        try:
            services_list = []
            for name, service in self.services.items():
                # 获取服务统计信息
                stats = self.stats.get(name, {
                    "total_requests": 0,
                    "success_rate": 1.0,
                    "avg_response_time": 0.0
                })
                
                # 构建服务响应
                service_info = {
                    "name": service.name,
                    "url": service.url,
                    "status": service.status,
                    "uptime": (datetime.now() - service.started_at).total_seconds() if service.started_at else None,
                    "total_requests": stats["total_requests"],
                    "success_rate": stats["success_rate"],
                    "avg_response_time": stats["avg_response_time"]
                }
                services_list.append(service_info)
                
            return services_list
            
        except Exception as e:
            logger.error(f"Failed to get services: {str(e)}")
            raise
    
    async def get_service(self, service_name: str) -> Optional[ServiceInfo]:
        """获取服务信息"""
        return self.services.get(service_name)
    
    async def get_service_stats(self, service_name: str) -> Dict:
        """获取服务统计信息"""
        return self.stats.get(service_name, {
            "total_requests": 0,
            "success_requests": 0,
            "failed_requests": 0,
            "avg_response_time": 0.0,
            "status": "unknown",
            "uptime": None
        })
    
    async def start_health_check(self):
        """启动健康检查"""
        self.is_running = True
        while self.is_running:
            try:
                await self.discover_services()
            except Exception as e:
                logger.error(f"Health check failed: {str(e)}")
            finally:
                await asyncio.sleep(settings.DISCOVERY.interval)
    
    async def stop(self):
        """停止服务"""
        self.is_running = False

# 创建全局实例
service_registry = ServiceRegistry() 