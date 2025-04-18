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
        self.data = data
        super().__init__(self.message)

class ServiceNotFoundException(GatewayException):
    """服务未找到异常"""
    def __init__(self, service: str):
        super().__init__(
            message=f"Service '{service}' not found",
            code=404
        )

class ServiceUnhealthyException(GatewayException):
    """服务不健康异常"""
    def __init__(self, service: str):
        super().__init__(
            message=f"Service '{service}' is unhealthy",
            code=503
        )

class ServiceURLNotFoundException(GatewayException):
    """服务URL未找到异常"""
    def __init__(self, service: str):
        super().__init__(
            message=f"URL for service '{service}' not found",
            code=404
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
    def __init__(self, service: str, status_code: int, error_message: str):
        super().__init__(
            message=f"Downstream service '{service}' error: {error_message}",
            code=status_code
        )

class AuthenticationException(GatewayException):
    """认证异常基类"""
    def __init__(
        self,
        message: str = "认证失败",
        code: int = 401,
        data: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message=message, code=code, data=data)

class InvalidCredentialsException(AuthenticationException):
    """无效的凭证"""
    def __init__(self):
        super().__init__(message="用户名、密码或口令错误")

class InvalidTOTPException(AuthenticationException):
    """无效的TOTP口令异常"""
    def __init__(self):
        super().__init__(message="Invalid TOTP code")

class TokenExpiredException(AuthenticationException):
    """令牌过期"""
    def __init__(self):
        super().__init__(message="令牌已过期")

class InvalidTokenException(AuthenticationException):
    """无效的令牌"""
    def __init__(self):
        super().__init__(message="无效的令牌")

class UserExistsException(AuthenticationException):
    """用户已存在"""
    def __init__(self):
        super().__init__(message="已存在用户，系统只允许一个用户", code=409) 