"""
密钥服务
"""
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException
import httpx
from model_service.models.database import MarketKey
from model_service.models.schemas import KeyCreate
from model_service.services.cloud_client import CloudClient
from model_service.services.base import get_key
from shared.utils.logger import setup_logger
from datetime import datetime

logger = setup_logger(__name__)

class KeyService:
    """密钥服务"""
    
    def __init__(self):
        self.cloud_client = CloudClient()
    
    async def get_key(self, db: Session) -> Optional[MarketKey]:
        """获取密钥"""
        return await get_key(db)
    
    async def create_or_update_key(self, db: Session, data: KeyCreate) -> MarketKey:
        """创建或更新密钥"""
        try:
            # 获取现有密钥
            key = db.query(MarketKey).first()
            
            # 调用云服务
            cloud_client = CloudClient()
            try:
                if key:
                    # 更新密钥
                    result = await cloud_client.update_key(key.cloud_id, data.model_dump())
                else:
                    # 创建新密钥
                    result = await cloud_client.create_key(data.model_dump())
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
            
            # 保存到数据库
            try:
                if key:
                    key.name = result["name"]
                    key.description = result.get("description")
                    key.expires_at = result.get("expires_at")
                    key.updated_at = datetime.now()
                else:
                    key = MarketKey(
                        cloud_id=result["id"],
                        name=result["name"],
                        description=result.get("description"),
                        expires_at=result.get("expires_at")
                    )
                    db.add(key)
                
                db.commit()
                db.refresh(key)
                return key
            except Exception as e:
                logger.error(f"数据库操作失败: {str(e)}")
                db.rollback()
                raise HTTPException(
                    status_code=500,
                    detail="数据库操作失败"
                )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"创建/更新密钥失败: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="创建/更新密钥失败"
            )