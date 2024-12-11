"""
服务发现工具
"""
import aiohttp
from typing import Dict, Optional
from shared.utils.logger import setup_logger
from shared.utils.load_balancer import (
    LoadBalancer,
    LoadBalanceStrategy,
    ServiceInstance
)
from shared.models.base import ServiceInfo
from datetime import datetime

logger = setup_logger(__name__)

class ServiceDiscovery:
    """服务发现类"""
    
    def __init__(self):
        self.load_balancers: Dict[str, LoadBalancer] = {}
        
    def register_service(self, service_name: str, instance: ServiceInstance) -> None:
        """注册服务实例"""
        if service_name not in self.load_balancers:
            self.load_balancers[service_name] = LoadBalancer(
                strategy=LoadBalanceStrategy.ROUND_ROBIN
            )
        
        self.load_balancers[service_name].add_instance(instance)
        logger.info(f"Registered service instance: {service_name}/{instance.id}")
        
    def deregister_service(self, service_name: str, instance_id: str) -> None:
        """注销服务实例"""
        if service_name in self.load_balancers:
            self.load_balancers[service_name].remove_instance(instance_id)
            logger.info(f"Deregistered service instance: {service_name}/{instance_id}")
            
    async def get_service_url(self, service_name: str) -> Optional[str]:
        """获取服务URL"""
        if service_name not in self.load_balancers:
            return None
            
        instance = self.load_balancers[service_name].get_instance()
        if not instance:
            return None
            
        # 更新访问信息
        instance.last_access = datetime.now()
        instance.active_connections += 1
        
        return f"http://{instance.host}:{instance.port}"
        
    def release_connection(self, service_name: str, instance_id: str) -> None:
        """释放连接计数"""
        if service_name in self.load_balancers:
            instance = self.load_balancers[service_name].instances.get(instance_id)
            if instance and instance.active_connections > 0:
                instance.active_connections -= 1 
        
    async def check_service_health(self, url: str) -> bool:
        """检查服务健康状态"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{url}/health", timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("status") == "healthy"
            return False
        except Exception as e:
            logger.error(f"Health check failed for {url}: {str(e)}")
            return False
            
    async def get_service_info(self, url: str) -> Optional[ServiceInfo]:
        """获取服务信息"""
        try:
            # 先检查健康状态
            is_healthy = await self.check_service_health(url)
            if not is_healthy:
                logger.warning(f"Service at {url} is not healthy")
                return None
            
            # 创建基本的服务信息
            service_name = self._get_service_name(url)
            service_info = ServiceInfo(
                name=service_name,
                url=url,
                status="healthy",
                started_at=datetime.now()
            )
            
            try:
                # 尝试获取更多信息
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{url}/openapi.json") as response:
                        if response.status == 200:
                            openapi = await response.json()
                            info = openapi.get("info", {})
                            service_info.description = info.get("description")
                            service_info.version = info.get("version")
                            
                logger.info(f"Created service info for {service_name}: {service_info}")
                return service_info
                
            except Exception as e:
                logger.warning(f"Failed to get OpenAPI info from {url}: {str(e)}")
                # 继续使用基本信息
                return service_info
                
        except Exception as e:
            logger.error(f"Failed to get service info from {url}: {str(e)}")
            return None
            
    def _get_service_name(self, url: str) -> str:
        """从URL获取服务名称"""
        if ":8001" in url:
            return "api"
        elif ":8002" in url:
            return "model"
        elif ":8003" in url:
            return "analysis"
        elif ":8004" in url:
            return "cloud"
        else:
            return "unknown"