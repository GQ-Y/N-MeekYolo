"""
应用主程序
"""
import sys
import logging

# 设置基本日志
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                   stream=sys.stdout)

logger = logging.getLogger(__name__)
logger.debug("Starting application...")

try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from cloud_service.core.config import settings
    from cloud_service.services.database import init_db
    from cloud_service.routers import model, key
    from cloud_service.utils.logger import setup_logger
except Exception as e:
    logger.exception("Failed to import required modules")
    sys.exit(1)

logger = setup_logger(__name__)

# 创建应用
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="云服务"
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