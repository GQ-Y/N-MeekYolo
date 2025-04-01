"""
API网关入口
处理服务发现和请求路由
"""
import asyncio
from typing import List, Dict, Any
from fastapi import FastAPI, APIRouter, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, Field
from shared.utils.logger import setup_logger
from gateway.discovery.service_registry import service_registry
from gateway.router.api_router import router
from gateway.routers.admin import router as admin_router
from gateway.routers.auth import router as auth_router
from gateway.core.models import StandardResponse
from gateway.core.exceptions import GatewayException
import time
import uuid
from .routers import auth, system, user

# 配置日志
logger = setup_logger(__name__)

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件"""
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        request_id = str(uuid.uuid4())
        
        # 添加请求ID到请求头
        request.state.request_id = request_id
        
        # 记录请求信息
        logger.info(f"Request started: {request_id} - {request.method} {request.url.path}")
        
        try:
            response = await call_next(request)
            
            # 记录响应信息
            process_time = (time.time() - start_time) * 1000
            logger.info(
                f"Request completed: {request_id} - {request.method} {request.url.path} "
                f"- Status: {response.status_code} - Time: {process_time:.2f}ms"
            )
            
            # 添加请求ID到响应头
            response.headers["X-Request-ID"] = request_id
            return response
            
        except Exception as e:
            process_time = (time.time() - start_time) * 1000
            logger.error(
                f"Request failed: {request_id} - {request.method} {request.url.path} "
                f"- Error: {str(e)} - Time: {process_time:.2f}ms"
            )
            raise

# 定义基础响应模型
class HTTPError(BaseModel):
    detail: str

class ValidationError(BaseModel):
    loc: List[str]
    msg: str
    type: str

class HTTPValidationError(BaseModel):
    detail: List[ValidationError]

# 创建FastAPI应用
app = FastAPI(
    title="MeekYolo Gateway",
    description="""
    API网关服务
    
    提供以下功能:
    - API路由和转发
    - 服务发现和注册
    - 服务健康监控
    - 服务状态管理
    - 用户认证和授权
    """,
    version="1.0.0",
    docs_url=None,
    redoc_url=None
)

# 添加中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 添加Gzip压缩
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 添加请求日志中间件
app.add_middleware(RequestLoggingMiddleware)

# 注册路由
app.include_router(auth_router)  # 添加认证路由
app.include_router(admin_router)
app.include_router(router)
app.include_router(auth.router)
app.include_router(system.router)
app.include_router(user.router)  # 添加用户路由

# 挂载静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")

# 全局异常处理
@app.exception_handler(GatewayException)
async def gateway_exception_handler(request: Request, exc: GatewayException):
    """处理网关异常"""
    return JSONResponse(
        status_code=exc.code,
        content=StandardResponse(
            requestId=getattr(request.state, "request_id", str(uuid.uuid4())),
            path=request.url.path,
            success=False,
            code=exc.code,
            message=exc.message,
            data=exc.data
        ).dict()
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """处理通用异常"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content=StandardResponse(
            requestId=getattr(request.state, "request_id", str(uuid.uuid4())),
            path=request.url.path,
            success=False,
            code=500,
            message="Internal server error",
            data={"error": str(exc)} if app.debug else None
        ).dict()
    )

# 自定义OpenAPI文档
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
        
    openapi_schema = get_openapi(
        title="MeekYolo API Gateway",
        version="1.0.0",
        description=app.description,
        routes=app.routes,
    )
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# 自定义Swagger UI
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - API Documentation",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="/static/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger-ui.css",
    )

@app.on_event("startup")
async def startup_event():
    """应用启动时的初始化"""
    logger.info("Starting API Gateway...")
    
    # 启动服务健康检查
    asyncio.create_task(service_registry.start_health_check())

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时的清理"""
    logger.info("Shutting down API Gateway...")

@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "healthy"}

@app.get("/")
async def root():
    return {"message": "Welcome to MeekYolo Gateway"} 