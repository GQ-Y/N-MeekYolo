"""
测试模型同步
"""
import os
import sys
import asyncio
from pathlib import Path

# 添加项目根目录到 Python 路径
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
sys.path.append(str(project_root))

import logging
from sqlalchemy.orm import Session
from services.model import ModelService
from services.database import SessionLocal
from models.database import Model

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def sync_models():
    """测试模型同步功能"""
    db = SessionLocal()
    try:
        model_service = ModelService()
        logger.info("开始同步模型...")
        
        # 检查服务是否可用
        is_available = await model_service.check_model_service()
        if not is_available:
            logger.error("模型服务不可用，无法同步")
            return
            
        # 同步模型
        models = await model_service.sync_models(db)
        
        logger.info(f"同步完成，共同步了 {len(models)} 个模型")
        
        # 打印同步的模型信息
        for model in models:
            logger.info(f"模型: {model.code}")
            logger.info(f"  名称: {model.name}")
            logger.info(f"  版本: {model.version}")
            logger.info(f"  作者: {model.author}")
            logger.info(f"  描述: {model.description}")
            logger.info(f"  类别数: {model.nc}")
            logger.info(f"  类别: {model.names}")
            logger.info("-----------------------------")
        
    except Exception as e:
        logger.error(f"同步失败: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(sync_models()) 