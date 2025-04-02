"""
任务 CRUD 操作
"""
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
from api_service.models.database import Task, Stream, Model, Callback, Node
from api_service.crud.node import NodeCRUD

logger = logging.getLogger(__name__)

def create_task(
    db: Session,
    name: str,
    stream_ids: List[int],
    model_ids: List[int],
    callback_ids: List[int] = None,
    callback_interval: int = 1,
    enable_callback: bool = True,
    save_result: bool = False,
    config: Optional[Dict[str, Any]] = None,
    node_id: Optional[int] = None
) -> Task:
    """创建任务"""
    # 获取关联对象
    streams = db.query(Stream).filter(Stream.id.in_(stream_ids)).all()
    models = db.query(Model).filter(Model.id.in_(model_ids)).all()
    callbacks = []
    if callback_ids:
        callbacks = db.query(Callback).filter(Callback.id.in_(callback_ids)).all()
    
    # 节点负载均衡逻辑
    selected_node_id = node_id
    if not selected_node_id:
        # 如果没有指定节点，使用负载均衡算法选择节点
        available_node = NodeCRUD.get_available_node(db)
        if available_node:
            selected_node_id = available_node.id
            logger.info(f"通过负载均衡选择节点: {available_node.ip}:{available_node.port}, ID: {available_node.id}")
        else:
            logger.warning("未找到可用节点，任务将在没有节点关联的情况下创建")
    
    # 创建任务
    task = Task(
        name=name,
        callback_interval=callback_interval,
        enable_callback=enable_callback,
        save_result=save_result,
        config=config or {},
        node_id=selected_node_id,
        streams=streams,
        models=models,
        callbacks=callbacks
    )
    
    db.add(task)
    db.commit()
    db.refresh(task)
    
    # 如果分配了节点，更新节点的任务计数
    if selected_node_id:
        node = db.query(Node).filter(Node.id == selected_node_id).first()
        if node:
            node.stream_task_count += len(streams)
            db.commit()
            logger.info(f"更新节点 {selected_node_id} 的任务计数: {node.stream_task_count}")
    
    return task

def get_task(db: Session, task_id: int) -> Optional[Task]:
    """获取任务详情"""
    return db.query(Task)\
        .options(
            joinedload(Task.streams),
            joinedload(Task.models),
            joinedload(Task.callbacks),
            joinedload(Task.node)
        )\
        .filter(Task.id == task_id)\
        .first()

def get_tasks(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None
) -> List[Task]:
    """获取任务列表"""
    query = db.query(Task)\
        .options(
            joinedload(Task.streams),
            joinedload(Task.models),
            joinedload(Task.callbacks)
        )
    
    if status:
        query = query.filter(Task.status == status)
    
    return query.offset(skip).limit(limit).all()

def update_task_status(
    db: Session,
    task_id: int,
    status: str,
    error_message: Optional[str] = None
) -> Optional[Task]:
    """更新任务状态"""
    task = db.query(Task)\
        .options(
            joinedload(Task.streams),
            joinedload(Task.models),
            joinedload(Task.callbacks)
        )\
        .filter(Task.id == task_id)\
        .first()
        
    if task:
        task.status = status
        if error_message is not None:
            task.error_message = error_message
            
        # 更新相关时间戳
        if status == "running":
            task.started_at = datetime.now()
        elif status in ["completed", "failed", "stopped"]:
            task.completed_at = datetime.now()
            
        db.commit()
        db.refresh(task)
        
    return task

def update_task(
    db: Session,
    task_id: int,
    name: str = None,
    stream_ids: List[int] = None,
    model_ids: List[int] = None,
    callback_ids: List[int] = None,
    callback_interval: int = None,
    enable_callback: bool = None,
    save_result: bool = None,
    config: Dict[str, Any] = None,
    node_id: int = None
) -> Optional[Task]:
    """更新任务"""
    # 使用 joinedload 获取任务及其关联数据
    task = db.query(Task)\
        .options(
            joinedload(Task.streams),
            joinedload(Task.models),
            joinedload(Task.callbacks),
            joinedload(Task.node)
        )\
        .filter(Task.id == task_id)\
        .first()
        
    if task:
        # 保存旧节点ID和流数量，用于更新任务计数
        old_node_id = task.node_id
        old_stream_count = len(task.streams) if task.streams else 0
        
        if name:
            task.name = name
        if callback_interval is not None:
            task.callback_interval = callback_interval
        if enable_callback is not None:
            task.enable_callback = enable_callback
        if save_result is not None:
            task.save_result = save_result
        if config is not None:
            task.config = config
        
        # 更新节点ID
        if node_id is not None and node_id != old_node_id:
            # 如果指定了新节点，直接使用
            task.node_id = node_id
        
        try:
            # 更新视频源关联
            if stream_ids is not None:
                streams = db.query(Stream).filter(Stream.id.in_(stream_ids)).all()
                task.streams = streams
                
            # 更新模型关联
            if model_ids is not None:
                models = db.query(Model).filter(Model.id.in_(model_ids)).all()
                task.models = models
                
            # 更新回调服务关联
            if callback_ids is not None:
                callbacks = db.query(Callback).filter(Callback.id.in_(callback_ids)).all()
                task.callbacks = callbacks
                
            db.commit()
            db.refresh(task)
            
            # 更新节点任务计数
            new_stream_count = len(task.streams) if task.streams else 0
            
            # 如果节点发生变化或流数量变化，更新节点任务计数
            if old_node_id:
                old_node = db.query(Node).filter(Node.id == old_node_id).first()
                if old_node:
                    # 减少旧节点的任务计数
                    old_node.stream_task_count = max(0, old_node.stream_task_count - old_stream_count)
                    db.commit()
                    logger.info(f"更新旧节点 {old_node_id} 的任务计数: {old_node.stream_task_count}")
            
            if task.node_id and task.node_id != old_node_id:
                # 增加新节点的任务计数
                new_node = db.query(Node).filter(Node.id == task.node_id).first()
                if new_node:
                    new_node.stream_task_count += new_stream_count
                    db.commit()
                    logger.info(f"更新新节点 {task.node_id} 的任务计数: {new_node.stream_task_count}")
            elif task.node_id and old_stream_count != new_stream_count:
                # 如果节点没变但流数量变了，更新节点任务计数
                node = db.query(Node).filter(Node.id == task.node_id).first()
                if node:
                    node.stream_task_count = node.stream_task_count - old_stream_count + new_stream_count
                    db.commit()
                    logger.info(f"更新节点 {task.node_id} 的任务计数: {node.stream_task_count}")
            
            return task
            
        except Exception as e:
            db.rollback()
            logger.error(f"更新任务关系失败: {str(e)}")
            raise
            
    return None

def delete_task(db: Session, task_id: int) -> bool:
    """删除任务"""
    task = get_task(db, task_id)
    if task:
        # 更新节点任务计数
        if task.node_id:
            node = db.query(Node).filter(Node.id == task.node_id).first()
            if node:
                stream_count = len(task.streams) if task.streams else 0
                node.stream_task_count = max(0, node.stream_task_count - stream_count)
                logger.info(f"更新节点 {task.node_id} 的任务计数: {node.stream_task_count}")
        
        db.delete(task)
        db.commit()
        return True
    return False 