"""
任务路由模块

提供分析任务的管理接口，支持：
- 创建任务：创建新的分析任务
- 查询任务：获取任务列表和详情
- 更新任务：修改任务配置
- 删除任务：移除不需要的任务
- 任务控制：启动、停止和监控任务执行
"""
from fastapi import APIRouter, Depends, Body, Request, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from models.responses import BaseResponse, TaskDetailResponse, SubTaskResponse
from models.requests import TaskCreate, TaskUpdate
from services.database import get_db
from crud import task as task_crud
from shared.utils.logger import setup_logger
from services.model import ModelService
from datetime import datetime

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/v1/tasks", tags=["任务管理"])

@router.post("/create", response_model=BaseResponse, summary="创建任务")
async def create_task(
    request: Request,
    task_data: TaskCreate,
    db: Session = Depends(get_db)
):
    """
    创建任务
    
    参数:
    - name: 任务名称
    - save_result: 是否保存结果
    - tasks: 子任务配置列表，每个子任务包含流ID和模型配置列表
    
    请求示例:
    ```json
    {
        "name": "多摄像头行人检测",
        "save_result": true,
        "tasks": [
            {
                "stream_id": 1,
                "stream_name": "前门摄像头",
                "models": [
                    {
                        "model_id": 2,
                        "config": {
                            "confidence": 0.5,
                            "iou": 0.45,
                            "classes": [0, 1, 2],
                            "roi_type": 1,
                            "roi": {
                                "x1": 0.1,
                                "y1": 0.1,
                                "x2": 0.9,
                                "y2": 0.9
                            },
                            "imgsz": 640,
                            "nested_detection": true,
                            "analysis_type": "detection",
                            "callback": {
                                "enabled": true,
                                "url": "http://example.com/callback",
                                "interval": 5
                            }
                        }
                    }
                ]
            },
            {
                "stream_id": 2,
                "stream_name": "后门摄像头",
                "models": [
                    {
                        "model_id": 2,
                        "config": {
                            "confidence": 0.4,
                            "iou": 0.4,
                            "classes": [0, 1, 2], 
                            "roi_type": 2,
                            "roi": {
                                "points": [
                                    [0.1, 0.1],
                                    [0.9, 0.1],
                                    [0.9, 0.9],
                                    [0.1, 0.9]
                                ]
                            },
                            "analysis_type": "tracking",
                            "callback": {
                                "enabled": true
                            }
                        }
                    },
                    {
                        "model_id": 3,
                        "config": {
                            "confidence": 0.6,
                            "analysis_type": "counting",
                            "roi_type": 3,
                            "roi": {
                                "points": [
                                    [0.2, 0.5],
                                    [0.8, 0.5]
                                ]
                            }
                        }
                    }
                ]
            }
        ]
    }
    ```
    
    返回:
    - 创建的任务ID和基本信息，包含子任务创建过程中的警告信息
    """
    try:
        # 首先尝试同步模型数据
        model_service = ModelService()
        
        # 记录所有配置中的模型ID
        all_model_ids = []
        for stream_config in task_data.tasks:
            for model_config in stream_config.models:
                all_model_ids.append(model_config.model_id)
        
        logger.info(f"任务创建包含模型ID: {all_model_ids}")
        
        # 尝试同步模型数据
        service_available = await model_service.check_model_service()
        if service_available:
            try:
                logger.info("模型服务可用，正在同步模型数据")
                models = await model_service.sync_models(db)
                logger.info(f"成功同步 {len(models)} 个模型")
            except Exception as e:
                logger.error(f"同步模型数据失败: {str(e)}")
        else:
            logger.warning("模型服务不可用，无法同步模型数据")
        
        # 尝试查找和处理任务中使用的每个模型
        for model_id in all_model_ids:
            model = db.query(task_crud.Model).filter(task_crud.Model.id == model_id).first()
            if not model:
                logger.warning(f"本地数据库中找不到模型ID {model_id}，尝试从模型服务获取")
                # 尝试通过ID获取模型详情
                try:
                    if service_available:
                        await model_service.get_model(db, model_id)
                        logger.info(f"成功从模型服务获取模型ID {model_id}")
                except Exception as e:
                    logger.error(f"从模型服务获取模型ID {model_id} 失败: {str(e)}")

        # 创建任务前先检查流存在性
        for stream_config in task_data.tasks:
            stream = db.query(task_crud.Stream).filter(task_crud.Stream.id == stream_config.stream_id).first()
            if not stream:
                logger.warning(f"流ID {stream_config.stream_id} 不存在，请检查数据")

        # 创建任务
        try:
            new_task = task_crud.create_task(db, task_data)
            logger.info(f"任务 {new_task.id} 创建成功")
            
            # 提交后验证子任务是否成功创建
            db.refresh(new_task)
            actual_subtasks = db.query(task_crud.SubTask).filter(task_crud.SubTask.task_id == new_task.id).all()
            logger.info(f"验证: 数据库中任务 {new_task.id} 的子任务数量: {len(actual_subtasks)}")
            
            # 如果没有成功创建子任务，尝试手动创建
            if len(actual_subtasks) == 0 and task_data.tasks:
                logger.warning(f"任务 {new_task.id} 没有成功创建子任务，尝试手动创建")
                
                created_subtasks = []
                # 手动创建子任务
                for stream_config in task_data.tasks:
                    stream = db.query(task_crud.Stream).filter(task_crud.Stream.id == stream_config.stream_id).first()
                    if not stream:
                        continue
                        
                    for model_config in stream_config.models:
                        model = db.query(task_crud.Model).filter(task_crud.Model.id == model_config.model_id).first()
                        if not model:
                            continue
                            
                        # 确保任务与流和模型建立关联
                        if stream not in new_task.streams:
                            new_task.streams.append(stream)
                        if model not in new_task.models:
                            new_task.models.append(model)
                        
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
                        subtask = task_crud.SubTask(
                            task_id=new_task.id,
                            stream_id=stream.id,
                            model_id=model.id,
                            status=0,  # 未启动状态(0)
                            config=model_config.config,
                            enable_callback=enable_callback,
                            callback_url=callback_url,
                            roi_type=roi_type,
                            analysis_type=analysis_type,
                            created_at=datetime.now(),
                            updated_at=datetime.now()
                        )
                        
                        db.add(subtask)
                        created_subtasks.append(subtask)
                        logger.info(f"手动创建子任务，task_id={new_task.id}, stream={stream.id}, model={model.id}")
                
                if created_subtasks:
                    try:
                        # 定期提交确保数据写入
                        db.flush()
                        logger.info(f"成功添加 {len(created_subtasks)} 个子任务到数据库会话")
                        
                        # 更新任务的子任务数量
                        new_task.total_subtasks = len(created_subtasks)
                        db.commit()
                        logger.info(f"成功提交手动创建的子任务到数据库")
                        
                        # 再次验证
                        db.refresh(new_task)
                        actual_subtasks = db.query(task_crud.SubTask).filter(task_crud.SubTask.task_id == new_task.id).all()
                        logger.info(f"再次验证: 数据库中任务 {new_task.id} 的子任务数量: {len(actual_subtasks)}")
                    except Exception as e:
                        db.rollback()
                        logger.error(f"手动创建子任务失败: {str(e)}")
                        import traceback
                        logger.error(f"详细错误跟踪: {traceback.format_exc()}")
        except Exception as e:
            logger.error(f"创建任务失败: {str(e)}")
            import traceback
            logger.error(f"详细错误跟踪: {traceback.format_exc()}")
            raise ValueError(f"创建任务失败: {str(e)}")
        
        # 构建响应数据
        response_data = {
            "id": new_task.id,
            "name": new_task.name,
            "status": new_task.status,
            "save_result": new_task.save_result,
            "total_subtasks": new_task.total_subtasks,
            "created_at": new_task.created_at
        }
        
        # 检查子任务创建情况
        has_subtasks = db.query(task_crud.SubTask).filter(task_crud.SubTask.task_id == new_task.id).count() > 0
        response_data["has_subtasks"] = has_subtasks
        
        # 添加警告信息
        message = "创建成功"
        if not has_subtasks:
            warning = "任务创建成功，但没有创建任何子任务"
            if new_task.error_message:
                warning += f"，原因：{new_task.error_message}"
            message = warning
            logger.warning(f"任务 {new_task.id} {warning}")
        elif new_task.error_message:
            message = f"创建成功，但有警告：{new_task.error_message}"
            logger.warning(f"任务 {new_task.id} 创建有警告：{new_task.error_message}")
        
        return BaseResponse(
            path=str(request.url),
            message=message,
            data=response_data
        )
    except Exception as e:
        logger.error(f"创建任务失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/list", response_model=BaseResponse, summary="获取任务列表")
async def get_tasks(
    request: Request,
    skip: int = 0,
    limit: int = 10,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    获取任务列表
    
    参数:
    - skip: 跳过的记录数
    - limit: 返回的最大记录数
    - status: 任务状态过滤
    
    返回:
    - 任务列表和总数
    """
    try:
        tasks = task_crud.get_tasks(db, skip, limit, status, include_subtasks=False)
        total = db.query(task_crud.Task).count()
        
        # 转换为响应格式
        task_list = []
        for t in tasks:
            task_list.append({
                "id": t.id,
                "name": t.name,
                "status": t.status,
                "save_result": t.save_result,
                "active_subtasks": t.active_subtasks,
                "total_subtasks": t.total_subtasks,
                "created_at": t.created_at,
                "updated_at": t.updated_at,
                "started_at": t.started_at,
                "completed_at": t.completed_at,
                "error_message": t.error_message
            })
        
        return BaseResponse(
            path=str(request.url),
            message="获取成功",
            data={
                "total": total,
                "items": task_list
            }
        )
    except Exception as e:
        logger.error(f"获取任务列表失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/detail", response_model=BaseResponse, summary="获取任务详情")
async def get_task(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db)
):
    """
    获取任务详情
    
    参数:
    - task_id: 任务ID
    
    返回:
    - 任务详细信息，包括子任务列表
    """
    try:
        task_obj = task_crud.get_task(db, task_id, include_subtasks=True)
        if not task_obj:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="任务不存在"
            )
        
        # 检查子任务情况
        has_subtasks = len(task_obj.sub_tasks) > 0
        if not has_subtasks:
            warning_message = "任务没有可用的子任务"
            if task_obj.error_message:
                warning_message += f"，原因：{task_obj.error_message}"
            logger.warning(f"任务 {task_id} {warning_message}")
        
        # 准备子任务响应
        subtasks = []
        for st in task_obj.sub_tasks:
            # 获取流和模型信息
            stream = db.query(task_crud.Stream).filter(task_crud.Stream.id == st.stream_id).first()
            model = db.query(task_crud.Model).filter(task_crud.Model.id == st.model_id).first()
            
            stream_name = stream.name if stream else "未知流"
            model_name = model.name if model else "未知模型"
            model_code = model.code if model else "未知"
            
            subtasks.append({
                "id": st.id,
                "stream_id": st.stream_id,
                "stream_name": stream_name,
                "model_id": st.model_id,
                "model_name": model_name,
                "model_code": model_code,
                "status": st.status,
                "config": st.config,
                "analysis_type": st.analysis_type,
                "roi_type": st.roi_type,
                "created_at": st.created_at,
                "started_at": st.started_at,
                "completed_at": st.completed_at,
                "error_message": st.error_message,
                "node_id": st.node_id,
                "mqtt_node_id": st.mqtt_node_id,
                "enable_callback": st.enable_callback,
                "callback_url": st.callback_url
            })
        
        # 准备任务响应
        task_data = {
            "id": task_obj.id,
            "name": task_obj.name,
            "status": task_obj.status,
            "save_result": task_obj.save_result,
            "save_images": task_obj.save_images,  # 新增字段
            "analysis_interval": task_obj.analysis_interval,  # 新增字段
            "specific_node_id": task_obj.specific_node_id,  # 新增字段
            "active_subtasks": task_obj.active_subtasks,
            "total_subtasks": task_obj.total_subtasks,
            "created_at": task_obj.created_at,
            "updated_at": task_obj.updated_at,
            "started_at": task_obj.started_at,
            "completed_at": task_obj.completed_at,
            "error_message": task_obj.error_message,
            "subtasks": subtasks
        }
        
        return BaseResponse(
            path=str(request.url),
            message="获取成功",
            data=task_data
        )
    except Exception as e:
        logger.error(f"获取任务详情失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/update", response_model=BaseResponse, summary="更新任务")
async def update_task(
    request: Request,
    task_data: TaskUpdate,
    db: Session = Depends(get_db)
):
    """
    更新任务配置
    
    参数:
    - id: 任务ID(必须)
    - name: 任务名称(可选)
    - save_result: 是否保存结果数据(可选)
    - save_images: 是否保存结果图片(可选)
    - analysis_interval: 分析间隔(秒)(可选)
    - specific_node_id: 指定运行节点ID(可选)
    - tasks: 子任务配置列表(可选)，如果提供则完全替换现有配置
    
    请求示例:
    ```json
    {
        "id": 1,
        "name": "更新后的任务名称",
        "save_result": true,
        "save_images": true,
        "analysis_interval": 2,
        "specific_node_id": 5,
        "tasks": [
            {
                "stream_id": 1,
                "stream_name": "前门摄像头",
                "models": [
                    {
                        "model_id": 2,
                        "config": {
                            "confidence": 0.5,
                            "iou": 0.45,
                            "classes": [0, 1, 2],
                            "roi_type": 1,
                            "roi": {
                                "x1": 0.1,
                                "y1": 0.1,
                                "x2": 0.9,
                                "y2": 0.9
                            },
                            "imgsz": 640,
                            "nested_detection": true,
                            "analysis_type": "detection",
                            "alarm_recording": {
                                "enabled": true,
                                "before_seconds": 5,
                                "after_seconds": 5
                            },
                            "callback": {
                                "enabled": true,
                                "url": "http://example.com/callback",
                                "interval": 5
                            }
                        }
                    }
                ]
            }
        ]
    }
    ```
    
    返回:
    - 更新后的任务基本信息
    """
    try:
        # 检查任务是否存在
        task_id = task_data.id
        task = db.query(task_crud.Task).filter(task_crud.Task.id == task_id).first()
        if not task:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message=f"任务 {task_id} 不存在"
            )
        
        # 任务更新
        try:
            updated_task = task_crud.update_task(db, task_id, task_data)
            logger.info(f"任务 {task_id} 更新成功")
            
            # 构建响应数据
            response_data = {
                "id": updated_task.id,
                "name": updated_task.name,
                "status": updated_task.status,
                "save_result": updated_task.save_result,
                "save_images": updated_task.save_images,
                "analysis_interval": updated_task.analysis_interval,
                "specific_node_id": updated_task.specific_node_id,
                "total_subtasks": updated_task.total_subtasks,
                "created_at": updated_task.created_at,
                "updated_at": updated_task.updated_at
            }
            
            return BaseResponse(
                path=str(request.url),
                message="更新成功",
                data=response_data
            )
        except ValueError as e:
            logger.error(f"更新任务 {task_id} 失败: {str(e)}")
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=400,
                message=str(e)
            )
    except Exception as e:
        logger.error(f"更新任务失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/delete", response_model=BaseResponse, summary="删除任务")
async def delete_task(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db)
):
    """
    删除任务
    
    参数:
    - task_id: 任务ID
    
    返回:
    - 删除操作结果
    """
    try:
        result = task_crud.delete_task(db, task_id)
        if not result:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="任务不存在或无法删除运行中的任务"
            )
        
        return BaseResponse(
            path=str(request.url),
            message="删除成功"
        )
    except Exception as e:
        logger.error(f"删除任务失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

@router.post("/start", response_model=BaseResponse, summary="启动任务")
async def start_task(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db)
):
    """
    启动任务
    
    参数:
    - task_id: 任务ID
    
    返回:
    - 启动操作结果，包含详细的错误信息
    """
    try:
        # 先检查任务是否存在并加载关联数据
        task = db.query(task_crud.Task).options(
            joinedload(task_crud.Task.sub_tasks),
            joinedload(task_crud.Task.streams),
            joinedload(task_crud.Task.models)
        ).filter(task_crud.Task.id == task_id).first()
        
        if not task:
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=404,
                message="任务不存在"
            )
        
        # 检查子任务情况
        has_subtasks = len(task.sub_tasks) > 0
        
        # 如果没有子任务，尝试同步模型并重新检查
        if not has_subtasks:
            logger.warning(f"任务 {task_id} 没有子任务，尝试同步模型后重新检查")
            
            # 尝试同步模型数据
            model_service = ModelService()
            service_available = await model_service.check_model_service()
            
            if service_available:
                try:
                    # 同步所有模型
                    logger.info("模型服务可用，正在同步模型数据")
                    models = await model_service.sync_models(db)
                    
                    # 尝试查找原始请求中的模型信息 (可能无法获取原始请求)
                    # 不过可以尝试从子任务表中查找失败的模型ID
                    # 检查是否有模型ID但没有创建子任务的情况
                    logger.info("尝试重建任务与模型的关联...")
                    
                    # 尝试1: 从数据库查询现有的模型，并尝试建立关联
                    # 对已经存在但还未关联的模型，尝试重建关联
                    model_codes = [m.code for m in models]
                    logger.info(f"系统中可用的模型代码: {model_codes}")
                    
                    # 检查任务是否有关联的流
                    if len(task.streams) == 0:
                        logger.warning(f"任务 {task_id} 没有关联的流，尝试添加可用流")
                        
                        # 从数据库获取一些可用的流
                        available_streams = db.query(task_crud.Stream).limit(5).all()
                        if available_streams:
                            for stream in available_streams:
                                # 添加流关联
                                if stream not in task.streams:
                                    task.streams.append(stream)
                                    logger.info(f"为任务 {task_id} 添加流关联: {stream.name} (ID: {stream.id})")
                        
                            # 提交流关联更改
                            try:
                                db.commit()
                                logger.info(f"成功为任务 {task_id} 添加 {len(available_streams)} 个流关联")
                            except Exception as commit_err:
                                db.rollback()
                                logger.error(f"添加流关联失败: {str(commit_err)}")
                        else:
                            logger.warning("系统中没有可用的视频流，请先添加视频流")
                    
                    # 获取任务的原始流信息
                    if len(task.streams) > 0:
                        logger.info(f"任务有 {len(task.streams)} 个关联的流")
                        
                        # 要创建子任务，需要关联流和模型
                        for stream in task.streams:
                            for model in models:
                                # 检查这个组合是否已经存在子任务
                                existing_subtask = db.query(task_crud.SubTask).filter(
                                    task_crud.SubTask.task_id == task.id,
                                    task_crud.SubTask.stream_id == stream.id,
                                    task_crud.SubTask.model_id == model.id
                                ).first()
                                
                                if not existing_subtask:
                                    # 如果是新添加的模型，我们需要先建立与任务的关联
                                    if model not in task.models:
                                        task.models.append(model)
                                        logger.info(f"为任务添加模型关联: {model.code} (ID: {model.id})")
                                    
                                    # 创建子任务
                                    subtask = task_crud.SubTask(
                                        task_id=task.id,
                                        stream_id=stream.id,
                                        model_id=model.id,
                                        status=0,  # 未启动状态
                                        config={
                                            "confidence": 0.5,
                                            "iou": 0.45,
                                            "classes": None,
                                            "roi_type": 0,
                                            "roi": None,
                                            "nested_detection": True,
                                            "analysis_type": "detection",
                                        },
                                        roi_type=0,
                                        analysis_type="detection"
                                    )
                                    
                                    db.add(subtask)
                                    logger.info(f"创建子任务: 流={stream.id}, 模型={model.id}")
                        
                        # 提交更改
                        try:
                            db.commit()
                            logger.info("成功重建任务关联和子任务")
                        except Exception as commit_err:
                            db.rollback()
                            logger.error(f"重建任务关联和子任务失败: {str(commit_err)}")
                    else:
                        logger.warning("任务没有关联的流，无法创建子任务")
                    
                except Exception as e:
                    logger.error(f"同步模型数据失败: {str(e)}")
            
            # 重新检查任务
            db.refresh(task)
            has_subtasks = len(task.sub_tasks) > 0
        
        # 检查子任务情况
        if not has_subtasks:
            warning_message = "任务没有可用的子任务"
            
            # 添加详细的失败原因
            problem_details = []
            
            # 检查任务是否有流和模型
            if len(task.streams) == 0:
                problem_details.append("没有关联的视频流")
            if len(task.models) == 0:
                problem_details.append("没有关联的模型")
                
            # 检查错误消息
            if task.error_message:
                problem_details.append(f"{task.error_message}")
                
            # 合并详细原因
            if problem_details:
                warning_message += f"，原因：{' | '.join(problem_details)}"
                
            logger.warning(f"任务 {task_id} {warning_message}")
            
            # 尝试诊断模型问题
            if len(task.models) == 0:
                all_models = db.query(task_crud.Model).limit(5).all()
                if not all_models:
                    additional_info = "系统中没有任何可用模型，请先配置模型"
                else:
                    available_model_ids = ", ".join([str(m.id) for m in all_models])
                    additional_info = f"系统中可用的模型ID有: {available_model_ids}"
                warning_message += f"。{additional_info}"
            
            # 返回错误信息
            return BaseResponse(
                path=str(request.url),
                success=False,
                code=400,
                message=warning_message
            )
        
        # 调用CRUD层的启动任务方法
        success, message = await task_crud.start_task(db, task_id)
        
        return BaseResponse(
            path=str(request.url),
            success=success,
            message=message
        )
    except Exception as e:
        logger.error(f"启动任务失败: {str(e)}")
        import traceback
        logger.error(f"详细错误: {traceback.format_exc()}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=f"启动任务失败: {str(e)}"
        )

@router.post("/stop", response_model=BaseResponse, summary="停止任务")
async def stop_task(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db)
):
    """
    停止任务
    
    参数:
    - task_id: 任务ID
    
    返回:
    - 停止操作结果
    """
    try:
        # 打印任务和子任务的ID关系
        task = db.query(task_crud.Task).options(joinedload(task_crud.Task.sub_tasks)).filter(task_crud.Task.id == task_id).first()
        if task:
            logger.info(f"准备停止任务 {task_id} (状态: {task.status})")
            logger.info(f"子任务情况: 总数={len(task.sub_tasks)}, 状态: {task.status}")
            
            # 打印每个子任务的ID和分析任务ID
            for idx, subtask in enumerate(task.sub_tasks):
                logger.info(f"子任务 {idx+1}/{len(task.sub_tasks)}: ID={subtask.id}, analysis_task_id={subtask.analysis_task_id}, 状态={subtask.status}")
                
        # 调用停止逻辑
        success, message = await task_crud.stop_task(db, task_id)
        
        return BaseResponse(
            path=str(request.url),
            success=success,
            message=message
        )
    except Exception as e:
        logger.error(f"停止任务失败: {str(e)}")
        return BaseResponse(
            path=str(request.url),
            success=False,
            code=500,
            message=str(e)
        )

