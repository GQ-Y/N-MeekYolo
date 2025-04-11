"""
服务模块
包含所有服务组件，按功能模块拆分为子包
"""
# 导入子包
from . import mqtt
from . import http
from . import node
from . import task
from . import stream
from . import core

# 为了向后兼容性，直接从子包中导入常用类
from .mqtt import MQTTClient, get_mqtt_client, MQTTMessageProcessor, MQTTTaskManager
from .http import AnalysisService, AnalysisClient
from .node import NodeManager, NodeHealthChecker
from .task import TaskManager, TaskPriorityManager, TaskRetryQueue, TaskController
from .stream import StreamService, StreamPlayerService, StreamGroupService, StreamMonitor
from .core import (
    init_db, get_db, SessionLocal, Base, MessageQueue, ModelService, 
    ResultProcessor, SmartTaskScheduler
)

__all__ = [
    # 子包
    'mqtt', 'http', 'node', 'task', 'stream', 'core',
    
    # MQTT相关
    'MQTTClient', 'get_mqtt_client', 'MQTTMessageProcessor', 'MQTTTaskManager',
    
    # HTTP相关
    'AnalysisService', 'AnalysisClient',
    
    # 节点相关
    'NodeManager', 'NodeHealthChecker',
    
    # 任务相关
    'TaskManager', 'TaskPriorityManager', 'TaskRetryQueue', 'TaskController',
    
    # 流媒体相关
    'StreamService', 'StreamPlayerService', 'StreamGroupService', 'StreamMonitor',
    
    # 核心服务
    'init_db', 'get_db', 'SessionLocal', 'Base', 'MessageQueue', 'ModelService', 
    'ResultProcessor', 'SmartTaskScheduler'
]
