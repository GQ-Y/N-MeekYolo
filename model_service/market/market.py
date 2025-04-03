"""
模型市场管理器
处理模型市场的同步和管理
"""
import aiohttp
import asyncio
from typing import Dict, Any, List
from datetime import datetime
from shared.utils.logger import setup_logger
from core.config import settings

logger = setup_logger(__name__)

class ModelMarket:
    """模型市场管理器"""
    
    def __init__(self):
        self.config = settings.MARKET
        self.last_sync: datetime = None
        
    async def sync_models(self) -> Dict[str, Any]:
        """同步远程模型"""
        if not self.config["enable_remote"]:
            return {"message": "远程市场已禁用"}
            
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.config['remote_url']}/models") as response:
                    if response.status == 200:
                        models = await response.json()
                        self.last_sync = datetime.now()
                        return {
                            "synced_at": self.last_sync.isoformat(),
                            "models": models
                        }
                    else:
                        raise Exception(f"同步失败: HTTP {response.status}")
                        
        except Exception as e:
            logger.error(f"同步模型失败: {str(e)}")
            raise
            
    async def list_available_models(self) -> List[Dict[str, Any]]:
        """获取可用模型列表"""
        # 如果距离上次同步时间超过间隔，重新同步
        if (not self.last_sync or 
            (datetime.now() - self.last_sync).total_seconds() > self.config["sync_interval"]):
            await self.sync_models()
            
        # 返回本地缓存的模型列表
        return []  # TODO: 实现本地缓存 