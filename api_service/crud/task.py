"""
任务 CRUD 操作
"""
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
import logging
from models.database import Task, Stream, Model, Callback, Node, SubTask, MQTTNode
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
    # 记录所有模型ID，用于日志和错误报告
    requested_model_ids = []
    for stream_config in task_data.tasks:
        for model_config in stream_config.models:
            requested_model_ids.append(model_config.model_id)
    
    logger.info(f"创建任务使用模型ID: {requested_model_ids}")
    
    # 检查数据库中可用的模型
    available_models = db.query(Model).filter(Model.id.in_(requested_model_ids)).all()
    available_model_ids = [model.id for model in available_models]
    
    # 检查是否所有请求的模型都可用
    missing_model_ids = [model_id for model_id in requested_model_ids if model_id not in available_model_ids]
    if missing_model_ids:
        logger.warning(f"创建任务时发现缺失的模型ID: {missing_model_ids}")
    
    # 创建任务主记录
    expected_subtasks = sum(len(stream_config.models) for stream_config in task_data.tasks)
    task = Task(
        name=task_data.name,
        save_result=task_data.save_result,
        status=0,  # 未启动状态(0)
        total_subtasks=0,  # 初始化为0，稍后根据实际创建的子任务更新
        active_subtasks=0
    )
    
    db.add(task)
    try:
        db.flush()  # 获取任务ID
        logger.info(f"成功创建主任务记录，ID: {task.id}")
    except Exception as e:
        db.rollback()
        logger.error(f"创建主任务记录失败: {str(e)}")
        raise ValueError(f"创建主任务记录失败: {str(e)}")
    
    created_subtasks = []
    failed_streams = []
    failed_models = []
    
    # 为每个流和模型创建子任务
    for stream_config in task_data.tasks:
        # 获取流
        stream = db.query(Stream).filter(Stream.id == stream_config.stream_id).first()
        if not stream:
            failed_streams.append(stream_config.stream_id)
            logger.warning(f"视频流 {stream_config.stream_id} 不存在，但继续创建任务")
            continue
            
        # 添加关联
        task.streams.append(stream)
        logger.info(f"为任务 {task.id} 添加流 ID={stream.id}, name={stream.name}")
            
        # 处理每个模型配置
        for model_config in stream_config.models:
            # 获取模型
            model = db.query(Model).filter(Model.id == model_config.model_id).first()
            if not model:
                failed_models.append(model_config.model_id)
                logger.warning(f"模型 {model_config.model_id} 不存在，但继续创建任务")
                continue
                
            # 添加关联
            if model not in task.models:
                task.models.append(model)
                logger.info(f"为任务 {task.id} 添加模型 ID={model.id}, code={model.code}, name={model.name}")
                
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
            logger.info(f"创建子任务，task_id={task.id}, stream={stream.id}({stream.name}), model={model.id}({model.code})")
            
            # 定期提交以确保数据写入
            try:
                db.flush()
                logger.info(f"成功添加子任务到数据库会话，stream={stream.id}, model={model.id}")
            except Exception as e:
                logger.error(f"添加子任务到会话失败: {str(e)}")
                # 继续执行，尝试创建其他子任务
    
    # 更新实际的子任务数量
    task.total_subtasks = len(created_subtasks)
    logger.info(f"任务 {task.id} 共创建了 {task.total_subtasks} 个子任务")
    
    # 生成警告信息
    warnings = []
    if expected_subtasks > task.total_subtasks:
        warnings.append(f"预期创建 {expected_subtasks} 个子任务，但只成功创建了 {task.total_subtasks} 个")
    
    if failed_streams:
        warnings.append(f"以下视频流不存在或无法连接: {', '.join(map(str, failed_streams))}")
    if failed_models:
        warnings.append(f"以下模型不存在或未下载: {', '.join(map(str, failed_models))}")
    
    # 更新任务信息
    if warnings:
        task.error_message = " | ".join(warnings)
    
    try:
        # 提交事务前再次检查
        subtask_count = db.query(SubTask).filter(SubTask.task_id == task.id).count()
        logger.info(f"提交前检查: 数据库中任务 {task.id} 的子任务数量: {subtask_count}")
        
        # 提交事务
        db.commit()
        logger.info(f"成功提交事务，任务 {task.id} 及其 {task.total_subtasks} 个子任务已保存到数据库")
        
        # 提交后再次验证
        db.refresh(task)
        actual_subtasks = db.query(SubTask).filter(SubTask.task_id == task.id).all()
        logger.info(f"提交后验证: 数据库中任务 {task.id} 的子任务数量: {len(actual_subtasks)}")
        
        if len(actual_subtasks) != task.total_subtasks:
            logger.warning(f"任务 {task.id} 的子任务数量不一致: 预期 {task.total_subtasks}，实际 {len(actual_subtasks)}")
            # 更新total_subtasks以匹配实际数量
            task.total_subtasks = len(actual_subtasks)
            db.commit()
        
        return task
    except Exception as e:
        db.rollback()
        logger.error(f"创建任务失败，事务回滚: {str(e)}")
        import traceback
        logger.error(f"详细错误跟踪: {traceback.format_exc()}")
        raise ValueError(f"创建任务失败，数据库错误: {str(e)}")

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
    if task.status == 1:
        logger.info(f"任务 {task_id} 已经处于运行中状态")
    elif task.status == 0:
        logger.info(f"任务 {task_id} 从未启动状态改为运行中状态")
        task.status = 1  # 运行中状态
        task.error_message = None
    elif task.status == 2:
        logger.info(f"任务 {task_id} 从已停止状态改为运行中状态")
        task.status = 1  # 运行中状态
        task.error_message = None
    else:
        logger.error(f"任务 {task_id} 状态为 {task.status}，无法启动")
        return False, f"任务状态无效，无法启动"
    
    # 获取子任务
    subtasks = task.sub_tasks
    if not subtasks:
        error_msg = "任务没有可用的子任务"
        if task.error_message:
            error_msg += f"，原因：{task.error_message}"
        logger.error(f"任务 {task_id} {error_msg}")
        return False, error_msg
    
    # 检查模型服务状态
    from services.model import ModelService
    model_service = ModelService()
    model_service_available = await model_service.check_model_service()
    
    if not model_service_available:
        logger.error(f"任务 {task_id} 无法启动：模型服务不可用")
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
    failed_subtasks = []
    
    for subtask in not_started_subtasks:
        try:
            # 获取流和模型信息
            stream = db.query(Stream).filter(Stream.id == subtask.stream_id).first()
            model = db.query(Model).filter(Model.id == subtask.model_id).first()
            
            if not stream or not model:
                error_msg = []
                if not stream:
                    error_msg.append("视频流不存在或无法连接")
                if not model:
                    error_msg.append("模型不存在或未下载")
                error_str = " 且 ".join(error_msg)
                logger.error(f"子任务 {subtask.id} 无法启动：{error_str}")
                failed_subtasks.append((subtask.id, error_str))
                continue
                
            logger.info(f"准备启动子任务 {subtask.id}: 流={stream.name}({stream.url}), 模型={model.name}({model.code})")
            
            # 调用分析服务启动实际分析任务
            try:
                # 用户配置的回调URL
                user_callback_url = subtask.callback_url
                
                logger.info(f"调用分析服务启动子任务 {subtask.id}")
                logger.info(f"子任务参数: 模型={model.code}, 流URL={stream.url}")
                logger.info(f"子任务配置: {subtask.config}")
                
                # 获取当前通信模式
                from core.config import settings as config_settings
                import yaml
                comm_mode = "http"  # 默认值
                try:
                    with open("config/config.yaml", "r", encoding="utf-8") as f:
                        config = yaml.safe_load(f)
                        comm_mode = config.get('COMMUNICATION', {}).get('mode', 'http')
                        logger.info(f"当前通信模式: {comm_mode}")
                except Exception as e:
                    logger.error(f"读取配置文件失败，使用默认HTTP模式: {e}")
                
                # 根据通信模式使用不同的客户端
                result = None
                if comm_mode == "mqtt":
                    # 使用应用级别的MQTT客户端而不是创建新的
                    from fastapi import FastAPI
                    from app import app as fastapi_app
                    
                    if not hasattr(fastapi_app.state, "analysis_client") or not fastapi_app.state.analysis_client:
                        logger.error("无法获取应用程序状态中的analysis_client，无法启动任务")
                        error_msg = "MQTT客户端不可用，任务无法启动"
                        failed_subtasks.append((subtask.id, error_msg))
                        continue
                    
                    analysis_client = fastapi_app.state.analysis_client
                    
                    # 确保MQTT客户端已连接
                    if not analysis_client.mqtt_connected:
                        logger.warning("应用程序中的MQTT客户端未连接，尝试重新连接")
                        analysis_client.mqtt_client.connect()
                        if not analysis_client.mqtt_connected:
                            logger.warning("MQTT客户端未连接，但会继续任务创建，等待客户端连接后会自动处理")
                    
                    # 调用MQTT客户端处理任务 - 不等待响应，只获取任务ID
                    response = await analysis_client.analyze_stream(
                        model_code=model.code,
                        stream_url=stream.url,
                        task_name=f"{task.name}-{subtask.id}",
                        callback_url=system_callback,
                        callback_urls=user_callback_url,
                        enable_callback=subtask.enable_callback,
                        save_result=task.save_result,
                        config=subtask.config,
                        task_id=subtask.analysis_task_id,
                        analysis_type=subtask.analysis_type
                    )
                    
                    if response.get('success', False):
                        data = response.get('data', {})
                        analysis_task_id = data.get('task_id')
                        
                        if analysis_task_id:
                            # 先记录任务，状态为已创建但未运行
                            # 保存分析任务ID
                            subtask.analysis_task_id = analysis_task_id
                            subtask.status = 0  # 未启动状态，等待客户端响应
                            subtask.error_message = "任务已创建，等待MQTT节点接收"
                            
                            # 记录MQTT节点ID - 简化处理，不直接使用node对象
                            mqtt_node_id = data.get('mqtt_node_id')
                            if mqtt_node_id:
                                # 这里不再需要复杂的会话处理，直接使用ID
                                subtask.mqtt_node_id = mqtt_node_id
                                logger.info(f"任务关联到MQTT节点ID={mqtt_node_id}")
                            
                            # 记录成功创建的任务
                            result = (analysis_task_id, None)  # node_id为None，表示使用MQTT
                            logger.info(f"成功创建MQTT任务：{analysis_task_id}，等待MQTT节点接收后运行")
                            success_count += 1
                        else:
                            logger.error(f"MQTT响应缺少任务ID: {response}")
                            error_msg = "MQTT响应缺少任务ID"
                            subtask.error_message = f"启动MQTT分析服务失败: {error_msg}"
                            failed_subtasks.append((subtask.id, error_msg))
                            continue
                    else:
                        error_msg = response.get('message', '未知错误')
                        logger.error(f"MQTT任务启动失败: {error_msg}")
                        subtask.error_message = f"启动MQTT分析服务失败: {error_msg}"
                        failed_subtasks.append((subtask.id, error_msg))
                        continue
                else:
                    # 使用HTTP分析服务
                    result = await analysis_service.analyze_stream(
                        model_code=model.code,
                        stream_url=stream.url,
                        task_name=f"{task.name}-{subtask.id}",
                        callback_url=system_callback,
                        callback_urls=user_callback_url,
                        enable_callback=subtask.enable_callback,
                        save_result=task.save_result,
                        config=subtask.config,
                        analysis_task_id=subtask.analysis_task_id,
                        analysis_type=subtask.analysis_type
                    )
                
                if not result:
                    error_msg = "未找到可用的分析节点"
                    logger.error(f"子任务 {subtask.id} 启动失败: {error_msg}")
                    subtask.error_message = f"启动分析服务失败: {error_msg}"
                    failed_subtasks.append((subtask.id, error_msg))
                    continue
                
                # 解包返回值
                analysis_task_id, node_id = result
                
                # 保存分析任务ID和节点ID
                subtask.analysis_task_id = analysis_task_id
                
                # 根据通信模式设置不同的节点ID
                if comm_mode == "mqtt":
                    subtask.node_id = None  # HTTP节点ID
                    subtask.mqtt_node_id = mqtt_node_id  # MQTT节点ID
                else:
                    subtask.node_id = node_id  # HTTP节点ID
                    subtask.mqtt_node_id = None  # MQTT节点ID
                
                # 只有在确认启动成功后，才将状态设为运行中(1)
                subtask.status = 1  # 运行中状态(1)
                subtask.started_at = datetime.now()
                
                logger.info(f"子任务 {subtask.id} 启动成功，分析任务ID: {analysis_task_id}，节点ID: {node_id if comm_mode != 'mqtt' else 'MQTT模式'}")
                success_count += 1
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"启动子任务 {subtask.id} 的分析服务失败: {error_msg}")
                subtask.error_message = f"启动分析服务失败: {error_msg}"
                failed_subtasks.append((subtask.id, error_msg))
                continue
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"处理子任务 {subtask.id} 失败: {error_msg}")
            failed_subtasks.append((subtask.id, error_msg))
            continue
    
    # 更新任务统计信息
    task.active_subtasks = success_count
    
    # 生成详细的错误信息
    if failed_subtasks:
        error_details = []
        for subtask_id, error in failed_subtasks:
            error_details.append(f"子任务 {subtask_id}: {error}")
        task.error_message = " | ".join(error_details)
    
    db.commit()

    if success_count == 0 and len(not_started_subtasks) > 0:
        # 如果有子任务需要启动但全部启动失败，保持主任务仍处于运行中状态(1)
        error_msg = "没有子任务启动成功"
        if task.error_message:
            error_msg += f"，原因：{task.error_message}"
        task.error_message = error_msg
        db.commit()
        logger.warn(f"任务 {task_id} 暂时未能启动子任务: {error_msg}")
        return True, f"任务保持运行中状态，但启动失败：{error_msg}"
    
    if success_count < len(not_started_subtasks) and len(not_started_subtasks) > 0:
        # 如果只有部分子任务启动成功
        error_msg = f"部分子任务启动成功 ({success_count}/{len(not_started_subtasks)})"
        if task.error_message:
            error_msg += f"，失败原因：{task.error_message}"
        task.error_message = error_msg
        db.commit()
        logger.warn(f"任务 {task_id} 部分启动成功: {error_msg}")
        return True, error_msg
    
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

class TaskCRUD:
    """
    TaskCRUD 类，作为适配器包装现有函数
    用于兼容导入 TaskCRUD 的代码
    """
    
    @staticmethod
    def create_task(db: Session, name: str = None, save_result: bool = False, **kwargs) -> Task:
        """
        创建任务的静态方法
        
        Args:
            db: 数据库会话
            name: 任务名称
            save_result: 是否保存结果
            
        Returns:
            Task: 创建的任务对象
        """
        # 创建一个简单的任务
        task = Task(
            name=name,
            save_result=save_result,
            status=0,  # 未启动状态
            total_subtasks=0,
            active_subtasks=0
        )
        
        db.add(task)
        db.commit()
        db.refresh(task)
        return task
    
    @staticmethod
    def update_task_status(db: Session, task_id: int) -> None:
        """
        根据子任务状态更新主任务状态
        
        Args:
            db: 数据库会话
            task_id: 任务ID
        """
        update_task_status_from_subtasks(db, task_id) 