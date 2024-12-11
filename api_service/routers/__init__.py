"""
路由模块
"""
from api_service.routers.stream import router as stream_router
from api_service.routers.stream_group import router as stream_group_router
from api_service.routers.model import router as model_router
from api_service.routers.callback import router as callback_router
from api_service.routers.task import router as task_router
from api_service.routers.analysis import router as analysis_router

__all__ = [
    'stream_router',
    'stream_group_router',
    'model_router',
    'callback_router',
    'task_router',
    'analysis_router'
] 