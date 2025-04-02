"""
为Task表添加缺少的字段
"""
from sqlalchemy import create_engine, text
from api_service.core.config import settings
from shared.utils.logger import setup_logger
import pymysql

logger = setup_logger(__name__)

def add_task_fields():
    """添加Task表中缺少的字段(enable_callback, save_result, config, node_id)"""
    try:
        logger.info("开始执行Task表迁移...")
        
        # 连接MySQL数据库
        connection = pymysql.connect(
            host=settings.DATABASE.host,
            user=settings.DATABASE.username,
            password=settings.DATABASE.password,
            database=settings.DATABASE.database
        )
        cursor = connection.cursor()
        
        # 检查enable_callback字段是否存在
        cursor.execute("SHOW COLUMNS FROM tasks LIKE 'enable_callback'")
        enable_callback_exists = cursor.fetchone()
        
        # 检查save_result字段是否存在
        cursor.execute("SHOW COLUMNS FROM tasks LIKE 'save_result'")
        save_result_exists = cursor.fetchone()
        
        # 检查config字段是否存在
        cursor.execute("SHOW COLUMNS FROM tasks LIKE 'config'")
        config_exists = cursor.fetchone()
        
        # 检查node_id字段是否存在
        cursor.execute("SHOW COLUMNS FROM tasks LIKE 'node_id'")
        node_id_exists = cursor.fetchone()
        
        # 添加缺少的字段
        if not enable_callback_exists:
            logger.info("添加enable_callback字段...")
            cursor.execute("ALTER TABLE tasks ADD COLUMN enable_callback BOOLEAN DEFAULT TRUE")
            logger.info("enable_callback字段添加成功")
        else:
            logger.info("enable_callback字段已存在")
            
        if not save_result_exists:
            logger.info("添加save_result字段...")
            cursor.execute("ALTER TABLE tasks ADD COLUMN save_result BOOLEAN DEFAULT FALSE")
            logger.info("save_result字段添加成功")
        else:
            logger.info("save_result字段已存在")
            
        if not config_exists:
            logger.info("添加config字段...")
            cursor.execute("ALTER TABLE tasks ADD COLUMN config JSON NULL")
            logger.info("config字段添加成功")
        else:
            logger.info("config字段已存在")
            
        if not node_id_exists:
            logger.info("添加node_id字段...")
            cursor.execute("ALTER TABLE tasks ADD COLUMN node_id INT NULL")
            cursor.execute("ALTER TABLE tasks ADD CONSTRAINT fk_tasks_node FOREIGN KEY (node_id) REFERENCES nodes(id) ON DELETE SET NULL")
            logger.info("node_id字段添加成功")
        else:
            logger.info("node_id字段已存在")
        
        # 提交更改
        connection.commit()
        logger.info("Task表迁移完成")
        
        # 关闭连接
        cursor.close()
        connection.close()
        
    except Exception as e:
        logger.error(f"Task表迁移失败: {str(e)}")
        raise
        
if __name__ == "__main__":
    add_task_fields() 