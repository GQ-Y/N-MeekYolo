"""
子任务 CRUD 操作
"""
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
import logging
from models.database import SubTask
from datetime import datetime

logger = logging.getLogger(__name__)

class SubTaskCRUD:
    """
    SubTaskCRUD 类，作为适配器包装子任务相关函数
    用于兼容导入 SubTaskCRUD 的代码
    """
    
    @staticmethod
    def create_subtask(
        db: Session, 
        task_id: int, 
        model_id: int = None,
        stream_id: int = None,
        config: Dict[str, Any] = None,
        status: int = 0,
        analysis_task_id: str = None,
        mqtt_node_id: int = None,
        enable_callback: bool = False,
        callback_url: str = None,
        roi_type: int = 0,
        analysis_type: str = "detection",
        name: str = None
    ) -> SubTask:
        """
        创建子任务
        
        Args:
            db: 数据库会话
            task_id: 主任务ID
            model_id: 模型ID
            stream_id: 流ID
            config: 配置信息
            status: 状态(0:未启动,1:运行中,2:已停止,3:失败)
            analysis_task_id: 分析任务ID
            mqtt_node_id: MQTT节点ID
            enable_callback: 是否启用回调
            callback_url: 回调URL
            roi_type: ROI类型
            analysis_type: 分析类型
            name: 子任务名称
            
        Returns:
            SubTask: 创建的子任务对象
        """
        try:
            # 查询主任务名称
            from models.database import Task
            task = db.query(Task).filter(Task.id == task_id).first()
            task_name = task.name if task else None
            
            # 查询模型名称
            from models.database import Model
            model = db.query(Model).filter(Model.id == model_id).first()
            model_name = model.name if model else None
            
            # 查询流名称
            stream_name = None
            if stream_id:
                from models.database import Stream
                stream = db.query(Stream).filter(Stream.id == stream_id).first()
                stream_name = stream.name if stream else None
            
            # 如果未提供名称，则自动生成
            if not name:
                # 优先使用流名称+模型名称
                if stream_name and model_name:
                    name = f"{stream_name}-{model_name}"
                # 其次使用主任务名称+模型名称
                elif task_name and model_name:
                    name = f"{task_name}-{model_name}"
                # 最后使用默认前缀+任务ID
                else:
                    name = f"子任务-{task_id}-{model_id}"
            
            subtask = SubTask(
                task_id=task_id,
                model_id=model_id,
                stream_id=stream_id,
                status=status,
                config=config or {},
                analysis_task_id=analysis_task_id,
                mqtt_node_id=mqtt_node_id,
                enable_callback=enable_callback,
                callback_url=callback_url,
                roi_type=roi_type,
                analysis_type=analysis_type,
                name=name  # 添加名称字段
            )
            
            # 如果是运行中状态，设置开始时间
            if status == 1:
                subtask.started_at = datetime.now()
                
            db.add(subtask)
            db.commit()
            db.refresh(subtask)
            
            logger.info(f"创建子任务成功: ID={subtask.id}, task_id={task_id}, name={name}")
            return subtask
            
        except Exception as e:
            db.rollback()
            logger.error(f"创建子任务失败: {str(e)}")
            raise 