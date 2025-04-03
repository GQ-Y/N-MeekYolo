"""
分析服务
"""
import httpx
import uuid
from typing import List, Optional, Dict, Any
from core.config import settings
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
        callback_url: Optional[str] = None,
        enable_callback: bool = True,
        save_result: bool = False,
        config: Optional[Dict[str, Any]] = None,
        analysis_task_id: Optional[str] = None,
        analysis_type: str = "detection"
    ) -> str:
        """流分析
        
        Args:
            model_code: 模型代码
            stream_url: 流URL
            task_name: 任务名称
            callback_urls: 回调地址，多个用逗号分隔
            callback_url: 单独的回调URL，优先级高于callback_urls
            enable_callback: 是否启用用户回调
            save_result: 是否保存结果
            config: 分析配置
            analysis_task_id: 分析任务ID，如果不提供将自动生成
            analysis_type: 分析类型，可选值：detection, segmentation, tracking, counting
            
        Returns:
            task_id: 任务ID
        """
        # 构建系统回调URL
        system_callback_url = callback_url
        if not system_callback_url:
            # 使用配置中的API服务URL创建系统回调
            api_host = settings.SERVICE.host
            api_port = settings.SERVICE.port
            system_callback_url = f"http://{api_host}:{api_port}/api/v1/callback"
            logger.info(f"使用系统回调URL: {system_callback_url}")
            
        # 如果有单独的回调URL，添加到回调列表
        combined_callback_urls = callback_urls or ""
        if callback_url and callback_url not in combined_callback_urls:
            if combined_callback_urls:
                combined_callback_urls = f"{combined_callback_urls},{callback_url}"
            else:
                combined_callback_urls = callback_url
        
        # 构建请求参数
        request_data = {
            "model_code": model_code,
            "stream_url": stream_url,
            "task_name": task_name,
            "callback_urls": combined_callback_urls,
            "callback_url": system_callback_url,  # 传递系统回调URL
            "enable_callback": enable_callback,
            "save_result": save_result,
            "config": config or {},
            "analysis_type": analysis_type,
            "task_id": analysis_task_id  # 传递任务ID
        }
        
        logger.info(f"准备向分析服务发送请求: URL={self._get_api_url('/analyze/stream')}")
        logger.info(f"请求参数: task_id={analysis_task_id}, model_code={model_code}, stream_url={stream_url}")
        logger.info(f"回调配置: system_callback={system_callback_url}, user_callbacks={combined_callback_urls}, enable_callback={enable_callback}")
                
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self._get_api_url("/analyze/stream"),
                    json=request_data
                )
                
                status_code = response.status_code
                logger.info(f"分析服务响应状态码: {status_code}")
                
                if status_code != 200:
                    logger.error(f"分析服务响应错误: {response.text}")
                    response.raise_for_status()
                
                data = response.json()
                logger.info(f"分析服务响应数据: {data}")
                
                task_id = data.get("data", {}).get("task_id")
                logger.info(f"获取到分析任务ID: {task_id}")
                
                return task_id
                
        except Exception as e:
            logger.error(f"向分析服务发送请求失败: {str(e)}", exc_info=True)
            raise
    
    async def stop_task(self, task_id: str):
        """停止分析任务"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._get_api_url(f"/task/stop"),
                json={"task_id": task_id}
            )
            response.raise_for_status() 