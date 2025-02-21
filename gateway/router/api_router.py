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

# 定义路由处理函数
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
        service_url = service.url  # 直接从服务信息获取URL
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
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Route request error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# API服务路由
@router.get("/api/{path:path}", operation_id="route_api_request_get")
async def route_api_request_get(path: str = Path(...), request: Request = None):
    return await route_request("api", path, request)

@router.post("/api/{path:path}", operation_id="route_api_request_post")
async def route_api_request_post(path: str = Path(...), request: Request = None):
    return await route_request("api", path, request)

@router.put("/api/{path:path}", operation_id="route_api_request_put")
async def route_api_request_put(path: str = Path(...), request: Request = None):
    return await route_request("api", path, request)

@router.delete("/api/{path:path}", operation_id="route_api_request_delete")
async def route_api_request_delete(path: str = Path(...), request: Request = None):
    return await route_request("api", path, request)

# 模型服务路由
@router.get("/model/{path:path}", operation_id="route_model_request_get")
async def route_model_request_get(path: str = Path(...), request: Request = None):
    return await route_request("model", path, request)

@router.post("/model/{path:path}", operation_id="route_model_request_post")
async def route_model_request_post(path: str = Path(...), request: Request = None):
    return await route_request("model", path, request)

@router.put("/model/{path:path}", operation_id="route_model_request_put")
async def route_model_request_put(path: str = Path(...), request: Request = None):
    return await route_request("model", path, request)

@router.delete("/model/{path:path}", operation_id="route_model_request_delete")
async def route_model_request_delete(path: str = Path(...), request: Request = None):
    return await route_request("model", path, request)

# 分析服务路由
@router.get("/analysis/{path:path}", operation_id="route_analysis_request_get")
async def route_analysis_request_get(path: str = Path(...), request: Request = None):
    return await route_request("analysis", path, request)

@router.post("/analysis/{path:path}", operation_id="route_analysis_request_post")
async def route_analysis_request_post(path: str = Path(...), request: Request = None):
    return await route_request("analysis", path, request)

@router.put("/analysis/{path:path}", operation_id="route_analysis_request_put")
async def route_analysis_request_put(path: str = Path(...), request: Request = None):
    return await route_request("analysis", path, request)

@router.delete("/analysis/{path:path}", operation_id="route_analysis_request_delete")
async def route_analysis_request_delete(path: str = Path(...), request: Request = None):
    return await route_request("analysis", path, request) 