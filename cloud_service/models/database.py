"""
数据库模型
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON
from sqlalchemy.sql import func
from cloud_service.models.base import Base

class CloudModel(Base):
    """云模型"""
    __tablename__ = "cloud_models"
    
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False)
    version = Column(String(20), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(String(500))
    author = Column(String(100))
    file_path = Column(String(500))
    status = Column(Boolean, default=True)
    
    # 添加新字段
    nc = Column(Integer, nullable=False, comment="类别数量")
    names = Column(JSON, nullable=False, comment="类别名称映射")
    
    # 时间字段
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    class Config:
        from_attributes = True

class ApiKey(Base):
    """API密钥"""
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, index=True)  # API密钥
    name = Column(String)                          # 名称
    phone = Column(String)                         # 手机号
    email = Column(String)                         # 邮箱
    status = Column(Boolean, default=True)         # 状态(True:可用/False:不可用)
    
    # 时间字段
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )