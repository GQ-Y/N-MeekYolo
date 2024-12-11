"""
数据库服务
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from api_service.core.config import settings
from shared.utils.logger import setup_logger
import os
from sqlalchemy import inspect

logger = setup_logger(__name__)

# 确保数据库目录存在
os.makedirs(settings.DATABASE_DIR, exist_ok=True)

# 创建数据库引擎
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False}  # SQLite 需要这个参数
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 声明基类
Base = declarative_base()

def init_db():
    """初始化数据库"""
    try:
        # 导入所有模型以确保它们被注册
        from api_service.models.database import Base
        from api_service.models.database import (
            Stream,
            StreamGroup,
            Model,
            Callback,
            Task,
            stream_group_association,
            task_stream_association,
            task_model_association,
            task_callback_association
        )
        
        # 检查表是否存在
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        logger.info(f"Existing tables before creation: {existing_tables}")
        
        # 在开发环境下强制重建表
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        
        # 验证表创建
        inspector = inspect(engine)
        created_tables = inspector.get_table_names()
        logger.info(f"Created tables after initialization: {created_tables}")
        
        # 记录数据库位置
        api_service_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.join(api_service_dir, settings.DATABASE_DIR, settings.DATABASE_NAME)
        logger.info(f"Database initialized at: {db_path}")
        
        if not created_tables:
            raise Exception("No tables were created during initialization")
        
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}", exc_info=True)
        raise

def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 在模块导入时初始化数据库
init_db() 