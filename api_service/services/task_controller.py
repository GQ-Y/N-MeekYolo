"""
任务控制服务
"""
import httpx
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from models.database import Task, Stream, Model, SubTask, Node
from core.config import settings
from shared.utils.logger import setup_logger
from models.requests import StreamStatus
from datetime import datetime
from services.analysis import AnalysisService
from services.database import get_db
import asyncio
from crud.node import NodeCRUD

logger = setup_logger(__name__)

class TaskController:
    """任务控制器"""
    
    def __init__(self):
        self.analysis_service = AnalysisService()
        
    def _get_api_url(self, path: str) -> str:
        """获取完整的API URL"""
        return self.analysis_service._get_api_url(path)
        
    async def start_task(self, db: Session, task_id: int) -> bool:
        """启动任务"""
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                logger.error(f"未找到任务 {task_id}")
                return False
            
            logger.info(f"开始启动任务 {task_id}，包含 {len(task.streams)} 个视频流和 {len(task.models)} 个模型")
            
            # 删除旧的子任务记录
            if task.sub_tasks:
                old_sub_tasks_count = len(task.sub_tasks)
                logger.info(f"删除任务 {task_id} 的 {old_sub_tasks_count} 个旧子任务记录")
                for sub_task in task.sub_tasks:
                    logger.info(f"删除子任务记录: ID={sub_task.id}, 分析任务ID={sub_task.analysis_task_id}")
                    db.delete(sub_task)
                db.commit()
                logger.info(f"旧子任务记录删除完成")
                
            # 更新任务状态
            task.status = "starting"
            task.started_at = datetime.now()
            task.error_message = None  # 清除错误信息
            
            # 构建回调URL列表
            callback_urls = ",".join([cb.url for cb in task.callbacks]) if task.callbacks else ""
            logger.debug(f"回调URL列表: {callback_urls}")
            
            # 获取任务配置，如果没有则使用默认值
            config = task.config or {
                "confidence": 0.1,
                "iou": 0.45,
                "nested_detection": True
            }
            
            # 获取节点信息
            node = task.node
            
            # 检查节点状态，如果节点不存在或不在线或未激活，则重新选择可用节点
            if not node or node.service_status != "online" or not node.is_active:
                if not node:
                    logger.warning(f"任务 {task_id} 未指定节点，尝试重新分配节点")
                else:
                    logger.warning(f"节点 {node.id} 不在线或未激活，尝试重新分配节点")
                
                # 使用负载均衡算法选择新节点
                available_node = NodeCRUD.get_available_node(db)
                
                if not available_node:
                    logger.error("无可用节点，任务启动失败")
                    task.status = "failed"
                    task.error_message = "无可用节点"
                    db.commit()
                    return False
                
                # 更新任务节点
                old_node_id = task.node_id
                task.node_id = available_node.id
                node = available_node
                
                logger.info(f"成功将任务 {task_id} 重新分配到节点 {node.id}")
                
                # 如果原节点存在，更新其任务计数
                if old_node_id:
                    old_node = db.query(Node).filter(Node.id == old_node_id).first()
                    if old_node:
                        stream_count = len(task.streams)
                        if old_node.stream_task_count >= stream_count:
                            old_node.stream_task_count -= stream_count
                        else:
                            old_node.stream_task_count = 0
                
                # 更新新节点的任务计数
                node.stream_task_count += len(task.streams)
                db.commit()
            
            # 构建节点URL
            node_url = f"http://{node.ip}:{node.port}"
            logger.info(f"使用节点 {node.id} URL: {node_url}")
            
            # 为每个视频流和模型组合创建分析任务
            sub_tasks_to_create = []
            for stream in task.streams:
                for model in task.models:
                    try:
                        # 调用分析服务创建任务
                        task_name = f"{task.name}-{stream.name}-{model.name}"
                        
                        # 使用httpx直接调用节点API
                        try:
                            async with httpx.AsyncClient() as client:
                                response = await client.post(
                                    f"{node_url}/api/v1/analyze/stream",
                                    json={
                                        "model_code": model.code,
                                        "stream_url": stream.url,
                                        "task_name": task_name,
                                        "callback_urls": callback_urls,
                                        "enable_callback": task.enable_callback and bool(callback_urls),
                                        "save_result": task.save_result,
                                        "config": config or {},
                                        "analysis_type": "detection"
                                    }
                                )
                                response.raise_for_status()
                                data = response.json()
                                analysis_task_id = data.get("data", {}).get("task_id")
                        except Exception as e:
                            logger.error(f"调用节点API失败: {str(e)}")
                            raise
                        
                        logger.info(f"创建分析任务成功:")
                        logger.info(f"  - 任务名称: {task_name}")
                        logger.info(f"  - 分析任务ID: {analysis_task_id}")
                        logger.info(f"  - 视频流: {stream.url}")
                        logger.info(f"  - 模型: {model.code}")
                        logger.info(f"  - 配置: {config}")
                        
                        # 创建子任务记录
                        sub_task = SubTask(
                            task_id=task.id,
                            analysis_task_id=analysis_task_id,
                            stream_id=stream.id,
                            model_id=model.id,
                            status="running",
                            started_at=datetime.now()
                        )
                        sub_tasks_to_create.append(sub_task)
                        
                    except Exception as e:
                        logger.error(f"创建分析任务失败: {str(e)}")
                        continue
            
            if not sub_tasks_to_create:
                logger.error("没有成功创建的子任务")
                task.status = "failed"
                db.commit()
                return False
            
            try:
                # 批量添加子任务
                db.bulk_save_objects(sub_tasks_to_create)
                
                # 更新流状态
                for stream in task.streams:
                    stream.status = 1  # 在线状态，使用整数1而不是字符串
                
                # 更新任务状态
                task.status = "running"
                
                # 提交所有更改
                db.commit()
                logger.info(f"任务 {task_id} 启动成功，创建了 {len(sub_tasks_to_create)} 个子任务")
                return True
                
            except Exception as e:
                db.rollback()
                logger.error(f"保存任务状态失败: {str(e)}")
                return False
            
        except Exception as e:
            logger.error(f"启动任务失败: {str(e)}")
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
                                stop_url = f"{self._get_api_url('/analyze/stream')}/{sub_task.analysis_task_id}/stop"
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
                                logger.info(f"已更新视频流 {sub_task.stream.id} 状态为非活动")
                            
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

    async def check_and_migrate_task(self, db: Session, task_id: int, target_node_id: int = None) -> bool:
        """
        检查任务并迁移到其他节点
        
        参数:
        - db: 数据库会话
        - task_id: 任务ID
        - target_node_id: 目标节点ID，如果不指定则自动选择
        
        返回:
        - 是否成功迁移
        """
        try:
            # 获取任务信息
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                logger.error(f"未找到任务 {task_id}")
                return False
                
            # 如果任务不在运行状态，不需要迁移
            if task.status not in ["running", "starting"]:
                logger.info(f"任务 {task_id} 不在运行状态，无需迁移")
                return False
                
            # 获取当前节点信息
            old_node = task.node
            if not old_node:
                logger.warning(f"任务 {task_id} 没有关联节点，无法迁移")
                return False
                
            # 如果当前节点在线，不需要迁移
            if old_node.service_status == "online" and old_node.is_active:
                logger.info(f"任务 {task_id} 当前节点 {old_node.id} 在线，无需迁移")
                return False
                
            # 记录旧节点ID
            old_node_id = old_node.id
                
            # 查找目标节点
            target_node = None
            if target_node_id:
                # 使用指定的节点
                target_node = db.query(Node).filter(
                    Node.id == target_node_id,
                    Node.service_status == "online",
                    Node.is_active == True
                ).first()
                
                if not target_node:
                    logger.error(f"指定的目标节点 {target_node_id} 不存在或不在线")
            
            if not target_node:
                # 使用负载均衡算法选择节点
                target_node = NodeCRUD.get_available_node(db)
                
            if not target_node:
                logger.error(f"无可用节点，任务 {task_id} 迁移失败")
                return False
                
            logger.info(f"开始将任务 {task_id} 从节点 {old_node_id} 迁移到节点 {target_node.id}")
            
            # 停止当前任务的子任务
            await self.stop_task(db, task_id)
            
            # 更新任务节点
            task.node_id = target_node.id
            
            # 更新节点任务计数
            stream_count = len(task.streams)
            
            # 减少旧节点的任务计数
            if old_node.stream_task_count >= stream_count:
                old_node.stream_task_count -= stream_count
            else:
                old_node.stream_task_count = 0
                
            # 增加新节点的任务计数
            target_node.stream_task_count += stream_count
            
            # 提交更改
            db.commit()
            
            # 重新启动任务
            result = await self.start_task(db, task_id)
            
            if result:
                logger.info(f"任务 {task_id} 已成功迁移到节点 {target_node.id}")
                return True
            else:
                logger.error(f"任务 {task_id} 迁移失败：无法在新节点上启动")
                return False
                
        except Exception as e:
            logger.error(f"迁移任务 {task_id} 失败: {str(e)}")
            return False