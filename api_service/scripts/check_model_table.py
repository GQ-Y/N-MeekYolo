"""
检查模型表结构
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
sys.path.append(str(project_root))

import logging
from sqlalchemy import create_engine, text
from shared.config.settings import settings

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_model_table():
    """检查模型表结构"""
    engine = None
    try:
        # 创建数据库连接
        engine = create_engine(settings.DATABASE["url"])
        
        logger.info("模型表结构：")
        
        with engine.connect() as conn:
            # 执行 DESC 命令查看表结构
            result = conn.execute(text("DESC models;"))
            
            # 打印结果
            for row in result:
                logger.info(f"字段: {row[0]}, 类型: {row[1]}, 可空: {row[2]}, 键: {row[3]}, 默认值: {row[4]}, 扩展: {row[5]}")
            
        logger.info("检查完成！")
        
    except Exception as e:
        logger.error(f"检查失败: {str(e)}")
        raise
    finally:
        if engine:
            engine.dispose()

if __name__ == "__main__":
    check_model_table() 