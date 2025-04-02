"""
综合的数据库初始化脚本，用于创建所有表结构和基础数据
"""
from sqlalchemy import create_engine, text
from api_service.core.config import settings
from api_service.models.database import Base, Stream, StreamGroup, Model, Callback, Task, Node, SubTask
from api_service.services.database import init_db, get_db
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

def init_database():
    """初始化所有数据库表结构和基础数据"""
    try:
        logger.info("开始初始化数据库...")
        
        # 创建数据库引擎
        engine = create_engine(settings.DATABASE.url)
        
        # 创建所有表结构
        logger.info("正在创建数据库表...")
        Base.metadata.create_all(engine)
        
        # 初始化数据库基础数据
        logger.info("正在初始化数据库基础数据...")
        init_db()
        
        # 设置所有视频源状态为离线
        logger.info("正在设置视频源状态...")
        with engine.connect() as conn:
            # 检查是否有需要设置的数据
            result = conn.execute(text("SELECT COUNT(*) FROM streams")).scalar()
            if result == 0:
                logger.info("没有找到需要设置状态的视频源")
            else:
                conn.execute(text("UPDATE streams SET status = 0"))
                conn.commit()
                logger.info(f"已将 {result} 个视频源状态设置为离线")
            
        # 确认表结构完整性
        logger.info("数据库初始化完成，检查表结构:")
        tables = [
            "streams", "stream_groups", "models", "callbacks", "tasks", "nodes", "sub_tasks", 
            "group_stream_association", "task_stream_association", "task_model_association", 
            "task_callback_association", "stream_group_association"
        ]
        
        with engine.connect() as conn:
            for table in tables:
                try:
                    conn.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))
                    logger.info(f" - 表 {table} 已创建 ✓")
                except Exception as e:
                    logger.warning(f" - 表 {table} 创建失败或为空: {str(e)} ✗")
        
        logger.info("数据库初始化完成!")
        
    except Exception as e:
        logger.error(f"数据库初始化失败: {str(e)}")
        raise

if __name__ == "__main__":
    init_database() 