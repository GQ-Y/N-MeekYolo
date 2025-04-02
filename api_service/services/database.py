"""
数据库服务
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from api_service.core.config import settings
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

# 创建数据库引擎
engine = create_engine(
    settings.DATABASE.url,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
    pool_pre_ping=True
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 声明基类
Base = declarative_base()

def init_db():
    """初始化数据库"""
    try:
        # 导入所有模型
        from api_service.models.database import Base as DBBase
        from api_service.models.database import StreamGroup, Stream
        from api_service.models.requests import StreamStatus
        from api_service.models.node import Node  # 导入节点模型
        
        # 创建所有表
        DBBase.metadata.create_all(bind=engine)
        Node.__table__.create(bind=engine, checkfirst=True)
        
        # 使用显式的事务管理
        db = SessionLocal()
        try:
            # 重置所有视频源状态
            affected = db.query(Stream).update(
                {Stream.status: StreamStatus.OFFLINE},
                synchronize_session=False
            )
            
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
            
            # 重置所有节点状态为离线
            try:
                nodes_affected = db.query(Node).update(
                    {Node.service_status: "offline"},
                    synchronize_session=False
                )
                if nodes_affected > 0:
                    logger.info(f"重置了 {nodes_affected} 个节点状态为离线")
            except Exception as e:
                logger.warning(f"重置节点状态失败: {str(e)}")
            
            # 提交事务
            db.commit()
            
            # 验证视频源状态
            online_count = db.query(Stream).filter(
                Stream.status == StreamStatus.ONLINE
            ).count()
            
            logger.info(f"数据库初始化完成，在线视频源：{online_count}")
            
        except Exception as e:
            db.rollback()
            logger.error(f"数据库初始化失败: {str(e)}")
            raise
        finally:
            db.close()
    except Exception as e:
        logger.error(f"数据库初始化过程出错: {str(e)}")
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