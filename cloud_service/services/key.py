"""
API密钥服务
"""
import secrets
from typing import List, Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session
from models.database import ApiKey
from models.schemas import ApiKeyCreate, ApiKeyUpdate
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class KeyService:
    """API密钥服务"""
    
    async def create_key(
        self,
        db: Session,
        data: ApiKeyCreate
    ) -> ApiKey:
        """创建API密钥"""
        try:
            # 生成密钥
            key = secrets.token_urlsafe(32)
            
            # 创建记录
            api_key = ApiKey(
                key=key,
                name=data.name,
                phone=data.phone,
                email=data.email
            )
            db.add(api_key)
            db.commit()
            db.refresh(api_key)
            
            return api_key
        except Exception as e:
            logger.error(f"Create API key failed: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def get_key(self, db: Session, key_id: int) -> Optional[ApiKey]:
        """获取API密钥"""
        return db.query(ApiKey).filter(ApiKey.id == key_id).first()
    
    async def get_key_by_value(self, db: Session, key: str) -> Optional[ApiKey]:
        """通过密钥值获取API密钥"""
        return db.query(ApiKey).filter(
            ApiKey.key == key,
            ApiKey.status == True
        ).first()
    
    async def update_key(
        self,
        db: Session,
        key_id: int,
        data: ApiKeyUpdate
    ) -> Optional[ApiKey]:
        """更新API密钥"""
        try:
            key = await self.get_key(db, key_id)
            if not key:
                return None
            
            # 更新字段
            for field, value in data.dict(exclude_unset=True).items():
                setattr(key, field, value)
            
            db.commit()
            db.refresh(key)
            return key
        except Exception as e:
            logger.error(f"Update API key failed: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def delete_key(self, db: Session, key_id: int) -> bool:
        """删除API密钥"""
        try:
            key = await self.get_key(db, key_id)
            if not key:
                return False
            
            db.delete(key)
            db.commit()
            return True
        except Exception as e:
            logger.error(f"Delete API key failed: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e)) 