"""
API路由模块
处理所有外部API请求的路由和转发
"""
from fastapi import APIRouter, HTTPException, Request, Path, Query
from typing import Optional
from shared.models.base import BaseResponse
from shared.utils.logger import setup_logger
from gateway.discovery.service_registry import service_registry
import aiohttp

logger = setup_logger(__name__)
router = APIRouter(tags=["API路由"])

@router.api_route("/api/{path:path}", 
    methods=["GET", "POST", "PUT", "DELETE"],
    summary="API服务路由"
)
async def route_api_request(
    path: str = Path(..., description="API路径"),
    request: Request = None
):
    """路由API服务请求"""
    return await route_request("api", path, request)

@router.api_route("/model/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE"],
    summary="模型服务路由"
)
async def route_model_request(
    path: str = Path(..., description="API路径"),
    request: Request = None
):
    """路由模型服务请求"""
    return await route_request("model", path, request)

@router.api_route("/analysis/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE"],
    summary="分析服务路由"
)
async def route_analysis_request(
    path: str = Path(..., description="API路径"),
    request: Request = None
):
    """路由分析服务请求"""
    return await route_request("analysis", path, request)

async def route_request(service_name: str, path: str, request: Request):
    """通用请求路由处理"""
    try:
        # 获取服务信息
        service = await service_registry.get_service(service_name)
        if not service:
            raise HTTPException(status_code=404, detail=f"Service {service_name} not found")
            
        if service.status != "healthy":
            raise HTTPException(status_code=503, detail=f"Service {service_name} is unhealthy")
            
        # 获取服务URL
        service_url = await service_registry.discovery.get_service_url(service_name)
        if not service_url:
            raise HTTPException(status_code=404, detail=f"Service URL not found")
            
        # 构建目标URL
        target_url = f"{service_url}/{path}"
        
        # 获取请求内容
        headers = dict(request.headers)
        method = request.method
        
        # 转发请求
        async with aiohttp.ClientSession() as session:
            async with session.request(
                method=method,
                url=target_url,
                headers=headers,
                params=request.query_params,
                data=await request.body() if method in ["POST", "PUT"] else None
            ) as response:
                return await response.json()
                
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Route request error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 