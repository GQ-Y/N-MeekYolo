"""
为节点表添加缺少的字段
"""
from sqlalchemy import create_engine, text
from api_service.core.config import settings
from shared.utils.logger import setup_logger
import pymysql

logger = setup_logger(__name__)

def add_node_fields():
    """添加节点表中缺少的字段(weight和max_tasks)"""
    try:
        logger.info("开始执行节点表迁移...")
        
        # 连接MySQL数据库
        connection = pymysql.connect(
            host=settings.DATABASE.host,
            user=settings.DATABASE.username,
            password=settings.DATABASE.password,
            database=settings.DATABASE.database
        )
        cursor = connection.cursor()
        
        # 检查weight字段是否存在
        cursor.execute("SHOW COLUMNS FROM nodes LIKE 'weight'")
        weight_exists = cursor.fetchone()
        
        # 检查max_tasks字段是否存在
        cursor.execute("SHOW COLUMNS FROM nodes LIKE 'max_tasks'")
        max_tasks_exists = cursor.fetchone()
        
        # 添加缺少的字段
        if not weight_exists:
            logger.info("添加weight字段...")
            cursor.execute("ALTER TABLE nodes ADD COLUMN weight INT DEFAULT 1")
            logger.info("weight字段添加成功")
        else:
            logger.info("weight字段已存在")
            
        if not max_tasks_exists:
            logger.info("添加max_tasks字段...")
            cursor.execute("ALTER TABLE nodes ADD COLUMN max_tasks INT DEFAULT 10")
            logger.info("max_tasks字段添加成功")
        else:
            logger.info("max_tasks字段已存在")
        
        # 提交更改
        connection.commit()
        logger.info("节点表迁移完成")
        
        # 关闭连接
        cursor.close()
        connection.close()
        
    except Exception as e:
        logger.error(f"节点表迁移失败: {str(e)}")
        raise
        
if __name__ == "__main__":
    add_node_fields() 