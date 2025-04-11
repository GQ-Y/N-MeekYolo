"""
系统配置相关路由
"""
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy import func # 导入 func
from pydantic import BaseModel, Field
from datetime import datetime
import json # 导入 json 用于处理可能的 JSON value

from core.database import get_db
from core.models.admin import SystemConfiguration # 导入新模型
from core.models.user import User # 导入 User 用于记录 updated_by
from core.auth import JWTBearer

router = APIRouter(prefix="/api/v1/system", tags=["system"])

# --- 新增 Pydantic 模型 ---
class ConfigurationItem(BaseModel):
    """单个配置项模型"""
    key: str = Field(..., description="配置项的 Key")
    value: Any = Field(..., description="配置项的值")

class ConfigurationUpdate(BaseModel):
    """配置更新请求模型 (批量)"""
    items: List[ConfigurationItem] = Field(..., description="要更新的配置项列表")

# --- 新增响应模型 ---
class ConfigurationUpdateResponse(BaseModel):
    """配置更新响应模型"""
    message: str
    updated: List[str]
    created: List[str]

# --- 定义配置 Key 常量 (推荐放在单独的常量文件) ---
class ConfigKeys:
    SYSTEM_DEVICE_NAME = "system.device_name"
    SYSTEM_AUTO_UPDATE = "system.auto_update"
    SYSTEM_DEBUG_MODE = "system.debug_mode"
    SYSTEM_LOG_LEVEL = "system.log_level"
    SYSTEM_STORAGE_PATH = "system.storage_path"
    SYSTEM_MAX_STORAGE_DAYS = "system.max_storage_days"
    # 决定是否保留网络和云配置，以及如何存储
    NETWORK_MODE = "network.mode"
    NETWORK_IP_ADDRESS = "network.ip_address"
    NETWORK_NETMASK = "network.netmask"
    NETWORK_GATEWAY = "network.gateway"
    NETWORK_DNS_SERVERS = "network.dns_servers" # 值可能是 JSON 字符串
    NETWORK_PROXY_ENABLED = "network.proxy_enabled"
    NETWORK_PROXY_SERVER = "network.proxy_server"
    NETWORK_PROXY_PORT = "network.proxy_port"
    CLOUD_ENABLED = "cloud.enabled"
    CLOUD_SERVICE_TYPE = "cloud.service_type"
    CLOUD_ENDPOINT = "cloud.endpoint"
    CLOUD_REGION = "cloud.region"
    CLOUD_BUCKET = "cloud.bucket"
    CLOUD_SYNC_INTERVAL = "cloud.sync_interval"

# 路由处理函数
@router.get("/config")
async def get_system_configurations(
    db: Session = Depends(get_db),
    current_user: User = Depends(JWTBearer(required_roles=['admin', 'super_admin'])) # 仅管理员可访问
) -> Dict[str, Any]:
    """获取所有系统配置项"""
    configs = db.query(SystemConfiguration).all()
    # 将配置列表转换为 key: value 字典
    config_dict = {config.key: config.value for config in configs}
    
    # 注意：value 存储的是字符串，需要根据 key 的类型进行转换 (如果前端需要)
    # 例如，布尔值、整数等。这里暂时直接返回字符串值。
    # 也可以考虑在 SystemConfiguration 模型中添加一个方法来获取转换后的值。
    
    return config_dict

@router.put("/config", response_model=ConfigurationUpdateResponse)
async def update_system_configurations(
    config_update: ConfigurationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(JWTBearer(required_roles=['admin', 'super_admin'])) # 仅管理员可操作
) -> ConfigurationUpdateResponse: # 更新返回类型提示
    """批量更新系统配置项"""
    updated_keys = []
    created_keys = []

    for item in config_update.items:
        key = item.key
        value = item.value
        
        # 查找现有配置项
        config_entry = db.query(SystemConfiguration).filter(SystemConfiguration.key == key).first()
        
        # 对 value 进行必要的类型转换或序列化 (示例)
        # 注意：这里假设所有 value 都应存储为字符串。更复杂的类型处理可能需要
        # 根据 key 进行判断。
        if isinstance(value, (dict, list)):
            try:
                value_str = json.dumps(value)
            except TypeError:
                raise HTTPException(status_code=400, detail=f"配置项 '{key}' 的值无法序列化为 JSON")
        elif isinstance(value, bool):
            value_str = str(value).lower() # 存储为 "true" 或 "false"
        else:
            value_str = str(value)

        if config_entry:
            # 更新现有配置项
            if config_entry.value != value_str: # 仅当值改变时更新
                config_entry.value = value_str
                config_entry.updated_at = func.now() # 使用数据库函数获取时间
                config_entry.updated_by_user_id = current_user.id
                updated_keys.append(key)
        else:
            # 创建新配置项
            new_config = SystemConfiguration(
                key=key,
                value=value_str,
                updated_by_user_id=current_user.id
                # description 和 is_enabled 可以根据需要在这里设置或留空/默认
            )
            db.add(new_config)
            created_keys.append(key)

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        # 考虑记录详细错误日志
        raise HTTPException(status_code=500, detail="数据库更新失败")

    return ConfigurationUpdateResponse(
        message="配置更新成功",
        updated=updated_keys,
        created=created_keys
    )

# --- 移除旧的网络和云路由 ---
# @router.get("/network")
# ...
# @router.put("/network")
# ...
# @router.get("/cloud")
# ...
# @router.put("/cloud")
# ... 