"""
模型服务应用
"""
from fastapi import FastAPI
from model_service.core.config import settings
from model_service.routers import models, market, key
from model_service.services.database import init_db
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

# 创建应用
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="模型服务API文档"
)

# 初始化数据库
try:
    init_db()
    logger.info("Database initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize database: {str(e)}")
    raise

# 注册路由
app.include_router(
    models,
    prefix="/api/v1/models",
    tags=["模型管理"]
)
app.include_router(
    market,
    prefix="/api/v1/market",
    tags=["模型市场"]
)
app.include_router(
    key,
    prefix="/api/v1/keys",
    tags=["密钥管理"]
)

# 健康检查
@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "name": "model"
    }

@app.get("/")
async def root():
    """根路由"""
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "model_service.app:app",
        host=settings.SERVICE.host,
        port=settings.SERVICE.port,
        reload=True
    ) 