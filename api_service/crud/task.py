"""
任务 CRUD 操作
"""
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
import logging
from models.database import Task, Stream, Model, Callback, Node, SubTask
from models.requests import TaskCreate, TaskUpdate, TaskStreamConfig, TaskModelConfig
from crud.node import NodeCRUD
from sqlalchemy.sql import text
from core.config import settings

logger = logging.getLogger(__name__)

def create_task(
    db: Session,
    task_data: TaskCreate
) -> Task:
    """创建任务"""
    # 创建任务主记录
    task = Task(
        name=task_data.name,
        save_result=task_data.save_result,
        status="created",
        total_subtasks=sum(len(stream_config.models) for stream_config in task_data.tasks)
    )
    
    db.add(task)
    db.flush()  # 获取任务ID
    
    created_subtasks = []
    
    # 为每个流和模型创建子任务
    for stream_config in task_data.tasks:
        # 获取流
        stream = db.query(Stream).filter(Stream.id == stream_config.stream_id).first()
        if not stream:
            logger.warning(f"视频流 {stream_config.stream_id} 不存在")
            continue
            
        # 添加关联
        task.streams.append(stream)
            
        # 处理每个模型配置
        for model_config in stream_config.models:
            # 获取模型
            model = db.query(Model).filter(Model.id == model_config.model_id).first()
            if not model:
                logger.warning(f"模型 {model_config.model_id} 不存在")
                continue
                
            # 添加关联
            if model not in task.models:
                task.models.append(model)
                
            # 提取回调配置
            enable_callback = False
            callback_url = None
            if model_config.config and "callback" in model_config.config:
                callback_conf = model_config.config["callback"]
                enable_callback = callback_conf.get("enabled", False)
                callback_url = callback_conf.get("url")
                
            # 确定ROI类型
            roi_type = 0
            if model_config.config:
                roi_type = model_config.config.get("roi_type", 0)
                
            # 确定分析类型
            analysis_type = "detection"
            if model_config.config:
                analysis_type = model_config.config.get("analysis_type", "detection")
                
            # 创建子任务
            subtask = SubTask(
                task_id=task.id,
                stream_id=stream.id,
                model_id=model.id,
                status="created",
                config=model_config.config,
                enable_callback=enable_callback,
                callback_url=callback_url,
                roi_type=roi_type,
                analysis_type=analysis_type
            )
            
            db.add(subtask)
            created_subtasks.append(subtask)
    
    db.commit()
    db.refresh(task)
    
    return task

def get_task(
    db: Session,
    task_id: int,
    include_subtasks: bool = True
) -> Optional[Task]:
    """获取任务详情"""
    query = db.query(Task)
    
    if include_subtasks:
        query = query.options(
            joinedload(Task.sub_tasks),
            joinedload(Task.streams),
            joinedload(Task.models)
        )
        
    return query.filter(Task.id == task_id).first()

def get_tasks(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    include_subtasks: bool = False
) -> List[Task]:
    """获取任务列表"""
    query = db.query(Task)
    
    if status:
        query = query.filter(Task.status == status)
        
    if include_subtasks:
        query = query.options(
            joinedload(Task.sub_tasks),
            joinedload(Task.streams),
            joinedload(Task.models)
        )
        
    return query.order_by(Task.created_at.desc()).offset(skip).limit(limit).all()

def update_task(
    db: Session,
    task_id: int,
    task_data: TaskUpdate
) -> Optional[Task]:
    """更新任务基本信息"""
    task = get_task(db, task_id, include_subtasks=False)
    if not task:
        return None
    
    # 仅允许在创建状态下更新任务
    if task.status != "created":
        return task
    
    if task_data.name:
        task.name = task_data.name
        
    if task_data.save_result is not None:
        task.save_result = task_data.save_result
    
    db.commit()
    db.refresh(task)
    
    return task

def delete_task(
    db: Session,
    task_id: int
) -> bool:
    """删除任务"""
    task = get_task(db, task_id, include_subtasks=False)
    if not task:
        return False
    
    # 只能删除非运行中的任务
    if task.status == "running":
        return False
    
    db.delete(task)
    db.commit()
    
    return True

async def start_task(
    db: Session,
    task_id: int
) -> Tuple[bool, str]:
    """启动任务"""
    logger.info(f"开始启动任务 {task_id}")
    
    # 使用 joinedload 获取任务及其关联数据
    task = db.query(Task)\
        .options(
            joinedload(Task.sub_tasks),
            joinedload(Task.streams),
            joinedload(Task.models)
        )\
        .filter(Task.id == task_id)\
        .first()
    
    if not task:
        logger.error(f"任务 {task_id} 不存在")
        return False, "任务不存在"
    
    # 检查任务状态
    if task.status != "created" and task.status != "stopped":
        logger.error(f"任务 {task_id} 状态为 {task.status}，无法启动")
        return False, f"任务状态为 {task.status}，无法启动"
    
    # 获取子任务
    subtasks = task.sub_tasks
    if not subtasks:
        logger.error(f"任务 {task_id} 没有子任务，无法启动")
        return False, "任务没有子任务，无法启动"
    
    logger.info(f"任务 {task_id} ({task.name}) 包含 {len(subtasks)} 个子任务")
    
    # 查找可用节点
    available_node = NodeCRUD.get_available_node(db)
    if not available_node:
        # 更新任务状态
        task.status = "no_node"
        task.error_message = "没有可用的分析节点"
        db.commit()
        logger.error(f"任务 {task_id} 启动失败: 没有可用的分析节点")
        return False, "没有可用的分析节点"
        
    logger.info(f"找到可用节点: ID={available_node.id}, IP={available_node.ip}, 端口={available_node.port}")
    
    # 导入分析服务
    from services.analysis import AnalysisService
    analysis_service = AnalysisService()
    
    # 更新任务状态
    task.status = "running"
    task.started_at = datetime.now()
    
    # 构建系统回调URL - API服务接收回调的地址
    system_callback = f"http://{settings.SERVICE.host}:{settings.SERVICE.port}/api/v1/callback"
    logger.info(f"系统回调URL: {system_callback}")
    
    # 逐个启动子任务
    success_count = 0
    
    for subtask in subtasks:
        try:
            # 先检查节点是否可用
            if not available_node or available_node.image_task_count + available_node.video_task_count + available_node.stream_task_count >= available_node.max_tasks:
                # 重新获取可用节点
                available_node = NodeCRUD.get_available_node(db)
                if not available_node:
                    logger.error(f"子任务 {subtask.id} 无可用节点，跳过")
                    continue
            
            # 获取流和模型信息
            stream = db.query(Stream).filter(Stream.id == subtask.stream_id).first()
            model = db.query(Model).filter(Model.id == subtask.model_id).first()
            
            if not stream or not model:
                logger.error(f"子任务 {subtask.id} 关联的流或模型不存在")
                continue
                
            logger.info(f"准备启动子任务 {subtask.id}: 流={stream.name}({stream.url}), 模型={model.name}({model.code})")
            
            # 更新子任务节点
            subtask.node_id = available_node.id
            subtask.status = "running"
            subtask.started_at = datetime.now()
            subtask.error_message = None
            
            # 更新节点任务计数
            available_node.stream_task_count += 1
            
            # 调用分析服务启动实际分析任务
            try:
                # 用户配置的回调URL
                user_callback_url = subtask.callback_url
                
                logger.info(f"调用分析服务启动子任务 {subtask.id}")
                logger.info(f"子任务参数: 模型={model.code}, 流URL={stream.url}, 节点={available_node.ip}:{available_node.port}")
                logger.info(f"子任务配置: {subtask.config}")
                
                analysis_task_id = await analysis_service.analyze_stream(
                    model_code=model.code,
                    stream_url=stream.url,
                    task_name=f"{task.name}-{subtask.id}",
                    callback_url=system_callback, # 系统回调
                    callback_urls=user_callback_url, # 用户配置的回调
                    enable_callback=subtask.enable_callback,
                    save_result=task.save_result,
                    config=subtask.config,
                    analysis_task_id=subtask.analysis_task_id, # 可能的已有任务ID
                    analysis_type=subtask.analysis_type
                )
                
                if not analysis_task_id:
                    logger.error(f"子任务 {subtask.id} 启动失败: 未获取到分析任务ID")
                    subtask.status = "error"
                    subtask.error_message = "启动分析服务失败: 未获取到分析任务ID"
                    available_node.stream_task_count -= 1
                    continue
                
                # 保存分析任务ID
                subtask.analysis_task_id = analysis_task_id
                logger.info(f"子任务 {subtask.id} 启动成功，分析任务ID: {analysis_task_id}")
                success_count += 1
                
            except Exception as e:
                logger.error(f"启动子任务 {subtask.id} 的分析服务失败: {str(e)}")
                subtask.status = "error"
                subtask.error_message = f"启动分析服务失败: {str(e)}"
                # 回滚节点任务计数
                available_node.stream_task_count -= 1
                continue
            
        except Exception as e:
            logger.error(f"处理子任务 {subtask.id} 失败: {str(e)}")
            continue
    
    # 更新任务统计信息
    task.active_subtasks = success_count
    
    db.commit()
    
    if success_count == 0:
        # 如果没有子任务启动成功，更新任务状态
        task.status = "error"
        task.error_message = "没有子任务启动成功"
        db.commit()
        logger.error(f"任务 {task_id} 启动失败: 没有子任务启动成功")
        return False, "没有子任务启动成功"
    
    if success_count < len(subtasks):
        # 如果只有部分子任务启动成功
        task.error_message = f"部分子任务启动成功 ({success_count}/{len(subtasks)})"
        db.commit()
        logger.warn(f"任务 {task_id} 部分启动成功: {success_count}/{len(subtasks)} 个子任务")
        return True, f"部分子任务启动成功 ({success_count}/{len(subtasks)})"
    
    logger.info(f"任务 {task_id} 启动成功: {success_count}/{len(subtasks)} 个子任务")
    return True, "任务启动成功"

async def stop_task(
    db: Session,
    task_id: int
) -> Tuple[bool, str]:
    """停止任务"""
    # 使用 joinedload 获取任务及其关联数据
    task = db.query(Task)\
        .options(
            joinedload(Task.sub_tasks)
        )\
        .filter(Task.id == task_id)\
        .first()
    
    if not task:
        return False, "任务不存在"
    
    # 检查任务状态
    if task.status != "running":
        return False, f"任务状态为 {task.status}，无法停止"
    
    # 导入分析服务
    from services.analysis import AnalysisService
    analysis_service = AnalysisService()
    
    # 更新任务状态
    task.status = "stopped"
    task.active_subtasks = 0
    
    # 逐个停止子任务
    stopped_count = 0
    for subtask in task.sub_tasks:
        if subtask.status == "running":
            try:
                # 更新子任务状态
                subtask.status = "stopped"
                subtask.completed_at = datetime.now()
                
                # 如果有节点，更新节点任务计数
                if subtask.node_id:
                    node = db.query(Node).filter(Node.id == subtask.node_id).first()
                    if node and node.stream_task_count > 0:
                        node.stream_task_count -= 1
                
                # 如果有分析任务ID，调用分析服务停止任务
                if subtask.analysis_task_id:
                    try:
                        await analysis_service.stop_task(subtask.analysis_task_id)
                        logger.info(f"已停止子任务 {subtask.id} 的分析任务 {subtask.analysis_task_id}")
                    except Exception as e:
                        logger.error(f"停止子任务 {subtask.id} 的分析任务失败: {str(e)}")
                        # 虽然停止分析任务可能失败，但我们仍认为子任务已停止
                
                stopped_count += 1
                
            except Exception as e:
                logger.error(f"停止子任务 {subtask.id} 失败: {str(e)}")
                continue
    
    db.commit()
    
    return True, f"成功停止 {stopped_count}/{len(task.sub_tasks)} 个子任务"

def update_subtask_status(
    db: Session,
    subtask_id: int,
    status: str,
    error_message: Optional[str] = None
) -> Tuple[bool, str]:
    """更新子任务状态"""
    subtask = db.query(SubTask).filter(SubTask.id == subtask_id).first()
    if not subtask:
        return False, "子任务不存在"
    
    # 更新子任务状态
    subtask.status = status
    if error_message:
        subtask.error_message = error_message
    
    # 如果是完成或错误状态，设置完成时间
    if status in ["completed", "error"]:
        subtask.completed_at = datetime.now()
        
        # 如果有节点，更新节点任务计数
        if subtask.node_id:
            node = db.query(Node).filter(Node.id == subtask.node_id).first()
            if node and node.stream_task_count > 0:
                node.stream_task_count -= 1
    
    db.commit()
    
    # 更新父任务状态
    return update_task_status_from_subtasks(db, subtask.task_id)

def update_task_status_from_subtasks(
    db: Session,
    task_id: int
) -> Tuple[bool, str]:
    """根据子任务状态更新任务状态"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return False, "任务不存在"
    
    # 获取所有子任务状态
    subtask_stats = db.execute(text("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) as running,
            SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed
        FROM sub_tasks
        WHERE task_id = :task_id
    """), {"task_id": task_id}).fetchone()
    
    total = subtask_stats[0] or 0
    running = subtask_stats[1] or 0
    errors = subtask_stats[2] or 0
    completed = subtask_stats[3] or 0
    
    # 更新任务统计信息
    task.active_subtasks = running
    task.total_subtasks = total
    
    # 根据子任务状态更新任务状态
    if running == 0 and total > 0:
        if completed == total:
            # 所有子任务都完成
            task.status = "completed"
            task.completed_at = datetime.now()
        elif errors > 0:
            # 有错误的子任务
            if errors == total:
                # 所有子任务都错误
                task.status = "error"
                task.error_message = "所有子任务执行失败"
            else:
                # 部分子任务错误
                task.status = "error"
                task.error_message = f"部分子任务执行失败 ({errors}/{total})"
    elif running > 0:
        # 有运行中的子任务
        task.status = "running"
        if errors > 0:
            # 有错误的子任务
            task.error_message = f"部分子任务执行失败 ({errors}/{total})"
    
    db.commit()
    
    return True, f"任务状态已更新: {task.status}" 