"""
数据库初始化脚本
"""
from core.database import engine
from models.database import Base

def init_db():
    """初始化数据库"""
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    init_db()
    print("数据库初始化完成") 