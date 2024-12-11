"""
断路器模块
实现服务熔断机制
"""
import time
import asyncio
from enum import Enum
from typing import Callable, Any, Optional
from dataclasses import dataclass
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class CircuitState(Enum):
    """断路器状态"""
    CLOSED = "CLOSED"       # 正常状态
    OPEN = "OPEN"          # 熔断状态
    HALF_OPEN = "HALF_OPEN"  # 半开状态

@dataclass
class CircuitBreakerConfig:
    """断路器配置"""
    failure_threshold: int = 5      # 错误阈值
    recovery_timeout: float = 60.0  # 恢复超时时间(秒)
    half_open_timeout: float = 5.0  # 半开状态超时时间(秒)
    reset_timeout: float = 300.0    # 重置超时时间(秒)

class CircuitBreaker:
    """断路器实现"""
    
    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0
        self.last_success_time = 0
        self._lock = asyncio.Lock()
        
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        执行受保护的调用
        
        Args:
            func: 要执行的函数
            args: 位置参数
            kwargs: 关键字参数
            
        Returns:
            Any: 函数执行结果
            
        Raises:
            Exception: 当断路器开启或调用失败时抛出
        """
        async with self._lock:
            await self._check_state()
            
            try:
                result = await func(*args, **kwargs)
                await self._on_success()
                return result
                
            except Exception as e:
                await self._on_failure()
                raise
                
    async def _check_state(self):
        """检查并更新断路器状态"""
        current_time = time.time()
        
        if self.state == CircuitState.OPEN:
            if current_time - self.last_failure_time >= self.config.recovery_timeout:
                logger.info(f"Circuit {self.name} entering half-open state")
                self.state = CircuitState.HALF_OPEN
            else:
                raise Exception(f"Circuit {self.name} is OPEN")
                
        elif self.state == CircuitState.HALF_OPEN:
            if current_time - self.last_success_time >= self.config.half_open_timeout:
                logger.info(f"Circuit {self.name} returning to OPEN state")
                self.state = CircuitState.OPEN
                raise Exception(f"Circuit {self.name} failed in HALF_OPEN state")
                
    async def _on_success(self):
        """处理成功调用"""
        self.last_success_time = time.time()
        
        if self.state == CircuitState.HALF_OPEN:
            logger.info(f"Circuit {self.name} recovered, closing")
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            
        elif self.state == CircuitState.CLOSED:
            # 重置错误计数
            if time.time() - self.last_failure_time >= self.config.reset_timeout:
                self.failure_count = 0
                
    async def _on_failure(self):
        """处理失败调用"""
        self.last_failure_time = time.time()
        self.failure_count += 1
        
        if self.state == CircuitState.CLOSED and self.failure_count >= self.config.failure_threshold:
            logger.warning(f"Circuit {self.name} tripped, opening")
            self.state = CircuitState.OPEN 