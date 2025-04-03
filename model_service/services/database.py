"""
数据库服务
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from core.config import settings
from shared.utils.logger import setup_logger
import os

logger = setup_logger(__name__)

# 获取服务根目录
SERVICE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 数据库目录和文件
DB_DIR = os.path.join(SERVICE_ROOT, "data")
DB_FILE = "model_service.db"
DB_PATH = os.path.join(DB_DIR, DB_FILE)

# 确保数据库目录存在
os.makedirs(DB_DIR, exist_ok=True)

# 创建数据库引擎
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False}
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 声明基类
Base = declarative_base()

def init_db():
    """初始化数据库"""
    try:
        from models.database import Base
        Base.metadata.create_all(bind=engine)
        logger.info(f"Database initialized at: {DB_PATH}")
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