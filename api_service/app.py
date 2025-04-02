"""
API服务入口
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import logging
import asyncio
from datetime import datetime
from api_service.core.config import settings
from api_service.routers import (
    stream_router,
    stream_group_router,
    model_router,
    callback_router,
    task_router,
    analysis_router,
    node_router
)
from api_service.services.monitor import StreamMonitor
from api_service.services.node_health_check import start_health_checker, stop_health_checker
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
app.include_router(stream_router)
app.include_router(stream_group_router)
app.include_router(model_router)
app.include_router(callback_router)
app.include_router(task_router)
app.include_router(analysis_router)
app.include_router(node_router)

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
        
        # 启动节点健康检查服务
        logger.info("正在启动节点健康检查服务...")
        health_check_task = asyncio.create_task(start_health_checker())
        await asyncio.sleep(1)  # 等待服务启动
        if not health_check_task.done():
            logger.info("节点健康检查服务启动成功")
            
            # 启动后立即手动执行一次节点健康检查
            from api_service.services.node_health_check import health_checker
            logger.info("执行首次节点健康检查...")
            try:
                await health_checker.check_nodes_health()
                logger.info("首次节点健康检查完成")
            except Exception as e:
                logger.error(f"首次节点健康检查失败: {str(e)}")
        else:
            error = health_check_task.exception()
            if error:
                logger.error(f"节点健康检查服务启动失败: {str(error)}")
                raise error
            
    except Exception as e:
        logger.error(f"启动失败: {str(e)}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """关闭事件"""
    try:
        # 停止视频源监控
        await stream_monitor.stop()
        logger.info("视频源监控服务已停止")
        
        # 停止节点健康检查服务
        stop_health_checker()
        logger.info("节点健康检查服务已停止")
    except Exception as e:
        logger.error(f"服务停止失败: {str(e)}")

# 健康检查
@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "name": "api"
    }