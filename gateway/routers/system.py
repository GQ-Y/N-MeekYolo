"""
系统配置相关路由
"""
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from core.database import get_db
from core.models import SystemConfig, NetworkConfig, CloudConfig
from core.auth import JWTBearer

router = APIRouter(prefix="/api/v1/system", tags=["system"])

# 请求模型
class SystemConfigUpdate(BaseModel):
    """系统配置更新请求"""
    device_name: Optional[str] = None
    auto_update: Optional[bool] = None
    debug_mode: Optional[bool] = None
    log_level: Optional[str] = None
    storage_path: Optional[str] = None
    max_storage_days: Optional[int] = None

class NetworkConfigUpdate(BaseModel):
    """网络配置更新请求"""
    mode: Optional[str] = None
    ip_address: Optional[str] = None
    netmask: Optional[str] = None
    gateway: Optional[str] = None
    dns_servers: Optional[list[str]] = None
    proxy_enabled: Optional[bool] = None
    proxy_server: Optional[str] = None
    proxy_port: Optional[int] = None

class CloudConfigUpdate(BaseModel):
    """云服务配置更新请求"""
    enabled: Optional[bool] = None
    service_type: Optional[str] = None
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    secret_key: Optional[str] = None
    region: Optional[str] = None
    bucket: Optional[str] = None
    sync_interval: Optional[int] = None

# 路由处理函数
@router.get("/config")
async def get_system_config(
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(JWTBearer())
) -> Dict[str, Any]:
    """获取系统配置"""
    config = db.query(SystemConfig).first()
    if not config:
        config = SystemConfig()
        db.add(config)
        db.commit()
        db.refresh(config)
    return {
        "device_name": config.device_name,
        "device_id": config.device_id,
        "version": config.version,
        "last_update": config.last_update,
        "auto_update": config.auto_update,
        "debug_mode": config.debug_mode,
        "log_level": config.log_level,
        "storage_path": config.storage_path,
        "max_storage_days": config.max_storage_days
    }

@router.put("/config")
async def update_system_config(
    config_update: SystemConfigUpdate,
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(JWTBearer())
) -> Dict[str, Any]:
    """更新系统配置"""
    config = db.query(SystemConfig).first()
    if not config:
        config = SystemConfig()
        db.add(config)
    
    # 更新配置
    for field, value in config_update.dict(exclude_unset=True).items():
        setattr(config, field, value)
    
    config.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(config)
    
    return {"message": "配置已更新"}

@router.get("/network")
async def get_network_config(
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(JWTBearer())
) -> Dict[str, Any]:
    """获取网络配置"""
    config = db.query(NetworkConfig).first()
    if not config:
        config = NetworkConfig()
        db.add(config)
        db.commit()
        db.refresh(config)
    return {
        "interface": config.interface,
        "mode": config.mode,
        "ip_address": config.ip_address,
        "netmask": config.netmask,
        "gateway": config.gateway,
        "dns_servers": config.dns_servers,
        "proxy_enabled": config.proxy_enabled,
        "proxy_server": config.proxy_server,
        "proxy_port": config.proxy_port
    }

@router.put("/network")
async def update_network_config(
    config_update: NetworkConfigUpdate,
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(JWTBearer())
) -> Dict[str, Any]:
    """更新网络配置"""
    config = db.query(NetworkConfig).first()
    if not config:
        config = NetworkConfig()
        db.add(config)
    
    # 更新配置
    for field, value in config_update.dict(exclude_unset=True).items():
        setattr(config, field, value)
    
    config.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(config)
    
    return {"message": "配置已更新"}

@router.get("/cloud")
async def get_cloud_config(
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(JWTBearer())
) -> Dict[str, Any]:
    """获取云服务配置"""
    config = db.query(CloudConfig).first()
    if not config:
        config = CloudConfig()
        db.add(config)
        db.commit()
        db.refresh(config)
    return {
        "enabled": config.enabled,
        "service_type": config.service_type,
        "endpoint": config.endpoint,
        "region": config.region,
        "bucket": config.bucket,
        "sync_interval": config.sync_interval,
        "last_sync": config.last_sync
    }

@router.put("/cloud")
async def update_cloud_config(
    config_update: CloudConfigUpdate,
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(JWTBearer())
) -> Dict[str, Any]:
    """更新云服务配置"""
    config = db.query(CloudConfig).first()
    if not config:
        config = CloudConfig()
        db.add(config)
    
    # 更新配置
    for field, value in config_update.dict(exclude_unset=True).items():
        setattr(config, field, value)
    
    config.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(config)
    
    return {"message": "配置已更新"} 