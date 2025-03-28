"""
网关服务异常定义模块
"""
from typing import Any, Dict, Optional

class GatewayException(Exception):
    """网关基础异常类"""
    def __init__(
        self,
        message: str,
        code: int = 500,
        data: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.code = code
        self.data = data or {}
        super().__init__(self.message)

class ServiceNotFoundException(GatewayException):
    """服务未找到异常"""
    def __init__(self, service_name: str):
        super().__init__(
            message=f"Service {service_name} not found",
            code=404,
            data={"service": service_name}
        )

class ServiceUnhealthyException(GatewayException):
    """服务不健康异常"""
    def __init__(self, service_name: str):
        super().__init__(
            message=f"Service {service_name} is unhealthy",
            code=503,
            data={"service": service_name}
        )

class ServiceURLNotFoundException(GatewayException):
    """服务URL未找到异常"""
    def __init__(self, service_name: str):
        super().__init__(
            message=f"Service URL not found for {service_name}",
            code=404,
            data={"service": service_name}
        )

class InvalidRequestException(GatewayException):
    """无效请求异常"""
    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(
            message=message,
            code=400,
            data=details or {}
        )

class DownstreamServiceException(GatewayException):
    """下游服务异常"""
    def __init__(self, service_name: str, status_code: int, message: str):
        super().__init__(
            message=f"Downstream service error: {message}",
            code=status_code,
            data={
                "service": service_name,
                "downstream_status": status_code,
                "downstream_message": message
            }
        ) 