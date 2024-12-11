"""
API网关入口
处理服务发现和请求路由
"""
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles
from shared.utils.logger import setup_logger
from gateway.discovery.service_registry import service_registry
from gateway.router.api_router import router

# 配置日志
logger = setup_logger(__name__)

# 创建FastAPI应用
app = FastAPI(
    title="MeekYolo Gateway",
    description="API网关服务",
    version="1.0.0",
    docs_url=None,  # 禁用默认的swagger路由
    redoc_url=None  # 禁用默认的redoc路由
)

# 挂载静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(router)

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    """自定义Swagger UI路由"""
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="/static/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger-ui.css",
    )

@app.on_event("startup")
async def startup_event():
    """应用启动时的初始化"""
    logger.info("Starting API Gateway...")
    
    # 启动服务健康检查
    asyncio.create_task(service_registry.start_health_check())

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时的清理"""
    logger.info("Shutting down API Gateway...")

@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "healthy"} 