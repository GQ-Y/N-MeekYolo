"""
MQTT节点管理路由模块

提供MQTT节点的管理接口，支持：
- 获取节点列表
- 获取节点详情
- 编辑节点
- 删除节点
- 启用/停用节点
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Body
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import time

from core.database import get_db
from crud.mqtt_node import MQTTNodeCRUD
from models.responses import BaseResponse, PaginationResponse
from models.schemas import MQTTNodeResponse, MQTTNodeUpdate
from shared.utils.logger import setup_logger

# 设置日志记录器
logger = setup_logger(__name__)

# 创建路由器
router = APIRouter(prefix="/api/v1/mqtt/nodes", tags=["MQTT节点"])

@router.post("/list", response_model=PaginationResponse, summary="获取MQTT节点列表")
def get_mqtt_nodes(
    request: Request,
    skip: int = Body(0, description="跳过记录数", embed=True),
    limit: int = Body(20, description="返回记录数", ge=1, le=100, embed=True),
    service_type: Optional[str] = Body(None, description="服务类型", embed=True),
    status: Optional[str] = Body(None, description="节点状态", embed=True),
    is_active: Optional[bool] = Body(None, description="是否启用", embed=True),
    keyword: Optional[str] = Body(None, description="关键词搜索", embed=True),
    order_by: str = Body("id", description="排序字段", embed=True),
    order_direction: str = Body("desc", description="排序方向", embed=True),
    db: Session = Depends(get_db)
):
    """
    获取MQTT节点列表，支持分页、过滤和排序
    如果不传入is_active参数，则返回所有节点，否则按照is_active状态过滤
    
    请求参数:
    - skip: 跳过记录数
    - limit: 返回记录数，范围1-100
    - service_type: 服务类型过滤
    - status: 节点状态过滤
    - is_active: 是否启用过滤（可选，不传则返回所有节点）
    - keyword: 关键词搜索
    - order_by: 排序字段
    - order_direction: 排序方向，asc或desc
    
    返回:
    - 分页的节点列表数据
    """
    try:
        # 参数验证
        if order_direction not in ["asc", "desc"]:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=400,
                message="排序方向必须是asc或desc"
            )
            
        # 获取MQTT节点列表
        nodes, total = MQTTNodeCRUD.get_mqtt_nodes(
            db=db,
            skip=skip,
            limit=limit,
            service_type=service_type,
            status=status,
            is_active=is_active,  # 如果不传入is_active，则返回所有节点
            keyword=keyword,
            order_by=order_by,
            order_direction=order_direction
        )
        
        # 转换为响应模型
        node_responses = [MQTTNodeResponse.model_validate(node) for node in nodes]
        
        # 构建分页响应
        return PaginationResponse(
            path="/api/v1/mqtt/nodes/list",
            success=True,
            message="获取节点列表成功",
            code=200,
            data=node_responses,
            pagination={
                "total": total,
                "page": skip // limit + 1 if limit > 0 else 1,
                "size": limit,
                "pages": (total + limit - 1) // limit if limit > 0 else 1
            }
        )
    except Exception as e:
        logger.error(f"获取MQTT节点列表失败: {e}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=f"获取MQTT节点列表失败: {str(e)}"
        )

@router.post("/detail", response_model=BaseResponse, summary="获取MQTT节点详情")
def get_mqtt_node(
    request: Request,
    node_id: int = Body(..., description="节点ID", embed=True),
    db: Session = Depends(get_db)
):
    """
    获取MQTT节点详情，不考虑节点的启用/停用状态
    
    请求参数:
    - node_id: 节点ID
    
    返回:
    - 节点详细信息
    """
    try:
        # 获取MQTT节点，不考虑is_active状态
        node = MQTTNodeCRUD.get_mqtt_node(db=db, node_id=node_id)
        if not node:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message=f"节点不存在: {node_id}"
            )
        
        # 构建响应
        return BaseResponse(
            path="/api/v1/mqtt/nodes/detail",
            success=True,
            message="获取节点详情成功",
            code=200,
            data=MQTTNodeResponse.model_validate(node)
        )
    except Exception as e:
        logger.error(f"获取MQTT节点详情失败: {e}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=f"获取MQTT节点详情失败: {str(e)}"
        )

@router.post("/update", response_model=BaseResponse, summary="更新MQTT节点")
def update_mqtt_node(
    request: Request,
    node_id: int = Body(..., description="节点ID", embed=True),
    service_type: Optional[str] = Body(None, description="服务类型", embed=True),
    max_tasks: Optional[int] = Body(None, description="最大任务数", embed=True),
    remark: Optional[str] = Body(None, description="备注", embed=True),
    ip: Optional[str] = Body(None, description="IP地址", embed=True),
    port: Optional[int] = Body(None, description="端口", embed=True),
    hostname: Optional[str] = Body(None, description="主机名", embed=True),
    status: Optional[str] = Body(None, description="状态", embed=True),
    version: Optional[str] = Body(None, description="版本", embed=True),
    node_metadata: Optional[Dict[str, Any]] = Body(None, description="节点元数据", embed=True),
    db: Session = Depends(get_db)
):
    """
    更新MQTT节点信息
    
    请求参数:
    - node_id: 节点ID
    - service_type: 服务类型
    - max_tasks: 最大任务数
    - remark: 备注
    - ip: IP地址
    - port: 端口
    - hostname: 主机名
    - status: 状态
    - version: 版本
    - node_metadata: 节点元数据
    
    返回:
    - 更新后的节点信息
    """
    try:
        # 检查节点是否存在
        node = MQTTNodeCRUD.get_mqtt_node(db=db, node_id=node_id)
        if not node:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message=f"节点不存在: {node_id}"
            )
        
        # 构建更新数据
        update_data = {}
        if service_type is not None:
            update_data["service_type"] = service_type
        if max_tasks is not None:
            update_data["max_tasks"] = max_tasks
        if remark is not None:
            update_data["remark"] = remark
        if ip is not None:
            update_data["ip"] = ip
        if port is not None:
            update_data["port"] = port
        if hostname is not None:
            update_data["hostname"] = hostname
        if status is not None:
            update_data["status"] = status
        if version is not None:
            update_data["version"] = version
        if node_metadata is not None:
            update_data["node_metadata"] = node_metadata
        
        # 更新节点
        updated_node = MQTTNodeCRUD.update_mqtt_node(
            db=db, 
            node_id=node_id, 
            node_data=update_data
        )
        
        # 构建响应
        return BaseResponse(
            path="/api/v1/mqtt/nodes/update",
            success=True,
            message="节点更新成功",
            code=200,
            data=MQTTNodeResponse.model_validate(updated_node)
        )
    except Exception as e:
        logger.error(f"更新MQTT节点失败: {e}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=f"更新MQTT节点失败: {str(e)}"
        )

@router.post("/delete", response_model=BaseResponse, summary="删除MQTT节点")
def delete_mqtt_node(
    request: Request,
    node_id: int = Body(..., description="节点ID", embed=True),
    db: Session = Depends(get_db)
):
    """
    删除MQTT节点
    
    请求参数:
    - node_id: 节点ID
    
    返回:
    - 删除操作结果
    """
    try:
        # 删除节点
        success = MQTTNodeCRUD.delete_mqtt_node(db=db, node_id=node_id)
        if not success:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message=f"节点不存在: {node_id}"
            )
        
        # 构建响应
        return BaseResponse(
            path="/api/v1/mqtt/nodes/delete",
            success=True,
            message="节点删除成功",
            code=200,
            data=None
        )
    except Exception as e:
        logger.error(f"删除MQTT节点失败: {e}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=f"删除MQTT节点失败: {str(e)}"
        )

@router.post("/toggle-status", response_model=BaseResponse, summary="启用/停用MQTT节点")
def toggle_mqtt_node_status(
    request: Request,
    node_id: int = Body(..., description="节点ID", embed=True),
    is_active: bool = Body(..., description="是否启用", embed=True),
    db: Session = Depends(get_db)
):
    """
    启用或停用MQTT节点
    
    请求参数:
    - node_id: 节点ID
    - is_active: 是否启用
    
    返回:
    - 更新后的节点信息
    """
    try:
        # 更新节点状态
        node = MQTTNodeCRUD.toggle_mqtt_node_active(
            db=db, 
            node_id=node_id, 
            is_active=is_active
        )
        if not node:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message=f"节点不存在: {node_id}"
            )
        
        # 构建响应
        status_str = "启用" if is_active else "停用"
        return BaseResponse(
            path="/api/v1/mqtt/nodes/toggle-status",
            success=True,
            message=f"节点{status_str}成功",
            code=200,
            data=MQTTNodeResponse.model_validate(node)
        )
    except Exception as e:
        logger.error(f"更改MQTT节点状态失败: {e}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=f"更改MQTT节点状态失败: {str(e)}"
        ) 