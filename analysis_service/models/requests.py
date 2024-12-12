from typing import List, Optional, Union
from pydantic import BaseModel, Field

class StreamAnalysisRequest(BaseModel):
    """流分析请求"""
    model_code: str = Field(
        ...,
        description="模型代码，例如：model-gcc",
        example="model-gcc"
    )
    stream_url: str = Field(
        ...,
        description="流地址，支持RTSP/HTTP等协议",
        example="rtsp://223.85.203.115:554/rtp/34020000001110000072_34020000001320000003"
    )
    callback_urls: Optional[str] = Field(
        None,
        description="回调地址",
        example="http://127.0.0.1:8081"
    )
    output_url: Optional[str] = Field(
        None,
        description="输出视频保存地址，可选",
        example="output/video.mp4"
    )
    callback_interval: int = Field(
        1,
        description="回调间隔(秒)，默认1秒",
        ge=1,
        example=1
    )

    class Config:
        schema_extra = {
            "example": {
                "model_code": "model-gcc",
                "stream_url": "rtsp://223.85.203.115:554/rtp/34020000001110000072_34020000001320000003",
                "callback_urls": "http://127.0.0.1:8081",
                "output_url": "output/video.mp4",
                "callback_interval": 1
            }
        }

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "model_code": "model-gcc",
                    "stream_url": "rtsp://223.85.203.115:554/stream",
                    "callback_urls": "http://127.0.0.1:8081",
                    "output_url": "output/video.mp4",
                    "callback_interval": 1
                }
            ]
        }
    }