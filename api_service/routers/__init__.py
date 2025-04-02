"""
路由模块
"""
from .stream import router as stream_router
from .stream_group import router as stream_group_router
from .model import router as model_router
from .callback import router as callback_router
from .task import router as task_router
from .analysis import router as analysis_router
from .node import router as node_router

__all__ = [
    'stream_router',
    'stream_group_router',
    'model_router',
    'callback_router',
    'task_router',
    'analysis_router',
    'node_router'
] 