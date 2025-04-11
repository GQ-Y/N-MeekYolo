"""
分析回调路由模块

提供接收分析服务回调的接口，用于处理分析结果数据。
当分析服务产生分析结果时，会通过该接口回调给API服务。
"""
from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
import uuid
import time
import json
from models.responses import BaseResponse
from services.core.database import get_db
from shared.utils.logger import setup_logger
from models.database import SubTask

logger = setup_logger(__name__)

# 创建路由器 - 这里不使用前缀，直接使用完整路径
router = APIRouter(tags=["回调"])

@router.post("/api/v1/callback", response_model=BaseResponse, summary="分析服务回调")
async def analysis_callback(
    request: Request,
    db: Session = Depends(get_db)
) -> BaseResponse:
    """
    接收分析服务的回调数据
    
    该接口会接收分析服务发送的分析结果，并将其打印到日志中。
    
    返回:
    - 标准响应对象，表示回调处理状态
    """
    try:
        # 获取请求数据
        callback_data = await request.json()
        logger.info(f"收到分析服务回调数据: {json.dumps(callback_data, ensure_ascii=False)}")
        
        # 提取任务ID
        analysis_task_id = callback_data.get("data_id") or callback_data.get("task_id") or callback_data.get("dataID")
        if analysis_task_id:
            logger.info(f"分析任务ID: {analysis_task_id}")
            
            # 查询与此分析任务ID相关的子任务
            subtask = db.query(SubTask).filter(SubTask.analysis_task_id == analysis_task_id).first()
            if subtask:
                logger.info(f"处理回调: 任务ID={subtask.task_id}, 子任务ID={subtask.id}, 节点ID={subtask.node_id}")
            else:
                logger.warning(f"未找到与分析任务ID {analysis_task_id} 关联的子任务")
        
        # 提取结果数据
        if "result_data" in callback_data:
            result_data = callback_data["result_data"]
            detections = result_data.get("detections", [])
            logger.info(f"检测到 {len(detections)} 个目标")
            
            # 打印每个检测结果的简要信息
            for i, detection in enumerate(detections):
                class_name = detection.get("class_name", "未知类别")
                confidence = detection.get("confidence", 0)
                logger.info(f"目标 {i+1}: 类别={class_name}, 置信度={confidence:.2f}")
        
        return BaseResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=True,
            message="回调处理成功",
            code=200,
            data={
                "received": True,
                "task_id": analysis_task_id if analysis_task_id else None
            },
            timestamp=int(time.time() * 1000)
        )
        
    except Exception as e:
        logger.error(f"处理回调失败: {str(e)}", exc_info=True)
        return BaseResponse(
            requestId=str(uuid.uuid4()),
            path=str(request.url.path),
            success=False,
            message=f"处理回调失败: {str(e)}",
            code=500,
            timestamp=int(time.time() * 1000)
        ) 