"""
数据库初始化
"""
from sqlalchemy import event, inspect, Index
from analysis_service.services.database import engine
from analysis_service.models.database import Base, Task, TaskQueue
from shared.utils.logger import setup_logger
import os

logger = setup_logger(__name__)

def init_database():
    """初始化数据库"""
    try:
        # 检查数据库是否存在
        db_file = "analysis_service.db"
        db_exists = os.path.exists(db_file)
        
        if db_exists:
            logger.info("Database file already exists, checking tables and indexes...")
        else:
            logger.info("Creating new database...")
        
        # 创建缺失的表
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables checked/created")
        
        # 创建缺失的索引
        _create_indexes()
        
        # 注册数据库事件
        _register_events()
        
        logger.info("Database initialization completed")
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

def _create_indexes():
    """创建数据库索引"""
    try:
        inspector = inspect(engine)
        
        def create_index_if_not_exists(index_name, table_name, column_name):
            if index_name not in [idx['name'] for idx in inspector.get_indexes(table_name)]:
                Index(index_name, column_name).create(engine)
                logger.info(f"Created index {index_name}")
        
        # 创建Task表索引
        create_index_if_not_exists('idx_task_status', 'tasks', Task.status)
        create_index_if_not_exists('idx_task_start_time', 'tasks', Task.start_time)
        
        # 创建TaskQueue表索引
        create_index_if_not_exists('idx_queue_task_id', 'task_queue', TaskQueue.task_id)
        create_index_if_not_exists('idx_queue_status', 'task_queue', TaskQueue.status)
        create_index_if_not_exists('idx_queue_priority', 'task_queue', TaskQueue.priority)
        
        logger.info("Database indexes created successfully")
        
    except Exception as e:
        logger.error(f"Create indexes failed: {e}")
        raise

def _register_events():
    """注册数据库事件"""
    
    @event.listens_for(TaskQueue, 'after_insert')
    def task_queue_after_insert(mapper, connection, target):
        """任务入队后的处理"""
        logger.info(f"New task queued: {target.id}")
    
    @event.listens_for(TaskQueue, 'after_update')
    def task_queue_after_update(mapper, connection, target):
        """任务状态更新后的处理"""
        logger.info(f"Task status updated: {target.id} -> {target.status}")
        
    @event.listens_for(Task, 'after_update')
    def task_after_update(mapper, connection, target):
        """任务更新后的处理"""
        logger.info(f"Task updated: {target.id}, status: {target.status}")

def cleanup_old_data():
    """清理过期数据"""
    try:
        from datetime import datetime, timedelta
        from sqlalchemy import delete
        
        # 清理30天前的已完成任务
        threshold = datetime.now() - timedelta(days=30)
        
        with engine.connect() as conn:
            # 清理Task表
            conn.execute(
                delete(Task).where(
                    Task.status.in_([2, -1]),  # 已完成或失败的任务
                    Task.stop_time < threshold
                )
            )
            
            # 清理TaskQueue表
            conn.execute(
                delete(TaskQueue).where(
                    TaskQueue.status.in_([2, -1]),
                    TaskQueue.completed_at < threshold
                )
            )
            
            conn.commit()
            
        logger.info("Old data cleaned up successfully")
        
    except Exception as e:
        logger.error(f"Data cleanup failed: {e}")
        raise