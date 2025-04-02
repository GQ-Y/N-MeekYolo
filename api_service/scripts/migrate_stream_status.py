"""
初始化视频源状态
"""
from sqlalchemy import create_engine, text
from api_service.core.config import settings
from api_service.models.database import Base, Stream, StreamGroup, Model, Callback, Task
from api_service.services.database import init_db, get_db

def init_stream_status():
    """初始化视频源状态为整数"""
    try:
        # 创建数据库引擎
        engine = create_engine(settings.DATABASE.url)
        
        # 创建表结构
        print("正在创建数据库表...")
        Base.metadata.create_all(engine)
        
        # 初始化数据库
        print("正在初始化数据库...")
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
        
    except Exception as e:
        print(f"初始化失败: {str(e)}")
        raise

if __name__ == "__main__":
    init_stream_status() 