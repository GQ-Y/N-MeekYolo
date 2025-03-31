"""
API服务入口
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from api_service.core.config import settings
from api_service.routers import (
    stream_router,
    stream_group_router,
    model_router,
    callback_router,
    task_router,
    analysis_router
)
from api_service.services.monitor import StreamMonitor
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

# 创建FastAPI应用
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    docs_url="/api/v1/docs",  # 明确指定swagger ui路径
    redoc_url="/api/v1/redoc",  # 明确指定redoc路径
    openapi_url="/api/v1/openapi.json"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由 - 使用统一的中文标签
app.include_router(stream_router, prefix="/api/v1", tags=["视频源"])
app.include_router(stream_group_router, prefix="/api/v1", tags=["视频源分组"])
app.include_router(model_router, prefix="/api/v1", tags=["模型"])
app.include_router(callback_router, prefix="/api/v1", tags=["回调服务"])
app.include_router(task_router, prefix="/api/v1", tags=["任务"])
app.include_router(analysis_router, prefix="/api/v1", tags=["分析"])

# 创建视频源监控器
stream_monitor = StreamMonitor()

@app.on_event("startup")
async def startup_event():
    """启动事件"""
    try:
        # 先初始化数据库
        logger.info("正在初始化数据库...")
        from api_service.services.database import init_db
        init_db()
        
        logger.info("正在启动API服务...")
        
        # 启动视频源监控服务(不等待初始化完成)
        await stream_monitor.start()
        logger.info("视频源监控服务启动成功")
        
    except Exception as e:
        logger.error(f"启动失败: {str(e)}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """关闭事件"""
    try:
        # 停止视频源监控
        await stream_monitor.stop()
        logger.info("Stream monitor stopped successfully")
    except Exception as e:
        logger.error(f"Failed to stop stream monitor: {str(e)}")

# 健康检查
@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "name": "api"
    }