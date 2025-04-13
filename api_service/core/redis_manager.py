"""Redis管理器模块"""
import json
from redis import asyncio as aioredis
from typing import Optional, Any, Dict, List
import asyncio
from core.config import settings
from shared.utils.logger import setup_logger
import threading

logger = setup_logger(__name__)

class Redis:
    """Redis客户端封装"""
    
    def __init__(self, host="localhost", port=6379, db=1, password=""):
        """初始化Redis连接"""
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.redis = None
        
        # 添加同步连接池
        self._sync_pool = None
        
        # 初始化连接
        self._init_connection()
    
    def _init_connection(self):
        """初始化连接"""
        try:
            # 异步连接初始化
            self.redis = aioredis.from_url(
                f"redis://{self.host}:{self.port}/{self.db}",
                password=self.password,
                decode_responses=True
            )
            
            # 初始化同步连接池
            import redis
            self._sync_pool = redis.ConnectionPool(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password,
                decode_responses=True,
                max_connections=10  # 设置最大连接数
            )
            
            logger.info(f"Redis连接池初始化成功: {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Redis连接池初始化失败: {str(e)}")
            raise

class RedisManager:
    """Redis连接管理器"""
    
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls):
        """获取Redis管理器实例（单例模式）"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = RedisManager()
            return cls._instance
    
    def __init__(self):
        """初始化Redis连接"""
        # Redis客户端实例
        self.redis = None
        self.pool = None
        # 添加同步连接池
        self._sync_pool = None
        
        # 初始化连接
        self._init_connection()
    
    def _init_connection(self):
        """初始化Redis连接池"""
        try:
            # 保持原有异步连接池实现
            self.pool = aioredis.ConnectionPool(
                host=settings.config.get('REDIS', {}).get('host', 'localhost'),
                port=settings.config.get('REDIS', {}).get('port', 6379),
                db=settings.config.get('REDIS', {}).get('db', 1),
                password=settings.config.get('REDIS', {}).get('password', ''),
                max_connections=settings.config.get('REDIS', {}).get('max_connections', 10),
                socket_timeout=settings.config.get('REDIS', {}).get('socket_timeout', 5),
                decode_responses=True
            )
            self.redis = aioredis.Redis(connection_pool=self.pool)
            
            # 初始化同步连接池
            import redis
            self._sync_pool = redis.ConnectionPool(
                host=settings.config.get('REDIS', {}).get('host', 'localhost'),
                port=settings.config.get('REDIS', {}).get('port', 6379),
                db=settings.config.get('REDIS', {}).get('db', 1),
                password=settings.config.get('REDIS', {}).get('password', ''),
                decode_responses=True,
                max_connections=settings.config.get('REDIS', {}).get('max_connections', 10),
                socket_timeout=settings.config.get('REDIS', {}).get('socket_timeout', 5)
            )
            
            logger.info(f"Redis连接池初始化成功: {settings.config.get('REDIS', {}).get('host', 'localhost')}:{settings.config.get('REDIS', {}).get('port', 6379)}")
        except Exception as e:
            logger.error(f"Redis连接池初始化失败: {str(e)}")
            raise
            
    async def close(self):
        """关闭Redis连接"""
        if self.pool:
            await self.pool.disconnect()
            logger.info("Redis异步连接池已关闭")
        
        # 关闭同步连接池
        if self._sync_pool:
            self._sync_pool.disconnect()
            logger.info("Redis同步连接池已关闭")
            
    async def get_value(self, key: str, as_json: bool = False) -> Any:
        """获取键值"""
        try:
            logger.debug(f"Redis.get_value - 获取键: {key}")
            value = await self.redis.get(key)
            
            if value:
                logger.debug(f"Redis.get_value - 成功获取键 {key} 的值")
                if as_json:
                    try:
                        parsed_value = json.loads(value)
                        return parsed_value
                    except json.JSONDecodeError as e:
                        logger.error(f"Redis.get_value - JSON解析失败 - {key}: {str(e)}")
                        return None
                return value
            else:
                logger.debug(f"Redis.get_value - 键 {key} 不存在")
                return None
                
        except Exception as e:
            logger.error(f"Redis.get_value - 获取键值失败 - {key}: {str(e)}")
            return None
            
    async def set_value(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        """设置键值"""
        try:
            logger.debug(f"Redis.set_value - 设置键: {key}")
            
            if isinstance(value, (dict, list)):
                try:
                    value = json.dumps(value)
                    logger.debug(f"Redis.set_value - 字典/列表转为JSON字符串: {key}")
                except Exception as e:
                    logger.error(f"Redis.set_value - JSON序列化失败 - {key}: {str(e)}")
                    raise
            
            result = await self.redis.set(key, value, ex=ex)
            
            if result:
                logger.debug(f"Redis.set_value - 成功设置键 {key} 的值")
            else:
                logger.warning(f"Redis.set_value - 设置键 {key} 返回结果: {result}")
            
            return bool(result)
            
        except Exception as e:
            logger.error(f"Redis.set_value - 设置键值失败 - {key}: {str(e)}")
            return False
            
    async def delete_key(self, key: str) -> bool:
        """删除键"""
        try:
            await self.redis.delete(key)
            return True
        except Exception as e:
            logger.error(f"删除Redis键失败 - {key}: {str(e)}")
            return False
            
    async def exists_key(self, key: str) -> bool:
        """检查键是否存在"""
        try:
            return await self.redis.exists(key)
        except Exception as e:
            logger.error(f"检查Redis键是否存在失败 - {key}: {str(e)}")
            return False
            
    def exists_key_sync(self, key: str) -> bool:
        """
        同步方式检查键是否存在
        
        Args:
            key: 键名
            
        Returns:
            bool: 键是否存在
        """
        try:
            import redis
            r = redis.Redis(connection_pool=self._sync_pool)
            return bool(r.exists(key))
        except Exception as e:
            logger.error(f"同步方式检查Redis键是否存在失败 - {key}: {str(e)}")
            return False

    async def ping(self) -> bool:
        """测试连接"""
        try:
            return await self.redis.ping()
        except Exception as e:
            logger.error(f"Redis连接测试失败: {str(e)}")
            return False

    # 哈希操作
    async def hset_dict(self, name: str, mapping: Dict[str, Any]):
        """设置哈希表"""
        try:
            processed_mapping = {
                k: json.dumps(v) if isinstance(v, (dict, list)) else str(v)
                for k, v in mapping.items()
            }
            await self.redis.hset(name, mapping=processed_mapping)
        except Exception as e:
            logger.error(f"设置哈希表失败: {str(e)}")
            raise

    async def hget_dict(self, name: str, key: str, as_json: bool = False) -> Any:
        """获取哈希表字段"""
        try:
            value = await self.redis.hget(name, key)
            if value and as_json:
                return json.loads(value)
            return value
        except Exception as e:
            logger.error(f"获取哈希表字段失败: {str(e)}")
            return None

    # 列表操作
    async def list_push(self, name: str, value: Any):
        """推入列表"""
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            await self.redis.rpush(name, value)
        except Exception as e:
            logger.error(f"推入列表失败: {str(e)}")
            raise

    async def list_pop(self, name: str, as_json: bool = False) -> Any:
        """弹出列表"""
        try:
            value = await self.redis.lpop(name)
            if value and as_json:
                return json.loads(value)
            return value
        except Exception as e:
            logger.error(f"弹出列表失败: {str(e)}")
            return None

    # 键过期
    async def set_expiry(self, name: str, seconds: int):
        """设置键过期时间"""
        try:
            await self.redis.expire(name, seconds)
        except Exception as e:
            logger.error(f"设置键过期时间失败: {str(e)}")
            raise

    def get_value_sync(self, key: str, as_json: bool = False) -> Any:
        """获取键值（同步版本）"""
        try:
            logger.debug(f"Redis.get_value_sync - 获取键: {key}")
            
            # 使用同步连接池
            import redis
            r = redis.Redis(connection_pool=self._sync_pool)
            
            try:
                value = r.get(key)
                
                if value:
                    logger.debug(f"Redis.get_value_sync - 成功获取键 {key} 的值")
                    if as_json:
                        try:
                            parsed_value = json.loads(value)
                            return parsed_value
                        except json.JSONDecodeError as e:
                            logger.error(f"Redis.get_value_sync - JSON解析失败 - {key}: {str(e)}")
                            return None
                    return value
                else:
                    logger.debug(f"Redis.get_value_sync - 键 {key} 不存在")
                    return None
            finally:
                # 使用连接池时不需要手动关闭连接，连接会自动回到池中
                pass
            
        except Exception as e:
            logger.error(f"Redis.get_value_sync - 获取键值失败 - {key}: {str(e)}")
            return None
        
    def set_value_sync(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        """设置键值（同步版本）"""
        try:
            logger.debug(f"Redis.set_value_sync - 设置键: {key}")
            
            if isinstance(value, (dict, list)):
                try:
                    value = json.dumps(value)
                    logger.debug(f"Redis.set_value_sync - 字典/列表转为JSON字符串: {key}")
                except Exception as e:
                    logger.error(f"Redis.set_value_sync - JSON序列化失败 - {key}: {str(e)}")
                    raise
            
            # 使用同步连接池
            import redis
            r = redis.Redis(connection_pool=self._sync_pool)
            
            try:
                result = r.set(key, value, ex=ex)
                
                if result:
                    logger.debug(f"Redis.set_value_sync - 成功设置键 {key} 的值")
                else:
                    logger.warning(f"Redis.set_value_sync - 设置键 {key} 返回结果: {result}")
                
                return bool(result)
            finally:
                # 使用连接池时不需要手动关闭连接，连接会自动回到池中
                pass
        
        except Exception as e:
            logger.error(f"Redis.set_value_sync - 设置键值失败 - {key}: {str(e)}")
            return False

    def delete_key_sync(self, key: str) -> bool:
        """
        同步方式删除键
        
        Args:
            key: 键名
            
        Returns:
            bool: 是否成功删除
        """
        try:
            import redis
            r = redis.Redis(connection_pool=self._sync_pool)
            r.delete(key)
            logger.debug(f"同步方式成功删除Redis键: {key}")
            return True
        except Exception as e:
            logger.error(f"同步方式删除Redis键失败 - {key}: {str(e)}")
            return False