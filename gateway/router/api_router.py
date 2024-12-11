"""
API路由模块
处理所有外部API请求的路由和转发
"""
from fastapi import APIRouter, HTTPException, Request
from shared.models.base import BaseResponse
from shared.utils.logger import setup_logger
from gateway.discovery.service_registry import service_registry
import aiohttp

logger = setup_logger(__name__)
router = APIRouter()

@router.api_route("/{service_name}/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def route_request(service_name: str, path: str, request: Request):
    """
    路由请求到对应的服务
    
    Args:
        service_name: 服务名称
        path: 请求路径
        request: 请求对象
    """
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