"""
任务控制服务
"""
import httpx
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from api_service.models.database import Task, Stream, Model, SubTask
from api_service.core.config import settings
from shared.utils.logger import setup_logger
from api_service.models.requests import StreamStatus
from datetime import datetime
from api_service.services.analysis import AnalysisService
from api_service.services.database import get_db
import asyncio

logger = setup_logger(__name__)

class TaskController:
    """任务控制器"""
    
    def __init__(self):
        self.analysis_service = AnalysisService()
        
    async def start_task(self, db: Session, task_id: int) -> bool:
        """启动任务"""
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                logger.error(f"未找到任务 {task_id}")
                return False
            
            logger.info(f"开始启动任务 {task_id}，包含 {len(task.streams)} 个视频流和 {len(task.models)} 个模型")
            
            # 更新任务状态
            task.status = "starting"
            task.started_at = datetime.now()
            
            # 构建回调URL列表
            callback_urls = ",".join([cb.url for cb in task.callbacks])
            logger.debug(f"回调URL列表: {callback_urls}")
            
            # 构建分析任务请求
            analysis_tasks = []
            for stream in task.streams:
                for model in task.models:
                    analysis_tasks.append({
                        "model_code": model.code,
                        "stream_url": stream.url,
                        "output_url": None
                    })
            
            analysis_request = {
                "tasks": analysis_tasks,
                "callback_urls": callback_urls,
                "callback_interval": task.callback_interval
            }
            
            logger.info(f"正在发送分析请求到 {self.analysis_service.analysis_url}/analyze/stream")
            logger.info(f"请求数据: {analysis_request}")
            
            try:
                # 调用Analysis Service创建分析任务
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.analysis_service.analysis_url}/analyze/stream",
                        json=analysis_request
                    )
                    response.raise_for_status()
                    result = response.json()
                    logger.info(f"分析服务原始响应: {response.text}")
                    logger.info(f"分析服务解析响应: {result}")
                    
                    # 保存父任务ID
                    parent_task_id = result["data"]["parent_task_id"]
                    logger.info(f"提取到父任务ID: {parent_task_id}")
                    task.analysis_task_id = parent_task_id
                    
                    # ���建子任务记录
                    sub_tasks = result["data"]["sub_tasks"]
                    logger.info(f"从响应中提取到 {len(sub_tasks)} 个子任务:")
                    for idx, st in enumerate(sub_tasks):
                        logger.info(f"子任务 {idx + 1}:")
                        logger.info(f"  - 任务ID: {st['task_id']}")
                        logger.info(f"  - 状态: {st['status']}")
                        logger.info(f"  - 视频流URL: {st['stream_url']}")
                        logger.info(f"  - 输出URL: {st['output_url']}")
                    
                    # 先提交父任务的更改
                    try:
                        db.flush()
                        logger.info(f"已提交父任务更:")
                        logger.info(f"  - 任务ID: {task.id}")
                        logger.info(f"  - 分析任务ID: {task.analysis_task_id}")
                        logger.info(f"  - 状态: {task.status}")
                    except Exception as e:
                        logger.error(f"提交父任务更改失败: {str(e)}", exc_info=True)
                        raise
                    
                    sub_tasks_to_create = []
                    for sub_task_info in result["data"]["sub_tasks"]:
                        try:
                            # 从URL中提取stream_id
                            stream_url = sub_task_info["stream_url"]
                            stream = next(s for s in task.streams if s.url == stream_url)
                            model = task.models[0]  # 假设每个流只使用一个模型
                            
                            logger.info(f"准备创建子任务:")
                            logger.info(f"  - 视频流ID: {stream.id}")
                            logger.info(f"  - 视频流URL: {stream_url}")
                            logger.info(f"  - 模型ID: {model.id}")
                            logger.info(f"  - 模型代码: {model.code}")
                            
                            # 创建子任务记录
                            sub_task = SubTask(
                                task_id=task.id,
                                analysis_task_id=sub_task_info["task_id"],
                                stream_id=stream.id,
                                model_id=model.id,
                                status="running",
                                started_at=datetime.now()
                            )
                            
                            # 添加到待创建列表
                            sub_tasks_to_create.append(sub_task)
                            logger.info(f"子任务详情:")
                            logger.info(f"  - 任务ID: {sub_task.task_id}")
                            logger.info(f"  - 分析任务ID: {sub_task.analysis_task_id}")
                            logger.info(f"  - 视频流ID: {sub_task.stream_id}")
                            logger.info(f"  - 模型ID: {sub_task.model_id}")
                            
                        except Exception as e:
                            logger.error(f"准备子任务失败，视频流URL: {stream_url}: {str(e)}", exc_info=True)
                            continue
                    
                    # 批量添加子任务
                    try:
                        logger.info(f"正在添加 {len(sub_tasks_to_create)} 个子任务到数据库")
                        db.bulk_save_objects(sub_tasks_to_create)
                        db.flush()
                        logger.info("子任务已成功提交")
                    except Exception as e:
                        logger.error("批量保存子任务失败", exc_info=True)
                        raise
                    
                    # 更新流状态
                    for stream in task.streams:
                        stream.status = "active"
                        logger.info(f"已更新���频流 {stream.id} 状态为活动")
                    
                    # 最终提交
                    try:
                        db.commit()
                        # 验证保存结果
                        saved_sub_tasks = db.query(SubTask).filter(SubTask.task_id == task_id).all()
                        logger.info(f"更改已成功提交。在数据库中找到 {len(saved_sub_tasks)} 个子任务")
                        for st in saved_sub_tasks:
                            logger.info(f"已保存的子任务:")
                            logger.info(f"  - ID: {st.id}")
                            logger.info(f"  - 任务ID: {st.task_id}")
                            logger.info(f"  - 分析任务ID: {st.analysis_task_id}")
                            logger.info(f"  - 视频流ID: {st.stream_id}")
                            logger.info(f"  - 模型ID: {st.model_id}")
                            logger.info(f"  - 状态: {st.status}")
                    except Exception as e:
                        db.rollback()
                        logger.error("提交更改失败", exc_info=True)
                        raise
                
            except Exception as e:
                logger.error(f"创建分析任务失败: {str(e)}")
                logger.error(f"请求详情: {analysis_request}")
                raise
                
            # 更新任务状态
            task.status = "running"
            db.commit()
            logger.info(f"任务 {task_id} 启动成功")
            
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"启动任务 {task_id} 失败: {str(e)}", exc_info=True)
            return False
            
    async def stop_task(self, db: Session, task_id: int) -> bool:
        """停止任务"""
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                logger.error(f"未找到任务 {task_id}")
                return False
            
            logger.info(f"正在停止任务 {task_id}，包含 {len(task.sub_tasks)} 个子任务")
            
            # 更新任务状态
            task.status = "stopping"
            db.commit()
            
            # 启动后台任务
            asyncio.create_task(self._stop_task_background(task_id))
            
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"停止任务 {task_id} 失败: {str(e)}", exc_info=True)
            return False

    async def _stop_task_background(self, task_id: int):
        """后台执行停止任务"""
        # 创建新的数据库会话
        db = next(get_db())
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                logger.error(f"未找到任务 {task_id}")
                return
            
            # 停止所有子任务
            stopped_sub_tasks = []  # 记录已停止的子任务
            for sub_task in task.sub_tasks:
                try:
                    if sub_task.status == "running":
                        logger.info(f"正在停止子任务:")
                        logger.info(f"  - 子任务ID: {sub_task.id}")
                        logger.info(f"  - 分析任务ID: {sub_task.analysis_task_id}")
                        
                        # 调用Analysis Service停止任务
                        try:
                            async with httpx.AsyncClient(timeout=10.0) as client:
                                stop_url = f"{self.analysis_service.analysis_url}/analyze/stream/{sub_task.analysis_task_id}/stop"
                                logger.info(f"发送停止请求到: {stop_url}")
                                
                                for retry in range(3):
                                    try:
                                        response = await client.post(
                                            stop_url,
                                            headers={"accept": "application/json"}
                                        )
                                        response.raise_for_status()
                                        result = response.json()
                                        logger.info(f"停止子任务响应: {result}")
                                        break
                                    except httpx.TimeoutException:
                                        if retry == 2:
                                            logger.warning(f"停止子任务请求超时，任务可能已停止: {sub_task.analysis_task_id}")
                                        else:
                                            logger.warning(f"停止子任务请求超时，正在重试: {retry + 1}/3")
                                            await asyncio.sleep(1)
                                    except httpx.HTTPError as e:
                                        if e.response.status_code == 404:
                                            logger.warning(f"子任务不存在或已停止: {sub_task.analysis_task_id}")
                                            break
                                        raise
                                
                            # 无论停止请求是否成功，都更新本地状态
                            sub_task.status = "stopped"
                            sub_task.completed_at = datetime.now()
                            logger.info(f"子任务 {sub_task.id} 已标记为停止")
                            
                            # 更新流状态
                            if sub_task.stream:
                                sub_task.stream.status = "inactive"
                                logger.info(f"已更新视频流 {sub_task.stream.id} 状��为非活动")
                            
                            # 添加到已停止列表
                            stopped_sub_tasks.append(sub_task)
                                
                        except Exception as e:
                            logger.error(f"调用分析服务停止子任务失败: {str(e)}", exc_info=True)
                            # 如果停止失败，回退状态
                            sub_task.status = "running"
                            sub_task.completed_at = None
                            if sub_task.stream:
                                sub_task.stream.status = "active"
                            db.commit()
                            continue
                    
                except Exception as e:
                    logger.error(f"停止子任务 {sub_task.id} 失败: {str(e)}", exc_info=True)
                    continue
                
            try:
                if stopped_sub_tasks:
                    # 删除已停止的子任务
                    for sub_task in stopped_sub_tasks:
                        logger.info(f"删除子任务: {sub_task.id}")
                        db.delete(sub_task)
                    
                    # 更新任务状态
                    task.status = "stopped"
                    task.completed_at = datetime.now()
                    
                    # 提交所有更改
                    db.commit()
                    
                    # 验证删除结果
                    remaining_sub_tasks = db.query(SubTask).filter(
                        SubTask.id.in_([st.id for st in stopped_sub_tasks])
                    ).all()
                    
                    if remaining_sub_tasks:
                        logger.warning(f"仍有 {len(remaining_sub_tasks)} 个子任务未被删除:")
                        for st in remaining_sub_tasks:
                            logger.warning(f"  - 子任务ID: {st.id}")
                    else:
                        logger.info("所有已停止的子任务已成功删除")
                else:
                    # 如果没有成功停止任何子任务，回退主任务状态
                    task.status = "running"
                    db.commit()
                    logger.warning(f"任务 {task_id} 停止失败，已回退状态")
                
                logger.info(f"任务 {task_id} 停止处理完成")
                
            except Exception as e:
                db.rollback()
                # 回退所有状态
                task.status = "running"
                for sub_task in stopped_sub_tasks:
                    sub_task.status = "running"
                    sub_task.completed_at = None
                    if sub_task.stream:
                        sub_task.stream.status = "active"
                db.commit()
                logger.error(f"提交任务停止更改失败，已回退状态: {str(e)}", exc_info=True)
                
        except Exception as e:
            db.rollback()
            logger.error(f"后台停止任务 {task_id} 失败: {str(e)}", exc_info=True)
            # 回退主任务状态
            try:
                task = db.query(Task).filter(Task.id == task_id).first()
                if task and task.status == "stopping":
                    task.status = "running"
                    db.commit()
            except Exception as e2:
                logger.error(f"回退任务状态失败: {str(e2)}", exc_info=True)
        finally:
            db.close()