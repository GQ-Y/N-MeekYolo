"""
API服务入口
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import logging
import asyncio
import yaml
from datetime import datetime
from core.config import settings
from routers import (
    stream_router,
    stream_group_router,
    model_router,
    callback_router,
    task_router,
    analysis_router,
    node_router
)
# 导入新的分析回调路由
from routers.analysis_callback import router as analysis_callback_router
from services.monitor import StreamMonitor
from services.node_health_check import start_health_checker, stop_health_checker
from shared.utils.logger import setup_logger
# 导入MQTT相关服务
from services.analysis_client import AnalysisClient
# 导入新的MQTT节点路由
from routers.mqtt_node import router as mqtt_node_router
# 导入新的视频流播放路由
from routers.stream_player import router as stream_player_router
from fastapi.staticfiles import StaticFiles
import os

logger = setup_logger(__name__)

# 创建FastAPI应用
app = FastAPI(
    title=settings.config.get('PROJECT', {}).get('name', 'MeekYOLO'),
    version=settings.config.get('PROJECT', {}).get('version', '0.3.0'),
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

# 挂载静态文件目录
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# 注册路由 - 使用统一的中文标签
app.include_router(stream_router)
app.include_router(stream_group_router)
app.include_router(model_router)
app.include_router(callback_router)
app.include_router(task_router)
app.include_router(analysis_router)
app.include_router(node_router)
# 注册分析回调路由
app.include_router(analysis_callback_router)
# 注册MQTT节点路由
app.include_router(mqtt_node_router)
# 注册视频流播放路由
app.include_router(stream_player_router)

# 创建视频源监控器
stream_monitor = StreamMonitor()

# 声明全局分析服务客户端
analysis_client = None

def load_config():
    """加载配置文件"""
    try:
        with open("config/config.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        return {}

def show_service_banner(service_name: str):
    """显示服务启动标识"""
    config = load_config()
    project_name = config.get('PROJECT', {}).get('name', 'MeekYOLO')
    project_version = config.get('PROJECT', {}).get('version', '0.3.0')
    
    banner = f"""
███╗   ███╗███████╗███████╗██╗  ██╗██╗   ██╗ ██████╗ ██╗      ██████╗     @{service_name}
████╗ ████║██╔════╝██╔════╝██║ ██╔╝╚██╗ ██╔╝██╔═══██╗██║     ██╔═══██╗
██╔████╔██║█████╗  █████╗  █████╔╝  ╚████╔╝ ██║   ██║██║     ██║   ██║
██║╚██╔╝██║██╔══╝  ██╔══╝  ██╔═██╗   ╚██╔╝  ██║   ██║██║     ██║   ██║
██║ ╚═╝ ██║███████╗███████╗██║  ██╗   ██║   ╚██████╔╝███████╗╚██████╔╝
╚═╝     ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝   ╚═╝    ╚═════╝ ╚══════╝ ╚═════╝ 
{project_name} v{project_version}
启动时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    """
    print(banner)

@app.on_event("startup")
async def startup_event():
    """应用启动时的事件处理"""
    logger.info("API服务启动...")
    
    # 读取配置
    comm_mode = settings.config.get('COMMUNICATION', {}).get('mode', 'http')
    logger.info(f"通信模式: {comm_mode}")
    
    # 初始化分析客户端
    app.state.analysis_client = AnalysisClient(config=settings.config)
    
    # 检查MQTT连接状态
    if comm_mode == 'mqtt':
        if not hasattr(app.state, 'analysis_client') or not app.state.analysis_client or not app.state.analysis_client.mqtt_connected:
            logger.error("MQTT客户端连接失败! 请检查以下MQTT配置:")
            logger.error(f"  - 服务器: {settings.config.get('MQTT', {}).get('broker_host')}:{settings.config.get('MQTT', {}).get('broker_port')}")
            logger.error(f"  - 客户端ID: {settings.config.get('MQTT', {}).get('client_id')}")
            logger.error(f"  - 用户名: {settings.config.get('MQTT', {}).get('username')}")
            logger.error(f"  - 密码: {'已设置' if settings.config.get('MQTT', {}).get('password') else '未设置'}")
            logger.error(f"  - 主题前缀: {settings.config.get('MQTT', {}).get('topic_prefix')}")
            logger.warning("API服务将以受限模式运行，直到MQTT连接恢复")
            
            # 尝试再次连接
            try:
                if app.state.analysis_client and app.state.analysis_client.mqtt_client:
                    logger.info("尝试重新连接MQTT...")
                    app.state.analysis_client.mqtt_client.connect()
                    if app.state.analysis_client.mqtt_connected:
                        logger.info("MQTT重新连接成功!")
                    else:
                        logger.warning("MQTT重新连接失败，将在后台继续尝试")
            except Exception as e:
                logger.error(f"MQTT重新连接异常: {e}")
        else:
            logger.info("MQTT客户端连接成功!")
    
    # 初始化健康检查服务
    try:
        from services.node_health_check import start_health_checker
        app.state.health_checker = await start_health_checker()
        logger.info("节点健康检查服务启动成功")
        
        # 执行首次健康检查
        if comm_mode == 'mqtt':
            logger.info("执行首次MQTT节点健康检查")
            await app.state.health_checker.check_mqtt_nodes_health()
        else:
            logger.info("执行首次HTTP节点健康检查")
            await app.state.health_checker.check_nodes_health()
    except Exception as e:
        logger.error(f"健康检查服务启动失败: {e}")
        # 不中断启动过程，继续运行服务
    
    logger.info("API服务启动完成")

@app.on_event("shutdown")
async def shutdown_event():
    """关闭事件"""
    global analysis_client
    
    try:
        # 关闭分析服务客户端
        if analysis_client:
            await analysis_client.close()
            logger.info("分析服务客户端已关闭")
        
        # 停止视频源监控
        await stream_monitor.stop()
        logger.info("视频源监控服务已停止")
        
        # 停止节点健康检查服务
        stop_health_checker()
        logger.info("节点健康检查服务已停止")
        
        # 停止所有视频流转换进程
        from services.stream_player import stream_player_service
        await stream_player_service.stop_all_conversions()
        logger.info("所有视频流转换进程已停止")
    except Exception as e:
        logger.error(f"服务停止失败: {str(e)}")

# 健康检查
@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "name": "api",
        "communication_mode": app.state.analysis_client.mode if hasattr(app.state, "analysis_client") else "unknown"
    }

# 为依赖注入提供分析服务客户端
@app.middleware("http")
async def add_analysis_client(request: Request, call_next):
    """将分析服务客户端添加到请求状态中"""
    request.state.analysis_client = app.state.analysis_client
    response = await call_next(request)
    return response