"""
管理接口路由
"""
from fastapi import APIRouter, HTTPException, Path, Body
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
from shared.models.base import ServiceInfo
from gateway.discovery.service_registry import service_registry
import time
import uuid

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["管理接口"],
    responses={
        404: {"description": "服务未找到"},
        503: {"description": "服务不可用"}
    }
)

class StandardResponse(BaseModel):
    """标准API响应模型"""
    requestId: str = Field(default_factory=lambda: str(uuid.uuid4()))
    path: str = ""
    success: bool = True
    message: str = "Success"
    code: int = 200
    data: Any = None
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))

# 定义响应模型
class ServiceStats(BaseModel):
    """服务统计信息"""
    total_requests: int = Field(0, description="总请求数")
    success_requests: int = Field(0, description="成功请求数")
    failed_requests: int = Field(0, description="失败请求数")
    avg_response_time: float = Field(0.0, description="平均响应时间")
    status: str = Field("unknown", description="服务状态")
    uptime: Optional[float] = Field(None, description="运行时间")

class ServiceResponse(BaseModel):
    """服务信息响应"""
    name: str = Field(..., description="服务名称")
    url: str = Field(..., description="服务URL")
    status: str = Field(..., description="服务状态")
    uptime: Optional[float] = Field(None, description="运行时间")
    total_requests: int = Field(..., description="总请求数")
    success_rate: float = Field(..., description="成功率")
    avg_response_time: float = Field(..., description="平均响应时间")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "api",
                "url": "http://localhost:8001",
                "status": "healthy",
                "uptime": 3600.0,
                "total_requests": 1000,
                "success_rate": 0.99,
                "avg_response_time": 0.1
            }
        }

class ServiceRegistration(BaseModel):
    """服务注册请求"""
    name: str = Field(..., description="服务名称", example="api")
    url: str = Field(..., description="服务URL", example="http://localhost:8001")
    description: Optional[str] = Field(None, description="服务描述")
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "api",
                "url": "http://localhost:8001",
                "description": "API服务"
            }
        }

class ServiceDetailResponse(BaseModel):
    """服务详细信息响应"""
    service: ServiceInfo
    stats: ServiceStats

    class Config:
        json_schema_extra = {
            "example": {
                "service": {
                    "name": "api",
                    "url": "http://localhost:8001",
                    "description": "API服务",
                    "version": "1.0.0",
                    "status": "healthy"
                },
                "stats": {
                    "total_requests": 1000,
                    "success_requests": 990,
                    "failed_requests": 10,
                    "avg_response_time": 0.1,
                    "status": "healthy",
                    "uptime": 3600.0
                }
            }
        }

class ServiceQueryRequest(BaseModel):
    """服务查询请求"""
    service_name: Optional[str] = Field(None, description="服务名称")

class ServiceDeregisterRequest(BaseModel):
    """服务注销请求"""
    service_name: str = Field(..., description="服务名称")

@router.post("/services/register", 
    summary="注册服务",
    response_model=StandardResponse,
    responses={
        200: {"description": "服务注册成功"},
        400: {"description": "服务注册失败"}
    }
)
async def register_service(service: ServiceRegistration) -> StandardResponse:
    """手动注册服务"""
    try:
        success = await service_registry.register_service(
            ServiceInfo(
                name=service.name,
                url=service.url,
                description=service.description
            )
        )
        if not success:
            return StandardResponse(
                path="/api/v1/admin/services/register",
                success=False,
                code=400,
                message="Service registration failed"
            )
        return StandardResponse(
            path="/api/v1/admin/services/register",
            message="Service registered successfully"
        )
    except Exception as e:
        return StandardResponse(
            path="/api/v1/admin/services/register",
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/services/deregister",
    summary="注销服务",
    response_model=StandardResponse,
    responses={
        200: {"description": "服务注销成功"},
        404: {"description": "服务未找到"}
    }
)
async def deregister_service(request: ServiceDeregisterRequest) -> StandardResponse:
    """注销服务"""
    try:
        success = await service_registry.deregister_service(request.service_name)
        if not success:
            return StandardResponse(
                path="/api/v1/admin/services/deregister",
                success=False,
                code=404,
                message="Service not found"
            )
        return StandardResponse(
            path="/api/v1/admin/services/deregister",
            message="Service deregistered successfully"
        )
    except Exception as e:
        return StandardResponse(
            path="/api/v1/admin/services/deregister",
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/services/list",
    summary="获取服务列表",
    response_model=StandardResponse,
    responses={
        200: {"description": "成功获取服务列表"},
        500: {"description": "服务器内部错误"}
    }
)
async def get_services() -> StandardResponse:
    """获取所有服务信息"""
    try:
        services = await service_registry.get_all_services()
        return StandardResponse(
            path="/api/v1/admin/services/list",
            data=services
        )
    except Exception as e:
        return StandardResponse(
            path="/api/v1/admin/services/list",
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/services/detail",
    summary="获取服务详情",
    response_model=StandardResponse,
    responses={
        200: {"description": "成功获取服务详情"},
        404: {"description": "服务未找到"}
    }
)
async def get_service(request: ServiceQueryRequest) -> StandardResponse:
    """获取服务详细信息"""
    try:
        if not request.service_name:
            return StandardResponse(
                path="/api/v1/admin/services/detail",
                success=False,
                code=400,
                message="Service name is required"
            )
            
        service = await service_registry.get_service(request.service_name)
        if not service:
            return StandardResponse(
                path="/api/v1/admin/services/detail",
                success=False,
                code=404,
                message="Service not found"
            )
            
        stats = await service_registry.get_service_stats(request.service_name)
        
        return StandardResponse(
            path="/api/v1/admin/services/detail",
            data=ServiceDetailResponse(
                service=service,
                stats=stats
            )
        )
    except Exception as e:
        return StandardResponse(
            path="/api/v1/admin/services/detail",
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/services/discover",
    summary="触发服务发现",
    response_model=StandardResponse,
    responses={
        200: {"description": "服务发现触发成功"},
        500: {"description": "服务发现失败"}
    }
)
async def trigger_discovery() -> StandardResponse:
    """手动触发服务发现"""
    try:
        await service_registry.discover_services()
        return StandardResponse(
            path="/api/v1/admin/services/discover",
            message="Service discovery triggered successfully"
        )
    except Exception as e:
        return StandardResponse(
            path="/api/v1/admin/services/discover",
            success=False,
            code=500,
            message=str(e)
        ) 