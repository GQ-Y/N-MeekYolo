"""
请求数据模型
"""
from typing import Dict, Optional
from pydantic import BaseModel
from datetime import datetime

class ModelUploadRequest(BaseModel):
    """模型上传请求"""
    code: str                # 模型编码
    version: str            # 模型版本
    name: str              # 模型名称
    description: str       # 模型描述
    author: str           # 作者
    nc: int              # 类别数
    names: Dict[int, str]  # 类别名称映射 