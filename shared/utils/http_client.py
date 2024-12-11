"""
HTTP客户端工具
用于服务间通信
"""
import aiohttp
import asyncio
from typing import Dict, Any, Optional
from shared.utils.logger import setup_logger
from shared.models.base import BaseResponse
from shared.utils.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

logger = setup_logger(__name__)

class ServiceClient:
    """服务通信客户端"""
    
    def __init__(self, service_name: str, discovery_service):
        self.service_name = service_name
        self.discovery = discovery_service
        self.session: Optional[aiohttp.ClientSession] = None
        self.retry_count = 3
        self.retry_delay = 1.0  # 秒
        
        # 添加断路器
        self.circuit_breaker = CircuitBreaker(
            f"{service_name}_client",
            CircuitBreakerConfig(
                failure_threshold=5,
                recovery_timeout=60.0,
                half_open_timeout=5.0,
                reset_timeout=300.0
            )
        )
        
    async def __aenter__(self):
        """异步上下文管理器入口"""
        if not self.session:
            self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        if self.session:
            await self.session.close()
            self.session = None
            
    async def _get_service_url(self) -> str:
        """获取服务URL"""
        service_url = await self.discovery.get_service_url(self.service_name)
        if not service_url:
            raise Exception(f"Service {self.service_name} not available")
        return service_url
        
    async def request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 30.0
    ) -> Dict[str, Any]:
        """
        发送请求到服务
        
        Args:
            method: 请求方法
            path: 请求路径
            data: 请求数据
            params: 查询参数
            headers: 请求头
            timeout: 超时时间
            
        Returns:
            Dict: 响应数据
        """
        async def _do_request():
            attempt = 0
            last_error = None
            
            while attempt < self.retry_count:
                try:
                    service_url = await self._get_service_url()
                    url = f"{service_url}/{path.lstrip('/')}"
                    
                    async with self.session.request(
                        method=method,
                        url=url,
                        json=data,
                        params=params,
                        headers=headers,
                        timeout=timeout
                    ) as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            error_text = await response.text()
                            raise Exception(f"Request failed with status {response.status}: {error_text}")
                            
                except Exception as e:
                    last_error = e
                    attempt += 1
                    if attempt < self.retry_count:
                        await asyncio.sleep(self.retry_delay)
                        continue
                        
            raise Exception(f"Request failed after {self.retry_count} attempts: {str(last_error)}")
            
        # 使用断路器包装请求
        return await self.circuit_breaker.call(_do_request)

class AnalysisServiceClient(ServiceClient):
    """分析服务客户端"""
    
    def __init__(self, discovery_service):
        super().__init__("analysis", discovery_service)
        
    async def analyze_image(self, image_data: Dict[str, Any]) -> Dict[str, Any]:
        """发送图片分析请求"""
        return await self.request("POST", "/image/analyze", data=image_data)
        
    async def start_video_analysis(self, video_data: Dict[str, Any]) -> str:
        """启动视频分析"""
        result = await self.request("POST", "/video/start", data=video_data)
        return result["task_id"]
        
    async def start_stream_analysis(self, stream_data: Dict[str, Any]) -> str:
        """启动流分析"""
        result = await self.request("POST", "/stream/start", data=stream_data)
        return result["task_id"]

class ModelServiceClient(ServiceClient):
    """模型服务客户端"""
    
    def __init__(self, discovery_service):
        super().__init__("model", discovery_service)
        
    async def get_model_info(self, model_code: str) -> Dict[str, Any]:
        """获取模型信息"""
        return await self.request("GET", f"/models/{model_code}")
        
    async def load_model(self, model_code: str) -> Dict[str, Any]:
        """加载模型"""
        return await self.request("POST", f"/models/{model_code}/load") 