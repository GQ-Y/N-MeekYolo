"""
分析服务
"""
import httpx
import uuid
from typing import List, Optional, Dict, Any
from api_service.core.config import settings
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class AnalysisService:
    """分析服务"""
    
    def __init__(self):
        self.base_url = settings.ANALYSIS_SERVICE.url
    
    def _get_api_url(self, path: str) -> str:
        """获取完整的API URL"""
        return f"{self.base_url}/api/v1{path}"
    
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
        task_name: Optional[str] = None,
        callback_urls: Optional[str] = None,
        enable_callback: bool = True,
        save_result: bool = False,
        config: Optional[Dict[str, Any]] = None,
        analysis_type: str = "detection"
    ) -> str:
        """流分析
        
        Args:
            model_code: 模型代码
            stream_url: 流URL
            task_name: 任务名称
            callback_urls: 回调地址，多个用逗号分隔
            enable_callback: 是否启用回调
            save_result: 是否保存结果
            config: 分析配置
            analysis_type: 分析类型，可选值：detection, segmentation, tracking, cross_camera
            
        Returns:
            task_id: 任务ID
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._get_api_url("/analyze/stream"),
                json={
                    "model_code": model_code,
                    "stream_url": stream_url,
                    "task_name": task_name,
                    "callback_urls": callback_urls,
                    "enable_callback": enable_callback,
                    "save_result": save_result,
                    "config": config or {},
                    "analysis_type": analysis_type
                }
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", {}).get("task_id")
    
    async def stop_task(self, task_id: str):
        """停止分析任务"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._get_api_url(f"/task/stop"),
                json={"task_id": task_id}
            )
            response.raise_for_status() 