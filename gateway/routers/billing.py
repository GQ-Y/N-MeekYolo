"""
账单与支付相关路由 (用户侧)
"""
import logging # 添加 logging
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query, Path, Body # 添加 Query, Path, Body
from sqlalchemy.orm import Session
from sqlalchemy import func # 导入 func
from pydantic import BaseModel, Field, ConfigDict # 添加 BaseModel, Field, ConfigDict
from typing import List, Optional, Any, Dict
import datetime
import uuid # 添加 uuid

from core.database import get_db
# 从 core.schemas 导入标准模型
from core.schemas import (
    StandardResponse, 
    BillingSearchRequest, 
    BillingRecordResponse, 
    BillingRecordListResponse, 
    ApplyCouponRequest, 
    ApplyCouponResponse, 
    PaginationData
)
from core.auth import JWTBearer
from core.models.user import User # 正确导入 User
# 导入服务和异常
from services.billing_service import BillingService
from core.exceptions import (
    GatewayException, 
    NotFoundException, 
    InvalidInputException, 
    ForbiddenException, # 保留
    PermissionDeniedException # 添加
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/billing",
    tags=["账单与支付"], # 更新 tag
    dependencies=[Depends(JWTBearer())], # 添加 JWT 依赖
    responses={ # 添加通用响应
        400: {"description": "无效请求"},
        401: {"description": "认证失败"},
        403: {"description": "权限不足"},
        404: {"description": "资源未找到"},
        409: {"description": "冲突"},
        500: {"description": "内部服务器错误"}
    }
)

# --- 移除本地 Pydantic 模型定义 ---
# class BillingSearchRequest(BaseModel):
#     ...
# class BillingDetailRequest(BaseModel):
#     ...
# class ApplyCouponRequest(BaseModel):
#     ...
# class BillingRecordResponse(BaseModel):
#     ...

# --- 保留支付相关模型 (待后续处理) ---
class InitiatePaymentResponse(BaseModel):
    # 定义 initiate_payment 返回的数据结构
    message: str
    gateway: str
    billing_record_id: int
    amount: float
    # payment_url: Optional[str] = None
    # client_secret: Optional[str] = None

# --- 路由 --- 

# 路由: 获取账单列表 (GET /records/)
@router.get(
    "/records", 
    response_model=StandardResponse[BillingRecordListResponse],
    summary="获取当前用户账单列表 (分页)"
)
async def list_billing_records(
    request: Request,
    page: int = Query(1, description="页码 (从1开始)", ge=1),
    size: int = Query(10, description="每页数量 (1-100)", ge=1, le=100),
    status: Optional[str] = Query(None, description="按状态过滤 (例如: pending, paid)"),
    start_date: Optional[datetime.date] = Query(None, description="按起始日期过滤 (YYYY-MM-DD)"),
    end_date: Optional[datetime.date] = Query(None, description="按结束日期过滤 (YYYY-MM-DD)"),
    current_user: User = Depends(JWTBearer()),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """获取当前认证用户的账单列表，支持分页和按状态/日期过滤"""
    billing_service = BillingService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    # 将查询参数组装成字典传递给服务层
    search_params = {
        "status": status,
        "start_date": start_date,
        "end_date": end_date
    }
    # 移除 None 值，避免传递空参数
    search_params = {k: v for k, v in search_params.items() if v is not None}
    
    try:
        # 调用服务层搜索
        service_result = billing_service.search_billing_records(
            user_id=current_user.id,
            search_params=search_params,
            page=page,
            size=size
        )
        # 转换模型
        record_items = [BillingRecordResponse.model_validate(record) for record in service_result["items"]]
        response_data = BillingRecordListResponse(
            items=record_items,
            pagination=service_result["pagination"]
        )
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            message="获取账单列表成功",
            code=200,
            data=response_data
        )
    except GatewayException as e:
        logger.error(f"搜索账单路由出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"搜索账单路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="搜索账单记录时发生内部错误")

# 路由: 获取账单详情 (GET /records/{billing_id})
@router.get(
    "/records/{billing_id}", 
    response_model=StandardResponse[BillingRecordResponse],
    summary="获取指定账单详情"
)
async def get_billing_detail(
    request: Request,
    billing_id: int = Path(..., description="要获取详情的账单ID", ge=1),
    current_user: User = Depends(JWTBearer()),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """获取当前认证用户拥有的指定账单的详细信息"""
    billing_service = BillingService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        # 调用服务层获取详情
        record = billing_service.get_billing_details(
            user_id=current_user.id,
            billing_id=billing_id
        )
        # 转换模型
        response_data = BillingRecordResponse.model_validate(record)
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=True,
            message="获取账单详情成功",
            code=200,
            data=response_data
        )
    except NotFoundException as e:
        logger.warning(f"获取账单详情失败: {e} (Request ID: {req_id})")
        raise HTTPException(status_code=404, detail=str(e))
    except GatewayException as e:
        logger.error(f"获取账单详情路由出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"获取账单详情路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="获取账单详情时发生内部错误")

# 路由: 应用优惠券 (POST /coupons/apply)
@router.post(
    "/coupons/apply", 
    response_model=StandardResponse[ApplyCouponResponse],
    summary="应用优惠券"
)
async def apply_coupon(
    request: Request,
    request_body: ApplyCouponRequest, # 使用标准模型
    current_user: User = Depends(JWTBearer()),
    db: Session = Depends(get_db)
) -> StandardResponse:
    """用户尝试应用一个优惠券码 (具体应用逻辑在服务层)"""
    billing_service = BillingService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        # 调用服务层应用优惠券
        # 服务层目前返回字典，需适配 ApplyCouponResponse
        result_dict = billing_service.apply_coupon(
            user_id=current_user.id,
            coupon_code=request_body.coupon_code
        )
        # 将服务层返回的字典转换为 Pydantic 模型
        response_data = ApplyCouponResponse(**result_dict)
        logger.info(f"用户 {current_user.id} 应用优惠券 {request_body.coupon_code} 结果: {response_data.message} (Request ID: {req_id})")
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=response_data.success,
            message=response_data.message,
            code=200 if response_data.success else 400, # 成功200，失败400
            data=response_data
        )
    except NotFoundException as e: # 优惠券未找到
        logger.warning(f"应用优惠券失败 (NotFound): {e} (Request ID: {req_id})")
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidInputException as e: # 优惠券不适用
        logger.warning(f"应用优惠券失败 (InvalidInput): {e} (Request ID: {req_id})")
        raise HTTPException(status_code=400, detail=str(e))
    except GatewayException as e:
        logger.error(f"应用优惠券路由出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"应用优惠券路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="应用优惠券时发生内部错误")

# --- 保留支付相关路由 (待实现服务方法) ---

@router.post(
    "/records/{record_id}/pay", 
    response_model=StandardResponse[InitiatePaymentResponse], # 使用本地模型
    summary="为账单发起支付 (待实现)"
)
async def initiate_payment_endpoint(
    request: Request,
    record_id: int = Path(..., description="要支付的账单ID", ge=1),
    gateway_name: str = Query('stripe', description="支付网关名称 (例如: stripe, alipay)"), # 使用 Query
    current_user: User = Depends(JWTBearer()), 
    db: Session = Depends(get_db)
) -> StandardResponse:
    """用户请求为特定账单发起支付流程 (TODO: 实现服务层逻辑)"""
    billing_service = BillingService(db)
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        # TODO: 调用服务层 billing_service.initiate_payment(...)
        payment_info = {
            "message": "Initiate payment logic not implemented yet.",
            "gateway": gateway_name,
            "billing_record_id": record_id,
            "amount": 0.0 # 示例金额
        }
        response_data = InitiatePaymentResponse(**payment_info) 
        return StandardResponse(
            requestId=req_id,
            path=request.url.path,
            success=False, # 标记为未实现
            message="支付发起功能待实现",
            code=501, # Not Implemented
            data=response_data
            )
    except NotFoundException as e:
        logger.warning(f"发起支付失败: {e} (Request ID: {req_id})")
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidInputException as e:
        logger.warning(f"发起支付失败: {e} (Request ID: {req_id})")
        raise HTTPException(status_code=400, detail=str(e))
    except GatewayException as e:
        logger.error(f"发起支付路由出错: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception as e:
        logger.error(f"发起支付路由时未知错误: {e} (Request ID: {req_id})", exc_info=True)
        raise HTTPException(status_code=500, detail="发起支付时发生内部错误")

# Webhook 路由保持不变 (但标记为待实现)
@router.post(
    "/webhooks/payment/{gateway_name}",
    status_code=200,
    summary="接收支付网关回调 (Webhook - 待实现)",
    include_in_schema=False
)
async def handle_payment_webhook(
    gateway_name: str,
    request: Request,
    db: Session = Depends(get_db)
) -> Response:
    """处理来自指定支付网关的异步通知 (TODO: 实现服务层逻辑)"""
    billing_service = BillingService(db)
    payload_bytes = await request.body()
    payload_str = payload_bytes.decode('utf-8')
    headers = dict(request.headers)
    logger.info(f"收到来自 '{gateway_name}' 的 Webhook: {payload_str[:500]}... Headers: {headers}") # 记录部分内容
    
    try:
        # TODO: 调用服务层 billing_service.handle_payment_callback(...)
        logger.warning(f"Webhook handler for '{gateway_name}' not fully implemented.")
        # 模拟成功处理
        success = True 
        
        if success:
             return Response(status_code=200)
        else:
             logger.warning(f"Webhook from '{gateway_name}' handled but indicated failure")
             return Response(content="Webhook handled but failed internally", status_code=400)
             
    except ForbiddenException as e:
        logger.error(f"Webhook from '{gateway_name}' failed signature verification: {e}")
        return Response(content="Signature verification failed", status_code=403)
    except GatewayException as e:
        logger.error(f"Error handling webhook from '{gateway_name}': {e}", exc_info=True)
        return Response(content=f"Internal server error: {e.message}", status_code=e.code or 500)
    except Exception as e:
        logger.error(f"Unexpected error handling webhook from '{gateway_name}': {e}", exc_info=True)
        return Response(content="Unexpected internal server error", status_code=500) 