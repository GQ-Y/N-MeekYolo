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

class ServiceRegistration(BaseModel):
    """服务注册请求"""
    name: str = Field(..., description="服务名称", example="api")
    url: str = Field(..., description="服务URL", example="http://localhost:8001")
    description: Optional[str] = Field(None, description="服务描述")
    
    class Config:
        schema_extra = {
            "example": {
                "name": "api",
                "url": "http://localhost:8001",
                "description": "API服务"
            }
        }

@router.post("/services", summary="注册服务")
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

@router.delete("/services/{service_name}", summary="注销服务")
async def deregister_service(service_name: str):
    """注销服务"""
    success = await service_registry.deregister_service(service_name)
    if not success:
        raise HTTPException(status_code=404, detail="Service not found")
    return {"message": "Service deregistered successfully"}

@router.get("/services", summary="获取所有服务")
async def get_services() -> List[Dict]:
    """获取所有服务信息"""
    return await service_registry.get_all_services()

@router.get("/services/{service_name}", summary="获取服务详情")
async def get_service(service_name: str):
    """获取服务详细信息"""
    service = await service_registry.get_service(service_name)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
        
    stats = await service_registry.get_service_stats(service_name)
    
    return {
        "service": service,
        "stats": stats
    }

@router.post("/discover", summary="触发服务发现")
async def trigger_discovery():
    """手动触发服务发现"""
    await service_registry.discover_services()
    return {"message": "Service discovery triggered"} 