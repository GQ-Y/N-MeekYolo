"""
应用主程序
"""
import sys
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from cloud_service.core.config import settings
from cloud_service.services.database import init_db
from cloud_service.routers import model, key
from cloud_service.utils.logger import setup_logger

# 配置日志
logging.basicConfig(level=settings.LOGGING.level)
logger = setup_logger(__name__)

# 创建限速器
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.SECURITY.rate_limit])

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用程序生命周期事件处理器
    """
    # 启动事件
    try:
        logger.debug("Starting cloud service application...")
        init_db()
        logger.info("Application startup complete")
    except Exception as e:
        logger.error(f"Application startup failed: {str(e)}")
        raise
    
    yield
    
    # 关闭事件
    logger.info("Application shutdown")

# 创建应用程序
app = FastAPI(
    title="MeekYolo 云服务",
    description="""
    MeekYolo 云服务 API 文档
    
    提供以下功能：
    * 模型管理：上传、下载、查询模型
    * 密钥管理：创建、查询、更新、删除密钥
    * 模型同步：提供模型同步接口
    """,
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json",
    debug=settings.SERVICE.debug
)

# 添加中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS.allow_origins,
    allow_credentials=settings.CORS.allow_credentials,
    allow_methods=settings.CORS.allow_methods,
    allow_headers=settings.CORS.allow_headers,
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.SECURITY.allowed_hosts)

# 添加限速中间件
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 注册路由
app.include_router(
    model.router, 
    prefix="/api/v1",
    responses={404: {"description": "未找到模型"}}
)
app.include_router(
    key.router, 
    prefix="/api/v1",
    responses={404: {"description": "未找到密钥"}}
)

@app.get("/health")
@limiter.limit(settings.SECURITY.rate_limit)
async def health_check(request: Request):
    """健康检查"""
    return {
        "status": "healthy",
        "name": "cloud"
    } 