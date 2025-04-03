"""
更新节点表结构
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

def column_exists(conn, table_name: str, column_name: str) -> bool:
    """检查列是否存在"""
    result = conn.execute(text(f"""
        SELECT COUNT(*) 
        FROM information_schema.columns 
        WHERE table_name = '{table_name}' 
        AND column_name = '{column_name}';
    """))
    return result.scalar() > 0

def update_node_table():
    """更新节点表结构"""
    engine = None
    try:
        # 创建数据库连接
        engine = create_engine(settings.DATABASE["url"])
        
        logger.info("开始更新节点表结构...")
        
        with engine.begin() as conn:
            # 添加 node_type 字段
            if not column_exists(conn, 'nodes', 'node_type'):
                logger.info("添加 node_type 字段...")
                conn.execute(text("""
                    ALTER TABLE nodes 
                    ADD COLUMN node_type VARCHAR(50) NOT NULL DEFAULT 'edge' 
                    COMMENT '节点类型：edge(边缘节点)、cluster(集群节点)';
                """))
            
            # 添加 service_type 字段
            if not column_exists(conn, 'nodes', 'service_type'):
                logger.info("添加 service_type 字段...")
                conn.execute(text("""
                    ALTER TABLE nodes 
                    ADD COLUMN service_type INT NOT NULL DEFAULT 1 
                    COMMENT '服务类型：1-分析服务、2-模型服务、3-云服务';
                """))
            
            # 添加 memory_usage 字段
            if not column_exists(conn, 'nodes', 'memory_usage'):
                logger.info("添加 memory_usage 字段...")
                conn.execute(text("""
                    ALTER TABLE nodes 
                    ADD COLUMN memory_usage FLOAT NOT NULL DEFAULT 0 
                    COMMENT '内存占用率';
                """))
            
            # 添加 gpu_memory_usage 字段
            if not column_exists(conn, 'nodes', 'gpu_memory_usage'):
                logger.info("添加 gpu_memory_usage 字段...")
                conn.execute(text("""
                    ALTER TABLE nodes 
                    ADD COLUMN gpu_memory_usage FLOAT NOT NULL DEFAULT 0 
                    COMMENT 'GPU显存占用率';
                """))
            
            # 添加 compute_type 字段
            if not column_exists(conn, 'nodes', 'compute_type'):
                logger.info("添加 compute_type 字段...")
                conn.execute(text("""
                    ALTER TABLE nodes 
                    ADD COLUMN compute_type VARCHAR(50) NOT NULL DEFAULT 'cpu' 
                    COMMENT '计算类型：cpu(CPU计算边缘节点)、camera(摄像头边缘节点)、gpu(GPU计算边缘节点)、elastic(弹性集群节点)';
                """))
            
            # 添加索引
            logger.info("添加索引...")
            try:
                conn.execute(text("""
                    CREATE INDEX idx_node_service_type ON nodes (service_type);
                """))
            except Exception as e:
                if "Duplicate key name" not in str(e):
                    raise
                logger.info("索引已存在，跳过创建")
        
        logger.info("节点表结构更新完成！")
        
    except Exception as e:
        logger.error(f"更新失败: {str(e)}")
        raise
    finally:
        if engine:
            engine.dispose()

if __name__ == "__main__":
    update_node_table() 