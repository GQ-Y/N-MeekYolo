"""
数据库模型
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class MarketKey(Base):
    """云市场密钥"""
    __tablename__ = "market_keys"
    
    id = Column(Integer, primary_key=True)
    cloud_id = Column(Integer, nullable=False)  # 云市场密钥ID
    key = Column(String, unique=True, index=True)  # API密钥
    name = Column(String, nullable=False)          # 用户名称
    phone = Column(String, nullable=False)         # 手机号
    email = Column(String, nullable=False)         # 邮箱
    status = Column(Boolean, default=True)         # 状态
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now()) 