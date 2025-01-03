"""
模型服务应用
"""
import sys
import logging

# 设置基本日志
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                   stream=sys.stdout)

logger = logging.getLogger(__name__)
logger.debug("Starting model service application...")

try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    logger.debug("FastAPI imported")
    
    from model_service.core.config import settings
    logger.debug("Config loaded")
    
    from model_service.routers import models, market, key
    logger.debug("Routers imported")
    
    from model_service.services.database import init_db
    logger.debug("Database module imported")
    
except Exception as e:
    logger.exception("Failed to import required modules")
    sys.exit(1)

# 创建应用
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="模型服务API文档"
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "model_service.app:app",
        host=settings.SERVICE.host,
        port=settings.SERVICE.port,
        reload=True
    ) 