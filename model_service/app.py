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
from core.config import settings
from routers.models import router as models_router
from routers.market import router as market_router
from routers.key import router as key_router
from services.database import init_db
from manager.model_manager import ModelManager
import psutil
import uuid
from datetime import datetime
import GPUtil

# 配置日志
logging.basicConfig(
    level=settings.LOGGING.level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
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
    title="MeekYolo 模型服务",
    description="""
    MeekYolo 模型服务 API 文档
    
    提供以下功能：
    * 模型管理：上传、下载、删除、查询模型
    * 模型市场：同步云市场模型
    * 密钥管理：创建、查询、删除密钥
    """,
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json"
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
app.include_router(
    models_router, 
    prefix="/api/v1/models", 
    tags=["模型管理"],
    responses={404: {"description": "未找到模型"}}
)
app.include_router(
    market_router, 
    prefix="/api/v1/market",  # 这里只需要基本前缀，子路径由路由器自己定义
    tags=["模型市场"],
    responses={404: {"description": "未找到模型"}}
)
app.include_router(
    key_router, 
    prefix="/api/v1/keys", 
    tags=["密钥管理"],
    responses={404: {"description": "未找到密钥"}}
)

@app.get("/health")
@limiter.limit("5/minute")
async def health_check(request: Request):
    """健康检查"""
    # 获取CPU使用率
    cpu_percent = psutil.cpu_percent(interval=1)
    
    # 获取内存使用情况
    memory = psutil.virtual_memory()
    memory_percent = memory.percent
    
    # 获取GPU使用情况
    try:
        gpus = GPUtil.getGPUs()
        gpu_usage = f"{gpus[0].load * 100:.1f}%" if gpus else "N/A"
    except:
        gpu_usage = "N/A"
    
    return {
        "requestId": str(uuid.uuid4()),
        "path": "/health",
        "success": True,
        "message": "服务正常运行",
        "code": 200,
        "data": {
            "status": "healthy",
            "name": "model",
            "version": settings.VERSION,
            "cpu": f"{cpu_percent:.1f}%",
            "gpu": gpu_usage,
            "memory": f"{memory_percent:.1f}%"
        },
        "timestamp": int(datetime.now().timestamp() * 1000)
    }

def show_service_banner(service_name: str):
    """显示服务启动标识"""
    banner = f"""
███╗   ███╗███████╗███████╗██╗  ██╗██╗   ██╗ ██████╗ ██╗      ██████╗     @{service_name}
████╗ ████║██╔════╝██╔════╝██║ ██╔╝╚██╗ ██╔╝██╔═══██╗██║     ██╔═══██╗
██╔████╔██║█████╗  █████╗  █████╔╝  ╚████╔╝ ██║   ██║██║     ██║   ██║
██║╚██╔╝██║██╔══╝  ██╔══╝  ██╔═██╗   ╚██╔╝  ██║   ██║██║     ██║   ██║
██║ ╚═╝ ██║███████╗███████╗██║  ██╗   ██║   ╚██████╔╝███████╗╚██████╔╝
╚═╝     ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝   ╚═╝    ╚═════╝ ╚══════╝ ╚═════╝ 
    """
    print(banner)

@app.on_event("startup")
async def startup_event():
    """应用启动时的初始化"""
    show_service_banner("model_service")
    logger.info("Starting Model Service...")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.SERVICE.host, port=settings.SERVICE.port)