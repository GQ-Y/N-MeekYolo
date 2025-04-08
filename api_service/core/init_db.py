"""
数据库初始化脚本
"""
from core.database import engine
# 显式导入所有模型类，确保它们被正确注册到Base.metadata中
from models.database import Base, Task, SubTask, Node, Stream, Model, StreamGroup, Callback, MQTTNode
import logging

logger = logging.getLogger(__name__)

def init_db():
    """初始化数据库"""
    # 创建所有表
    logger.info("开始初始化数据库表...")
    
    # 打印即将创建的表
    tables = Base.metadata.tables
    logger.info(f"要创建的表: {', '.join(tables.keys())}")
    
    # 创建所有表
    Base.metadata.create_all(bind=engine)
    
    logger.info("数据库初始化完成")

if __name__ == "__main__":
    init_db()
    print("数据库初始化完成") 