"""
网关服务数据模型定义
"""
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, validator, constr
from enum import Enum
import time
import uuid

class HttpMethod(str, Enum):
    """HTTP方法枚举"""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"

class StandardResponse(BaseModel):
    """标准API响应模型"""
    requestId: str = Field(default_factory=lambda: str(uuid.uuid4()))
    path: str = ""
    success: bool = True
    message: str = "Success"
    code: int = 200
    data: Any = None
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))

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
    query_params: Dict[str, str] = Field(
        default_factory=dict,
        description="查询参数",
        example={"page": "1", "size": "10"}
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
        return v.strip('/')

    @validator('headers')
    def validate_headers(cls, v):
        # 移除敏感头部
        sensitive_headers = {'host', 'connection', 'proxy'}
        return {k: v for k, v in v.items() if k.lower() not in sensitive_headers}

    class Config:
        json_schema_extra = {
            "example": {
                "service": "api",
                "path": "users/profile",
                "method": "POST",
                "headers": {
                    "Content-Type": "application/json",
                    "Authorization": "Bearer token"
                },
                "query_params": {
                    "page": "1",
                    "size": "10"
                },
                "body": {
                    "user_id": 123
                }
            }
        } 