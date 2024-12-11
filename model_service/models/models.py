"""
模型相关的数据模型
"""
from typing import List
from pydantic import BaseModel

class ModelInfo(BaseModel):
    """模型信息"""
    name: str
    code: str
    version: str = "1.0.0"
    author: str = ""
    description: str = ""

class ModelList(BaseModel):
    """模型列表"""
    total: int
    items: List[ModelInfo]
    page: int = 1
    size: int = 10