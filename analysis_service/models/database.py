"""
数据库模型
"""
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Float
from analysis_service.models.base import Base

class Task(Base):
    """任务表"""
    __tablename__ = "tasks"
    
    id = Column(String, primary_key=True)  # 使用 id 而不是 task_id
    model_code = Column(String)
    stream_url = Column(String)
    callback_urls = Column(String, nullable=True)
    output_url = Column(String, nullable=True)
    status = Column(Integer, default=0)  # 0:初始化 1:运行中 2:已完成 -1:异常
    start_time = Column(DateTime, default=datetime.now)
    stop_time = Column(DateTime, nullable=True)
    duration = Column(Float, nullable=True)  # 运行时长(分钟)
    
    def to_dict(self):
        """转换为字典"""
        return {
            "task_id": self.id,
            "status": self.status,
            "start_time": self.start_time.strftime("%Y-%m-%d %H:%M:%S") if self.start_time else None,
            "stop_time": self.stop_time.strftime("%Y-%m-%d %H:%M:%S") if self.stop_time else None,
            "duration": round(self.duration, 2) if self.duration else 0
        } 