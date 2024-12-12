"""
数据库初始化
"""
from analysis_service.services.database import engine
from analysis_service.models.database import Base
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

def init_database():
    """初始化数据库"""
    try:
        # 导入所有模型以确保它们被注册
        from analysis_service.models.database import Task  # noqa
        
        # 创建所有表
        Base.metadata.create_all(bind=engine)
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise 