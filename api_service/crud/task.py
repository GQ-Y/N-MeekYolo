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
        status=0,  # 未启动状态(0)
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
                status=0,  # 未启动状态(0)
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
    # 如果任务已经处于运行中状态(1)，直接进入子任务处理
    # 如果任务是未启动状态(0)，改为运行中状态(1)
    # 如果任务是已停止状态(2)，不管原因，都允许启动任务
    if task.status == 1:
        logger.info(f"任务 {task_id} 已经处于运行中状态")
    elif task.status == 0:
        logger.info(f"任务 {task_id} 从未启动状态改为运行中状态")
        task.status = 1  # 运行中状态
        task.error_message = None
    elif task.status == 2:
        # 允许启动所有已停止的任务，包括用户手动停止的任务
        logger.info(f"任务 {task_id} 从已停止状态改为运行中状态")
        task.status = 1  # 运行中状态
        task.error_message = None
    else:
        logger.error(f"任务 {task_id} 状态为 {task.status}，无法启动")
        return False, f"任务状态无效，无法启动"
    
    # 获取子任务
    subtasks = task.sub_tasks
    if not subtasks:
        logger.error(f"任务 {task_id} 没有子任务，无法启动")
        return False, "任务没有子任务，无法启动"
    
    # 检查模型服务状态
    from services.model import ModelService
    model_service = ModelService()
    model_service_available = await model_service.check_model_service()
    
    if not model_service_available:
        logger.error(f"任务 {task_id} 无法启动：模型服务不可用")
        # 如果模型服务不可用，将任务状态重置为未启动状态(0)
        task.status = 0  # 未启动状态(0)
        task.error_message = "模型服务不可用，任务无法启动"
        db.commit()
        return False, "模型服务不可用，任务无法启动"
    
    # 如果是重新启动任务，更新启动时间和计数
    if task.started_at:
        logger.info(f"重启任务 {task_id}，清除之前的启动时间")
    
    task.started_at = datetime.now()
    task.completed_at = None
    task.active_subtasks = 0
    
    # 处理未启动状态(0)的子任务
    not_started_subtasks = [subtask for subtask in subtasks if subtask.status == 0]
    logger.info(f"任务 {task_id} 中有 {len(not_started_subtasks)} 个未启动的子任务")
    
    # 如果没有未启动的子任务，检查是否有任何子任务处于运行中状态
    if not not_started_subtasks:
        running_subtasks = [subtask for subtask in subtasks if subtask.status == 1]
        if running_subtasks:
            logger.info(f"任务 {task_id} 中有 {len(running_subtasks)} 个运行中的子任务，无需额外启动")
            task.active_subtasks = len(running_subtasks)
            db.commit()
            return True, f"任务中已有 {len(running_subtasks)} 个运行中的子任务"
        else:
            # 如果所有子任务都是已停止状态，将它们重置为未启动状态
            logger.info(f"任务 {task_id} 中没有运行中或未启动的子任务，将所有子任务重置为未启动状态")
            for subtask in subtasks:
                subtask.status = 0  # 未启动状态
                subtask.error_message = None
                subtask.started_at = None
                subtask.completed_at = None
                subtask.node_id = None
                subtask.analysis_task_id = None
            not_started_subtasks = subtasks
    
    db.commit()
    
    logger.info(f"任务 {task_id} ({task.name}) 准备启动 {len(not_started_subtasks)} 个子任务")
    
    # 导入分析服务
    from services.analysis import AnalysisService
    analysis_service = AnalysisService()
    
    # 构建系统回调URL - API服务接收回调的地址
    system_callback = f"http://{settings.SERVICE.host}:{settings.SERVICE.port}/api/v1/callback"
    logger.info(f"系统回调URL: {system_callback}")
    
    # 逐个启动未启动状态的子任务
    success_count = 0
    
    for subtask in not_started_subtasks:
        try:
            # 获取流和模型信息
            stream = db.query(Stream).filter(Stream.id == subtask.stream_id).first()
            model = db.query(Model).filter(Model.id == subtask.model_id).first()
            
            if not stream or not model:
                logger.error(f"子任务 {subtask.id} 关联的流或模型不存在")
                continue
                
            logger.info(f"准备启动子任务 {subtask.id}: 流={stream.name}({stream.url}), 模型={model.name}({model.code})")
            
            # 调用分析服务启动实际分析任务
            try:
                # 用户配置的回调URL
                user_callback_url = subtask.callback_url
                
                logger.info(f"调用分析服务启动子任务 {subtask.id}")
                logger.info(f"子任务参数: 模型={model.code}, 流URL={stream.url}")
                logger.info(f"子任务配置: {subtask.config}")
                
                result = await analysis_service.analyze_stream(
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
                
                if not result:
                    logger.error(f"子任务 {subtask.id} 启动失败: 未找到可用的分析节点")
                    subtask.error_message = "启动分析服务失败: 未找到可用的分析节点"
                    # 保持未启动状态(0)不变
                    continue
                
                # 解包返回值
                analysis_task_id, node_id = result
                
                # 保存分析任务ID和节点ID
                subtask.analysis_task_id = analysis_task_id
                subtask.node_id = node_id
                
                # 只有在确认启动成功后，才将状态设为运行中(1)
                subtask.status = 1  # 运行中状态(1)
                subtask.started_at = datetime.now()
                
                logger.info(f"子任务 {subtask.id} 启动成功，分析任务ID: {analysis_task_id}，节点ID: {node_id}")
                success_count += 1
                
            except Exception as e:
                logger.error(f"启动子任务 {subtask.id} 的分析服务失败: {str(e)}")
                subtask.error_message = f"启动分析服务失败: {str(e)}"
                # 保持未启动状态(0)
                continue
            
        except Exception as e:
            logger.error(f"处理子任务 {subtask.id} 失败: {str(e)}")
            continue
    
    # 更新任务统计信息
    task.active_subtasks = success_count
    
    db.commit()

    if success_count == 0 and len(not_started_subtasks) > 0:
        # 如果有子任务需要启动但全部启动失败，保持主任务仍处于运行中状态(1)
        # 这样系统可以后续继续尝试启动这些子任务
        task.error_message = "没有子任务启动成功，但任务保持运行中，等待后续尝试"
        db.commit()
        logger.warn(f"任务 {task_id} 暂时未能启动子任务: 所有子任务启动暂未成功，但任务保持运行中状态")
        return True, "任务保持运行中状态，等待后续尝试启动子任务"
    
    if success_count < len(not_started_subtasks) and len(not_started_subtasks) > 0:
        # 如果只有部分子任务启动成功
        task.error_message = f"部分子任务启动成功 ({success_count}/{len(not_started_subtasks)})"
        db.commit()
        logger.warn(f"任务 {task_id} 部分启动成功: {success_count}/{len(not_started_subtasks)} 个子任务")
        return True, f"部分子任务启动成功 ({success_count}/{len(not_started_subtasks)})"
    
    if len(not_started_subtasks) > 0:
        logger.info(f"任务 {task_id} 启动成功: {success_count}/{len(not_started_subtasks)} 个子任务")
        return True, "任务启动成功"
    else:
        logger.info(f"任务 {task_id} 无需启动新的子任务")
        return True, "任务已经处于运行状态"

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
    if task.status != 1:  # 只有运行中的任务(1)可以停止
        return False, f"任务状态为 {task.status}，不是运行中状态，无法停止"
    
    # 导入分析服务
    from services.analysis import AnalysisService
    analysis_service = AnalysisService()
    
    # 更新任务状态
    task.status = 2  # 已停止状态(2)
    task.active_subtasks = 0
    # 设置明确的错误消息，表明是用户手动停止的任务
    task.error_message = "任务由用户手动停止"
    
    # 逐个停止子任务
    stopped_count = 0
    for subtask in task.sub_tasks:
        if subtask.status == 1:  # 只停止运行中的子任务(1)
            try:
                # 更新子任务状态
                subtask.status = 2  # 已停止状态(2)
                subtask.completed_at = datetime.now()
                subtask.error_message = "子任务由用户手动停止"
                
                # 如果有节点，更新节点任务计数
                if subtask.node_id:
                    node = db.query(Node).filter(Node.id == subtask.node_id).first()
                    if node and node.stream_task_count > 0:
                        node.stream_task_count -= 1
                
                # 如果有分析任务ID，调用分析服务停止任务
                if subtask.analysis_task_id:
                    try:
                        # 传递节点ID，确保使用正确的节点停止任务
                        await analysis_service.stop_task(subtask.analysis_task_id, subtask.node_id)
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
    status: int,
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
    
    # 如果是已停止状态(2)，设置完成时间
    if status == 2:
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
    """根据子任务状态更新任务状态（三态模型：未启动、运行中、停止）"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return False, "任务不存在"
    
    # 获取所有子任务状态
    subtask_stats = db.execute(text("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status = 1 THEN 1 ELSE 0 END) as running,
            SUM(CASE WHEN status = 0 THEN 1 ELSE 0 END) as not_started,
            SUM(CASE WHEN status = 2 THEN 1 ELSE 0 END) as stopped
        FROM sub_tasks
        WHERE task_id = :task_id
    """), {"task_id": task_id}).fetchone()
    
    total = subtask_stats[0] or 0
    running = subtask_stats[1] or 0
    not_started = subtask_stats[2] or 0
    stopped = subtask_stats[3] or 0
    
    # 更新任务统计信息
    task.active_subtasks = running
    task.total_subtasks = total
    
    # 根据子任务状态更新任务状态 - 三态模型
    if running > 0:
        # 只要有运行中的子任务，主任务就是运行中
        task.status = 1  # 运行中状态(1)
        
        # 检查是否有子任务停止，记录原因
        if stopped > 0:
            task.error_message = f"部分子任务已停止 ({stopped}/{total})"
    elif total == not_started:
        # 所有子任务都未启动
        task.status = 0  # 未启动状态(0)
        task.error_message = None  # 清除错误消息
    else:
        # 没有运行中的子任务，且不是全部未启动，则标记为停止
        task.status = 2  # 已停止状态(2)
        
        # 区分不同的停止原因
        if stopped == total:
            # 所有子任务都已停止
            # 检查是否所有子任务都是因用户停止
            user_stopped_count = db.query(SubTask).filter(
                SubTask.task_id == task_id,
                SubTask.status == 2,
                SubTask.error_message == "子任务由用户手动停止"
            ).count()
            
            if user_stopped_count == total:
                task.error_message = "任务由用户手动停止"
                task.completed_at = datetime.now()
            else:
                task.error_message = "所有子任务已停止"
                task.completed_at = datetime.now()
        else:
            # 部分子任务已停止，部分未启动
            task.error_message = f"部分子任务未启动 ({not_started}/{total})"
    
    db.commit()
    
    return True, f"任务状态已更新: {task.status}"

def normalize_task_status(status: int) -> int:
    """
    将不同的状态规范化为三态模型中的一种状态
    
    参数:
    - status: 原始状态
    
    返回:
    - 规范化后的状态：0(未启动)、1(运行中)或2(已停止)
    """
    # 确保状态是整数并在有效范围内
    try:
        status_int = int(status)
        if status_int in [0, 1, 2]:
            return status_int
        else:
            logger.warning(f"遇到无效状态值: {status}，默认规范化为未启动(0)")
            return 0
    except (TypeError, ValueError):
        logger.warning(f"无法将状态 {status} 转换为整数，默认规范化为未启动(0)")
        return 0 