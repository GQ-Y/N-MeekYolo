"""
分析服务入口
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from analysis_service.core.config import settings
from analysis_service.routers import analyze_router

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
app.include_router(analyze_router, prefix="/analyze", tags=["analyze"])

# 健康检查
@app.get("/health")
async def health_check():
    return {"status": "healthy"} 