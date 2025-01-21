"""
数据库模型
"""
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Table,
    Boolean,
    JSON,
    Text
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
from typing import List

Base = declarative_base()

# 视频源组和视频源的多对多关系表
group_stream_association = Table(
    'group_stream_association',
    Base.metadata,
    Column('group_id', Integer, ForeignKey('stream_groups.id')),
    Column('stream_id', Integer, ForeignKey('streams.id'))
)

# 任务与视频源的多对多关系表
task_stream_association = Table(
    'task_stream_association',
    Base.metadata,
    Column('task_id', Integer, ForeignKey('tasks.id')),
    Column('stream_id', Integer, ForeignKey('streams.id'))
)

# 任务与模型的多对多关系表
task_model_association = Table(
    'task_model_association',
    Base.metadata,
    Column('task_id', Integer, ForeignKey('tasks.id')),
    Column('model_id', Integer, ForeignKey('models.id'))
)

# 任务与回调服务的多关系表
task_callback_association = Table(
    'task_callback_association',
    Base.metadata,
    Column('task_id', Integer, ForeignKey('tasks.id')),
    Column('callback_id', Integer, ForeignKey('callbacks.id'))
)

# 流分组和流的多对多关系表
stream_group_association = Table(
    'stream_group_association',
    Base.metadata,
    Column('stream_id', Integer, ForeignKey('streams.id', ondelete='CASCADE')),
    Column('group_id', Integer, ForeignKey('stream_groups.id', ondelete='CASCADE'))
)

class StreamGroup(Base):
    """流分组模型"""
    __tablename__ = "stream_groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联关系
    streams = relationship(
        "Stream",
        secondary=stream_group_association,
        back_populates="groups"
    )

class Stream(Base):
    """流模型"""
    __tablename__ = "streams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    url = Column(String(500), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Integer, default=0)  # 修改为Integer类型,默认为离线(0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联关系
    groups = relationship(
        "StreamGroup",
        secondary=stream_group_association,
        back_populates="streams"
    )
    # 关联任务
    tasks = relationship('Task', secondary=task_stream_association, back_populates='streams')

class Model(Base):
    """模型表"""
    __tablename__ = "models"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)
    name = Column(String)
    path = Column(String)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联任务
    tasks = relationship('Task', secondary=task_model_association, back_populates='models')

class Callback(Base):
    """回调服务"""
    __tablename__ = 'callbacks'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    url = Column(String(200), nullable=False, unique=True)
    description = Column(String(200))
    headers = Column(JSON)  # 自定义请求头
    retry_count = Column(Integer, default=3)  # 重试次数
    retry_interval = Column(Integer, default=1)  # 重试间隔(秒)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联任务
    tasks = relationship('Task', secondary=task_callback_association, back_populates='callbacks')

class Task(Base):
    """分析任务"""
    __tablename__ = 'tasks'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    status = Column(String(20), default='created')  # created, running, paused, error, completed
    error_message = Column(String(200))
    callback_interval = Column(Integer, default=1)  # 回调间隔(秒)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    analysis_task_id = Column(String(50))  # 存储 analysis_service 的任务ID
    
    # 关联关系
    streams = relationship('Stream', secondary=task_stream_association, back_populates='tasks')
    models = relationship('Model', secondary=task_model_association, back_populates='tasks')
    callbacks = relationship('Callback', secondary=task_callback_association, back_populates='tasks')
    
    # 添加子任务关联
    sub_tasks = relationship("SubTask", back_populates="task", cascade="all, delete-orphan")
    
    @property
    def stream_ids(self) -> List[int]:
        """获取流ID列表"""
        return [stream.id for stream in self.streams]
        
    @property
    def model_ids(self) -> List[int]:
        """获取模型ID列表"""
        return [model.id for model in self.models]
        
    @property
    def callback_ids(self) -> List[int]:
        """获取回调ID列表"""
        return [callback.id for callback in self.callbacks] 

class SubTask(Base):
    """子任务表"""
    __tablename__ = "sub_tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey('tasks.id', ondelete='CASCADE'))
    analysis_task_id = Column(String(50))  # Analysis Service的任务ID
    stream_id = Column(Integer, ForeignKey('streams.id'))
    model_id = Column(Integer, ForeignKey('models.id'))
    status = Column(String(20), default="created")
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # 关联关系
    task = relationship("Task", back_populates="sub_tasks")
    stream = relationship("Stream")
    model = relationship("Model")