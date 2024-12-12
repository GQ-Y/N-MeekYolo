"""
数据库服务
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from analysis_service.models.base import Base
import os
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

# 数据库文件路径
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "analysis_service.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

logger.info(f"Initializing database at: {DB_PATH}")

# 创建数据库引擎
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)

# 创建数据库会话
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db() -> Session:
    """获取数据库会话"""
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()

# 用于依赖注入的生成器函数
async def get_db_dependency():
    """获取数据库会话（用于依赖注入）"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 