"""
数据库模型
"""
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Float, JSON, ForeignKey
from analysis_service.models.base import Base
import uuid

class Task(Base):
    """任务表"""
    __tablename__ = "tasks"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
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

class TaskQueue(Base):
    """任务队列表"""
    __tablename__ = "task_queue"
    
    id = Column(String(36), primary_key=True)
    task_id = Column(String(36), ForeignKey('tasks.id'))
    parent_task_id = Column(String(36), ForeignKey('tasks.id'), nullable=True)
    priority = Column(Integer, default=0)
    status = Column(Integer, default=0)  # 0:等待中 1:运行中 2:已完成 -1:失败
    retry_count = Column(Integer, default=0)
    
    # 资源使用情况
    cpu_usage = Column(Float, nullable=True)
    memory_usage = Column(Float, nullable=True)
    gpu_usage = Column(Float, nullable=True)
    
    # 时间信息
    created_at = Column(DateTime, default=datetime.now)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(String, nullable=True)
    
    def to_dict(self):
        """转换为字典"""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "parent_task_id": self.parent_task_id,
            "priority": self.priority,
            "status": self.status,
            "retry_count": self.retry_count,
            "cpu_usage": self.cpu_usage,
            "memory_usage": self.memory_usage,
            "gpu_usage": self.gpu_usage,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
            "started_at": self.started_at.strftime("%Y-%m-%d %H:%M:%S") if self.started_at else None,
            "completed_at": self.completed_at.strftime("%Y-%m-%d %H:%M:%S") if self.completed_at else None,
            "error_message": self.error_message
        }
    
