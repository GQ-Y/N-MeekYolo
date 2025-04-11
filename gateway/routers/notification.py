"""
通知管理相关路由 (用户侧)
"""
import logging # 添加 logging
from fastapi import APIRouter, Depends, HTTPException, Request, Query, Path, Body # 添加 Query, Path, Body
from sqlalchemy.orm import Session
from sqlalchemy import func # 导入 func
from pydantic import BaseModel, Field # 添加 BaseModel, Field
from typing import List, Optional, Any, Dict
import datetime
import uuid # 添加 uuid

from core.database import get_db
from core.schemas import (
    StandardResponse, 
    NotificationResponse, 
    NotificationListResponse, 
    PaginationData
)
from core.auth import JWTBearer
from core.models.user import User # 正确导入 User
from services.notification_service import NotificationService
from core.exceptions import (
    GatewayException, 
    NotFoundException, 
    InvalidInputException, # 保留
    PermissionDeniedException, # 添加
    ForbiddenException # 保留
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/notifications", # 保持前缀
    tags=["通知管理"], # 更新 tag
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
# class NotificationSearchRequest(BaseModel):
#     ...
# class MarkReadRequest(BaseModel):
#     ...
# class NotificationResponse(BaseModel):
#     ...

# --- 保留本地偏好设置模型 (待后续处理) ---
class NotificationPreferenceItem(BaseModel):
    notification_type: str
    channel: int # 0: in_app, 1: email
    is_enabled: bool

class UpdatePreferencesRequest(BaseModel):
    preferences: List[NotificationPreferenceItem]

class NotificationPreferenceResponse(BaseModel):
    notification_type: str
    channel: int
    is_enabled: bool
    # model_config = ConfigDict(from_attributes=True) # Pydantic v1 用 orm_mode
    class Config:
        from_attributes = True # Pydantic v2

# --- 路由 --- 

# 路由: 获取通知列表 (GET /)
@router.get(
    "/", 
    response_model=StandardResponse[NotificationListResponse],
    summary="获取当前用户通知列表 (分页)"
)
async def list_notifications(
    request: Request,
    page: int = Query(1, description="页码 (从1开始)", ge=1),
    size: int = Query(10, description="每页数量 (1-100)", ge=1, le=100),
    unread_only: bool = Query(False, description="是否只显示未读通知"),
    current_user: User = Depends(JWTBearer()),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """获取当前认证用户的通知列表，支持分页和过滤未读"""
    notification_service = NotificationService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        service_result = notification_service.list_user_notifications(
            user_id=current_user.id,
            page=page,
            size=size,
            only_unread=unread_only
        )
        notification_items = [NotificationResponse.model_validate(n) for n in service_result["items"]]
        response_data = NotificationListResponse(
            items=notification_items,
            pagination=service_result["pagination"]
        )
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            message="获取通知列表成功",
            code=200,
            data=response_data
        )
    except GatewayException as e:
        logger.error(f"获取通知列表路由出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"获取通知列表路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="获取通知列表时发生内部错误")

# 路由: 标记单个通知为已读 (PUT /{notification_id}/read)
@router.put(
    "/{notification_id}/read", 
    response_model=StandardResponse[NotificationResponse],
    summary="标记单个通知为已读"
)
async def mark_notification_read(
    request: Request,
    notification_id: int = Path(..., description="要标记为已读的通知ID", ge=1),
    current_user: User = Depends(JWTBearer()),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """将当前认证用户拥有的指定通知标记为已读"""
    notification_service = NotificationService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        updated_notification = notification_service.mark_notification_as_read(
            user_id=current_user.id,
            notification_id=notification_id
        )
        response_data = NotificationResponse.model_validate(updated_notification)
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            message="通知已标记为已读",
            code=200,
            data=response_data
        )
    except NotFoundException as e:
        logger.warning(f"标记通知已读失败: {e} (Request ID: {req_id})")
        raise HTTPException(status_code=404, detail=str(e))
    except GatewayException as e:
        logger.error(f"标记通知已读路由出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"标记通知已读路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="标记通知为已读时发生内部错误")

# 路由: 标记所有通知为已读 (PUT /read/all)
@router.put(
    "/read/all", 
    response_model=StandardResponse[Dict[str, int]], # 返回标记的数量
    summary="标记所有未读通知为已读"
)
async def mark_all_notifications_read(
    request: Request,
    current_user: User = Depends(JWTBearer()),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """将当前认证用户的所有未读通知标记为已读"""
    notification_service = NotificationService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        marked_count = notification_service.mark_all_notifications_as_read(user_id=current_user.id)
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            message=f"成功标记 {marked_count} 条通知为已读",
            code=200,
            data={"marked_count": marked_count}
        )
    except GatewayException as e:
        logger.error(f"标记全部已读路由出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"标记全部已读路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="标记所有通知为已读时发生内部错误")

# 路由: 删除通知 (DELETE /{notification_id})
@router.delete(
    "/{notification_id}", 
    response_model=StandardResponse[None],
    status_code=200,
    summary="删除指定通知"
)
async def delete_notification(
    request: Request,
    notification_id: int = Path(..., description="要删除的通知ID", ge=1),
    current_user: User = Depends(JWTBearer()),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """删除当前认证用户拥有的指定通知"""
    notification_service = NotificationService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        success = notification_service.delete_notification(
            user_id=current_user.id, 
            notification_id=notification_id
        )
        logger.info(f"用户 {current_user.id} 成功删除通知 {notification_id} (Request ID: {req_id})")
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            message="通知删除成功",
            code=200,
            data=None
        )
    except NotFoundException as e:
        logger.warning(f"删除通知失败: {e} (Request ID: {req_id})")
        raise HTTPException(status_code=404, detail=str(e))
    except GatewayException as e:
        logger.error(f"删除通知路由出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"删除通知路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="删除通知时发生内部错误")

# --- 保留偏好设置路由 (待实现服务方法) ---
@router.get(
    "/preferences", 
    response_model=StandardResponse[List[NotificationPreferenceResponse]], # 使用本地模型
    summary="获取通知偏好设置 (待实现)"
)
async def get_notification_preferences(
    request: Request,
    current_user: User = Depends(JWTBearer()),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """获取当前用户的通知偏好设置 (TODO: 实现服务层逻辑)"""
    notification_service = NotificationService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        # TODO: 调用服务层 notification_service.get_user_preferences(user_id=current_user.id)
        preferences = [] # 示例空列表
        response_data = [NotificationPreferenceResponse.model_validate(p) for p in preferences]
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=False, # 标记未实现
            message="获取通知偏好设置功能待实现",
            code=501,
            data=response_data
            )
    except GatewayException as e:
        logger.error(f"获取通知偏好路由出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"获取通知偏好路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="获取通知偏好设置时发生内部错误")

@router.put(
    "/preferences", 
    response_model=StandardResponse[List[NotificationPreferenceResponse]], # 使用本地模型
    summary="更新通知偏好设置 (待实现)"
)
async def update_notification_preferences(
    request: Request,
    request_body: UpdatePreferencesRequest,
    current_user: User = Depends(JWTBearer()),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """批量更新当前用户的通知偏好设置 (TODO: 实现服务层逻辑)"""
    notification_service = NotificationService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    preferences_list = [p.dict() for p in request_body.preferences] 
    if not preferences_list:
        raise HTTPException(status_code=400, detail="偏好设置列表不能为空")

    try:
        # TODO: 调用服务层 notification_service.update_user_preferences(...)
        updated_preferences = [] # 示例空列表
        response_data = [NotificationPreferenceResponse.model_validate(p) for p in updated_preferences]
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=False, # 标记未实现
            message="更新通知偏好设置功能待实现",
            code=501,
            data=response_data
            )
    except GatewayException as e:
        logger.error(f"更新通知偏好路由出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"更新通知偏好路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="更新通知偏好设置时发生内部错误") 