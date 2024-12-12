"""
分析服务入口
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from analysis_service.core.config import settings
from analysis_service.routers.analyze import router as analyze_router
from shared.utils.logger import setup_logger
from analysis_service.services.init_db import init_database

logger = setup_logger(__name__)

# 初始化数据库
init_database()

# 创建FastAPI应用
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="分析服务模块",
    version=settings.VERSION
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
app.include_router(analyze_router)

# 健康检查
@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "name": "analysis"  
    }

@app.on_event("startup")
async def startup_event():
    """启动事件"""
    logger.info("分析服务启动...")
    logger.info(f"注册的路由: {app.routes}")