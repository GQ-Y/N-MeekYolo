"""
API服务主程序
"""
from fastapi import FastAPI
from api_service.routers import (
    stream_group,
    stream,
    model,
    callback,
    task,
    analysis
)
from api_service.services.database import init_db
from shared.utils.logger import setup_logger
import sys

logger = setup_logger(__name__)

# 创建FastAPI应用
app = FastAPI(
    title="MeekYolo API Service",
    description="MeekYolo API服务",
    version="1.0.0",
    docs_url="/docs",  # 启用Swagger文档
    redoc_url="/redoc"  # 启用ReDoc文档
)

# 初始化数据库
try:
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize database: {str(e)}")
    sys.exit(1)

# 注册路由
try:
    logger.info("Registering routers...")
    # 注册所有路由
    app.include_router(stream_group.router, prefix="/api/v1", tags=["视频源分组"])
    app.include_router(stream.router, prefix="/api/v1", tags=["视频源"])
    app.include_router(model.router, prefix="/api/v1", tags=["模型"])
    app.include_router(callback.router, prefix="/api/v1", tags=["回调服务"])
    app.include_router(task.router, prefix="/api/v1", tags=["任务"])
    app.include_router(analysis.router, prefix="/api/v1", tags=["分析"])
    logger.info("Routers registered successfully")
except Exception as e:
    logger.error(f"Failed to register routers: {str(e)}")
    sys.exit(1)

@app.get("/")
async def root():
    """根路由"""
    return {"message": "Welcome to MeekYolo API Service"}

@app.on_event("startup")
async def startup_event():
    """启动事件"""
    logger.info("API Service is starting up...")

@app.on_event("shutdown")
async def shutdown_event():
    """关闭事件"""
    logger.info("API Service is shutting down...") 