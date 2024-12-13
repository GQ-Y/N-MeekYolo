from typing import List, Optional
from pydantic import BaseModel, Field

class StreamTask(BaseModel):
    """单个流分析任务"""
    model_code: str = Field(
        ...,
        description="模型代码",
        example="model-gcc"
    )
    stream_url: str = Field(
        ..., 
        description="流地址",
        example="rtsp://example.com/stream"
    )
    output_url: Optional[str] = Field(
        None,
        description="输出地址"
    )

class StreamAnalysisRequest(BaseModel):
    """流分析请求"""
    tasks: List[StreamTask] = Field(
        ...,
        description="任务列表",
        min_items=1
    )
    callback_urls: Optional[str] = Field(
        None,
        description="回调地址,多个用逗号分隔",
        example="http://callback1,http://callback2"
    )
    callback_interval: int = Field(
        1,
        description="回调间隔(秒)",
        ge=1
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "callback_interval": 1,
                    "callback_urls": "http://127.0.0.1:8081,http://192.168.1.1:8081",
                    "tasks": [
                        {
                            "model_code": "model-gcc",
                            "stream_url": "rtsp://example.com/stream1"
                        },
                        {
                            "model_code": "model-gcc", 
                            "stream_url": "rtsp://example.com/stream2"
                        }
                    ]
                }
            ]
        }
    }