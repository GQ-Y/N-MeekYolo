"""
后台管理相关路由
需要管理员权限访问
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Path, Body, Request, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
from shared.models.base import ServiceInfo
from discovery.service_registry import service_registry
import time
import uuid
from datetime import datetime, date

from core.database import get_db
from core.schemas import (
    StandardResponse, 
    UserResponse, 
    UserListResponse, 
    UserStatusUpdate,
    SystemLogResponse,
    SystemLogListResponse,
    PaginationData
)
from core.auth import JWTBearer
from core.models.user import User
from core.exceptions import GatewayException, NotFoundException

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["管理接口"],
    dependencies=[Depends(JWTBearer(required_roles=['admin', 'super_admin']))],
    responses={
        401: {"description": "认证失败或令牌无效"},
        403: {"description": "权限不足"},
        400: {"description": "无效请求"},
        404: {"description": "资源未找到"},
        500: {"description": "内部服务器错误"}
    }
)

class SystemOverviewResponse(BaseModel):
    total_users: int
    total_nodes: int
    active_tasks: int
    status: str
    error: Optional[str] = None

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

class UserListRequest(BaseModel):
    """获取用户列表的请求体"""
    page: int = Field(1, description="页码 (从1开始)", ge=1)
    size: int = Field(10, description="每页数量 (1-100)", ge=1, le=100)

@router.post("/services/register", 
    summary="注册服务",
    response_model=StandardResponse,
    responses={
        200: {"description": "服务注册/更新成功"},
        400: {"description": "服务注册失败"},
        500: {"description": "服务器内部错误"}
    }
)
async def register_service(
    service: ServiceRegistration, 
    request: Request,
    db: Session = Depends(get_db)
) -> StandardResponse:
    """手动注册服务到数据库 (存在则更新)"""
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        success = service_registry.register_service(
            ServiceInfo(
                name=service.name,
                url=str(service.url),
                description=service.description
            ),
            db=db
        )
        if not success:
            raise GatewayException("服务注册失败", code=400)
        
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            code=200,
            message="服务注册/更新成功"
        )
    except GatewayException as e:
        logger.warning(f"注册服务路由出错 (GatewayException): {e} (Request ID: {req_id})")
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"注册服务路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="注册服务时发生内部错误")

@router.post("/services/deregister",
    summary="注销服务",
    response_model=StandardResponse,
    responses={
        200: {"description": "服务注销成功"},
        404: {"description": "服务未找到"},
        500: {"description": "服务器内部错误"}
    }
)
async def deregister_service(
    request_body: ServiceDeregisterRequest,
    request: Request,
    db: Session = Depends(get_db)
) -> StandardResponse:
    """从数据库注销服务"""
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        success = service_registry.deregister_service(request_body.service_name, db=db)
        if not success:
            logger.warning(f"尝试注销不存在的服务: {request_body.service_name} (Request ID: {req_id})")
            raise NotFoundException(f"服务 '{request_body.service_name}' 未找到")
        
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            code=200,
            message="服务注销成功"
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
async def get_services(request: Request, db: Session = Depends(get_db)) -> StandardResponse:
    """获取数据库中所有服务信息"""
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        # 注意：get_all_services 现在是同步方法，不需要 await
        # 修正：确保传递 db 参数
        services_data = service_registry.get_all_services(db=db)
        # 需要将返回的字典列表转换为 ServiceResponse 模型列表 (如果需要严格类型检查)
        # Pydantic v2: response_data = [ServiceResponse.model_validate(s) for s in services_data]
        # 暂时直接返回字典列表
        response_data = services_data
        
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            message="成功获取服务列表",
            code=200,
            data=response_data
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
            success=True,
            code=200,
            message="成功获取服务详情",
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
            success=True,
            code=200,
            message="Service discovery triggered successfully"
        )
    except Exception as e:
        return StandardResponse(
            path="/api/v1/admin/services/discover",
            success=False,
            code=500,
            message=str(e)
        )

@router.get(
    "/dashboard", 
    response_model=StandardResponse,
    summary="获取系统概览"
)
async def get_dashboard_overview(
    request: Request,
    db: Session = Depends(get_db)
) -> StandardResponse:
    """获取系统运行状态和关键指标概览"""
    admin_service = AdminService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        overview_data = admin_service.get_system_overview()
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            message="获取系统概览成功",
            code=200,
            data=overview_data
        )
    except GatewayException as e:
        logger.error(f"获取管理后台概览时出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"获取管理后台概览时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="获取系统概览时发生内部错误")

@router.post(
    "/users/list",
    response_model=StandardResponse[UserListResponse],
    summary="获取用户列表 (分页)",
    description="管理员获取系统中的用户列表，支持分页。"
)
async def list_users(
    request_body: UserListRequest,
    request: Request,
    db: Session = Depends(get_db)
) -> StandardResponse:
    """获取分页的用户列表"""
    admin_service = AdminService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        service_result = admin_service.list_users(page=request_body.page, size=request_body.size)
        
        user_items = [UserResponse.model_validate(user) for user in service_result["items"]]
        
        user_list_data = UserListResponse(
            items=user_items,
            pagination=service_result["pagination"]
        )
        
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            message="获取用户列表成功",
            code=200,
            data=user_list_data
        )
    except GatewayException as e:
        logger.error(f"管理员获取用户列表时出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"管理员获取用户列表时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="获取用户列表时发生内部错误")

@router.get(
    "/users/{user_id}",
    response_model=StandardResponse[UserResponse],
    summary="获取指定用户详情",
    description="管理员根据用户ID获取用户的详细信息。"
)
async def get_user_details(
    request: Request,
    user_id: int = Path(..., description="要查询的用户ID", ge=1),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """获取指定用户的详细信息"""
    admin_service = AdminService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        user = admin_service.get_user_details(user_id)
        
        user_data = UserResponse.model_validate(user)
        
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            message="获取用户详情成功",
            code=200,
            data=user_data
        )
    except NotFoundException as e:
        logger.warning(f"管理员获取用户详情失败: {e} (Request ID: {req_id})")
        raise HTTPException(status_code=404, detail=str(e))
    except GatewayException as e:
        logger.error(f"管理员获取用户详情时出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"管理员获取用户详情时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="获取用户详情时发生内部错误")

@router.put(
    "/users/{user_id}/status",
    response_model=StandardResponse[UserResponse],
    summary="更新指定用户状态",
    description="管理员更新指定用户的状态 (例如 0 表示正常, 1 表示禁用)。"
)
async def update_user_status(
    request: Request,
    user_id: int = Path(..., description="要更新状态的用户ID", ge=1),
    status_update: UserStatusUpdate = Body(...),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """更新指定用户的状态"""
    admin_service = AdminService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        updated_user = admin_service.update_user_status(user_id, status_update.status)
        
        updated_user_data = UserResponse.model_validate(updated_user)
        
        logger.info(f"管理员成功更新用户 {user_id} 状态为 {status_update.status} (Request ID: {req_id})")
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            message=f"用户 {user_id} 状态已成功更新",
            code=200,
            data=updated_user_data
        )
    except NotFoundException as e:
        logger.warning(f"管理员更新用户状态失败: {e} (Request ID: {req_id})")
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        logger.warning(f"管理员尝试设置无效用户状态: {e} (Request ID: {req_id})")
        raise HTTPException(status_code=400, detail=str(e))
    except GatewayException as e:
        logger.error(f"管理员更新用户状态时出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"管理员更新用户状态时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="更新用户状态时发生内部错误")

@router.get(
    "/logs",
    response_model=StandardResponse[SystemLogListResponse],
    summary="获取系统日志记录 (分页、过滤)"
)
async def get_system_logs(
    request: Request,
    page: int = Query(1, description="页码 (从1开始)", ge=1),
    size: int = Query(10, description="每页数量 (1-100)", ge=1, le=100),
    level: Optional[str] = Query(None, description="按日志级别过滤 (INFO, WARNING, ERROR, CRITICAL, DEBUG)"),
    start_date: Optional[date] = Query(None, description="按起始日期过滤 (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="按结束日期过滤 (YYYY-MM-DD)"),
    user_id: Optional[int] = Query(None, description="按用户ID过滤"),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """获取系统日志记录，支持分页和按级别、日期、用户ID过滤"""
    admin_service = AdminService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    
    start_datetime = datetime.combine(start_date, datetime.min.time()) if start_date else None
    end_datetime = datetime.combine(end_date, datetime.max.time()) if end_date else None
    
    try:
        service_result = admin_service.list_system_logs(
            page=page,
            size=size,
            level=level,
            start_date=start_datetime,
            end_date=end_datetime,
            user_id=user_id
        )
        response_data = SystemLogListResponse(**service_result)
        
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            message="获取系统日志成功",
            code=200,
            data=response_data
        )
    except GatewayException as e:
        logger.error(f"获取系统日志路由出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"获取系统日志路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="获取系统日志时发生内部错误") 