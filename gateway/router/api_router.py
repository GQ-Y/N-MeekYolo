"""
API路由模块
处理所有外部API请求的路由和转发
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from typing import Optional, Any, Dict
from shared.utils.logger import setup_logger
from discovery.service_registry import service_registry, ServiceInfo
from core.schemas import StandardResponse, RouteRequest
from core.models.user import User
from core.auth import JWTBearer, Auth
from core.exceptions import (
    GatewayException,
    ServiceNotFoundException,
    ServiceUnhealthyException,
    ServiceURLNotFoundException,
    DownstreamServiceException
)
import aiohttp
import uuid
import asyncio
from sqlalchemy.orm import Session
from core.database import get_db
from core.models.admin import RegisteredService

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

async def route_request(route_req: RouteRequest, request: Request, db: Session, current_user: User = None) -> StandardResponse:
    """通用请求路由处理
    
    Args:
        route_req: 路由请求对象，包含目标服务、路径、方法等信息
        request: FastAPI请求对象
        db: SQLAlchemy 数据库会话
        current_user: 当前认证的用户对象 (如果需要)
        
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
        service = service_registry.get_service(route_req.service, db=db)
        if not service:
            raise ServiceNotFoundException(route_req.service)
            
        if service.status != RegisteredService.STATUS_HEALTHY:
            raise ServiceUnhealthyException(f"{route_req.service} (Status: {service.status_name})")
            
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
            # 增加超时时间到120秒
            timeout = aiohttp.ClientTimeout(total=120)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                try:
                    async with session.request(
                        method=route_req.method,
                        url=target_url,
                        headers=headers,
                        params=route_req.query_params,
                        json=route_req.body
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
                except asyncio.TimeoutError:
                    # 处理超时异常，返回超时信息而非抛出异常
                    logger.error(f"Request to {route_req.service} timed out after 120 seconds: {target_url}")
                    return StandardResponse(
                        requestId=request_id,
                        path=request.url.path,
                        success=False,
                        code=504,  # Gateway Timeout
                        message=f"请求超时: 服务 {route_req.service} 响应时间超过120秒",
                        data={
                            "service": route_req.service,
                            "url": target_url,
                            "timeout": 120
                        }
                    )
                except aiohttp.ClientError as e:
                    # 处理其他客户端错误
                    logger.error(f"Client error when connecting to {route_req.service}: {str(e)}")
                    return StandardResponse(
                        requestId=request_id,
                        path=request.url.path,
                        success=False,
                        code=502,  # Bad Gateway
                        message=f"无法连接到服务 {route_req.service}: {str(e)}",
                        data={
                            "service": route_req.service,
                            "url": target_url,
                            "error": str(e)
                        }
                    )
                        
        except DownstreamServiceException:
            raise
        except aiohttp.ClientError as e:
            logger.error(f"Failed to connect to downstream service {route_req.service}: {str(e)}")
            return StandardResponse(
                requestId=request_id,
                path=request.url.path,
                success=False,
                code=502,  # Bad Gateway
                message=f"无法连接到服务 {route_req.service}: {str(e)}",
                data=None
            )
                
    except GatewayException:
        raise
    except Exception as e:
        logger.error(f"Route request error: {str(e)}", exc_info=True)
        return StandardResponse(
            requestId=request_id,
            path=request.url.path,
            success=False,
            code=500,  # Internal Server Error
            message=f"网关内部错误: {str(e)}",
            data=None
        )

# 自定义依赖函数，确保Token验证不受下游服务超时影响
async def get_current_user(auth_header = Depends(JWTBearer())):
    """获取当前用户数据，与下游服务请求分离"""
    return auth_header

@router.post(
    "/route",
    operation_id="route_request",
    response_model=StandardResponse,
    dependencies=[],  # 移除直接依赖
    description="""
    统一的路由处理入口
    
    此接口用于处理所有对下游服务的请求。所有请求参数必须通过请求体传递。
    需要在请求头中提供有效的Bearer Token进行认证。
    
    示例请求:
    ```json
    {
        "service": "api",
        "path": "users/profile",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json"
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
async def handle_route_request(
    route_req: RouteRequest, 
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user) # 现在依赖返回 User 对象
) -> StandardResponse:
    """统一的路由处理入口
    
    Args:
        route_req: 路由请求对象，包含目标服务、路径、方法等信息
        request: FastAPI请求对象
        db: SQLAlchemy 数据库会话
        current_user: 当前认证的用户对象
        
    Returns:
        StandardResponse: 标准响应对象
    """
    return await route_request(route_req=route_req, request=request, db=db, current_user=current_user) 