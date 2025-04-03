"""
路由模块
"""
from routers.models import router as models
from routers.market import router as market
from routers.key import router as key

__all__ = ["models", "market", "key"] 