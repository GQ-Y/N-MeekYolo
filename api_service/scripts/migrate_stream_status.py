"""
初始化数据库和视频源状态
"""
from sqlalchemy import create_engine, text
from core.config import settings
from models.database import Base, Stream, StreamGroup, Model, Callback, Task, Node, SubTask
from services.database import init_db, get_db

def init_database():
    """初始化数据库表结构和基础数据"""
    try:
        # 创建数据库引擎
        engine = create_engine(settings.DATABASE.url)
        
        # 创建表结构 - 确保所有表都被创建
        print("正在创建数据库表...")
        Base.metadata.create_all(engine)
        
        # 初始化数据库基础数据
        print("正在初始化数据库基础数据...")
        init_db()
        
        print("正在设置视频源状态...")
        with engine.connect() as conn:
            # 检查是否有需要设置的数据
            result = conn.execute(text("SELECT COUNT(*) FROM streams")).scalar()
            if result == 0:
                print("没有找到需要设置状态的视频源")
                return
                
            # 设置所有状态为 0 (离线)
            conn.execute(text(
                "UPDATE streams SET status = 0"
            ))
            
            conn.commit()
            
        print("视频源状态设置完成")
        
        # 确认表结构完整性
        print("\n数据库初始化完成，检查表结构:")
        tables = ["streams", "stream_groups", "models", "callbacks", "tasks", "nodes", "sub_tasks", 
                  "group_stream_association", "task_stream_association", "task_model_association", 
                  "task_callback_association", "stream_group_association"]
        
        with engine.connect() as conn:
            for table in tables:
                try:
                    result = conn.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))
                    print(f" - 表 {table} 已创建 ✓")
                except Exception as e:
                    print(f" - 表 {table} 创建失败: {str(e)} ✗")
        
    except Exception as e:
        print(f"初始化失败: {str(e)}")
        raise

if __name__ == "__main__":
    init_database() 