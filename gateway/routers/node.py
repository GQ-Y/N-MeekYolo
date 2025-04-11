"""
用户节点管理相关路由
"""
import logging # 添加 logging
# 导入 Query, Path 用于查询和路径参数
from fastapi import APIRouter, Depends, HTTPException, Request, Query, Path, Body
from sqlalchemy.orm import Session
# 移除本地 Pydantic 定义
# from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Any, Dict
import datetime
import uuid # 添加 uuid

from core.database import get_db
# 从 core.schemas 导入标准模型
from core.schemas import (
    StandardResponse, 
    NodeCreate, 
    NodeUpdate, 
    NodeResponse, 
    NodeListResponse, # 导入列表响应模型
    PaginationData # 导入分页数据模型
)
from core.auth import JWTBearer
from core.models.user import User # 正确导入 User
# 导入服务和异常
from services.node_service import NodeService
from core.exceptions import (
    GatewayException, 
    NotFoundException, 
    PermissionDeniedException, # 更新为 PermissionDeniedException
    ForbiddenException # 保留 ForbiddenException (虽然服务层暂时没用)
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/nodes",
    tags=["节点管理"], # 更新 tag
    dependencies=[Depends(JWTBearer())], # 添加 JWT 依赖到整个路由
    responses={ # 添加通用响应
        400: {"description": "无效请求"},
        401: {"description": "认证失败"},
        403: {"description": "权限不足"},
        404: {"description": "资源未找到"},
        500: {"description": "内部服务器错误"}
    }
)

# --- 移除本地 Pydantic 模型定义 ---
# class NodeCreateRequest(BaseModel):
#     ...
# class NodeUpdateRequest(BaseModel):
#     ...
# class NodeSearchRequest(BaseModel):
#     ...
# class NodeDetailRequest(BaseModel):
#     ...
# class NodeDeleteRequest(BaseModel):
#     ...
# class NodeResponse(BaseModel):
#     ...

# --- 路由 --- 

# 路由: 创建节点 (POST /)
@router.post(
    "/", 
    response_model=StandardResponse[NodeResponse], # 返回创建的节点信息
    status_code=201,
    summary="创建新节点"
)
async def create_node(
    node_create: NodeCreate, # 使用标准模型
    request: Request, # 添加 Request
    current_user: User = Depends(JWTBearer()),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """为当前认证用户创建一个新的节点"""
    node_service = NodeService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        # 将 Pydantic 模型转为字典传递给服务层
        node_data = node_create.model_dump()
        new_node = node_service.create_node(
            user_id=current_user.id,
            node_data=node_data
        )
        response_data = NodeResponse.model_validate(new_node)
        logger.info(f"用户 {current_user.id} 成功创建节点 {response_data.id} (Request ID: {req_id})")
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            message="节点创建成功", 
            code=201,
            data=response_data
        )
    except ForbiddenException as e: # 如果服务层添加了限制检查
        logger.warning(f"创建节点失败 (Forbidden): {e} (Request ID: {req_id})")
        raise HTTPException(status_code=403, detail=str(e))
    except NotFoundException as e: # 用户未找到 (理论上不太可能发生)
        logger.warning(f"创建节点失败 (NotFound): {e} (Request ID: {req_id})")
        raise HTTPException(status_code=404, detail=str(e))
    except GatewayException as e:
        logger.error(f"创建节点路由出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"创建节点路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="创建节点时发生内部错误")

# 路由: 获取节点列表 (GET /)
@router.get(
    "/", 
    response_model=StandardResponse[NodeListResponse], # 使用列表响应模型
    summary="获取当前用户节点列表 (分页)"
)
async def list_nodes(
    request: Request,
    page: int = Query(1, description="页码 (从1开始)", ge=1),
    size: int = Query(10, description="每页数量 (1-100)", ge=1, le=100),
    current_user: User = Depends(JWTBearer()),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """获取当前认证用户的所有节点，支持分页"""
    node_service = NodeService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        # 调用服务层获取分页数据
        service_result = node_service.list_user_nodes(
            user_id=current_user.id,
            page=page,
            size=size
        )
        # 转换 ORM 列表为 Pydantic 列表
        node_items = [NodeResponse.model_validate(node) for node in service_result["items"]]
        # 创建 NodeListResponse
        response_data = NodeListResponse(
            items=node_items,
            pagination=service_result["pagination"]
        )
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            message="获取节点列表成功",
            code=200,
            data=response_data
        )
    except GatewayException as e:
        logger.error(f"获取节点列表路由出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"获取节点列表路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="获取节点列表时发生内部错误")

# 路由: 获取节点详情 (GET /{node_id})
@router.get(
    "/{node_id}", 
    response_model=StandardResponse[NodeResponse],
    summary="获取指定节点详情"
)
async def get_node(
    request: Request,
    node_id: int = Path(..., description="要获取详情的节点ID", ge=1),
    current_user: User = Depends(JWTBearer()),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """获取当前认证用户拥有的指定节点的详细信息"""
    node_service = NodeService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        # 调用服务层获取详情
        node = node_service.get_node_details(
            user_id=current_user.id, 
            node_id=node_id
        )
        response_data = NodeResponse.model_validate(node)
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            message="获取节点详情成功",
            code=200,
            data=response_data
        )
    except NotFoundException as e:
        logger.warning(f"获取节点详情失败: {e} (Request ID: {req_id})")
        raise HTTPException(status_code=404, detail=str(e))
    except GatewayException as e:
        logger.error(f"获取节点详情路由出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"获取节点详情路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="获取节点详情时发生内部错误")

# 路由: 更新节点信息 (PUT /{node_id})
@router.put(
    "/{node_id}", 
    response_model=StandardResponse[NodeResponse],
    summary="更新指定节点信息"
)
async def update_node(
    request: Request,
    node_id: int = Path(..., description="要更新的节点ID", ge=1),
    node_update: NodeUpdate = Body(...), # 使用标准模型作为 Body
    current_user: User = Depends(JWTBearer()),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """更新当前认证用户拥有的指定节点的信息"""
    node_service = NodeService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    # 获取需要更新的数据，排除未设置的字段
    update_data = node_update.model_dump(exclude_unset=True)
    if not update_data:
         logger.warning(f"尝试更新节点 {node_id} 但未提供任何数据 (Request ID: {req_id})")
         raise HTTPException(status_code=400, detail="没有提供需要更新的数据")
         
    try:
        # 调用服务层更新
        updated_node = node_service.update_node(
            user_id=current_user.id,
            node_id=node_id,
            update_data=update_data
        )
        response_data = NodeResponse.model_validate(updated_node)
        logger.info(f"用户 {current_user.id} 成功更新节点 {node_id} (Request ID: {req_id})")
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            message="节点更新成功",
            code=200,
            data=response_data
        )
    except NotFoundException as e:
        logger.warning(f"更新节点失败: {e} (Request ID: {req_id})")
        raise HTTPException(status_code=404, detail=str(e))
    except GatewayException as e:
        logger.error(f"更新节点路由出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"更新节点路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="更新节点时发生内部错误")

# 路由: 删除节点 (DELETE /{node_id})
@router.delete(
    "/{node_id}", 
    response_model=StandardResponse[None], # 成功时 data 为 None
    status_code=200, # 也可以用 204 No Content，但 StandardResponse 需要调整
    summary="删除指定节点"
)
async def delete_node(
    request: Request,
    node_id: int = Path(..., description="要删除的节点ID", ge=1),
    current_user: User = Depends(JWTBearer()),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """删除当前认证用户拥有的指定节点"""
    node_service = NodeService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        # 调用服务层删除
        success = node_service.delete_node(user_id=current_user.id, node_id=node_id)
        # 服务层成功返回 True，失败抛异常
        logger.info(f"用户 {current_user.id} 成功删除节点 {node_id} (Request ID: {req_id})")
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            message="节点删除成功",
            code=200,
            data=None
        )
    except NotFoundException as e:
        logger.warning(f"删除节点失败: {e} (Request ID: {req_id})")
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionDeniedException as e: # 捕获权限异常 (例如，节点有活动任务)
        logger.warning(f"删除节点失败 (Permission Denied): {e} (Request ID: {req_id})")
        raise HTTPException(status_code=403, detail=str(e))
    except GatewayException as e:
        logger.error(f"删除节点路由出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"删除节点路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="删除节点时发生内部错误") 