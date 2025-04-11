"""
应用配置
使用 Pydantic BaseSettings 从环境变量或 .env 文件加载配置。
"""
import logging
import os
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, AnyHttpUrl, validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

# --- 新增内部配置模型 ---
class ServiceRegistryItem(BaseModel):
    """下游服务配置项"""
    name: str
    url: AnyHttpUrl # 使用 AnyHttpUrl 确保是合法的 URL
    description: Optional[str] = None

class DiscoveryConfig(BaseModel):
    """服务发现配置"""
    interval: int = 60 # 健康检查间隔 (秒)
    timeout: int = 10 # 健康检查超时 (秒)
    # 可以添加其他发现机制相关的配置, 如 consul_address 等

class Settings(BaseSettings):
    # --- 基础信息 ---
    PROJECT_NAME: str = "N-MeekYolo Gateway"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False # 控制调试模式 (影响异常信息显示等)

    # --- 服务发现与注册 ---
    SERVICES: Optional[List[ServiceRegistryItem]] = [] # 下游服务列表
    DISCOVERY: DiscoveryConfig = DiscoveryConfig() # 服务发现配置

    # --- 数据库配置 --- 
    # 使用 DATABASE_URL 替代分散的配置项
    DATABASE_URL: Optional[str] = None # 例如: mysql+aiomysql://user:password@host:port/db
    # 单独的字段仍然可以保留，用于构建 URL 或备用
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = "123456"
    MYSQL_DB: str = "meek_gateway"

    # 动态构建 DATABASE_URL (如果未直接提供)
    @validator("DATABASE_URL", pre=True, always=True)
    def assemble_db_connection(cls, v: Optional[str], values: Dict[str, Any]) -> Any:
        if isinstance(v, str):
            logger.info(f"使用提供的 DATABASE_URL: {v[:15]}...") # 只记录部分 URL
            return v

        # 明确获取各个部分，提供默认值以防万一
        user = values.get('MYSQL_USER', 'root')
        password = values.get('MYSQL_PASSWORD', '123456')
        host = values.get('MYSQL_HOST', 'localhost')
        port_val = values.get('MYSQL_PORT', 3306) # 直接从 values 获取
        db_name = values.get('MYSQL_DB', 'meek_gateway')

        # 确保端口是整数
        try:
            port = int(port_val)
        except (ValueError, TypeError):
            logger.error(f"无法将 MYSQL_PORT ('{port_val}') 转换为整数，将使用默认端口 3306")
            port = 3306 # 如果转换失败，使用默认值

        # db_url = f"mysql+aiomysql://{user}:{password}@{host}:{port}/{db_name}"
        db_url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{db_name}" # 改为使用 pymysql 同步驱动
        logger.info(f"构建的 DATABASE_URL: {db_url[:15]}...")
        return db_url
        
    # --- JWT 认证配置 --- 
    SECRET_KEY: str = "a_very_secret_key_please_change_this123123" # 必须修改!
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 # 令牌有效期 (24小时)

    # --- 服务配置 --- 
    # 可以简化，直接定义 host 和 port
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    # class ServiceConfig(BaseModel):
    #     host: str = "0.0.0.0"
    #     port: int = 8000
    # SERVICE: ServiceConfig = ServiceConfig()
    
    # --- 支付网关配置 (示例) ---
    # 这些应该通过环境变量设置，而不是硬编码
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_PUBLIC_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    # 可以添加其他网关的密钥...

    # --- CORS 配置 --- 
    # 如果需要严格控制 CORS 来源
    # BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = [] 
    # @validator("BACKEND_CORS_ORIGINS", pre=True)
    # def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
    #     if isinstance(v, str) and not v.startswith("["):
    #         return [i.strip() for i in v.split(",")]
    #     elif isinstance(v, (list, str)):
    #         return v
    #     raise ValueError(v)

    # --- .env 文件配置 --- 
    class Config:
        env_file = ".env"
        case_sensitive = True # 环境变量名区分大小写
        env_file_encoding = 'utf-8'

# --- 实例化配置对象 --- 
try:
    settings = Settings()
    logger.info(f"配置加载成功 from '{settings.Config.env_file if os.path.exists(settings.Config.env_file) else 'environment variables'}'")
    # 可以在这里做一些敏感信息存在的检查
    if settings.SECRET_KEY == "a_very_secret_key_please_change_this":
         logger.warning("安全警告: JWT SECRET_KEY 使用了默认值，请务必修改!")
except Exception as e:
    logger.error(f"加载配置时出错: {e}", exc_info=True)
    raise # 启动时配置加载失败应该直接失败 