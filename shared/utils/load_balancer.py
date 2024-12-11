"""
负载均衡器模块
实现服务实例的负载均衡
"""
import random
from enum import Enum
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class LoadBalanceStrategy(Enum):
    """负载均衡策略"""
    ROUND_ROBIN = "round_robin"  # 轮询
    RANDOM = "random"           # 随机
    LEAST_CONN = "least_conn"   # 最少连接
    WEIGHTED = "weighted"       # 加权轮询

@dataclass
class ServiceInstance:
    """服务实例信息"""
    id: str
    host: str
    port: int
    weight: int = 1
    active_connections: int = 0
    last_access: datetime = None
    health_score: float = 1.0
    metadata: Dict[str, Any] = None

class LoadBalancer:
    """负载均衡器"""
    
    def __init__(self, strategy: LoadBalanceStrategy = LoadBalanceStrategy.ROUND_ROBIN):
        self.strategy = strategy
        self.instances: Dict[str, ServiceInstance] = {}
        self.current_index = 0  # 用于轮询策略
        
    def add_instance(self, instance: ServiceInstance) -> None:
        """添加服务实例"""
        self.instances[instance.id] = instance
        logger.info(f"Added service instance: {instance.id}")
        
    def remove_instance(self, instance_id: str) -> None:
        """移除服务实例"""
        if instance_id in self.instances:
            del self.instances[instance_id]
            logger.info(f"Removed service instance: {instance_id}")
            
    def update_instance(self, instance_id: str, **kwargs) -> None:
        """更新服务实例信息"""
        if instance_id in self.instances:
            instance = self.instances[instance_id]
            for key, value in kwargs.items():
                if hasattr(instance, key):
                    setattr(instance, key, value)
            logger.debug(f"Updated service instance: {instance_id}")
            
    def get_instance(self) -> Optional[ServiceInstance]:
        """获取服务实例"""
        if not self.instances:
            return None
            
        if self.strategy == LoadBalanceStrategy.ROUND_ROBIN:
            return self._round_robin()
        elif self.strategy == LoadBalanceStrategy.RANDOM:
            return self._random()
        elif self.strategy == LoadBalanceStrategy.LEAST_CONN:
            return self._least_connections()
        elif self.strategy == LoadBalanceStrategy.WEIGHTED:
            return self._weighted_round_robin()
        else:
            raise ValueError(f"Unsupported load balance strategy: {self.strategy}")
            
    def _round_robin(self) -> ServiceInstance:
        """轮询策略"""
        instances = list(self.instances.values())
        if not instances:
            return None
            
        instance = instances[self.current_index]
        self.current_index = (self.current_index + 1) % len(instances)
        return instance
        
    def _random(self) -> ServiceInstance:
        """随机策略"""
        instances = list(self.instances.values())
        return random.choice(instances) if instances else None
        
    def _least_connections(self) -> ServiceInstance:
        """最少连接策略"""
        instances = list(self.instances.values())
        if not instances:
            return None
            
        return min(instances, key=lambda x: x.active_connections)
        
    def _weighted_round_robin(self) -> ServiceInstance:
        """加权轮询策略"""
        instances = list(self.instances.values())
        if not instances:
            return None
            
        total_weight = sum(instance.weight for instance in instances)
        if total_weight <= 0:
            return self._round_robin()
            
        # 使用当前索引和权重计算选择的实例
        point = self.current_index % total_weight
        for instance in instances:
            if point < instance.weight:
                self.current_index = (self.current_index + 1) % total_weight
                return instance
            point -= instance.weight
            
        return instances[0]  # 防止意外情况
        
    def get_stats(self) -> Dict[str, Any]:
        """获取负载均衡器统计信息"""
        return {
            "strategy": self.strategy.value,
            "instance_count": len(self.instances),
            "instances": {
                instance_id: {
                    "active_connections": instance.active_connections,
                    "health_score": instance.health_score,
                    "last_access": instance.last_access.isoformat() if instance.last_access else None
                }
                for instance_id, instance in self.instances.items()
            }
        }