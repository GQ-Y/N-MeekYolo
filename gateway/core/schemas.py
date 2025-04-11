"""
Pydantic Schema 定义 (用于 API 请求/响应校验)
"""
from typing import Any, Dict, Optional, Union, List, TypeVar, Generic
from pydantic import BaseModel, Field, validator, constr, EmailStr, computed_field
from enum import Enum
import time
import uuid
from datetime import datetime
import json

# --- 定义类型变量 ---
T = TypeVar('T')

# --- 枚举 ---
class HttpMethod(str, Enum):
    """HTTP方法枚举"""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"

# --- 通用分页模型 ---
class PaginationData(BaseModel):
    """分页信息模型"""
    total: int = Field(..., description="总记录数")
    page: int = Field(..., description="当前页码 (从1开始)")
    size: int = Field(..., description="每页大小")
    total_pages: int = Field(..., description="总页数")

# --- 通用响应 (改造为泛型) ---
class StandardResponse(BaseModel, Generic[T]):
    """标准API响应模型 (泛型)"""
    requestId: str = Field(default_factory=lambda: str(uuid.uuid4()), description="请求ID")
    path: str = Field("", description="请求路径")
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="响应消息")
    code: int = Field(..., description="响应代码")
    # 使用类型变量 T 作为 data 的类型
    data: Optional[T] = Field(None, description="响应数据")
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000), description="时间戳")

    class Config:
        json_schema_extra = {
            "example": {
                "requestId": "550e8400-e29b-41d4-a716-446655440000",
                "path": "/api/v1/route",
                "success": True,
                "message": "Success",
                "code": 200,
                "data": None,
                "timestamp": 1616633599000
            }
        }

# --- 认证相关 ---
class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")
    # token: str = Field(..., description="口令") # 移除 token

class RegisterRequest(BaseModel):
    """注册请求"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")
    # token: str = Field(..., description="口令") # 移除 token
    email: Optional[str] = Field(None, description="邮箱 (可选)") # 添加 email
    nickname: Optional[str] = Field(None, description="昵称 (可选)") # 添加 nickname

class TokenResponse(BaseModel):
    """令牌响应 (用于登录接口)"""
    # 这个模型可能不再直接需要，因为 authenticate_user 返回的是包含多信息的字典
    # 但可以保留用于定义文档或特定场景
    access_token: str = Field(..., description="访问令牌")
    token_type: str = Field("bearer", description="令牌类型")
    expires_in: int = Field(..., description="过期时间(秒)")
    user_info: Optional[dict] = Field(None, description="用户信息") # 添加可选的用户信息

# 添加密码重置请求模型
class PasswordResetRequest(BaseModel):
    """密码重置请求模型"""
    email: EmailStr = Field(..., description="用户注册时使用的邮箱地址")

# 添加密码重置确认模型
class PasswordResetConfirm(BaseModel):
    """密码重置确认模型"""
    token: str = Field(..., description="通过邮件收到的密码重置令牌")
    new_password: str = Field(..., min_length=8, description="用户设置的新密码 (最小长度8)") # 添加最小长度约束

# --- 用户相关 ---
class UserProfileUpdate(BaseModel):
    """用户个人资料更新请求 (用于 /api/v1/user/profile)"""
    nickname: Optional[str] = Field(None, description="用户昵称")
    phone: Optional[str] = Field(None, description="电话号码")
    # 可以根据需要添加其他允许用户更新的字段, 如 avatar_url

class PasswordUpdate(BaseModel):
    """密码更新请求"""
    old_password: str
    new_password: str

# 添加 UserResponse 模型
class UserResponse(BaseModel):
    """用户信息的标准响应模型 (不含敏感信息)"""
    id: int = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")
    email: Optional[EmailStr] = Field(None, description="用户邮箱")
    nickname: Optional[str] = Field(None, description="用户昵称")
    phone: Optional[str] = Field(None, description="电话号码")
    role_id: Optional[int] = Field(None, description="角色ID") # TODO: 替换为 RoleResponse 模型?
    status: int = Field(..., description="用户状态 (0: 正常, 1: 禁用, ...)")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="最后更新时间")

    class Config:
        from_attributes = True # Pydantic v2 (替代 orm_mode=True)
        json_schema_extra = {
            "example": {
                "id": 1,
                "username": "johndoe",
                "email": "johndoe@example.com",
                "nickname": "Johnny",
                "phone": "1234567890",
                "role_id": 2,
                "status": 0,
                "created_at": "2023-10-27T10:00:00Z",
                "updated_at": "2023-10-28T11:30:00Z"
            }
        }

# 添加 UserStatusUpdate 模型 (用于管理员更新用户状态)
class UserStatusUpdate(BaseModel):
    """管理员更新用户状态的请求模型"""
    status: int = Field(..., description="新的用户状态 (例如 0: 正常, 1: 禁用)")
    # 可以添加校验器确保 status 值在允许范围内
    # @validator('status')
    # def validate_status(cls, v):
    #     if v not in [0, 1]: # 假设只有 0 和 1 是有效状态
    #         raise ValueError('无效的用户状态值')
    #     return v

# 添加 UserListResponse 模型 (用于管理员列表)
class UserListResponse(BaseModel):
    """用户列表响应模型 (包含分页信息)"""
    items: List[UserResponse] = Field(..., description="当前页的用户列表")
    pagination: PaginationData = Field(..., description="分页信息")

# --- 路由转发 ---
class RouteRequest(BaseModel):
    """路由请求模型"""
    service: constr(min_length=1, max_length=50) = Field(
        ...,
        description="目标服务名称",
        example="api"
    )
    path: constr(min_length=1, max_length=500) = Field(
        ...,
        description="目标路径",
        example="users/profile"
    )
    method: HttpMethod = Field(
        HttpMethod.POST,
        description="HTTP请求方法"
    )
    headers: Dict[str, str] = Field(
        default_factory=dict,
        description="请求头",
        example={"Content-Type": "application/json"}
    )
    query_params: Dict[str, Any] = Field(
        default_factory=dict,
        description="查询参数",
        example={
            "name": "测试",
            "url": "rtsp://example.com/stream",
            "description": "测试",
            "group_ids": [1, 2, 3]
        }
    )
    body: Any = Field(
        None,
        description="请求体"
    )

    @validator('path')
    def validate_path(cls, v):
        if '..' in v:
            raise ValueError('Path traversal is not allowed')
        if not v.strip('/'):
            raise ValueError('Path cannot be empty')
        # 移除路径开头的斜杠，便于拼接
        return v.lstrip('/')

    @validator('headers')
    def validate_headers(cls, v):
        # 移除敏感头部
        sensitive_headers = {'host', 'connection', 'proxy'}
        return {k: v for k, v in v.items() if k.lower() not in sensitive_headers}

    class Config:
        json_schema_extra = {
            "example": {
                "service": "api",
                "path": "stream/create",
                "method": "POST",
                "headers": {
                    "Content-Type": "application/json",
                    "Authorization": "Bearer token"
                },
                "query_params": {
                    "name": "测试",
                    "url": "rtsp://example.com/stream",
                    "description": "测试",
                    "group_ids": [1, 2, 3]
                },
                "body": None
            }
        }

# --- 订阅相关 ---
class SubscriptionPlanResponse(BaseModel):
    """订阅计划的响应模型"""
    id: int = Field(..., description="计划ID")
    name: str = Field(..., description="计划名称")
    description: Optional[str] = Field(None, description="计划描述")
    price: float = Field(..., description="价格")
    duration_days: Optional[int] = Field(None, description="有效时长（天），None表示永久或按其他方式计算")
    features: Optional[Dict[str, Any]] = Field(None, description="计划包含的特性 (键值对)")

    @validator('features', pre=True, always=True)
    def parse_features_json(cls, v):
        """如果 features 是字符串，尝试解析为 JSON 字典"""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                # 如果解析失败，可以选择返回 None 或原始字符串，或抛出 ValueError
                # 返回 None 可能更安全，因为模型定义了 Optional[Dict]
                return None
        # 如果不是字符串 (例如已经是字典或 None)，直接返回
        return v

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "name": "Pro Plan",
                "description": "Professional tier subscription",
                "price": 29.99,
                "duration_days": 30,
                "features": {"storage": "100GB", "support": "priority"}
            }
        }

class SubscriptionCreateRequest(BaseModel):
    """创建订阅的请求模型"""
    plan_id: int = Field(..., description="要订阅的计划ID")

class SubscriptionResponse(BaseModel):
    """用户订阅信息的响应模型"""
    id: int = Field(..., description="订阅记录ID")
    tenant_id: int = Field(..., description="用户 (租户) ID")
    plan: SubscriptionPlanResponse = Field(..., description="订阅的计划详情") # 嵌套计划详情
    start_date: datetime = Field(..., description="订阅开始日期")
    end_date: Optional[datetime] = Field(None, description="订阅结束日期 (如果适用)")
    status: int = Field(..., description="订阅状态 (0: active, 1: inactive, ...)")
    auto_renew: bool = Field(..., description="是否自动续订")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    
    @computed_field
    @property
    def is_active(self) -> bool:
        """根据 status 计算订阅是否活动"""
        return self.status == 0 # 假设 0 表示活动

    class Config:
        from_attributes = True # Pydantic v2
        json_schema_extra = {
            "example": {
                "id": 1,
                "tenant_id": 1,
                "plan": {
                    "id": 2,
                    "name": "Pro Monthly",
                    "description": "Professional tier, billed monthly",
                    "price": 29.99,
                    "duration_days": None,
                    "features": {"storage": "50GB"}
                },
                "start_date": "2023-10-01T00:00:00Z",
                "end_date": "2023-11-01T00:00:00Z",
                "status": 0,
                "auto_renew": True,
                "created_at": "2023-10-01T00:00:00Z",
                "updated_at": "2023-10-01T00:00:00Z",
                "is_active": True
            }
        }

# --- 节点管理 ---
class NodeBase(BaseModel):
    """节点信息基础模型"""
    name: str = Field(..., description="节点名称", min_length=1, max_length=100)
    # config_details 可以根据具体业务定义更详细的结构
    config_details: Optional[Dict[str, Any]] = Field({}, description="节点的具体配置信息 (例如 IP, 端口, 认证等)")
    description: Optional[str] = Field(None, description="节点描述")

class NodeCreate(NodeBase):
    """创建新节点的请求模型"""
    # 创建时不需要传 user_id，会从认证信息中获取
    pass

class NodeUpdate(BaseModel):
    """更新节点信息的请求模型 (所有字段可选)"""
    name: Optional[str] = Field(None, description="新的节点名称", min_length=1, max_length=100)
    config_details: Optional[Dict[str, Any]] = Field(None, description="新的节点配置信息")
    description: Optional[str] = Field(None, description="新的节点描述")
    # 不允许更新状态或用户ID等字段

class NodeResponse(NodeBase):
    """节点信息的标准响应模型"""
    id: int = Field(..., description="节点ID")
    tenant_id: int = Field(..., description="所属租户 (用户) ID")
    status: int = Field(..., description="节点状态 (例如 0: 在线, 1: 离线, 2: 维护中)")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后更新时间")
    # 可以添加最后心跳时间等字段
    # last_heartbeat: Optional[datetime] = Field(None, description="最后心跳时间")

    class Config:
        from_attributes = True # Pydantic v2
        json_schema_extra = {
            "example": {
                "id": 1,
                "tenant_id": 1,
                "name": "Example Node",
                "config_details": {"ip": "192.168.0.10", "port": 8080},
                "description": "An example node configuration",
                "status": 0,
                "created_at": "2023-10-27T12:00:00Z",
                "updated_at": "2023-10-28T14:00:00Z"
            }
        }

class NodeListResponse(BaseModel):
    """节点列表响应模型 (包含分页信息)"""
    items: List[NodeResponse] = Field(..., description="当前页的节点列表")
    pagination: PaginationData = Field(..., description="分页信息")

# --- 任务管理 ---
class TaskBase(BaseModel):
    """任务信息基础模型"""
    name: Optional[str] = Field(None, description="任务名称", max_length=100)
    task_type: str = Field(..., description="任务类型 (例如: data_processing, monitoring)")
    params: Optional[Dict[str, Any]] = Field({}, description="任务执行所需的参数")

class TaskCreate(TaskBase):
    """创建新任务的请求模型"""
    node_id: int = Field(..., description="任务将执行的节点ID")
    # user_id 将从认证信息中获取

class TaskUpdate(BaseModel):
    """更新任务信息的请求模型 (可选字段)"""
    name: Optional[str] = Field(None, description="新的任务名称", max_length=100)
    status: Optional[int] = Field(None, description="新的任务状态 (0: pending, 1: running, ...)")
    result: Optional[Dict[str, Any]] = Field(None, description="任务执行结果")
    # 通常不允许更新 node_id, task_type, params, user_id

class TaskResponse(TaskBase):
    """任务信息的标准响应模型"""
    id: int = Field(..., description="任务ID")
    tenant_id: int = Field(..., description="所属租户 (用户) ID")
    node_id: int = Field(..., description="执行节点ID")
    status: int = Field(..., description="任务当前状态 (0: pending, 1: running, ...)")
    result: Optional[Dict[str, Any]] = Field(None, description="任务执行结果")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后更新时间")
    # 可以添加 started_at, completed_at 等时间戳
    # started_at: Optional[datetime] = None
    # completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True # Pydantic v2
        json_schema_extra = {
            "example": {
                "id": 101,
                "tenant_id": 1,
                "node_id": 5,
                "name": "Daily Backup Task",
                "task_type": "backup",
                "params": {"source": "/data", "destination": "/backup"},
                "status": 2,
                "result": {"files_processed": 1024, "size": "10GB"},
                "created_at": "2023-10-28T08:00:00Z",
                "updated_at": "2023-10-28T08:30:00Z"
            }
        }

class TaskListResponse(BaseModel):
    """任务列表响应模型 (包含分页信息)"""
    items: List[TaskResponse] = Field(..., description="当前页的任务列表")
    pagination: PaginationData = Field(..., description="分页信息")

# --- 账单与支付 ---
class BillingSearchRequest(BaseModel):
    """搜索账单记录的请求模型"""
    status: Optional[str] = Field(None, description="账单状态 (例如: pending, paid, failed, canceled)")
    start_date: Optional[datetime] = Field(None, description="查询起始日期")
    end_date: Optional[datetime] = Field(None, description="查询结束日期")
    # 可以添加其他过滤字段，如 subscription_id, order_id 等

class BillingRecordResponse(BaseModel):
    """账单记录的响应模型"""
    id: int = Field(..., description="账单记录ID")
    user_id: int = Field(..., description="用户ID")
    amount: float = Field(..., description="账单金额")
    status: str = Field(..., description="账单状态")
    description: Optional[str] = Field(None, description="账单描述")
    related_type: Optional[str] = Field(None, description="关联类型 (例如: subscription, one-time)")
    related_id: Optional[int] = Field(None, description="关联的订阅或订单ID")
    payment_method: Optional[str] = Field(None, description="支付方式")
    transaction_id: Optional[str] = Field(None, description="支付网关交易ID")
    created_at: datetime = Field(..., description="创建时间")
    paid_at: Optional[datetime] = Field(None, description="支付时间")

    class Config:
        from_attributes = True # Pydantic v2

class BillingRecordListResponse(BaseModel):
    """账单记录列表响应模型 (包含分页信息)"""
    items: List[BillingRecordResponse] = Field(..., description="当前页的账单记录列表")
    pagination: PaginationData = Field(..., description="分页信息")

class ApplyCouponRequest(BaseModel):
    """应用优惠券的请求模型"""
    coupon_code: str = Field(..., description="要应用的优惠券代码")

class ApplyCouponResponse(BaseModel):
    """应用优惠券结果的响应模型"""
    success: bool = Field(..., description="是否成功应用")
    message: str = Field(..., description="结果消息")
    coupon_code: str = Field(..., description="应用的优惠券代码")
    discount_type: Optional[str] = Field(None, description="折扣类型 (fixed, percentage)")
    discount_value: Optional[float] = Field(None, description="折扣值 (金额或百分比)")
    calculated_discount: Optional[float] = Field(None, description="计算出的实际折扣金额")

    class Config:
        json_schema_extra = {
            "example_success": {
                "success": True,
                "message": "优惠券应用成功",
                "coupon_code": "WELCOME10",
                "discount_type": "fixed",
                "discount_value": 10.0,
                "calculated_discount": 10.0
            },
            "example_fail": {
                "success": False,
                "message": "无效或已过期的优惠券代码",
                "coupon_code": "EXPIRED20",
                "discount_type": None,
                "discount_value": None,
                "calculated_discount": None
            }
        }

# --- 通知管理 ---
class NotificationResponse(BaseModel):
    """通知信息的标准响应模型"""
    id: int = Field(..., description="通知ID")
    user_id: int = Field(..., description="接收用户ID")
    title: str = Field(..., description="通知标题")
    message: str = Field(..., description="通知内容")
    level: str = Field('info', description="通知级别 (例如: info, warning, error, success)")
    is_read: bool = Field(False, description="是否已读")
    created_at: datetime = Field(..., description="创建时间")
    # 可以添加 link 字段用于点击跳转
    # link: Optional[str] = Field(None, description="相关链接")

    class Config:
        from_attributes = True # Pydantic v2
        json_schema_extra = {
            "example": {
                "id": 10,
                "user_id": 1,
                "title": "订阅即将到期",
                "message": "您的 PRO 订阅计划将于 2024-12-31 到期，请及时续费。",
                "level": "warning",
                "is_read": False,
                "created_at": "2024-12-20T10:00:00Z"
            }
        }

class NotificationListResponse(BaseModel):
    """通知列表响应模型 (包含分页信息)"""
    items: List[NotificationResponse] = Field(..., description="当前页的通知列表")
    pagination: PaginationData = Field(..., description="分页信息")

# (可选) 用于批量标记已读的请求模型
# class MarkNotificationsReadRequest(BaseModel):
#     notification_ids: List[int] = Field(..., description="要标记为已读的通知ID列表")

# --- 系统日志模型 ---
class SystemLogResponse(BaseModel):
    """系统日志记录的响应模型"""
    id: int # 使用 int 即可，BigInteger 主要用于数据库
    timestamp: datetime = Field(..., description="日志时间戳")
    level: str = Field(..., description="日志级别名称 (e.g., INFO, WARNING, ERROR)")
    message: str = Field(..., description="日志消息")
    source: Optional[str] = Field(None, description="日志来源 (e.g., 模块名)")
    user_id: Optional[int] = Field(None, description="关联的用户ID (如果适用)")
    details: Optional[Dict[str, Any]] = Field(None, description="附加的结构化日志详情 (JSON)")

    class Config:
        from_attributes = True

class SystemLogListResponse(BaseModel):
    """系统日志列表响应模型 (包含分页信息)"""
    items: List[SystemLogResponse]
    pagination: PaginationData

# --- 节点管理 ---
class NodeCreateRequest(BaseModel):
    # ... existing code ...
    pass

# --- 节点管理 ---
class NodeCreateRequest(BaseModel):
    # ... existing code ...
    pass 