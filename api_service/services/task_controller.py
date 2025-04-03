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
            
            # 检查任务状态
            if task.status != "created" and task.status != "stopped":
                logger.error(f"任务 {task_id} 状态为 {task.status}，无法启动")
                return False
                
            # 检查子任务
            sub_tasks = db.query(SubTask).filter(SubTask.task_id == task_id).all()
            if not sub_tasks:
                logger.error(f"任务 {task_id} 没有子任务，无法启动")
                return False
            
            logger.info(f"开始启动任务 {task_id}，包含 {len(sub_tasks)} 个子任务")
                
            # 更新任务状态
            task.status = "running"
            task.started_at = datetime.now()
            task.error_message = None  # 清除错误信息
            task.active_subtasks = 0
            task.total_subtasks = len(sub_tasks)
            db.commit()
            
            # 逐个启动子任务
            successful_tasks = 0
            
            for sub_task in sub_tasks:
                try:
                    # 获取流和模型信息
                    stream = db.query(Stream).filter(Stream.id == sub_task.stream_id).first()
                    model = db.query(Model).filter(Model.id == sub_task.model_id).first()
                    
                    if not stream or not model:
                        logger.error(f"子任务 {sub_task.id} 关联的流或模型不存在")
                        continue
                    
                    # 为每个子任务分配节点
                    available_node = NodeCRUD.get_available_node(db)
                    if not available_node:
                        logger.error(f"子任务 {sub_task.id} 无可用节点，跳过")
                        continue
                    
                    # 更新子任务节点
                    sub_task.node_id = available_node.id
                    sub_task.status = "running"
                    sub_task.started_at = datetime.now()
                    sub_task.error_message = None
                    
                    # 更新节点任务计数
                    available_node.stream_task_count += 1
                    
                    # 构建节点URL
                    node_url = f"http://{available_node.ip}:{available_node.port}"
                    logger.info(f"子任务 {sub_task.id} 使用节点 {available_node.id}, URL: {node_url}")
                    
                    # 构建任务名称
                    task_name = f"{task.name}-{stream.name}-{model.name}"
                    
                    # 准备回调配置
                    callback_enabled = sub_task.enable_callback
                    callback_url = sub_task.callback_url if callback_enabled else None
                    
                    # 从子任务配置中提取分析配置
                    config = sub_task.config or {
                        "confidence": 0.5,
                        "iou": 0.45,
                        "classes": None,
                        "roi_type": 0,
                        "roi": None,
                        "nested_detection": True
                    }
                    
                    analysis_type = sub_task.analysis_type or "detection"
                    
                    # 使用httpx直接调用节点API
                    try:
                        async with httpx.AsyncClient() as client:
                            response = await client.post(
                                f"{node_url}/api/v1/analyze/stream",
                                json={
                                    "model_code": model.code,
                                    "stream_url": stream.url,
                                    "task_name": task_name,
                                    "callback_url": callback_url,
                                    "enable_callback": callback_enabled,
                                    "save_result": task.save_result,
                                    "config": config,
                                    "analysis_type": analysis_type
                                }
                            )
                            response.raise_for_status()
                            data = response.json()
                            sub_task.analysis_task_id = data.get("data", {}).get("task_id")
                            
                            logger.info(f"创建分析任务成功:")
                            logger.info(f"  - 子任务ID: {sub_task.id}")
                            logger.info(f"  - 任务名称: {task_name}")
                            logger.info(f"  - 分析任务ID: {sub_task.analysis_task_id}")
                            logger.info(f"  - 视频流: {stream.url}")
                            logger.info(f"  - 模型: {model.code}")
                            
                            # 标记子任务成功
                            successful_tasks += 1
                            
                    except Exception as e:
                        logger.error(f"调用节点API失败: {str(e)}")
                        # 回滚子任务状态
                        sub_task.status = "error"
                        sub_task.error_message = f"启动失败: {str(e)}"
                        # 回滚节点任务计数
                        available_node.stream_task_count -= 1
                except Exception as e:
                    logger.error(f"处理子任务 {sub_task.id} 失败: {str(e)}")
                    continue
            
            # 更新任务统计信息
            task.active_subtasks = successful_tasks
            
            if successful_tasks == 0:
                # 如果没有子任务启动成功，标记任务为错误状态
                task.status = "error"
                task.error_message = "所有子任务启动失败"
            elif successful_tasks < len(sub_tasks):
                # 如果部分子任务启动成功
                task.error_message = f"部分子任务启动成功 ({successful_tasks}/{len(sub_tasks)})"
            
            db.commit()
            
            logger.info(f"任务 {task_id} 启动完成，{successful_tasks}/{len(sub_tasks)} 个子任务启动成功")
            return successful_tasks > 0
            
        except Exception as e:
            logger.error(f"启动任务失败: {str(e)}")
            db.rollback()
            return False
            
    async def stop_task(self, db: Session, task_id: int) -> bool:
        """停止任务"""
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                logger.error(f"未找到任务 {task_id}")
                return False
            
            # 获取所有运行中的子任务
            sub_tasks = db.query(SubTask).filter(
                SubTask.task_id == task_id,
                SubTask.status == "running"
            ).all()
            
            if not sub_tasks:
                logger.warning(f"任务 {task_id} 没有运行中的子任务")
                # 如果任务仍处于运行状态，但没有运行中的子任务，更新主任务状态
                if task.status == "running":
                    task.status = "stopped"
                    task.active_subtasks = 0
                    db.commit()
                return True
            
            logger.info(f"正在停止任务 {task_id}，包含 {len(sub_tasks)} 个运行中的子任务")
            
            # 更新任务状态
            task.status = "stopping"
            db.commit()
            
            # 停止所有子任务
            stopped_count = 0
            for sub_task in sub_tasks:
                try:
                    # 获取节点信息
                    node = db.query(Node).filter(Node.id == sub_task.node_id).first()
                    if not node:
                        logger.warning(f"子任务 {sub_task.id} 没有关联节点，标记为已停止")
                        sub_task.status = "stopped"
                        sub_task.completed_at = datetime.now()
                        stopped_count += 1
                        continue
                    
                    # 构建节点URL
                    node_url = f"http://{node.ip}:{node.port}"
                    
                    # 调用节点API停止任务
                    try:
                        async with httpx.AsyncClient(timeout=10.0) as client:
                            stop_url = f"{node_url}/api/v1/analyze/stream/{sub_task.analysis_task_id}/stop"
                            logger.info(f"发送停止请求到节点 {node.id}: {stop_url}")
                            
                            response = await client.post(
                                stop_url,
                                headers={"accept": "application/json"}
                            )
                            response.raise_for_status()
                            result = response.json()
                            logger.info(f"停止子任务响应: {result}")
                    except Exception as e:
                        logger.warning(f"调用节点API停止子任务 {sub_task.id} 失败: {str(e)}")
                        # 即使API调用失败，也标记为已停止
                    
                    # 更新子任务状态
                    sub_task.status = "stopped"
                    sub_task.completed_at = datetime.now()
                    
                    # 更新节点任务计数
                    if node.stream_task_count > 0:
                        node.stream_task_count -= 1
                    
                    stopped_count += 1
                    
                except Exception as e:
                    logger.error(f"停止子任务 {sub_task.id} 失败: {str(e)}")
                    continue
            
            # 更新任务状态
            task.status = "stopped"
            task.active_subtasks = 0
            task.completed_at = datetime.now() if stopped_count == len(sub_tasks) else None
            
            db.commit()
            
            logger.info(f"任务 {task_id} 停止完成，{stopped_count}/{len(sub_tasks)} 个子任务成功停止")
            return True
            
        except Exception as e:
            logger.error(f"停止任务失败: {str(e)}")
            return False

    async def check_and_migrate_task(self, db: Session, task_id: int, target_node_id: int = None) -> bool:
        """
        检查任务并迁移故障子任务到其他节点
        
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
            if task.status != "running":
                logger.info(f"任务 {task_id} 不在运行状态，无需迁移")
                return False
                
            # 获取所有运行中的子任务及其节点信息
            sub_tasks_with_nodes = db.query(SubTask, Node)\
                .join(Node, SubTask.node_id == Node.id)\
                .filter(
                    SubTask.task_id == task_id,
                    SubTask.status == "running"
                ).all()
                
            if not sub_tasks_with_nodes:
                logger.info(f"任务 {task_id} 没有运行中的子任务，无需迁移")
                return False
                
            # 检查每个子任务的节点状态
            need_migration = []
            for sub_task, node in sub_tasks_with_nodes:
                if node.service_status != "online" or not node.is_active:
                    logger.info(f"子任务 {sub_task.id} 的节点 {node.id} 不在线或不活跃，需要迁移")
                    need_migration.append(sub_task)
                    
            if not need_migration:
                logger.info(f"任务 {task_id} 的所有子任务节点均正常，无需迁移")
                return False
                
            logger.info(f"任务 {task_id} 有 {len(need_migration)} 个子任务需要迁移")
            
            # 查找可用节点
            available_node = None
            if target_node_id:
                # 使用指定的节点
                available_node = db.query(Node).filter(
                    Node.id == target_node_id,
                    Node.service_status == "online",
                    Node.is_active == True
                ).first()
                
                if not available_node:
                    logger.error(f"指定的目标节点 {target_node_id} 不存在或不在线")
            
            # 逐个迁移子任务
            migrated_count = 0
            for sub_task in need_migration:
                # 为每个子任务单独获取节点
                if not available_node:
                    available_node = NodeCRUD.get_available_node(db)
                    
                if not available_node:
                    logger.error(f"无可用节点，无法迁移子任务 {sub_task.id}")
                    continue
                    
                try:
                    # 获取流和模型信息
                    stream = db.query(Stream).filter(Stream.id == sub_task.stream_id).first()
                    model = db.query(Model).filter(Model.id == sub_task.model_id).first()
                    
                    if not stream or not model:
                        logger.error(f"子任务 {sub_task.id} 关联的流或模型不存在")
                        continue
                    
                    # 获取旧节点信息
                    old_node = db.query(Node).filter(Node.id == sub_task.node_id).first()
                    old_node_id = old_node.id if old_node else None
                    
                    # 更新子任务节点
                    sub_task.node_id = available_node.id
                    
                    # 更新节点任务计数
                    if old_node and old_node.stream_task_count > 0:
                        old_node.stream_task_count -= 1
                    available_node.stream_task_count += 1
                    
                    # 停止原有子任务
                    if old_node_id:
                        logger.info(f"停止子任务 {sub_task.id} 在原节点 {old_node_id} 上的任务")
                        try:
                            # 尝试停止原有任务，但忽略失败
                            if old_node.service_status == "online" and sub_task.analysis_task_id:
                                old_node_url = f"http://{old_node.ip}:{old_node.port}"
                                try:
                                    async with httpx.AsyncClient(timeout=5.0) as client:
                                        stop_url = f"{old_node_url}/api/v1/analyze/stream/{sub_task.analysis_task_id}/stop"
                                        await client.post(stop_url, headers={"accept": "application/json"})
                                except:
                                    # 忽略停止失败
                                    pass
                        except:
                            # 忽略任何错误
                            pass
                    
                    # 构建节点URL和任务名称
                    node_url = f"http://{available_node.ip}:{available_node.port}"
                    task_name = f"{task.name}-{stream.name}-{model.name}"
                    
                    # 从子任务配置中提取所需配置
                    config = sub_task.config or {
                        "confidence": 0.5,
                        "iou": 0.45,
                        "classes": None,
                        "roi_type": 0,
                        "roi": None,
                        "nested_detection": True
                    }
                    
                    callback_enabled = sub_task.enable_callback
                    callback_url = sub_task.callback_url if callback_enabled else None
                    analysis_type = sub_task.analysis_type or "detection"
                    
                    # 创建新的分析任务
                    async with httpx.AsyncClient() as client:
                        response = await client.post(
                            f"{node_url}/api/v1/analyze/stream",
                            json={
                                "model_code": model.code,
                                "stream_url": stream.url,
                                "task_name": task_name,
                                "callback_url": callback_url,
                                "enable_callback": callback_enabled,
                                "save_result": task.save_result,
                                "config": config,
                                "analysis_type": analysis_type
                            }
                        )
                        response.raise_for_status()
                        data = response.json()
                        sub_task.analysis_task_id = data.get("data", {}).get("task_id")
                    
                    logger.info(f"迁移子任务 {sub_task.id} 成功，从节点 {old_node_id} 迁移到节点 {available_node.id}")
                    migrated_count += 1
                    
                except Exception as e:
                    logger.error(f"迁移子任务 {sub_task.id} 失败: {str(e)}")
                    # 标记子任务为错误状态
                    sub_task.status = "error"
                    sub_task.error_message = f"迁移失败: {str(e)}"
                    
                    # 更新节点任务计数
                    if available_node:
                        available_node.stream_task_count -= 1
                    
                    db.commit()
                    continue
                
                # 清除available_node以便为下一个子任务重新选择
                available_node = None
            
            # 提交所有更改
            db.commit()
            
            # 更新任务状态
            if migrated_count == 0 and len(need_migration) > 0:
                # 所有迁移都失败，更新任务状态
                updated = await self._update_task_status_from_subtasks(db, task_id)
                if updated:
                    logger.info(f"所有子任务迁移失败，已更新任务 {task_id} 状态")
            
            return migrated_count > 0
                
        except Exception as e:
            logger.error(f"检查和迁移任务 {task_id} 失败: {str(e)}")
            return False
            
    async def _update_task_status_from_subtasks(self, db: Session, task_id: int) -> bool:
        """
        根据子任务状态更新任务状态
        
        参数:
        - db: 数据库会话
        - task_id: 任务ID
        
        返回:
        - 是否成功更新
        """
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                return False
                
            # 获取子任务统计
            running_count = db.query(SubTask).filter(
                SubTask.task_id == task_id,
                SubTask.status == "running"
            ).count()
            
            error_count = db.query(SubTask).filter(
                SubTask.task_id == task_id,
                SubTask.status == "error"
            ).count()
            
            total_count = db.query(SubTask).filter(
                SubTask.task_id == task_id
            ).count()
            
            # 更新任务统计
            task.active_subtasks = running_count
            task.total_subtasks = total_count
            
            # 根据子任务状态更新任务状态
            if running_count == 0:
                if error_count == total_count:
                    # 所有子任务都出错
                    task.status = "error"
                    task.error_message = "所有子任务执行失败"
                elif error_count > 0:
                    # 部分子任务出错
                    task.status = "error"
                    task.error_message = f"部分子任务执行失败 ({error_count}/{total_count})"
                else:
                    # 所有子任务完成
                    task.status = "completed"
                    task.completed_at = datetime.now()
            elif error_count > 0:
                # 部分子任务出错，但仍有子任务运行
                task.error_message = f"部分子任务执行失败 ({error_count}/{total_count})"
            
            db.commit()
            return True
            
        except Exception as e:
            logger.error(f"更新任务状态失败: {str(e)}")
            return False