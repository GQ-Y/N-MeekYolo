"""
分析服务入口
提供视觉分析和数据处理功能
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from core.config import settings
from routers.analyze import router as analyze_router
from core.exceptions import AnalysisException
from core.models import StandardResponse
from shared.utils.logger import setup_logger
import time
import uuid

logger = setup_logger(__name__)

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件"""
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        request_id = str(uuid.uuid4())
        
        # 添加请求ID到请求状态
        request.state.request_id = request_id
        
        # 记录请求信息
        logger.info(f"请求开始: {request_id} - {request.method} {request.url.path}")
        
        try:
            response = await call_next(request)
            
            # 记录响应信息
            process_time = (time.time() - start_time) * 1000
            logger.info(
                f"请求完成: {request_id} - {request.method} {request.url.path} "
                f"- 状态: {response.status_code} - 耗时: {process_time:.2f}ms"
            )
            
            # 添加请求ID到响应头
            response.headers["X-Request-ID"] = request_id
            return response
            
        except Exception as e:
            process_time = (time.time() - start_time) * 1000
            logger.error(
                f"请求失败: {request_id} - {request.method} {request.url.path} "
                f"- 错误: {str(e)} - 耗时: {process_time:.2f}ms"
            )
            raise

# 创建FastAPI应用
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="""
    分析服务模块
    
    提供以下功能:
    - 视觉对象检测和分析
    - 实例分割
    - 目标跟踪
    - 跨摄像头目标跟踪
    - 分析结果存储和查询
    """,
    version=settings.VERSION,
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json"
)

# 添加中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

# 添加Gzip压缩
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 添加请求日志中间件
app.add_middleware(RequestLoggingMiddleware)

# 注册路由
app.include_router(
    analyze_router,
    prefix="/api/v1/analyze"
)

# 全局异常处理
@app.exception_handler(AnalysisException)
async def analysis_exception_handler(request: Request, exc: AnalysisException):
    """处理分析服务异常"""
    return JSONResponse(
        status_code=exc.code,
        content=StandardResponse(
            requestId=getattr(request.state, "request_id", str(uuid.uuid4())),
            path=request.url.path,
            success=False,
            code=exc.code,
            message=exc.message,
            data=exc.data
        ).dict()
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """处理通用异常"""
    logger.error(f"未处理的异常: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content=StandardResponse(
            requestId=getattr(request.state, "request_id", str(uuid.uuid4())),
            path=request.url.path,
            success=False,
            code=500,
            message="服务器内部错误",
            data={"error": str(exc)} if settings.DEBUG else None
        ).dict()
    )

# 健康检查
@app.get("/health")
async def health_check():
    """健康检查接口"""
    return StandardResponse(
        requestId=str(uuid.uuid4()),
        path="/health",
        success=True,
        code=200,
        message="服务正常运行",
        data={
            "status": "healthy",
            "name": "analysis",
            "version": settings.VERSION
        }
    )

@app.on_event("startup")
async def startup_event():
    """启动事件"""
    logger.info("分析服务启动...")
    logger.info(f"环境: {settings.ENVIRONMENT}")
    logger.info(f"调试模式: {settings.DEBUG}")
    logger.info(f"版本: {settings.VERSION}")
    logger.info(f"注册的路由: {[route.path for route in app.routes]}")
    
@app.on_event("shutdown")
async def shutdown_event():
    """关闭事件"""
    logger.info("分析服务关闭...")