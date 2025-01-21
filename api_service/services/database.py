"""
数据库服务
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from api_service.core.config import settings
from shared.utils.logger import setup_logger
import os

logger = setup_logger(__name__)

# 获取服务根目录
SERVICE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 数据库目录和文件
DB_DIR = os.path.join(SERVICE_ROOT, "data")
DB_FILE = "api_service.db"
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
        # 导入所有模型
        from api_service.models.database import Base, StreamGroup, Stream
        from api_service.models.requests import StreamStatus
        
        # 创建表
        Base.metadata.create_all(bind=engine)
        
        # 使用显式的事务管理
        db = SessionLocal()
        try:
            # 方案1: 使用ORM API
            affected = db.query(Stream).update(
                {Stream.status: StreamStatus.OFFLINE},
                synchronize_session=False
            )
            
            # 或者方案2: 使用text()包装SQL
            # result = db.execute(
            #     text("UPDATE streams SET status = :status"),
            #     {"status": StreamStatus.OFFLINE}
            # )
            # affected = result.rowcount
            
            # 创建默认分组
            default_group = db.query(StreamGroup).filter(
                StreamGroup.name == settings.DEFAULT_GROUP.name
            ).first()
            
            if not default_group:
                default_group = StreamGroup(
                    name=settings.DEFAULT_GROUP.name,
                    description=settings.DEFAULT_GROUP.description
                )
                db.add(default_group)
            
            # 提交事务
            db.commit()
            
            # 验证状态
            online_count = db.query(Stream).filter(
                Stream.status == StreamStatus.ONLINE
            ).count()
            
            if online_count > 0:
                logger.warning(f"发现 {online_count} 个视频源状态未被重置为离线")
                # 再次尝试重置
                db.query(Stream).update(
                    {Stream.status: StreamStatus.OFFLINE},
                    synchronize_session=False
                )
                db.commit()
            
            logger.info(f"数据库初始化完成, 重置了 {affected} 个视频源状态")
            
        except Exception as e:
            db.rollback()
            logger.error(f"数据库初始化失败: {str(e)}")
            raise
        finally:
            db.close()
            
        logger.info(f"数据库已初始化: {DB_PATH}")
        
    except Exception as e:
        logger.error(f"数据库初始化失败: {str(e)}")
        raise

def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        # 设置会话选项
        db.expire_on_commit = True  # 提交后过期缓存
        yield db
    finally:
        db.close()

# 移除自动初始化
# init_db()