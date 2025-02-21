"""
分析服务
"""
import httpx
import uuid
from typing import List, Optional
from api_service.core.config import settings
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class AnalysisService:
    """分析服务"""
    
    def __init__(self):
        self.base_url = settings.ANALYSIS_SERVICE.url
        self.api_prefix = settings.ANALYSIS_SERVICE.api_prefix
    
    def _get_api_url(self, path: str) -> str:
        """获取完整的API URL"""
        return f"{self.base_url}{self.api_prefix}{path}"
    
    async def analyze_image(
        self,
        model_code: str,
        image_urls: List[str],
        callback_url: Optional[str] = None,
        is_base64: bool = False
    ) -> str:
        """图片分析"""
        task_id = str(uuid.uuid4())
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._get_api_url("/analyze/image"),
                json={
                    "task_id": task_id,
                    "model_code": model_code,
                    "image_urls": image_urls,
                    "callback_url": callback_url,
                    "is_base64": is_base64
                }
            )
            response.raise_for_status()
        return task_id
    
    async def analyze_video(
        self,
        model_code: str,
        video_url: str,
        callback_url: Optional[str] = None
    ) -> str:
        """视频分析"""
        task_id = str(uuid.uuid4())
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._get_api_url("/analyze/video"),
                json={
                    "task_id": task_id,
                    "model_code": model_code,
                    "video_url": video_url,
                    "callback_url": callback_url
                }
            )
            response.raise_for_status()
        return task_id
    
    async def analyze_stream(
        self,
        model_code: str,
        stream_url: str,
        callback_url: Optional[str] = None,
        output_url: Optional[str] = None,
        callback_interval: int = 1
    ) -> str:
        """流分析"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._get_api_url("/analyze/stream"),
                json={
                    "model_code": model_code,
                    "stream_url": stream_url,
                    "callback_url": callback_url,
                    "output_url": output_url,
                    "callback_interval": callback_interval
                }
            )
            response.raise_for_status()
            data = response.json()
            return data.get("task_id")
    
    async def stop_task(self, task_id: str):
        """停止分析任务"""
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                self._get_api_url(f"/analyze/stream/{task_id}/stop")
            )
            response.raise_for_status() 