"""
密钥服务
"""
from typing import Optional, Dict, Any, List
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
    
    async def get_key(self, db: Session, key_id: Optional[int] = None) -> Optional[MarketKey]:
        """
        获取密钥
        
        Args:
            db: 数据库会话
            key_id: 密钥ID，如果不提供则返回第一个可用密钥
            
        Returns:
            Optional[MarketKey]: 密钥信息
        """
        if key_id:
            return db.query(MarketKey).filter(MarketKey.id == key_id).first()
        return await get_key(db)
    
    async def get_keys(self, db: Session, skip: int = 0, limit: int = 10) -> List[MarketKey]:
        """
        获取密钥列表
        
        Args:
            db: 数据库会话
            skip: 分页起始位置
            limit: 每页数量
            
        Returns:
            List[MarketKey]: 密钥列表
        """
        return db.query(MarketKey).offset(skip).limit(limit).all()
    
    async def create_key(self, db: Session, data: KeyCreate) -> MarketKey:
        """
        创建密钥
        
        Args:
            db: 数据库会话
            data: 密钥创建参数
            
        Returns:
            MarketKey: 创建的密钥信息
        """
        try:
            # 调用云服务创建密钥
            result, error = await self.cloud_client._make_request(
                "POST",
                "/api/v1/keys",
                db,
                params={
                    "name": data.name,
                    "phone": data.phone,
                    "email": data.email
                }
            )
            
            if error:
                raise HTTPException(status_code=400, detail=error)
            
            # 保存到数据库
            try:
                key = MarketKey(
                    cloud_id=result["id"],
                    key=result["key"],
                    name=data.name,
                    phone=data.phone,
                    email=data.email,
                    status=True
                )
                db.add(key)
                db.commit()
                db.refresh(key)
                return key
                
            except Exception as e:
                logger.error(f"数据库操作失败: {str(e)}")
                db.rollback()
                raise HTTPException(status_code=500, detail="数据库操作失败")
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"创建密钥失败: {str(e)}")
            raise HTTPException(status_code=500, detail="创建密钥失败")
    
    async def delete_key(self, db: Session, key_id: int) -> bool:
        """
        删除密钥
        
        Args:
            db: 数据库会话
            key_id: 密钥ID
            
        Returns:
            bool: 是否删除成功
        """
        try:
            # 获取密钥
            key = await self.get_key(db, key_id)
            if not key:
                return False
                
            # 调用云服务删除密钥
            result, error = await self.cloud_client._make_request(
                "DELETE",
                "/api/v1/keys",
                db,
                params={"key_id": key.cloud_id}
            )
            
            if error:
                raise HTTPException(status_code=400, detail=error)
            
            # 从数据库删除
            db.delete(key)
            db.commit()
            return True
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"删除密钥失败: {str(e)}")
            db.rollback()
            raise HTTPException(status_code=500, detail="删除密钥失败")