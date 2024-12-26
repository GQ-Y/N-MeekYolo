"""
管理接口路由
"""
from fastapi import APIRouter, HTTPException, Path, Body
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from shared.models.base import ServiceInfo
from gateway.discovery.service_registry import service_registry

router = APIRouter(
    prefix="/admin",
    tags=["管理接口"],
    responses={
        404: {"description": "服务未找到"},
        503: {"description": "服务不可用"}
    }
)

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

@router.post("/services", 
    summary="注册服务",
    response_model=dict,
    responses={
        200: {"description": "服务注册成功"},
        400: {"description": "服务注册失败"}
    }
)
async def register_service(service: ServiceRegistration):
    """手动注册服务"""
    success = await service_registry.register_service(
        ServiceInfo(
            name=service.name,
            url=service.url,
            description=service.description
        )
    )
    if not success:
        raise HTTPException(status_code=400, detail="Service registration failed")
    return {"message": "Service registered successfully"}

@router.delete("/services/{service_name}",
    summary="注销服务",
    response_model=dict,
    responses={
        200: {"description": "服务注销成功"},
        404: {"description": "服务未找到"}
    }
)
async def deregister_service(service_name: str):
    """注销服务"""
    success = await service_registry.deregister_service(service_name)
    if not success:
        raise HTTPException(status_code=404, detail="Service not found")
    return {"message": "Service deregistered successfully"}

@router.get("/services",
    summary="获取所有服务",
    response_model=List[ServiceResponse],
    responses={
        200: {"description": "成功获取服务列表"},
        500: {"description": "服务器内部错误"}
    }
)
async def get_services() -> List[ServiceResponse]:
    """获取所有服务信息"""
    try:
        return await service_registry.get_all_services()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/services/{service_name}",
    summary="获取服务详情",
    response_model=ServiceDetailResponse,
    responses={
        200: {"description": "成功获取服务详情"},
        404: {"description": "服务未找到"}
    }
)
async def get_service(service_name: str) -> ServiceDetailResponse:
    """获取服务详细信息"""
    service = await service_registry.get_service(service_name)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
        
    stats = await service_registry.get_service_stats(service_name)
    
    return ServiceDetailResponse(
        service=service,
        stats=stats
    )

@router.post("/discover",
    summary="触发服务发现",
    response_model=dict,
    responses={
        200: {"description": "服务发现触发成功"},
        500: {"description": "服务发现失败"}
    }
)
async def trigger_discovery():
    """手动触发服务发现"""
    try:
        await service_registry.discover_services()
        return {"message": "Service discovery triggered"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 