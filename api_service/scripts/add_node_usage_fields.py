"""
为Node表添加资源使用率相关字段
"""
import sys
import os
from datetime import datetime

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api_service.core.config import settings
from api_service.shared.utils.logger import setup_logger
import pymysql

logger = setup_logger(__name__)

def add_node_usage_fields():
    """添加Node表中资源使用率相关字段(cpu_usage, gpu_usage)"""
    try:
        start_time = datetime.now()
        logger.info(f"开始执行Node表迁移... 时间: {start_time}")
        
        # 连接MySQL数据库
        connection = pymysql.connect(
            host=settings.DATABASE.host,
            user=settings.DATABASE.username,
            password=settings.DATABASE.password,
            database=settings.DATABASE.database
        )
        logger.info(f"成功连接到数据库: {settings.DATABASE.database}@{settings.DATABASE.host}")
        
        cursor = connection.cursor()
        
        # 检查cpu_usage字段是否存在
        cursor.execute("SHOW COLUMNS FROM nodes LIKE 'cpu_usage'")
        cpu_usage_exists = cursor.fetchone()
        
        # 检查gpu_usage字段是否存在
        cursor.execute("SHOW COLUMNS FROM nodes LIKE 'gpu_usage'")
        gpu_usage_exists = cursor.fetchone()
        
        # 检查memory_usage字段是否存在
        cursor.execute("SHOW COLUMNS FROM nodes LIKE 'memory_usage'")
        memory_usage_exists = cursor.fetchone()
        
        # 检查gpu_memory_usage字段是否存在
        cursor.execute("SHOW COLUMNS FROM nodes LIKE 'gpu_memory_usage'")
        gpu_memory_usage_exists = cursor.fetchone()
        
        logger.info(f"现有字段检查结果: cpu_usage={bool(cpu_usage_exists)}, gpu_usage={bool(gpu_usage_exists)}, "
                   f"memory_usage={bool(memory_usage_exists)}, gpu_memory_usage={bool(gpu_memory_usage_exists)}")
        
        # 添加缺少的字段
        if not cpu_usage_exists:
            logger.info("添加cpu_usage字段...")
            cursor.execute("ALTER TABLE nodes ADD COLUMN cpu_usage FLOAT NOT NULL DEFAULT 0 COMMENT 'CPU占用率'")
            logger.info("cpu_usage字段添加成功")
        else:
            logger.info("cpu_usage字段已存在")
            
        if not gpu_usage_exists:
            logger.info("添加gpu_usage字段...")
            cursor.execute("ALTER TABLE nodes ADD COLUMN gpu_usage FLOAT NOT NULL DEFAULT 0 COMMENT 'GPU占用率'")
            logger.info("gpu_usage字段添加成功")
        else:
            logger.info("gpu_usage字段已存在")
            
        if not memory_usage_exists:
            logger.info("添加memory_usage字段...")
            cursor.execute("ALTER TABLE nodes ADD COLUMN memory_usage FLOAT NOT NULL DEFAULT 0 COMMENT '内存占用率'")
            logger.info("memory_usage字段添加成功")
        else:
            logger.info("memory_usage字段已存在")
            
        if not gpu_memory_usage_exists:
            logger.info("添加gpu_memory_usage字段...")
            cursor.execute("ALTER TABLE nodes ADD COLUMN gpu_memory_usage FLOAT NOT NULL DEFAULT 0 COMMENT 'GPU显存占用率'")
            logger.info("gpu_memory_usage字段添加成功")
        else:
            logger.info("gpu_memory_usage字段已存在")
        
        # 提交更改
        connection.commit()
        
        # 输出字段验证信息
        cursor.execute("""
            SELECT column_name, data_type, column_comment
            FROM information_schema.columns
            WHERE table_schema = DATABASE() AND table_name = 'nodes'
              AND column_name IN ('cpu_usage', 'gpu_usage', 'memory_usage', 'gpu_memory_usage')
        """)
        fields = cursor.fetchall()
        logger.info(f"Node表字段验证: {fields}")
        
        # 关闭连接
        cursor.close()
        connection.close()
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.info(f"Node表迁移完成，耗时: {duration:.2f}秒")
        
    except Exception as e:
        logger.error(f"Node表迁移失败: {str(e)}")
        raise
        
if __name__ == "__main__":
    add_node_usage_fields() 