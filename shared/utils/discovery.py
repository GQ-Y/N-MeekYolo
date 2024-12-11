"""
服务发现工具
提供服务注册和发现功能
"""
from typing import Dict, Optional
from shared.utils.logger import setup_logger
from shared.utils.load_balancer import (
    LoadBalancer,
    LoadBalanceStrategy,
    ServiceInstance
)

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