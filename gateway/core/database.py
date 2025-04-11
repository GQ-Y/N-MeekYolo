"""
数据库连接管理
"""
import os
import logging # 导入 logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base # 确保 Base 被定义

from core.config import settings # 导入 settings

logger = logging.getLogger(__name__) # 获取 logger

from core.models.base import Base # 从 core.models.base 导入唯一的 Base


# --- 使用 settings 中的 DATABASE_URL --- 
if not settings.DATABASE_URL:
    logger.error("数据库连接 URL (DATABASE_URL) 未在配置中设置!")
    raise ValueError("DATABASE_URL must be set in the environment or .env file")

DATABASE_URL = settings.DATABASE_URL
logger.info(f"数据库连接 URL (来自 settings): {DATABASE_URL[:15]}...") # 已有日志

# --- 添加显式日志记录最终使用的 URL ---
logger.critical(f"即将用于创建引擎的最终 DATABASE_URL: {DATABASE_URL}")

# 建议在生产环境中使用连接池配置，例如 pool_size, max_overflow
engine = create_engine(
    DATABASE_URL,
    echo=settings.DEBUG, # 只在 Debug 模式下开启 SQL 日志
    # 添加连接池配置 (高并发起点，需要调优)
    pool_size=100,           # 基础连接数
    max_overflow=200,        # 允许超出的连接数
    pool_recycle=3600,       # 连接回收时间 (1小时)
    pool_timeout=30          # 获取连接的超时时间 (秒)
)


# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db() -> Session:
    """依赖项：获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 