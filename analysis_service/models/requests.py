from typing import List, Optional, Tuple
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
    """流分析请求
    
    参数:
        tasks: 任务列表
        callback_urls: 回调地址,多个用逗号分隔
        analyze_interval: 分析间隔(秒)
        alarm_interval: 报警间隔(秒)
        random_interval: 随机间隔范围(秒)
        confidence_threshold: 目标置信度阈值
        push_interval: 推送间隔(秒)
    """
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
    analyze_interval: Optional[int] = Field(
        None,
        description="分析间隔(秒)",
        ge=1,
        example=1
    )
    alarm_interval: Optional[int] = Field(
        None,
        description="报警间隔(秒)", 
        ge=1,
        example=60
    )
    random_interval: Optional[Tuple[int, int]] = Field(
        None,
        description="随机间隔范围(秒)",
        example=[1, 10]
    )
    confidence_threshold: Optional[float] = Field(
        None,
        description="目标置信度阈值",
        gt=0,
        lt=1,
        example=0.8
    )
    push_interval: Optional[int] = Field(
        None,
        description="推送间隔(秒)",
        ge=1,
        example=5
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "tasks": [
                        {
                            "model_code": "model-gcc",
                            "stream_url": "rtsp://example.com/stream1"
                        },
                        {
                            "model_code": "model-gcc", 
                            "stream_url": "rtsp://example.com/stream2"
                        }
                    ],
                    "callback_urls": "http://127.0.0.1:8081,http://192.168.1.1:8081",
                    "analyze_interval": 1,
                    "alarm_interval": 60,
                    "random_interval": [1, 10],
                    "confidence_threshold": 0.8,
                    "push_interval": 5
                }
            ]
        }
    }