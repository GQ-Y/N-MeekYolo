"""
路由模块
"""
from model_service.routers.models import router as models
from model_service.routers.market import router as market
from model_service.routers.key import router as key

__all__ = ["models", "market", "key"] 