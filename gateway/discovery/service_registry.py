"""
服务注册中心
管理服务的注册、注销和健康检查
"""
from typing import Dict, List, Optional
import asyncio
from datetime import datetime
from pydantic import BaseModel, Field
from shared.utils.logger import setup_logger
from shared.models.base import ServiceInfo
from shared.utils.discovery import ServiceDiscovery
from shared.utils.load_balancer import ServiceInstance

logger = setup_logger(__name__)

class ServiceStats(BaseModel):
    """服务统计信息"""
    total_requests: int = Field(default=0, description="总请求数")
    success_requests: int = Field(default=0, description="成功请求数")
    failed_requests: int = Field(default=0, description="失败请求数")
    last_success: Optional[datetime] = Field(default=None, description="最后成功时间")
    last_failure: Optional[datetime] = Field(default=None, description="最后失败时间")
    avg_response_time: float = Field(default=0.0, description="平均响应时间")
    status: str = Field(default="unknown", description="服务状态")
    uptime: Optional[float] = Field(default=None, description="运行时间")

    class Config:
        from_attributes = True

class ServiceRegistry:
    """服务注册中心"""
    
    def __init__(self):
        self.services: Dict[str, ServiceInfo] = {}
        self.stats: Dict[str, ServiceStats] = {}
        self.discovery = ServiceDiscovery()
        self.health_check_interval = 30
        self._last_discovery = None
        
    async def register_service(self, service_info: ServiceInfo) -> bool:
        """注册服务"""
        try:
            logger.info(f"Attempting to register service: {service_info}")
            
            # 验证服务是否可访问
            is_healthy = await self.discovery.check_service_health(service_info.url)
            if not is_healthy:
                logger.warning(f"Service {service_info.name} is not healthy")
                return False
                
            # 更新或添加服务
            self.services[service_info.name] = service_info
            
            # 确保统计信息存在
            if service_info.name not in self.stats:
                self.stats[service_info.name] = ServiceStats()
            
            # 更新状态
            self.stats[service_info.name].status = "healthy"
            
            # 注册到负载均衡器
            host, port = self._parse_url(service_info.url)
            instance = ServiceInstance(
                id=f"{host}:{port}",
                host=host,
                port=port
            )
            self.discovery.register_service(service_info.name, instance)
            
            logger.info(f"Successfully registered service: {service_info.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register service {service_info.name}: {str(e)}")
            return False
            
    async def deregister_service(self, service_name: str) -> bool:
        """注销服务"""
        try:
            if service_name in self.services:
                del self.services[service_name]
                del self.stats[service_name]
                logger.info(f"Service deregistered: {service_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to deregister service {service_name}: {str(e)}")
            return False
            
    async def get_service(self, service_name: str) -> Optional[ServiceInfo]:
        """获取服务信息"""
        try:
            service = self.services.get(service_name)
            if service:
                return ServiceInfo.model_validate(service)
            return None
        except Exception as e:
            logger.error(f"Error getting service {service_name}: {str(e)}")
            return None
        
    async def get_service_stats(self, service_name: str) -> Dict:
        """获取服务统计信息"""
        try:
            if service_name not in self.stats:
                self.stats[service_name] = ServiceStats()
            
            stats = self.stats[service_name]
            
            # 更新服务状态
            service = self.services.get(service_name)
            if service:
                stats.status = service.status
                if service.started_at:
                    stats.uptime = (datetime.now() - service.started_at).total_seconds()
            
            # 转换为字典
            return stats.model_dump()
        except Exception as e:
            logger.error(f"Error getting service stats for {service_name}: {str(e)}")
            return ServiceStats().model_dump()  # 返回默认统计信息字典
        
    async def get_all_services(self) -> List[Dict]:
        """获取所有服务信息"""
        try:
            result = []
            for name, service in self.services.items():
                stats = await self.get_service_stats(name)
                success_rate = (stats["success_requests"] / stats["total_requests"] 
                              if stats["total_requests"] > 0 else 0.0)
                
                result.append({
                    "name": service.name,
                    "url": service.url,
                    "status": service.status,
                    "uptime": stats["uptime"],
                    "total_requests": stats["total_requests"],
                    "success_rate": success_rate,
                    "avg_response_time": stats["avg_response_time"]
                })
            return result
        except Exception as e:
            logger.error(f"Error getting all services: {str(e)}")
            return []
        
    async def discover_services(self):
        """自动发现服务"""
        try:
            logger.info("Starting service discovery...")
            # 扫描常用端口查找服务
            ports = [8001, 8002, 8003, 8004]
            for port in ports:
                url = f"http://localhost:{port}"
                try:
                    logger.debug(f"Checking service at {url}")
                    is_healthy = await self.discovery.check_service_health(url)
                    if is_healthy:
                        logger.info(f"Found healthy service at {url}")
                        # 获取服务信息
                        info = await self.discovery.get_service_info(url)
                        # 添加详细日志
                        logger.info(f"Service info from {url}:")
                        logger.info(f"  - Name: {info.name if info else 'None'}")
                        logger.info(f"  - URL: {info.url if info else 'None'}")
                        logger.info(f"  - Description: {info.description if info else 'None'}")
                        logger.info(f"  - Status: {info.status if info else 'None'}")
                        logger.info(f"  - Started at: {info.started_at if info else 'None'}")
                        logger.info(f"  - Raw response: {info}")
                        
                        if info and info.name not in self.services:
                            logger.info(f"Registering new service: {info.name} at {url}")
                            await self.register_service(info)
                        elif not info:
                            logger.warning(f"Got empty service info from {url}")
                        elif info.name in self.services:
                            logger.info(f"Service {info.name} already registered")
                    else:
                        logger.warning(f"Service at {url} is not healthy")
                except Exception as e:
                    logger.error(f"Error checking service at {url}: {str(e)}")
                    logger.exception("Full traceback:")
                    continue
                    
            self._last_discovery = datetime.now()
            logger.info("Service discovery completed")
            
        except Exception as e:
            logger.error(f"Service discovery failed: {str(e)}")
            logger.exception("Full traceback:")
            
    async def update_service_stats(self, service_name: str, response_time: float, success: bool):
        """更新服务统计信息"""
        if service_name in self.stats:
            stats = self.stats[service_name]
            stats.total_requests += 1
            if success:
                stats.success_requests += 1
                stats.last_success = datetime.now()
            else:
                stats.failed_requests += 1
                stats.last_failure = datetime.now()
            
            # 更新平均响应时间
            stats.avg_response_time = (
                (stats.avg_response_time * (stats.total_requests - 1) + response_time)
                / stats.total_requests
            )
            
    async def start_health_check(self):
        """动健康检查循环"""
        while True:
            try:
                # 自动发现服务
                await self.discover_services()
                
                # 检查所有服务健康状态
                for service_name in list(self.services.keys()):
                    service = self.services[service_name]
                    stats = self.stats[service_name]
                    
                    is_healthy = await self.discovery.check_service_health(service.url)
                    stats.status = "healthy" if is_healthy else "unhealthy"
                    
                    if not is_healthy:
                        logger.warning(f"Service {service_name} is unhealthy")
                        
                    # 更新运行时间
                    if service.started_at:
                        stats.uptime = (datetime.now() - service.started_at).total_seconds()
                        
            except Exception as e:
                logger.error(f"Health check error: {str(e)}")
                
            await asyncio.sleep(self.health_check_interval)

    def _parse_url(self, url: str) -> tuple[str, int]:
        """从URL解析主机和端口"""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.hostname or "localhost", parsed.port or 80

# 创建全局服务注册中心实例
service_registry = ServiceRegistry() 