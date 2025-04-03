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
    Text,
    Index,
    Float
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
    Column('group_id', Integer, ForeignKey('stream_groups.id', ondelete='CASCADE')),
    Column('stream_id', Integer, ForeignKey('streams.id', ondelete='CASCADE')),
    Index('idx_gs_group_id', 'group_id'),
    Index('idx_gs_stream_id', 'stream_id')
)

# 任务与视频源的多对多关系表
task_stream_association = Table(
    'task_stream_association',
    Base.metadata,
    Column('task_id', Integer, ForeignKey('tasks.id', ondelete='CASCADE')),
    Column('stream_id', Integer, ForeignKey('streams.id', ondelete='CASCADE')),
    Index('idx_ts_task_id', 'task_id'),
    Index('idx_ts_stream_id', 'stream_id')
)

# 任务与模型的多对多关系表
task_model_association = Table(
    'task_model_association',
    Base.metadata,
    Column('task_id', Integer, ForeignKey('tasks.id', ondelete='CASCADE')),
    Column('model_id', Integer, ForeignKey('models.id', ondelete='CASCADE')),
    Index('idx_tm_task_id', 'task_id'),
    Index('idx_tm_model_id', 'model_id')
)

# 任务与回调服务的多关系表
task_callback_association = Table(
    'task_callback_association',
    Base.metadata,
    Column('task_id', Integer, ForeignKey('tasks.id', ondelete='CASCADE')),
    Column('callback_id', Integer, ForeignKey('callbacks.id', ondelete='CASCADE')),
    Index('idx_tc_task_id', 'task_id'),
    Index('idx_tc_callback_id', 'callback_id')
)

# 流分组和流的多对多关系表
stream_group_association = Table(
    'stream_group_association',
    Base.metadata,
    Column('stream_id', Integer, ForeignKey('streams.id', ondelete='CASCADE')),
    Column('group_id', Integer, ForeignKey('stream_groups.id', ondelete='CASCADE')),
    Index('idx_sg_stream_id', 'stream_id'),
    Index('idx_sg_group_id', 'group_id')
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
    
    __table_args__ = (
        Index('idx_streamgroup_name', 'name'),
    )

class Stream(Base):
    """流模型"""
    __tablename__ = "streams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    url = Column(String(500), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Integer, default=0)  # 0: 离线, 1: 在线
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
    
    __table_args__ = (
        Index('idx_stream_name', 'name'),
        Index('idx_stream_status', 'status'),
        Index('idx_stream_url', 'url'),
    )

class Model(Base):
    """模型表"""
    __tablename__ = "models"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    code = Column(String(50), unique=True, index=True, nullable=False, comment="模型代码")
    name = Column(String(100), nullable=False, comment="模型名称")
    path = Column(String(255), nullable=True, comment="模型路径")
    description = Column(String(500), nullable=True, comment="模型描述")
    nc = Column(Integer, nullable=False, default=0, comment="模型支持的检测类别数量")
    names = Column(JSON, nullable=True, comment="模型支持的检测类别名称映射")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    # 关联任务
    tasks = relationship("Task", secondary="task_model_association", back_populates="models")

    def __repr__(self):
        return f"<Model {self.code}>"

class Callback(Base):
    """回调服务"""
    __tablename__ = 'callbacks'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    url = Column(String(200), nullable=False, unique=True)
    description = Column(String(200))
    headers = Column(JSON)  # 自定义请求头
    method = Column(String(10), default='POST')  # 请求方法
    body_template = Column(JSON, nullable=True)  # 请求体模板
    retry_count = Column(Integer, default=3)  # 重试次数
    retry_interval = Column(Integer, default=1)  # 重试间隔(秒)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联任务
    tasks = relationship('Task', secondary=task_callback_association, back_populates='callbacks')
    
    __table_args__ = (
        Index('idx_callback_name', 'name'),
        Index('idx_callback_url', 'url'),
    )

class Task(Base):
    """分析任务"""
    __tablename__ = 'tasks'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    status = Column(Integer, default=0, nullable=False, comment="任务状态: 0(未启动), 1(运行中), 2(已停止)")
    error_message = Column(String(200))
    save_result = Column(Boolean, default=False, comment="是否保存结果")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    active_subtasks = Column(Integer, default=0, nullable=False, comment="运行中的子任务数量")
    total_subtasks = Column(Integer, default=0, nullable=False, comment="子任务总数量")
    
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
        
    __table_args__ = (
        Index('idx_task_name', 'name'),
        Index('idx_task_status', 'status'),
        Index('idx_task_created_at', 'created_at'),
    )

class SubTask(Base):
    """子任务表"""
    __tablename__ = "sub_tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey('tasks.id', ondelete='CASCADE'))
    analysis_task_id = Column(String(50), comment="Analysis Service的任务ID")
    stream_id = Column(Integer, ForeignKey('streams.id'))
    model_id = Column(Integer, ForeignKey('models.id'))
    status = Column(Integer, default=0, comment="状态: 0(未启动), 1(运行中), 2(已停止)")
    error_message = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    config = Column(JSON, nullable=True, comment="子任务配置信息(置信度、IOU阈值、ROI设置等)")
    enable_callback = Column(Boolean, default=False, nullable=False, comment="是否启用回调")
    callback_url = Column(String(255), nullable=True, comment="回调URL")
    node_id = Column(Integer, ForeignKey('nodes.id', ondelete='SET NULL'), nullable=True, comment="节点ID")
    roi_type = Column(Integer, default=0, nullable=False, comment="ROI类型: 0-无ROI, 1-矩形, 2-多边形, 3-线段")
    analysis_type = Column(String(50), default="detection", nullable=False, comment="分析类型: detection, tracking, counting等")
    
    # 关联关系
    task = relationship("Task", back_populates="sub_tasks")
    stream = relationship("Stream")
    model = relationship("Model")
    node = relationship("Node", back_populates="sub_tasks")
    
    __table_args__ = (
        Index('idx_subtask_task_id', 'task_id'),
        Index('idx_subtask_stream_id', 'stream_id'),
        Index('idx_subtask_model_id', 'model_id'),
        Index('idx_subtask_status', 'status'),
        Index('idx_subtask_node_id', 'node_id'),
    )

class Node(Base):
    """节点模型"""
    __tablename__ = "nodes"
    
    id = Column(Integer, primary_key=True, index=True)
    ip = Column(String(50), nullable=False, comment="节点IP地址")
    port = Column(String(10), nullable=False, comment="节点端口")
    service_name = Column(String(100), nullable=False, comment="服务名称")
    service_status = Column(String(20), default="offline", comment="服务状态")  # online, offline
    image_task_count = Column(Integer, default=0, comment="图像任务数量")
    video_task_count = Column(Integer, default=0, comment="视频任务数量")
    stream_task_count = Column(Integer, default=0, comment="流任务数量")
    weight = Column(Integer, default=1, comment="负载均衡权重")
    max_tasks = Column(Integer, default=10, comment="最大任务数量")
    is_active = Column(Boolean, default=True, comment="是否激活")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    last_heartbeat = Column(DateTime, nullable=True, comment="最后心跳时间")
    
    # 新增字段
    node_type = Column(String(50), nullable=False, default="edge", comment="节点类型：edge(边缘节点)、cluster(集群节点)")
    service_type = Column(Integer, nullable=False, default=1, comment="服务类型：1-分析服务、2-模型服务、3-云服务")
    cpu_usage = Column(Float, nullable=False, default=0, comment="CPU占用率")
    memory_usage = Column(Float, nullable=False, default=0, comment="内存占用率")
    gpu_usage = Column(Float, nullable=False, default=0, comment="GPU占用率")
    gpu_memory_usage = Column(Float, nullable=False, default=0, comment="GPU显存占用率")
    compute_type = Column(String(50), nullable=False, default="cpu", comment="计算类型：cpu(CPU计算边缘节点)、camera(摄像头边缘节点)、gpu(GPU计算边缘节点)、elastic(弹性集群节点)")
    
    # 关联子任务
    sub_tasks = relationship('SubTask', back_populates='node')
    
    __table_args__ = (
        Index('idx_node_ip_port', 'ip', 'port'),
        Index('idx_node_service_name', 'service_name'),
        Index('idx_node_service_status', 'service_status'),
        Index('idx_node_service_type', 'service_type'),
    )
    
    def __repr__(self):
        """返回节点的字符串表示"""
        return f"<Node(id={self.id}, ip={self.ip}, port={self.port}, service_name={self.service_name}, status={self.service_status})>"