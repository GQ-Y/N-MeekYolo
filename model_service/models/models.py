"""
模型相关的数据模型
"""
from typing import List, Dict, Union
from pydantic import BaseModel

class ModelInfo(BaseModel):
    """模型信息"""
    name: str
    code: str
    version: str = "1.0.0"
    author: str = ""
    description: str = ""
    nc: int = 0  # 模型支持的检测类别数量
    names: Dict[Union[int, str], str] = {}  # 模型支持的检测类别名称映射，键可以是整数或字符串

class ModelList(BaseModel):
    """模型列表"""
    total: int
    items: List[ModelInfo]
    page: int = 1
    size: int = 10