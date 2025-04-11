"""
任务管理相关路由
"""
import logging # 添加 logging
from fastapi import APIRouter, Depends, HTTPException, Request, Query, Path, Body # 添加 Query, Path, Body
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field # 添加 BaseModel, Field 导入
from typing import List, Optional, Any, Dict
import datetime
import uuid # 添加 uuid

from core.database import get_db
from core.schemas import (
    StandardResponse, 
    TaskCreate, 
    TaskUpdate, 
    TaskResponse, 
    TaskListResponse, # 导入列表响应模型
    PaginationData # 导入分页数据模型
)
from core.auth import JWTBearer
from core.models.user import User # 正确导入 User
from services.task_service import TaskService
from core.exceptions import (
    GatewayException, 
    NotFoundException, 
    PermissionDeniedException, # 添加 PermissionDeniedException
    ForbiddenException, # 保留
    InvalidInputException # 保留
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/tasks",
    tags=["任务管理"], # 更新 tag
    dependencies=[Depends(JWTBearer())], # 添加 JWT 依赖
    responses={ # 添加通用响应
        400: {"description": "无效请求"},
        401: {"description": "认证失败"},
        403: {"description": "权限不足"},
        404: {"description": "资源未找到"},
        500: {"description": "内部服务器错误"}
    }
)

# --- 移除本地 Pydantic 模型定义 ---
# class TaskSearchRequest(BaseModel):
#     ...
# class TaskDetailRequest(BaseModel):
#     ...
# class TaskCreateRequest(BaseModel):
#     ...
# class TaskCancelRequest(BaseModel):
#     ...
# class TaskNodeResponse(BaseModel):
#     ...
# class TaskResponse(BaseModel):
#     ...

# --- 保留本地 Output/Logs 模型 (待后续处理) ---
class TaskOutputRequest(BaseModel):
    task_id: int = Field(..., description="要获取输出的任务 ID")

class TaskLogsRequest(BaseModel):
    task_id: int = Field(..., description="要获取日志的任务 ID")

class TaskOutputResponse(BaseModel):
    output: Optional[str] = None

class TaskLogsResponse(BaseModel):
    logs: Optional[str] = None

# --- 路由 --- 

# 路由: 创建任务 (POST /)
@router.post(
    "/", 
    response_model=StandardResponse[TaskResponse],
    status_code=201,
    summary="创建新任务"
)
async def create_task(
    task_create: TaskCreate, # 使用标准模型
    request: Request,
    current_user: User = Depends(JWTBearer()),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """在指定节点上为当前认证用户创建并启动一个新任务"""
    task_service = TaskService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        # 将 Pydantic 模型转为字典传递给服务层
        task_data = task_create.model_dump()
        new_task = task_service.create_task(
            user_id=current_user.id,
            task_data=task_data
        )
        response_data = TaskResponse.model_validate(new_task)
        logger.info(f"用户 {current_user.id} 成功创建任务 {response_data.id} (Request ID: {req_id})")
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            message="任务创建成功", 
            code=201,
            data=response_data
        )
    except NotFoundException as e: # 节点未找到
        logger.warning(f"创建任务失败 (NotFound): {e} (Request ID: {req_id})")
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e: # 例如 node_id 缺失
        logger.warning(f"创建任务失败 (ValueError): {e} (Request ID: {req_id})")
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionDeniedException as e: # 如果服务层添加了权限检查
        logger.warning(f"创建任务失败 (Forbidden): {e} (Request ID: {req_id})")
        raise HTTPException(status_code=403, detail=str(e))
    except GatewayException as e:
        logger.error(f"创建任务路由出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"创建任务路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="创建任务时发生内部错误")

# 路由: 获取任务列表 (GET /)
@router.get(
    "/", 
    response_model=StandardResponse[TaskListResponse], # 使用列表响应模型
    summary="获取当前用户任务列表 (分页)"
)
async def list_tasks(
    request: Request,
    page: int = Query(1, description="页码 (从1开始)", ge=1),
    size: int = Query(10, description="每页数量 (1-100)", ge=1, le=100),
    node_id: Optional[int] = Query(None, description="按节点ID过滤"), # 添加 node_id 查询参数
    # TODO: 添加其他过滤参数，如 status, task_type 等
    current_user: User = Depends(JWTBearer()),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """获取当前认证用户的任务列表，支持分页和按节点过滤"""
    task_service = TaskService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        # 调用服务层获取分页数据
        service_result = task_service.list_user_tasks(
            user_id=current_user.id,
            page=page,
            size=size,
            node_id=node_id
        )
        # 转换 ORM 列表为 Pydantic 列表
        task_items = [TaskResponse.model_validate(task) for task in service_result["items"]]
        # 创建 TaskListResponse
        response_data = TaskListResponse(
            items=task_items,
            pagination=service_result["pagination"]
        )
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            message="获取任务列表成功",
            code=200,
            data=response_data
        )
    except GatewayException as e:
        logger.error(f"获取任务列表路由出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"获取任务列表路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="获取任务列表时发生内部错误")

# 路由: 获取任务详情 (GET /{task_id})
@router.get(
    "/{task_id}", 
    response_model=StandardResponse[TaskResponse],
    summary="获取指定任务详情"
)
async def get_task(
    request: Request,
    task_id: int = Path(..., description="要获取详情的任务ID", ge=1),
    current_user: User = Depends(JWTBearer()),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """获取当前认证用户拥有的指定任务的详细信息"""
    task_service = TaskService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        # 调用服务层获取详情
        task = task_service.get_task_detail(
            user_id=current_user.id, 
            task_id=task_id
        )
        response_data = TaskResponse.model_validate(task)
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            message="获取任务详情成功",
            code=200,
            data=response_data
        )
    except NotFoundException as e:
        logger.warning(f"获取任务详情失败: {e} (Request ID: {req_id})")
        raise HTTPException(status_code=404, detail=str(e))
    except GatewayException as e:
        logger.error(f"获取任务详情路由出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"获取任务详情路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="获取任务详情时发生内部错误")

# 路由: 更新任务信息 (PUT /{task_id})
@router.put(
    "/{task_id}", 
    response_model=StandardResponse[TaskResponse],
    summary="更新指定任务信息 (例如状态)"
)
async def update_task(
    request: Request,
    task_id: int = Path(..., description="要更新的任务ID", ge=1),
    task_update: TaskUpdate = Body(...), # 使用标准更新模型
    current_user: User = Depends(JWTBearer()),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """更新当前认证用户拥有的指定任务的信息 (例如状态或结果)"""
    task_service = TaskService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    # 获取需要更新的数据
    update_data = task_update.model_dump(exclude_unset=True)
    if not update_data:
         logger.warning(f"尝试更新任务 {task_id} 但未提供任何数据 (Request ID: {req_id})")
         raise HTTPException(status_code=400, detail="没有提供需要更新的数据")
         
    try:
        # 调用服务层更新
        updated_task = task_service.update_task(
            user_id=current_user.id,
            task_id=task_id,
            update_data=update_data
        )
        response_data = TaskResponse.model_validate(updated_task)
        logger.info(f"用户 {current_user.id} 成功更新任务 {task_id} (Request ID: {req_id})")
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            message="任务更新成功",
            code=200,
            data=response_data
        )
    except NotFoundException as e:
        logger.warning(f"更新任务失败: {e} (Request ID: {req_id})")
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionDeniedException as e: # 如果服务层添加了状态检查
        logger.warning(f"更新任务失败 (Permission Denied): {e} (Request ID: {req_id})")
        raise HTTPException(status_code=403, detail=str(e))
    except GatewayException as e:
        logger.error(f"更新任务路由出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"更新任务路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="更新任务时发生内部错误")

# 路由: 删除任务 (DELETE /{task_id})
@router.delete(
    "/{task_id}", 
    response_model=StandardResponse[None],
    status_code=200,
    summary="删除指定任务"
)
async def delete_task(
    request: Request,
    task_id: int = Path(..., description="要删除的任务ID", ge=1),
    current_user: User = Depends(JWTBearer()),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """删除当前认证用户拥有的指定任务"""
    task_service = TaskService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        # 调用服务层删除
        success = task_service.delete_task(user_id=current_user.id, task_id=task_id)
        logger.info(f"用户 {current_user.id} 成功删除任务 {task_id} (Request ID: {req_id})")
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            message="任务删除成功",
            code=200,
            data=None
        )
    except NotFoundException as e:
        logger.warning(f"删除任务失败: {e} (Request ID: {req_id})")
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionDeniedException as e: # 捕获权限异常 (例如，任务正在运行)
        logger.warning(f"删除任务失败 (Permission Denied): {e} (Request ID: {req_id})")
        raise HTTPException(status_code=403, detail=str(e))
    except GatewayException as e:
        logger.error(f"删除任务路由出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"删除任务路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="删除任务时发生内部错误")

# --- 保留 Output/Logs 路由 (待实现服务方法) ---
@router.post(
    "/{task_id}/output", # 调整路径风格
    response_model=StandardResponse[TaskOutputResponse],
    summary="获取任务输出"
)
async def get_task_output_endpoint(
    request: Request,
    task_id: int = Path(..., description="任务ID"), # 使用路径参数
    # request_body: TaskOutputRequest, # 不再需要请求体
    current_user: User = Depends(JWTBearer()),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """获取指定任务的标准输出 (TODO: 实现服务层逻辑)"""
    task_service = TaskService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        # TODO: 调用服务层 task_service.get_task_output(user_id=current_user.id, task_id=task_id)
        output_str = "TODO: Implement task output retrieval" 
        response_data = TaskOutputResponse(output=output_str)
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            message="获取任务输出成功 (待实现)",
            code=200,
            data=response_data
            )
    except NotFoundException as e:
        logger.warning(f"获取任务输出失败: {e} (Request ID: {req_id})")
        raise HTTPException(status_code=404, detail=str(e))
    except GatewayException as e:
        logger.error(f"获取任务输出路由出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"获取任务输出路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="获取任务输出时发生内部错误")

@router.post(
    "/{task_id}/logs", # 调整路径风格
    response_model=StandardResponse[TaskLogsResponse],
    summary="获取任务日志"
)
async def get_task_logs_endpoint(
    request: Request,
    task_id: int = Path(..., description="任务ID"), # 使用路径参数
    # request_body: TaskLogsRequest, # 不再需要请求体
    current_user: User = Depends(JWTBearer()),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """获取指定任务的日志信息 (TODO: 实现服务层逻辑)"""
    task_service = TaskService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        # TODO: 调用服务层 task_service.get_task_logs(user_id=current_user.id, task_id=task_id)
        logs_str = "TODO: Implement task logs retrieval" 
        response_data = TaskLogsResponse(logs=logs_str)
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            message="获取任务日志成功 (待实现)",
            code=200,
            data=response_data
            )
    except NotFoundException as e:
        logger.warning(f"获取任务日志失败: {e} (Request ID: {req_id})")
        raise HTTPException(status_code=404, detail=str(e))
    except GatewayException as e:
        logger.error(f"获取任务日志路由出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"获取任务日志路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="获取任务日志时发生内部错误")

# TODO: 未来添加获取输出/日志等路由，并调用 TaskService 中相应的方法 