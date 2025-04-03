"""
云服务客户端
"""
import aiohttp
from typing import Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from core.config import settings
from services.base import get_api_key, invalidate_key
from shared.utils.logger import setup_logger
import os

logger = setup_logger(__name__)

class CloudClient:
    """云服务客户端"""
    
    def __init__(self):
        self.base_url = settings.CLOUD.url
        self.api_prefix = settings.CLOUD.api_prefix
    
    def _get_api_url(self, path: str) -> str:
        """获取完整的API URL"""
        # 确保path以/开头
        if not path.startswith("/"):
            path = "/" + path
        # 如果path已经包含api_prefix，则不再添加
        if path.startswith(self.api_prefix):
            return f"{self.base_url}{path}"
        return f"{self.base_url}{self.api_prefix}{path}"
    
    async def _make_request(
        self, 
        method: str, 
        path: str, 
        db: Session,
        params: Optional[Dict] = None,
        json: Optional[Dict] = None,
        **kwargs
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """
        统一的API请求处理
        
        Args:
            method: 请求方法
            path: API路径
            db: 数据库会话
            params: URL参数
            json: 请求体
            **kwargs: 其他参数
            
        Returns:
            Tuple[Optional[Dict], Optional[str]]: (响应数据, 错误信息)
        """
        # 获取API密钥
        api_key, error = await get_api_key(db)
        if error:
            return None, error
            
        url = self._get_api_url(path)
        headers = {"x-api-key": api_key}
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))
            
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method, 
                    url, 
                    headers=headers,
                    params=params,
                    json=json,
                    **kwargs
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result, None
                    elif response.status == 401:
                        # 标记密钥为无效
                        await invalidate_key(db, api_key)
                        return None, "API密钥无效或未授权"
                    elif response.status == 404:
                        return None, "请求的资源不存在"
                    elif response.status == 422:
                        error_data = await response.json()
                        return None, f"参数验证错误: {error_data.get('detail', '未知错误')}"
                    else:
                        error_text = await response.text()
                        logger.error(f"API调用失败: {error_text}")
                        return None, f"API调用失败: {response.status}"
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络请求失败: {str(e)}")
            return None, f"网络请求失败: {str(e)}"
        except Exception as e:
            logger.error(f"请求处理失败: {str(e)}")
            return None, f"请求处理失败: {str(e)}"

    async def sync_model(self, db: Session, model_code: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        同步模型
        
        Args:
            db: 数据库会话
            model_code: 模型代码
            
        Returns:
            Tuple[Optional[Dict], Optional[str]]: (同步结果, 错误信息)
        """
        if not model_code:
            return None, "模型代码不能为空"
            
        return await self._make_request(
            "POST",
            "/api/v1/models/sync",
            db,
            params={"code": model_code}
        )
    
    async def get_model_info(self, db: Session, model_code: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        获取模型信息
        
        Args:
            db: 数据库会话
            model_code: 模型代码
            
        Returns:
            Tuple[Optional[Dict], Optional[str]]: (模型信息, 错误信息)
        """
        if not model_code:
            return None, "模型代码不能为空"
            
        return await self._make_request(
            "GET",
            "/api/v1/models/detail",
            db,
            params={"code": model_code}
        )
    
    async def get_available_models(
        self, 
        db: Session, 
        skip: int = 0, 
        limit: int = 100
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """
        获取可用模型列表
        
        Args:
            db: 数据库会话
            skip: 分页起始位置，必须大于等于0
            limit: 每页数量，必须大于0且小于等于1000
            
        Returns:
            Tuple[Optional[Dict], Optional[str]]: (模型列表, 错误信息)
        """
        # 验证参数
        if skip < 0:
            return None, "分页起始位置必须大于等于0"
        if limit <= 0 or limit > 1000:
            return None, "每页数量必须大于0且小于等于1000"
            
        return await self._make_request(
            "GET",
            "/api/v1/models/available",
            db,
            params={"skip": skip, "limit": limit}
        )
        
    async def download_model(self, db: Session, model_code: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        下载模型
        
        Args:
            db: 数据库会话
            model_code: 模型代码
            
        Returns:
            Tuple[Optional[Dict], Optional[str]]: (下载信息, 错误信息)
        """
        if not model_code:
            return None, "模型代码不能为空"
            
        return await self._make_request(
            "GET",
            "/api/v1/models/download",
            db,
            params={"code": model_code}
        )