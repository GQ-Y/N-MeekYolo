from pydantic import BaseModel
from typing import Optional

class StreamAnalysisRequest(BaseModel):
    """流分析请求"""
    model_code: str
    stream_url: str
    callback_url: Optional[str] = None
    callback_interval: Optional[int] = 1 