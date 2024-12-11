"""
API网关入口
处理服务发现和请求路由
"""
import asyncio
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.utils import get_openapi
from shared.utils.logger import setup_logger
from gateway.discovery.service_registry import service_registry
from gateway.router.api_router import router
from gateway.routers.admin import router as admin_router

# 配置日志
logger = setup_logger(__name__)

# 创建FastAPI应用
app = FastAPI(
    title="MeekYolo Gateway",
    description="""
    API网关服务
    
    提供以下功能:
    - API路由和转发
    - 服务发现和注册
    - 服务健康监控
    - 服务状态管理
    """,
    version="1.0.0",
    docs_url=None,
    redoc_url=None
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

# 注册路由 - 调整顺序,先注册admin路由
app.include_router(admin_router)
app.include_router(router)

# 自定义OpenAPI文档
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
        
    openapi_schema = get_openapi(
        title="MeekYolo API Gateway",
        version="1.0.0",
        description=app.description,
        routes=app.routes,
        tags=[
            {
                "name": "管理接口",
                "description": "提供服务注册、发现和监控功能"
            },
            {
                "name": "API路由",
                "description": "处理API请求的路由和转发"
            }
        ]
    )
    
    # 添加服务说明
    openapi_schema["info"]["x-services"] = {
        "api": {
            "name": "API服务",
            "description": "提供核心业务API",
            "url": "http://localhost:8001"
        },
        "model": {
            "name": "模型服务",
            "description": "提供AI模型管理",
            "url": "http://localhost:8002"
        },
        "analysis": {
            "name": "分析服务", 
            "description": "提供视频分析能力",
            "url": "http://localhost:8003"
        },
        "cloud": {
            "name": "云服务",
            "description": "提供云服务",
            "url": "http://localhost:8004"
        }
    }
    
    # 添加安全配置
    openapi_schema["components"] = {
        "securitySchemes": {
            "APIKeyHeader": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key"
            }
        }
    }
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# 自定义Swagger UI
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - API文档",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="/static/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger-ui.css",
        swagger_favicon_url="/static/favicon.png",
        init_oauth={
            "clientId": "your-client-id",
            "clientSecret": "your-client-secret"
        }
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