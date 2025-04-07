"""
MQTT节点管理路由模块

提供MQTT节点的管理接口，支持：
- 获取节点列表
- 获取节点详情
- 编辑节点
- 删除节点
- 启用/停用节点
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from typing import List, Optional, Dict, Any
from models.responses import BaseResponse, PaginationResponse
from models.schemas import MQTTNodeResponse, MQTTNodeUpdate
from core.database import get_db
from crud.mqtt_node import MQTTNodeCRUD
from sqlalchemy.orm import Session
from shared.utils.logger import setup_logger
import time

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/v1/mqtt/nodes", tags=["MQTT节点"])

@router.get("", response_model=PaginationResponse, summary="获取MQTT节点列表")
async def get_mqtt_nodes(
    db: Session = Depends(get_db),
    skip: int = Query(0, description="跳过记录数"),
    limit: int = Query(20, description="返回记录数"),
    service_type: Optional[str] = Query(None, description="服务类型"),
    status: Optional[str] = Query(None, description="节点状态"),
    is_active: Optional[bool] = Query(None, description="是否启用"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
    order_by: str = Query("id", description="排序字段"),
    order_direction: str = Query("desc", description="排序方向")
):
    """
    获取MQTT节点列表，支持分页、过滤和排序
    """
    try:
        # 获取MQTT节点列表
        nodes, total = MQTTNodeCRUD.get_mqtt_nodes(
            db=db,
            skip=skip,
            limit=limit,
            service_type=service_type,
            status=status,
            is_active=is_active,
            keyword=keyword,
            order_by=order_by,
            order_direction=order_direction
        )
        
        # 转换为响应模型
        node_responses = [MQTTNodeResponse.from_orm(node) for node in nodes]
        
        # 构建分页响应
        return PaginationResponse(
            path=f"/api/v1/mqtt/nodes",
            success=True,
            message="Success",
            code=200,
            data=node_responses,
            pagination={
                "total": total,
                "page": skip // limit + 1 if limit > 0 else 1,
                "size": limit,
                "pages": (total + limit - 1) // limit if limit > 0 else 1
            },
            timestamp=int(time.time())
        )
    except Exception as e:
        logger.error(f"获取MQTT节点列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取MQTT节点列表失败: {str(e)}")

@router.get("/{node_id}", response_model=BaseResponse, summary="获取MQTT节点详情")
async def get_mqtt_node(
    node_id: int = Path(..., description="节点ID"),
    db: Session = Depends(get_db)
):
    """
    根据ID获取MQTT节点详情
    """
    try:
        # 获取MQTT节点
        node = MQTTNodeCRUD.get_mqtt_node(db=db, node_id=node_id)
        if not node:
            return BaseResponse(
                path=f"/api/v1/mqtt/nodes/{node_id}",
                success=False,
                message=f"节点不存在: {node_id}",
                code=404,
                data=None,
                timestamp=int(time.time())
            )
        
        # 构建响应
        return BaseResponse(
            path=f"/api/v1/mqtt/nodes/{node_id}",
            success=True,
            message="Success",
            code=200,
            data=MQTTNodeResponse.from_orm(node),
            timestamp=int(time.time())
        )
    except Exception as e:
        logger.error(f"获取MQTT节点详情失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取MQTT节点详情失败: {str(e)}")

@router.put("/{node_id}", response_model=BaseResponse, summary="更新MQTT节点")
async def update_mqtt_node(
    node_data: MQTTNodeUpdate,
    node_id: int = Path(..., description="节点ID"),
    db: Session = Depends(get_db)
):
    """
    更新MQTT节点信息
    """
    try:
        # 检查节点是否存在
        node = MQTTNodeCRUD.get_mqtt_node(db=db, node_id=node_id)
        if not node:
            return BaseResponse(
                path=f"/api/v1/mqtt/nodes/{node_id}",
                success=False,
                message=f"节点不存在: {node_id}",
                code=404,
                data=None,
                timestamp=int(time.time())
            )
        
        # 更新节点
        updated_node = MQTTNodeCRUD.update_mqtt_node(
            db=db, 
            node_id=node_id, 
            node_data=node_data.dict(exclude_unset=True)
        )
        
        # 构建响应
        return BaseResponse(
            path=f"/api/v1/mqtt/nodes/{node_id}",
            success=True,
            message="节点更新成功",
            code=200,
            data=MQTTNodeResponse.from_orm(updated_node),
            timestamp=int(time.time())
        )
    except Exception as e:
        logger.error(f"更新MQTT节点失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新MQTT节点失败: {str(e)}")

@router.delete("/{node_id}", response_model=BaseResponse, summary="删除MQTT节点")
async def delete_mqtt_node(
    node_id: int = Path(..., description="节点ID"),
    db: Session = Depends(get_db)
):
    """
    删除MQTT节点
    """
    try:
        # 删除节点
        success = MQTTNodeCRUD.delete_mqtt_node(db=db, node_id=node_id)
        if not success:
            return BaseResponse(
                path=f"/api/v1/mqtt/nodes/{node_id}",
                success=False,
                message=f"节点不存在或删除失败: {node_id}",
                code=404,
                data=None,
                timestamp=int(time.time())
            )
        
        # 构建响应
        return BaseResponse(
            path=f"/api/v1/mqtt/nodes/{node_id}",
            success=True,
            message="节点删除成功",
            code=200,
            data=None,
            timestamp=int(time.time())
        )
    except Exception as e:
        logger.error(f"删除MQTT节点失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除MQTT节点失败: {str(e)}")

@router.patch("/{node_id}/status", response_model=BaseResponse, summary="启用/停用MQTT节点")
async def toggle_mqtt_node_status(
    node_id: int = Path(..., description="节点ID"),
    is_active: bool = Query(..., description="是否启用"),
    db: Session = Depends(get_db)
):
    """
    启用或停用MQTT节点
    """
    try:
        # 更新节点状态
        node = MQTTNodeCRUD.toggle_mqtt_node_active(db=db, node_id=node_id, is_active=is_active)
        if not node:
            return BaseResponse(
                path=f"/api/v1/mqtt/nodes/{node_id}/status",
                success=False,
                message=f"节点不存在: {node_id}",
                code=404,
                data=None,
                timestamp=int(time.time())
            )
        
        # 构建响应
        status_str = "启用" if is_active else "停用"
        return BaseResponse(
            path=f"/api/v1/mqtt/nodes/{node_id}/status",
            success=True,
            message=f"节点{status_str}成功",
            code=200,
            data=MQTTNodeResponse.from_orm(node),
            timestamp=int(time.time())
        )
    except Exception as e:
        logger.error(f"更改MQTT节点状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"更改MQTT节点状态失败: {str(e)}") 