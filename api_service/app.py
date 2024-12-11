"""
API服务入口
"""
from fastapi import FastAPI
from api_service.core.config import settings
from api_service.services.database import init_db
from api_service.routers import (
    stream_group,
    stream,
    model,
    callback,
    task,
    analysis
)

# 创建FastAPI应用
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="MeekYolo API服务",
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc"
)

# 初始化数据库
init_db()

# 注册路由
app.include_router(stream_group, prefix="/api/v1")
app.include_router(stream, prefix="/api/v1")
app.include_router(model, prefix="/api/v1")
app.include_router(callback, prefix="/api/v1")
app.include_router(task, prefix="/api/v1")
app.include_router(analysis, prefix="/api/v1")

@app.get("/")
async def root():
    """根路由"""
    return {"message": "Welcome to MeekYolo API Service"} 