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
        # 导入所有模型
        from api_service.models.database import Base, StreamGroup
        from api_service.core.config import settings
        
        # 创建表
        Base.metadata.create_all(bind=engine)
        
        # 创建默认分组
        with SessionLocal() as db:
            # 检查默认分组是否存在
            default_group = db.query(StreamGroup).filter(
                StreamGroup.name == settings.DEFAULT_GROUP["name"]
            ).first()
            
            if not default_group:
                # 创建默认分组
                default_group = StreamGroup(
                    name=settings.DEFAULT_GROUP["name"],
                    description=settings.DEFAULT_GROUP["description"]
                )
                db.add(default_group)
                try:
                    db.commit()
                    logger.info(f"Created default stream group: {default_group.name}")
                except Exception as e:
                    db.rollback()
                    logger.error(f"Failed to create default group: {str(e)}")
            else:
                logger.info("Default stream group already exists")
        
        # 记录数据库位置
        api_service_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.join(api_service_dir, settings.DATABASE_DIR, settings.DATABASE_NAME)
        logger.info(f"Database initialized at: {db_path}")
        
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