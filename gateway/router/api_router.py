"""
API路由模块
处理所有外部API请求的路由和转发
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from typing import Optional, Any, Dict
from shared.utils.logger import setup_logger
from gateway.discovery.service_registry import service_registry
from gateway.core.models import StandardResponse, RouteRequest
from gateway.core.exceptions import (
    GatewayException,
    ServiceNotFoundException,
    ServiceUnhealthyException,
    ServiceURLNotFoundException,
    DownstreamServiceException
)
import aiohttp
import uuid

logger = setup_logger(__name__)

# 创建路由器，使用版本化前缀
router = APIRouter(
    prefix="/api/v1",
    tags=["API路由"],
    responses={
        400: {"model": StandardResponse, "description": "请求参数错误"},
        401: {"model": StandardResponse, "description": "未授权访问"},
        403: {"model": StandardResponse, "description": "禁止访问"},
        404: {"model": StandardResponse, "description": "服务未找到"},
        500: {"model": StandardResponse, "description": "服务器内部错误"}
    }
)

async def route_request(route_req: RouteRequest, request: Request) -> StandardResponse:
    """通用请求路由处理
    
    Args:
        route_req: 路由请求对象，包含目标服务、路径、方法等信息
        request: FastAPI请求对象
        
    Returns:
        StandardResponse: 标准响应对象
        
    Raises:
        ServiceNotFoundException: 服务未找到
        ServiceUnhealthyException: 服务不健康
        ServiceURLNotFoundException: 服务URL未找到
        DownstreamServiceException: 下游服务异常
        GatewayException: 网关内部错误
    """
    request_id = str(uuid.uuid4())
    try:
        # 获取服务信息
        service = await service_registry.get_service(route_req.service)
        if not service:
            raise ServiceNotFoundException(route_req.service)
            
        if service.status != "healthy":
            raise ServiceUnhealthyException(route_req.service)
            
        # 获取服务URL
        service_url = service.url
        if not service_url:
            raise ServiceURLNotFoundException(route_req.service)
            
        # 构建目标URL
        target_url = f"{service_url}/{route_req.path.lstrip('/')}"
        
        # 获取请求内容
        headers = {**route_req.headers, 'X-Request-ID': request_id}
        
        # 转发请求
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method=route_req.method,
                    url=target_url,
                    headers=headers,
                    params=route_req.query_params,
                    json=route_req.body,
                    timeout=30  # 设置超时时间
                ) as response:
                    response_data = await response.json()
                    
                    # 如果下游服务已经返回标准格式，进行格式转换
                    if isinstance(response_data, dict) and all(key in response_data for key in ['code', 'message', 'data']):
                        return StandardResponse(
                            requestId=request_id,
                            path=request.url.path,
                            success=response_data.get('code', 200) < 400,
                            code=response_data.get('code', 200),
                            message=response_data.get('message', 'Success'),
                            data=response_data.get('data')
                        )
                    
                    # 否则包装成标准格式
                    if response.status >= 400:
                        raise DownstreamServiceException(
                            route_req.service,
                            response.status,
                            str(response_data)
                        )
                        
                    return StandardResponse(
                        requestId=request_id,
                        path=request.url.path,
                        success=True,
                        code=response.status,
                        message="Success",
                        data=response_data
                    )
                    
        except aiohttp.ClientError as e:
            raise DownstreamServiceException(
                route_req.service,
                500,
                f"Failed to connect to downstream service: {str(e)}"
            )
                
    except GatewayException:
        raise
    except Exception as e:
        logger.error(f"Route request error: {str(e)}", exc_info=True)
        raise GatewayException(
            message=f"Internal gateway error: {str(e)}",
            code=500
        )

@router.post(
    "/route",
    operation_id="route_request",
    response_model=StandardResponse,
    description="""
    统一的路由处理入口
    
    此接口用于处理所有对下游服务的请求。所有请求参数必须通过请求体传递。
    
    示例请求:
    ```json
    {
        "service": "api",
        "path": "users/profile",
        "method": "POST",
        "headers": {
            "Authorization": "Bearer token"
        },
        "query_params": {
            "page": "1"
        },
        "body": {
            "user_id": 123
        }
    }
    ```
    """
)
async def handle_route_request(route_req: RouteRequest, request: Request) -> StandardResponse:
    """统一的路由处理入口
    
    Args:
        route_req: 路由请求对象，包含目标服务、路径、方法等信息
        request: FastAPI请求对象
        
    Returns:
        StandardResponse: 标准响应对象
    """
    return await route_request(route_req, request) 