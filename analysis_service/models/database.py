"""
数据库模型定义
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON, ForeignKey, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from analysis_service.models.base import Base
from analysis_service.core.models import AnalysisType

class Task(Base):
    """任务表"""
    __tablename__ = "tasks"

    id = Column(String(50), primary_key=True, comment="任务ID")
    task_name = Column(String(100), nullable=True, comment="任务名称")
    model_code = Column(String(50), nullable=False, comment="模型代码")
    stream_url = Column(String(500), nullable=False, comment="流URL")
    callback_urls = Column(String(1000), nullable=True, comment="回调地址")
    output_url = Column(String(500), nullable=True, comment="输出URL")
    analysis_type = Column(String(20), nullable=True, comment="分析类型")
    config = Column(JSON, nullable=True, comment="分析配置")
    enable_callback = Column(Boolean, default=False, comment="是否启用回调")
    save_result = Column(Boolean, default=False, comment="是否保存结果")
    status = Column(Integer, default=0, comment="任务状态: 0-等待中, 1-运行中, 2-已完成, -1-失败")
    error_message = Column(String(500), nullable=True, comment="错误信息")
    start_time = Column(DateTime, nullable=True, comment="开始时间")
    stop_time = Column(DateTime, nullable=True, comment="停止时间")
    duration = Column(Float, nullable=True, comment="运行时长(分钟)")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    # 关联队列任务
    queue_tasks = relationship("TaskQueue", back_populates="task")

    def to_dict(self):
        """转换为字典"""
        return {
            "id": self.id,
            "task_name": self.task_name,
            "model_code": self.model_code,
            "stream_url": self.stream_url,
            "callback_urls": self.callback_urls,
            "output_url": self.output_url,
            "analysis_type": self.analysis_type,
            "config": self.config,
            "enable_callback": self.enable_callback,
            "save_result": self.save_result,
            "status": self.status,
            "error_message": self.error_message,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "stop_time": self.stop_time.isoformat() if self.stop_time else None,
            "duration": self.duration,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }

class TaskQueue(Base):
    """任务队列表"""
    __tablename__ = "task_queue"

    id = Column(String(50), primary_key=True, comment="队列任务ID")
    task_id = Column(String(50), ForeignKey("tasks.id"), nullable=False, comment="关联任务ID")
    parent_task_id = Column(String(50), nullable=True, comment="父任务ID")
    status = Column(Integer, default=0, comment="任务状态: 0-等待中, 1-运行中, 2-已完成, -1-失败")
    error_message = Column(String(500), nullable=True, comment="错误信息")
    priority = Column(Integer, default=0, comment="优先级")
    retry_count = Column(Integer, default=0, comment="重试次数")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    started_at = Column(DateTime, nullable=True, comment="开始时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    # 关联任务
    task = relationship("Task", back_populates="queue_tasks")

    def to_dict(self):
        """转换为字典"""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "parent_task_id": self.parent_task_id,
            "status": self.status,
            "error_message": self.error_message,
            "priority": self.priority,
            "retry_count": self.retry_count,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "updated_at": self.updated_at.isoformat()
        }
    
