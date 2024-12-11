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
        self.analysis_url = f"http://{settings.SERVICES.analysis.host}:{settings.SERVICES.analysis.port}"
    
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
                f"{self.analysis_url}/image",
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
                f"{self.analysis_url}/video",
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
        task_id = str(uuid.uuid4())
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.analysis_url}/stream",
                json={
                    "task_id": task_id,
                    "model_code": model_code,
                    "stream_url": stream_url,
                    "callback_url": callback_url,
                    "output_url": output_url,
                    "callback_interval": callback_interval
                }
            )
            response.raise_for_status()
        return task_id
    
    async def stop_task(self, task_id: str):
        """停止分析任务"""
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.analysis_url}/tasks/{task_id}"
            )
            response.raise_for_status() 