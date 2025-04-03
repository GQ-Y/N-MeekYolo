"""
更新模型表结构
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

def update_model_table():
    """更新模型表结构，添加版本和作者字段"""
    engine = None
    try:
        # 创建数据库连接
        engine = create_engine(settings.DATABASE["url"])
        
        logger.info("开始更新模型表结构...")
        
        with engine.begin() as conn:
            # 检查字段是否存在
            check_version = conn.execute(text("""
                SELECT COUNT(*)
                FROM information_schema.columns 
                WHERE table_name = 'models' 
                AND column_name = 'version'
            """)).scalar()
            
            check_author = conn.execute(text("""
                SELECT COUNT(*)
                FROM information_schema.columns 
                WHERE table_name = 'models' 
                AND column_name = 'author'
            """)).scalar()
            
            # 添加 version 字段
            if check_version == 0:
                logger.info("添加 version 字段...")
                conn.execute(text("""
                    ALTER TABLE models 
                    ADD COLUMN version VARCHAR(50) DEFAULT '1.0.0' 
                    COMMENT '模型版本号';
                """))
                logger.info("version 字段添加成功")
            else:
                logger.info("version 字段已存在，跳过添加")
            
            # 添加 author 字段
            if check_author == 0:
                logger.info("添加 author 字段...")
                conn.execute(text("""
                    ALTER TABLE models 
                    ADD COLUMN author VARCHAR(100) 
                    COMMENT '模型作者';
                """))
                logger.info("author 字段添加成功")
            else:
                logger.info("author 字段已存在，跳过添加")
            
        logger.info("模型表结构更新完成！")
        
    except Exception as e:
        logger.error(f"更新失败: {str(e)}")
        raise
    finally:
        if engine:
            engine.dispose()

if __name__ == "__main__":
    update_model_table() 