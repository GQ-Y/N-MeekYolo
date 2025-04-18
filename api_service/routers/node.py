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
from fastapi import APIRouter, Depends, HTTPException, Request, Query, Body
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from core.database import get_db
from crud.node import NodeCRUD
from models.responses import (
    BaseResponse,
    NodeCreate,
    NodeUpdate,
    NodeResponse,
    NodeStatusUpdate,
    NodeTaskCountsUpdate
)

class NodeIdRequest(BaseModel):
    """节点ID请求模型"""
    node_id: int = Field(..., description="节点ID")

router = APIRouter(prefix="/api/v1/nodes", tags=["节点管理"])
node_crud = NodeCRUD()

@router.post("", response_model=BaseResponse, summary="创建节点")
def create_node(
    request: Request,
    ip: str = Body(..., description="节点IP地址"),
    port: str = Body(..., description="节点端口"),
    service_name: str = Body(..., description="服务名称"),
    weight: int = Body(1, description="负载均衡权重"),
    max_tasks: int = Body(10, description="最大任务数量"),
    node_type: str = Body("edge", description="节点类型：edge(边缘节点)、cluster(集群节点)"),
    service_type: int = Body(1, description="服务类型：1-分析服务、2-模型服务、3-云服务"),
    compute_type: str = Body("cpu", description="计算类型：cpu(CPU计算边缘节点)、camera(摄像头边缘节点)、gpu(GPU计算边缘节点)、elastic(弹性集群节点)"),
    db: Session = Depends(get_db)
):
    """
    创建新节点
    
    参数:
    - ip: 节点IP地址
    - port: 节点端口
    - service_name: 服务名称
    - weight: 负载均衡权重(默认1)
    - max_tasks: 最大任务数量(默认10)
    - node_type: 节点类型(默认edge)
    - service_type: 服务类型(默认1)
    - compute_type: 计算类型(默认cpu)
    
    返回:
    - 创建成功的节点信息
    """
    try:
        # 验证service_type
        if service_type not in [1, 2, 3]:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=400,
                message="无效的服务类型，必须是1(分析服务)、2(模型服务)或3(云服务)"
            )
        
        # 验证node_type
        if node_type not in ["edge", "cluster"]:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=400,
                message="无效的节点类型，必须是edge(边缘节点)或cluster(集群节点)"
            )
        
        # 验证compute_type
        if compute_type not in ["cpu", "camera", "gpu", "elastic"]:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=400,
                message="无效的计算类型，必须是cpu、camera、gpu或elastic"
            )
        
        # 如果是模型服务或云服务，检查是否已存在
        if service_type in [2, 3]:
            existing_node = node_crud.get_node_by_service_type(db, service_type)
            if existing_node:
                return BaseResponse(
                    path=str(request.url),
                    success=False,
                    code=400,
                    message=f"已存在{'模型' if service_type == 2 else '云'}服务节点"
                )
        
        node = NodeCreate(
            ip=ip,
            port=port,
            service_name=service_name,
            weight=weight,
            max_tasks=max_tasks,
            node_type=node_type,
            service_type=service_type,
            compute_type=compute_type
        )
        db_node = node_crud.create_node(db, node)
        
        # 手动构建响应数据
        node_data = {
            "id": db_node.id,
            "ip": db_node.ip,
            "port": db_node.port,
            "service_name": db_node.service_name,
            "service_status": db_node.service_status,
            "image_task_count": db_node.image_task_count,
            "video_task_count": db_node.video_task_count,
            "stream_task_count": db_node.stream_task_count,
            "weight": db_node.weight,
            "max_tasks": db_node.max_tasks,
            "is_active": db_node.is_active,
            "created_at": db_node.created_at,
            "updated_at": db_node.updated_at,
            "last_heartbeat": db_node.last_heartbeat,
            "node_type": db_node.node_type,
            "service_type": db_node.service_type,
            "compute_type": db_node.compute_type,
            "memory_usage": db_node.memory_usage,
            "gpu_memory_usage": db_node.gpu_memory_usage,
            "total_tasks": 0
        }
        
        return BaseResponse(
            path=str(request.url),
            message="节点创建成功",
            data=node_data
        )
    except Exception as e:
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=f"节点创建失败: {str(e)}"
        )

@router.get("", response_model=BaseResponse, summary="获取节点列表")
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
        db_nodes = node_crud.get_nodes(db, skip=skip, limit=limit)
        nodes = []
        
        # 手动构建响应数据
        for node in db_nodes:
            node_data = {
                "id": node.id,
                "ip": node.ip,
                "port": node.port,
                "service_name": node.service_name,
                "service_status": node.service_status,
                "image_task_count": node.image_task_count,
                "video_task_count": node.video_task_count,
                "stream_task_count": node.stream_task_count,
                "weight": node.weight,
                "max_tasks": node.max_tasks,
                "is_active": node.is_active,
                "created_at": node.created_at,
                "updated_at": node.updated_at,
                "last_heartbeat": node.last_heartbeat,
                "node_type": node.node_type,
                "service_type": node.service_type,
                "compute_type": node.compute_type,
                "memory_usage": node.memory_usage,
                "gpu_memory_usage": node.gpu_memory_usage,
                "cpu_usage": node.cpu_usage,
                "gpu_usage": node.gpu_usage,
                "total_tasks": (node.image_task_count or 0) + (node.video_task_count or 0) + (node.stream_task_count or 0)
            }
            nodes.append(node_data)
        
        return BaseResponse(
            path=str(request.url),
            message="获取成功",
            data=nodes
        )
    except Exception as e:
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=f"获取节点列表失败: {str(e)}"
        )

@router.post("/update", response_model=BaseResponse, summary="更新节点信息")
def update_node(
    request: Request,
    node_id: int = Body(..., description="节点ID"),
    ip: Optional[str] = Body(None, description="节点IP地址"),
    port: Optional[str] = Body(None, description="节点端口"),
    service_name: Optional[str] = Body(None, description="服务名称"),
    service_status: Optional[str] = Body(None, description="服务状态"),
    weight: Optional[int] = Body(None, description="负载均衡权重"),
    max_tasks: Optional[int] = Body(None, description="最大任务数量"),
    node_type: Optional[str] = Body(None, description="节点类型"),
    service_type: Optional[int] = Body(None, description="服务类型"),
    compute_type: Optional[str] = Body(None, description="计算类型"),
    memory_usage: Optional[float] = Body(None, description="内存占用率"),
    gpu_memory_usage: Optional[float] = Body(None, description="GPU显存占用率"),
    db: Session = Depends(get_db)
):
    """
    更新节点基本信息
    
    参数:
    - node_id: 节点ID
    - ip: 节点IP地址(可选)
    - port: 节点端口(可选)
    - service_name: 服务名称(可选)
    - service_status: 服务状态(可选)
    - weight: 负载均衡权重(可选)
    - max_tasks: 最大任务数量(可选)
    - node_type: 节点类型(可选)
    - service_type: 服务类型(可选)
    - compute_type: 计算类型(可选)
    - memory_usage: 内存占用率(可选)
    - gpu_memory_usage: GPU显存占用率(可选)
    
    返回:
    - 更新后的节点信息
    """
    try:
        # 验证service_type
        if service_type is not None and service_type not in [1, 2, 3]:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=400,
                message="无效的服务类型，必须是1(分析服务)、2(模型服务)或3(云服务)"
            )
        
        # 验证node_type
        if node_type is not None and node_type not in ["edge", "cluster"]:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=400,
                message="无效的节点类型，必须是edge(边缘节点)或cluster(集群节点)"
            )
        
        # 验证compute_type
        if compute_type is not None and compute_type not in ["cpu", "camera", "gpu", "elastic"]:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=400,
                message="无效的计算类型，必须是cpu、camera、gpu或elastic"
            )
        
        # 如果要更新为模型服务或云服务，检查是否已存在
        if service_type in [2, 3]:
            existing_node = node_crud.get_node_by_service_type(db, service_type)
            if existing_node and existing_node.id != node_id:
                return BaseResponse(
                    path=str(request.url),
                    success=False,
                    code=400,
                    message=f"已存在{'模型' if service_type == 2 else '云'}服务节点"
                )
        
        node_update = NodeUpdate(
            ip=ip,
            port=port,
            service_name=service_name,
            service_status=service_status,
            weight=weight,
            max_tasks=max_tasks,
            node_type=node_type,
            service_type=service_type,
            compute_type=compute_type,
            memory_usage=memory_usage,
            gpu_memory_usage=gpu_memory_usage
        )
        db_node = node_crud.update_node(db, node_id, node_update)
        if not db_node:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="节点不存在"
            )
            
        # 手动构建响应数据
        node_data = {
            "id": db_node.id,
            "ip": db_node.ip,
            "port": db_node.port,
            "service_name": db_node.service_name,
            "service_status": db_node.service_status,
            "image_task_count": db_node.image_task_count,
            "video_task_count": db_node.video_task_count,
            "stream_task_count": db_node.stream_task_count,
            "weight": db_node.weight,
            "max_tasks": db_node.max_tasks,
            "is_active": db_node.is_active,
            "created_at": db_node.created_at,
            "updated_at": db_node.updated_at,
            "last_heartbeat": db_node.last_heartbeat,
            "node_type": db_node.node_type,
            "service_type": db_node.service_type,
            "compute_type": db_node.compute_type,
            "memory_usage": db_node.memory_usage,
            "gpu_memory_usage": db_node.gpu_memory_usage,
            "total_tasks": (db_node.image_task_count or 0) + (db_node.video_task_count or 0) + (db_node.stream_task_count or 0)
        }
        
        return BaseResponse(
            path=str(request.url),
            message="更新成功",
            data=node_data
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
    node_data: NodeIdRequest,
    db: Session = Depends(get_db)
):
    """
    删除指定节点
    
    参数:
    - node_id: 节点ID (请求体参数)
    
    返回:
    - 删除结果
    """
    try:
        result = node_crud.delete_node(db, node_data.node_id)
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

@router.post("/status", response_model=BaseResponse, summary="更新节点状态")
def update_node_status(
    request: Request,
    node_id: int = Body(..., description="节点ID"),
    service_status: str = Body(..., description="服务状态"),
    memory_usage: Optional[float] = Body(None, description="内存占用率"),
    gpu_memory_usage: Optional[float] = Body(None, description="GPU显存占用率"),
    db: Session = Depends(get_db)
):
    """
    更新节点状态
    
    参数:
    - node_id: 节点ID
    - service_status: 服务状态
    - memory_usage: 内存占用率(可选)
    - gpu_memory_usage: GPU显存占用率(可选)
    
    返回:
    - 更新后的节点信息
    """
    try:
        node_update = NodeUpdate(
            service_status=service_status,
            memory_usage=memory_usage,
            gpu_memory_usage=gpu_memory_usage
        )
        db_node = node_crud.update_node(db, node_id, node_update)
        if not db_node:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="节点不存在"
            )
            
        # 手动构建响应数据
        node_data = {
            "id": db_node.id,
            "ip": db_node.ip,
            "port": db_node.port,
            "service_name": db_node.service_name,
            "service_status": db_node.service_status,
            "image_task_count": db_node.image_task_count,
            "video_task_count": db_node.video_task_count,
            "stream_task_count": db_node.stream_task_count,
            "weight": db_node.weight,
            "max_tasks": db_node.max_tasks,
            "is_active": db_node.is_active,
            "created_at": db_node.created_at,
            "updated_at": db_node.updated_at,
            "last_heartbeat": db_node.last_heartbeat,
            "node_type": db_node.node_type,
            "service_type": db_node.service_type,
            "compute_type": db_node.compute_type,
            "memory_usage": db_node.memory_usage,
            "gpu_memory_usage": db_node.gpu_memory_usage,
            "total_tasks": (db_node.image_task_count or 0) + (db_node.video_task_count or 0) + (db_node.stream_task_count or 0)
        }
        
        return BaseResponse(
            path=str(request.url),
            message="状态更新成功",
            data=node_data
        )
    except Exception as e:
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=f"更新节点状态失败: {str(e)}"
        )

@router.post("/task-counts", response_model=BaseResponse, summary="更新任务数量")
def update_task_counts(
    request: Request,
    node_id: int = Body(..., description="节点ID"),
    image_task_count: int = Body(0, description="图像任务数量"),
    video_task_count: int = Body(0, description="视频任务数量"),
    stream_task_count: int = Body(0, description="流任务数量"),
    db: Session = Depends(get_db)
):
    """
    更新节点任务数量
    
    参数:
    - node_id: 节点ID
    - image_task_count: 图像任务数量
    - video_task_count: 视频任务数量
    - stream_task_count: 流任务数量
    
    返回:
    - 更新后的节点信息
    """
    try:
        db_node = node_crud.update_node_status(
            db,
            node_id,
            "online",  # 更新任务数量时自动设置为在线状态
            {
                'image': image_task_count,
                'video': video_task_count,
                'stream': stream_task_count
            }
        )
        if not db_node:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="节点不存在"
            )
            
        # 手动构建响应数据
        node_data = {
            "id": db_node.id,
            "ip": db_node.ip,
            "port": db_node.port,
            "service_name": db_node.service_name,
            "service_status": db_node.service_status,
            "image_task_count": db_node.image_task_count,
            "video_task_count": db_node.video_task_count,
            "stream_task_count": db_node.stream_task_count,
            "weight": db_node.weight,
            "max_tasks": db_node.max_tasks,
            "is_active": db_node.is_active,
            "created_at": db_node.created_at,
            "updated_at": db_node.updated_at,
            "last_heartbeat": db_node.last_heartbeat,
            "node_type": db_node.node_type,
            "service_type": db_node.service_type,
            "compute_type": db_node.compute_type,
            "memory_usage": db_node.memory_usage,
            "gpu_memory_usage": db_node.gpu_memory_usage,
            "total_tasks": (db_node.image_task_count or 0) + (db_node.video_task_count or 0) + (db_node.stream_task_count or 0)
        }
        
        return BaseResponse(
            path=str(request.url),
            message="任务数量更新成功",
            data=node_data
        )
    except Exception as e:
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=f"更新任务数量失败: {str(e)}"
        ) 