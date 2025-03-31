"""
模型服务应用程序
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from model_service.core.config import settings
from model_service.routers.models import router as models_router
from model_service.routers.market import router as market_router
from model_service.routers.key import router as key_router
from model_service.services.database import init_db
from model_service.manager.model_manager import ModelManager

# 配置日志
logging.basicConfig(level=settings.LOGGING.level)
logger = logging.getLogger(__name__)

# 创建限速器
limiter = Limiter(key_func=get_remote_address, default_limits=["5/minute"])

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用程序生命周期事件处理器
    """
    # 启动事件
    logger.debug("Starting model service application...")
    init_db()
    model_manager = ModelManager()
    
    yield
    
    # 关闭事件
    logger.info("Application shutdown")

# 创建应用程序
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

# 添加中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)

# 添加限速中间件
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 注册路由
app.include_router(models_router, prefix="/api/v1/models", tags=["models"])
app.include_router(market_router, prefix="/api/v1/market", tags=["market"])
app.include_router(key_router, prefix="/api/v1/keys", tags=["keys"])

@app.get("/health")
@limiter.limit("5/minute")
async def health_check(request: Request):
    """健康检查"""
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.SERVICE.host, port=settings.SERVICE.port)