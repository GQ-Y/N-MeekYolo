"""
节点管理路由模块

提供节点的增删改查接口，支持：
- 节点列表：获取所有注册的节点
- 节点创建：注册新的节点
- 节点更新：更新节点基本信息
- 节点删除：删除指定节点
- 状态更新：更新节点状态
- 任务更新：更新节点任务数量
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from api_service.core.database import get_db
from api_service.crud.node import NodeCRUD
from api_service.models.responses import (
    BaseResponse,
    NodeCreate,
    NodeUpdate,
    NodeResponse,
    NodeListResponse,
    NodeStatusUpdate,
    NodeTaskCountsUpdate
)

class NodeIdRequest(BaseModel):
    """节点ID请求模型"""
    node_id: int = Field(..., description="节点ID")

router = APIRouter(prefix="/api/v1/nodes", tags=["节点管理"])
node_crud = NodeCRUD()

@router.post("", response_model=BaseResponse[NodeResponse], summary="创建节点")
def create_node(
    request: Request,
    node: NodeCreate,
    db: Session = Depends(get_db)
):
    """
    创建新节点
    
    参数:
    - node: 节点创建参数，包含IP、端口和服务名称
    
    返回:
    - 创建成功的节点信息
    """
    try:
        db_node = node_crud.create_node(db, node)
        return BaseResponse(
            path=str(request.url),
            message="节点创建成功",
            data=db_node
        )
    except Exception as e:
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=f"节点创建失败: {str(e)}"
        )

@router.get("", response_model=NodeListResponse, summary="获取节点列表")
def get_nodes(
    request: Request,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    获取所有节点列表
    
    参数:
    - skip: 跳过的记录数
    - limit: 返回的最大记录数
    
    返回:
    - 节点列表
    """
    try:
        nodes = node_crud.get_nodes(db, skip=skip, limit=limit)
        return NodeListResponse(
            path=str(request.url),
            message="获取成功",
            data=nodes
        )
    except Exception as e:
        return NodeListResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=f"获取节点列表失败: {str(e)}"
        )

@router.post("/update", response_model=BaseResponse[NodeResponse], summary="更新节点信息")
def update_node(
    request: Request,
    node_id_req: NodeIdRequest,
    node_update: NodeUpdate,
    db: Session = Depends(get_db)
):
    """
    更新节点基本信息
    
    参数:
    - node_id_req: 节点ID
    - node_update: 要更新的节点信息，包含IP、端口、服务名称等
    
    返回:
    - 更新后的节点信息
    """
    try:
        db_node = node_crud.update_node(db, node_id_req.node_id, node_update)
        if not db_node:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="节点不存在"
            )
        return BaseResponse(
            path=str(request.url),
            message="更新成功",
            data=db_node
        )
    except Exception as e:
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=f"更新节点失败: {str(e)}"
        )

@router.post("/delete", response_model=BaseResponse, summary="删除节点")
def delete_node(
    request: Request,
    node_id_req: NodeIdRequest,
    db: Session = Depends(get_db)
):
    """
    删除指定节点
    
    参数:
    - node_id_req: 节点ID
    
    返回:
    - 删除结果
    """
    try:
        result = node_crud.delete_node(db, node_id_req.node_id)
        if not result:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="节点不存在"
            )
        return BaseResponse(
            path=str(request.url),
            message="节点已删除"
        )
    except Exception as e:
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=f"删除节点失败: {str(e)}"
        )

@router.post("/status", response_model=BaseResponse[NodeResponse], summary="更新节点状态")
def update_node_status(
    request: Request,
    status_update: NodeStatusUpdate,
    db: Session = Depends(get_db)
):
    """
    更新节点状态
    
    参数:
    - status_update: 状态更新信息，包含节点ID和服务状态
    
    返回:
    - 更新后的节点信息
    """
    try:
        db_node = node_crud.update_node(
            db,
            status_update.node_id,
            NodeUpdate(service_status=status_update.service_status)
        )
        if not db_node:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="节点不存在"
            )
        return BaseResponse(
            path=str(request.url),
            message="状态更新成功",
            data=db_node
        )
    except Exception as e:
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=f"更新节点状态失败: {str(e)}"
        )

@router.post("/task-counts", response_model=BaseResponse[NodeResponse], summary="更新任务数量")
def update_task_counts(
    request: Request,
    task_counts: NodeTaskCountsUpdate,
    db: Session = Depends(get_db)
):
    """
    更新节点任务数量
    
    参数:
    - task_counts: 任务数量更新信息，包含节点ID和各类任务数量
    
    返回:
    - 更新后的节点信息
    """
    try:
        db_node = node_crud.update_node_status(
            db,
            task_counts.node_id,
            "online",  # 更新任务数量时自动设置为在线状态
            {
                'image': task_counts.image_task_count,
                'video': task_counts.video_task_count,
                'stream': task_counts.stream_task_count
            }
        )
        if not db_node:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="节点不存在"
            )
        return BaseResponse(
            path=str(request.url),
            message="任务数量更新成功",
            data=db_node
        )
    except Exception as e:
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=f"更新任务数量失败: {str(e)}"
        ) 