"""
市场服务
"""
import httpx
from sqlalchemy.orm import Session
from fastapi import HTTPException
from model_service.core.config import settings
from model_service.services.key import KeyService
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class MarketService:
    """市场服务"""
    
    def __init__(self):
        self.key_service = KeyService()
        self.base_url = settings.CLOUD.url
        self.api_prefix = settings.CLOUD.api_prefix
    
    def _get_api_url(self, path: str) -> str:
        """获取完整的API URL"""
        return f"{self.base_url}{self.api_prefix}{path}"
    
    async def get_models(self, db: Session, skip: int = 0, limit: int = 10):
        """
        获取云市场模型列表
        
        参数：
        - db: 数据库会话
        - skip: 跳过的记录数
        - limit: 返回的记录数
        
        返回：
        - 模型列表
        
        异常：
        - HTTPException(401): 无效的访问凭证
        - HTTPException(403): 没有权限执行此操作
        - HTTPException(503): 云服务暂时不可用
        """
        try:
            # 获取API密钥
            key = await self.key_service.get_key(db)
            if not key:
                raise HTTPException(
                    status_code=401,
                    detail="未找到有效的API密钥"
                )
            if not key.status:
                raise HTTPException(
                    status_code=403,
                    detail="API密钥已失效"
                )
            
            # 调用云市场API
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        self._get_api_url("/models"),
                        params={"skip": skip, "limit": limit},
                        headers={"x-api-key": key.key},
                        timeout=30.0  # 设置超时时间
                    )
                    response.raise_for_status()
                    result = response.json()
                    # 只返回data字段
                    return result.get("data", {})
            except httpx.TimeoutException:
                logger.error("云服务请求超时")
                raise HTTPException(
                    status_code=503,
                    detail="云服务请求超时，请稍后重试"
                )
            except httpx.RequestError as e:
                logger.error(f"云服务请求失败: {str(e)}")
                raise HTTPException(
                    status_code=503,
                    detail="云服务暂时不可用，请稍后重试"
                )
            except httpx.HTTPStatusError as e:
                logger.error(f"云服务返回错误: {str(e)}")
                if e.response.status_code == 401:
                    raise HTTPException(
                        status_code=401,
                        detail="无效的访问凭证"
                    )
                elif e.response.status_code == 403:
                    raise HTTPException(
                        status_code=403,
                        detail="没有权限执行此操作"
                    )
                elif e.response.status_code == 404:
                    raise HTTPException(
                        status_code=404,
                        detail="请求的资源不存在"
                    )
                else:
                    raise HTTPException(
                        status_code=500,
                        detail="云服务内部错误"
                    )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"获取模型列表失败: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="获取模型列表失败"
            )
    
    async def sync_models(self, db: Session):
        """
        同步云市场模型
        
        参数：
        - db: 数据库会话
        
        返回：
        - 同步结果
        
        异常：
        - HTTPException(401): 无效的访问凭证
        - HTTPException(403): 没有权限执行此操作
        - HTTPException(503): 云服务暂时不可用
        """
        try:
            # 获取API密钥
            key = await self.key_service.get_key(db)
            if not key:
                raise HTTPException(
                    status_code=401,
                    detail="未找到有效的API密钥"
                )
            if not key.status:
                raise HTTPException(
                    status_code=403,
                    detail="API密钥已失效"
                )
            
            # 调用云市场API
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        self._get_api_url("/models/available"),
                        headers={"x-api-key": key.key},
                        timeout=30.0  # 设置超时时间
                    )
                    response.raise_for_status()
                    result = response.json()
                    logger.info("成功从云市场同步模型")
                    # 只返回data字段
                    return result.get("data", {})
            except httpx.TimeoutException:
                logger.error("云服务请求超时")
                raise HTTPException(
                    status_code=503,
                    detail="云服务请求超时，请稍后重试"
                )
            except httpx.RequestError as e:
                logger.error(f"云服务请求失败: {str(e)}")
                raise HTTPException(
                    status_code=503,
                    detail="云服务暂时不可用，请稍后重试"
                )
            except httpx.HTTPStatusError as e:
                logger.error(f"云服务返回错误: {str(e)}")
                if e.response.status_code == 401:
                    raise HTTPException(
                        status_code=401,
                        detail="无效的访问凭证"
                    )
                elif e.response.status_code == 403:
                    raise HTTPException(
                        status_code=403,
                        detail="没有权限执行此操作"
                    )
                elif e.response.status_code == 404:
                    raise HTTPException(
                        status_code=404,
                        detail="请求的资源不存在"
                    )
                else:
                    raise HTTPException(
                        status_code=500,
                        detail="云服务内部错误"
                    )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"同步模型失败: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="同步模型失败"
            ) 