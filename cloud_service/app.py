"""
应用主程序
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from cloud_service.core.config import settings
from cloud_service.services.database import init_db
from cloud_service.routers import model, key
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

# 创建应用
app = FastAPI(
    title=settings.APP.title,
    version=settings.APP.version,
    description=settings.APP.description,
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs"
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(model.router, prefix="/api/v1")
app.include_router(key.router, prefix="/api/v1")

# 健康检查
@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "name": "cloud"
    }

# 启动事件
@app.on_event("startup")
async def startup_event():
    """启动事件"""
    try:
        # 初始化数据库
        init_db()
        logger.info("Application startup complete")
    except Exception as e:
        logger.error(f"Application startup failed: {str(e)}")
        raise

# 关闭事件
@app.on_event("shutdown")
async def shutdown_event():
    """关闭事件"""
    logger.info("Application shutdown") 