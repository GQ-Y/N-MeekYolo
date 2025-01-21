"""
迁移视频源状态
"""
import os
from sqlalchemy import create_engine, text
from api_service.core.config import settings
from api_service.models.database import Base, Stream, StreamGroup, Model, Callback, Task  # 导入所有模型
from api_service.services.database import init_db, get_db

def migrate_stream_status():
    """迁移视频源状态从字符串到整数"""
    try:
        # 确保数据库目录存在
        db_path = settings.DATABASE.url.replace('sqlite:///', '')
        db_dir = os.path.dirname(db_path)
        os.makedirs(db_dir, exist_ok=True)
        
        # 创建数据库引擎
        engine = create_engine(settings.DATABASE.url)
        
        # 创建表结构
        print("正在创建数据库表...")
        Base.metadata.create_all(engine)
        
        # 初始化数据库
        print("正在初始化数据库...")
        init_db()
        
        print("正在迁移视频源状态...")
        with engine.connect() as conn:
            # 检查是否有需要迁移的数据
            result = conn.execute(text("SELECT COUNT(*) FROM streams")).scalar()
            if result == 0:
                print("没有找到需要迁移的数据")
                return
                
            # 更新所有 inactive 状态为 0 (离线)
            conn.execute(text(
                "UPDATE streams SET status = 0 WHERE status = 'inactive'"
            ))
            
            # 更新所有 active 状态为 1 (在线)
            conn.execute(text(
                "UPDATE streams SET status = 1 WHERE status = 'active'"
            ))
            
            # 更新其他状态为 0 (离线)
            conn.execute(text(
                "UPDATE streams SET status = 0 WHERE status NOT IN (0, 1)"
            ))
            
            conn.commit()
            
        print("数据迁移完成")
        
    except Exception as e:
        print(f"迁移失败: {str(e)}")
        raise

if __name__ == "__main__":
    migrate_stream_status() 