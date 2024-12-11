"""
路由模块
"""
from api_service.routers.analysis import router as analysis
from api_service.routers.stream_group import router as stream_group
from api_service.routers.stream import router as stream
from api_service.routers.model import router as model
from api_service.routers.callback import router as callback
from api_service.routers.task import router as task

__all__ = [
    "analysis",
    "stream_group",
    "stream", 
    "model",
    "callback",
    "task"
] 