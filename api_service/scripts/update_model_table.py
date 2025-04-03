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

from sqlalchemy import create_engine, text
from core.config import settings
import logging

logger = logging.getLogger(__name__)

def update_model_table():
    """更新模型表结构"""
    try:
        # 创建数据库引擎
        engine = create_engine(settings.DATABASE.url)
        
        # 检查字段是否存在的SQL
        check_columns_sql = """
        SELECT COLUMN_NAME 
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_NAME = 'models' 
        AND COLUMN_NAME IN ('nc', 'names');
        """
        
        print("开始更新模型表结构...")
        
        with engine.begin() as conn:
            # 检查现有字段
            result = conn.execute(text(check_columns_sql))
            existing_columns = [row[0] for row in result]
            
            # 添加缺失的字段
            if 'nc' not in existing_columns:
                print("添加 nc 字段...")
                conn.execute(text(
                    "ALTER TABLE models ADD COLUMN nc INT NOT NULL DEFAULT 0 COMMENT '模型支持的检测类别数量';"
                ))
            
            if 'names' not in existing_columns:
                print("添加 names 字段...")
                conn.execute(text(
                    "ALTER TABLE models ADD COLUMN names JSON NULL COMMENT '模型支持的检测类别名称映射';"
                ))
            
            # 修改现有字段
            print("修改现有字段...")
            conn.execute(text("""
                ALTER TABLE models 
                MODIFY COLUMN code VARCHAR(50) NOT NULL COMMENT '模型代码',
                MODIFY COLUMN name VARCHAR(100) NOT NULL COMMENT '模型名称',
                MODIFY COLUMN path VARCHAR(255) NULL COMMENT '模型路径',
                MODIFY COLUMN description VARCHAR(500) NULL COMMENT '模型描述';
            """))
            
            # 添加索引
            print("确保索引存在...")
            try:
                conn.execute(text(
                    "CREATE INDEX idx_model_code ON models(code);"
                ))
            except Exception as e:
                if "Duplicate" not in str(e):
                    raise
                print("索引已存在")
            
        print("模型表结构更新成功！")
        
        # 验证更新
        with engine.connect() as conn:
            # 检查字段是否存在
            result = conn.execute(text("""
                SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_COMMENT 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'models'
            """))
            
            print("\n当前模型表结构：")
            for row in result:
                print(f"字段: {row[0]}")
                print(f"  类型: {row[1]}")
                print(f"  可空: {row[2]}")
                print(f"  注释: {row[3]}")
                print()
                
    except Exception as e:
        print(f"更新失败: {str(e)}")
        raise

if __name__ == "__main__":
    update_model_table() 