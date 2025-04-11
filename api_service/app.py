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
from services.stream.monitor import StreamMonitor
from services.node.node_health_check import start_health_checker, stop_health_checker
from shared.utils.logger import setup_logger
# 导入MQTT相关服务
from services.http.analysis_client import AnalysisClient
# 导入新的MQTT节点路由
from routers.mqtt_node import router as mqtt_node_router
# 导入新的视频流播放路由
from routers.stream_player import router as stream_player_router
from fastapi.staticfiles import StaticFiles
import os
# 导入Redis管理器
from core.redis_manager import RedisManager
# 导入任务状态管理器
from core.task_status_manager import TaskStatusManager
# 导入任务重试队列
from services.task.task_retry_queue import TaskRetryQueue
# 导入MQTT消息处理
from services.core.message_queue import MessageQueue
from services.mqtt.mqtt_message_processor import MQTTMessageProcessor
# 导入新的MQTT任务管理路由
from routers.mqtt_task import router as mqtt_task_router

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
app.include_router(analysis_callback_router) # 分析回调路由
app.include_router(mqtt_node_router) # MQTT节点路由
app.include_router(stream_player_router) # 视频流播放路由
app.include_router(mqtt_task_router) # MQTT任务管理路由

# 全局变量
stream_monitor = None

# Redis管理器
redis_manager = None
# 任务状态管理器
task_status_manager = None
# 任务重试队列
task_retry_queue = None
# MQTT消息处理器
mqtt_message_processor = None

# 启动处理
@app.on_event("startup")
async def startup_event():
    """应用启动时执行"""
    global stream_monitor, redis_manager, task_status_manager, task_retry_queue, mqtt_message_processor
    
    try:
        logger.info("API服务启动中...")
        
        # 初始化Redis管理器
        logger.info("初始化Redis管理器...")
        redis_manager = RedisManager.get_instance()
        
        # 初始化并测试Redis连接
        try:
            # 执行ping测试
            redis_alive = await redis_manager.ping()
            if redis_alive:
                logger.info("Redis连接测试成功")
            else:
                logger.warning("Redis连接测试失败，但不影响系统启动")
        except Exception as e:
            logger.error(f"Redis连接测试出错: {str(e)}")
        
        # 初始化任务状态管理器
        logger.info("初始化任务状态管理器...")
        task_status_manager = TaskStatusManager.get_instance()
        await task_status_manager.start()
        
        # 初始化任务重试队列
        logger.info("初始化任务重试队列...")
        task_retry_queue = TaskRetryQueue.get_instance()
        await task_retry_queue.start()
        
        # 初始化MQTT消息处理器
        logger.info("初始化MQTT消息处理器...")
        mqtt_message_processor = MQTTMessageProcessor.get_instance()
        mqtt_message_processor.initialize()

        # 获取通信模式
        communication_mode = settings.config.get('COMMUNICATION', {}).get('mode', 'http')
        logger.info(f"当前通信模式: {communication_mode}")

        # 获取MQTT配置
        mqtt_config = settings.config.get('MQTT', {})

        # 如果使用MQTT通信，初始化MQTT客户端
        if communication_mode.lower() == 'mqtt':
            # 初始化MQTT客户端
            from services.mqtt.mqtt_client import MQTTClient
            mqtt_client = MQTTClient(mqtt_config)
            
            # 连接到MQTT Broker
            logger.info(f"连接到MQTT Broker: {mqtt_config.get('broker_host')}:{mqtt_config.get('broker_port')}")
            try:
                connected = mqtt_client.connect()
                if connected:
                    logger.info("MQTT Broker连接成功")
                    # 设置MQTT客户端到应用状态
                    app.state.mqtt_client = mqtt_client
                    
                    # 初始化MQTT任务管理组件，共享同一个MQTT客户端实例
                    logger.info("初始化MQTT任务管理组件...")
                    
                    # 将共享的MQTT客户端设置为全局客户端
                    from services.mqtt.mqtt_client import get_mqtt_client
                    get_mqtt_client(mqtt_config, external_client=mqtt_client)
                    
                    from services.task.task_priority_manager import get_task_priority_manager
                    from services.core.smart_task_scheduler import get_smart_task_scheduler
                    from services.mqtt.mqtt_task_manager import get_mqtt_task_manager
                    
                    # 获取任务优先级管理器实例 - 会自动初始化
                    priority_manager = get_task_priority_manager()
                    
                    # 获取智能任务调度器实例 - 会自动初始化
                    scheduler = get_smart_task_scheduler()
                    
                    # 获取MQTT任务管理器实例 - 会自动初始化并启动
                    task_manager = get_mqtt_task_manager()
                    
                    # 同步节点信息
                    logger.info("同步MQTT节点信息...")
                    asyncio.create_task(scheduler.sync_nodes_from_db(force=True))
                else:
                    logger.error("MQTT Broker连接失败，将尝试使用HTTP模式")
                    communication_mode = 'http'  # 降级到HTTP模式
            except Exception as e:
                logger.error(f"MQTT Broker连接错误: {e}")
                communication_mode = 'http'  # 降级到HTTP模式
        
        # 创建分析服务客户端
        analysis_client = AnalysisClient({
            'COMMUNICATION': {'mode': communication_mode},
            'MQTT': mqtt_config
        }, mqtt_client=app.state.mqtt_client if hasattr(app.state, 'mqtt_client') else None)
        app.state.analysis_client = analysis_client
        
        # 设置通信模式到应用状态
        app.state.communication_mode = communication_mode
        
        # 启动视频源监控
        logger.info("启动视频源监控...")
        stream_monitor = StreamMonitor()
        asyncio.create_task(stream_monitor.start())
        
        # 如果使用MQTT通信，启动节点健康检查
        if communication_mode.lower() == 'mqtt':
            logger.info("启动MQTT节点健康检查...")
            await start_health_checker()
            
        logger.info("API服务启动完成")
        
    except Exception as e:
        logger.error(f"API服务启动出错: {e}")
        # 继续启动，不中断服务

# 关闭处理
@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时执行"""
    global stream_monitor, redis_manager, task_status_manager, task_retry_queue
    
    try:
        logger.info("API服务关闭中...")
        
        # 关闭视频源监控
        if stream_monitor:
            await stream_monitor.stop()
        
        # 关闭任务状态管理器
        if task_status_manager:
            await task_status_manager.stop()
            
        # 关闭任务重试队列
        if task_retry_queue:
            await task_retry_queue.stop()
        
        # 关闭Redis连接
        if redis_manager:
            await redis_manager.close()
        
        # 停止MQTT任务管理组件
        logger.info("停止MQTT任务管理组件...")
        try:
            from services.mqtt.mqtt_task_manager import get_mqtt_task_manager
            task_manager = get_mqtt_task_manager()
            if task_manager:
                await task_manager.stop()
                logger.info("MQTT任务管理器已停止")
        except Exception as e:
            logger.error(f"停止MQTT任务管理器出错: {e}")
        
        # 如果使用MQTT通信，关闭MQTT客户端和节点健康检查
        if hasattr(app.state, 'communication_mode') and app.state.communication_mode.lower() == 'mqtt':
            logger.info("关闭MQTT节点健康检查...")
            await stop_health_checker()
            
            if hasattr(app.state, 'mqtt_client'):
                logger.info("断开MQTT Broker连接...")
                app.state.mqtt_client.disconnect()
        
        # 关闭分析服务客户端
        if hasattr(app.state, 'analysis_client'):
            logger.info("关闭分析服务客户端...")
            await app.state.analysis_client.close()
        
        logger.info("API服务已完全关闭")
        
    except Exception as e:
        logger.error(f"API服务关闭出错: {e}")

# 为依赖注入提供分析服务客户端
@app.middleware("http")
async def add_analysis_client(request: Request, call_next):
    """将分析服务客户端添加到请求状态中"""
    request.state.analysis_client = app.state.analysis_client
    response = await call_next(request)
    return response

# 健康检查
@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "name": "api"
    }