"""
数据库服务
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from model_service.models.database import Base
from model_service.core.config import settings
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

def ensure_db_directory():
    """确保数据库目录存在"""
    db_path = settings.DATABASE.url.replace('sqlite:///', '')
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
        logger.info(f"Created database directory: {db_dir}")

# 确保数据库目录存在
ensure_db_directory()

# 创建数据库引擎
engine = create_engine(
    settings.DATABASE.url,
    connect_args={"check_same_thread": False}
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """初始化数据库"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        raise

def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 