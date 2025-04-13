"""
任务状态管理器
实现任务状态的计数器机制和批处理状态更新
"""
import json
import time
import asyncio
import threading
import enum
from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from core.database import SessionLocal
from core.redis_manager import RedisManager
from models.database import Task, SubTask
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class StatusFlag(enum.Enum):
    """任务状态标识"""
    PENDING = 0   # 未启动
    RUNNING = 1   # 运行中
    STOPPED = 2   # 已停止
    COMPLETED = 3 # 已完成
    ERROR = 4     # 出错

class TaskStatusManager:
    """
    任务状态管理器
    
    负责:
    1. 维护任务状态计数器
    2. 批量处理状态更新
    3. 确保数据库与缓存的状态一致性
    """
    
    def __init__(self, batch_update_interval: float = 0.1):
        """
        初始化任务状态管理器
        
        Args:
            batch_update_interval: 批量更新间隔(秒)
        """
        # Redis管理器
        self.redis = RedisManager.get_instance()
        
        # 批量更新间隔
        self.batch_update_interval = batch_update_interval
        
        # 待更新的任务ID集合
        self.pending_updates: Set[int] = set()
        
        # 等待更新的子任务状态
        self.pending_subtask_updates: Dict[int, Dict[str, int]] = {}
        
        # 线程锁
        self.lock = threading.RLock()
        
        # 批处理线程
        self.batch_thread = None
        self.running = False
        
        # 状态缓存键前缀
        self.task_status_prefix = "task:status:"
        self.subtask_status_prefix = "subtask:status:"
        
    async def start(self):
        """启动任务状态管理器"""
        with self.lock:
            if self.running:
                logger.info("任务状态管理器已经在运行中")
                return
                
            self.running = True
            
            # 启动批处理线程
            self.batch_thread = threading.Thread(
                target=self._batch_update_worker,
                name="TaskStatusBatchUpdater",
                daemon=True
            )
            self.batch_thread.start()
            
            logger.info(f"任务状态管理器已启动，批量更新间隔: {self.batch_update_interval}秒")
            
    async def stop(self):
        """停止任务状态管理器"""
        with self.lock:
            if not self.running:
                return
                
            self.running = False
            
            # 等待批处理线程结束
            if self.batch_thread and self.batch_thread.is_alive():
                logger.info("等待任务状态批处理线程结束...")
                self.batch_thread.join(timeout=2.0)
                
            # 执行最后一次批量更新
            await self._perform_batch_update()
                
            logger.info("任务状态管理器已停止")
            
    async def update_subtask_status(self, task_id: int, subtask_id: int, status: int):
        """
        更新子任务状态
        
        Args:
            task_id: 主任务ID
            subtask_id: 子任务ID
            status: 新状态
        """
        with self.lock:
            # 获取任务的当前状态计数
            counters = await self._get_task_status_counters(task_id)
            if not counters:
                logger.warning(f"任务 {task_id} 的状态计数器不存在，将初始化")
                counters = await self._initialize_task_counters(task_id)
                
            # 获取子任务当前状态
            old_status = await self._get_subtask_status(subtask_id)
            
            # 状态未变化，不需要更新
            if old_status == status:
                return
                
            # 减少旧状态计数
            if old_status is not None and old_status in counters:
                counters[old_status] = max(0, counters[old_status] - 1)
                
            # 增加新状态计数
            if status not in counters:
                counters[status] = 0
            counters[status] += 1
            
            # 保存子任务状态
            await self._set_subtask_status(subtask_id, status)
            
            # 保存任务状态计数
            await self._set_task_status_counters(task_id, counters)
            
            # 添加到待更新队列
            self.pending_updates.add(task_id)
            
            # 记录子任务更新信息
            if task_id not in self.pending_subtask_updates:
                self.pending_subtask_updates[task_id] = {}
            self.pending_subtask_updates[task_id][str(subtask_id)] = status
            
            logger.debug(f"子任务 {subtask_id} 状态从 {old_status} 更新为 {status}，任务 {task_id} 已加入待更新队列")
            
    async def get_task_status(self, task_id: int) -> Dict[str, Any]:
        """
        获取任务状态信息
        
        Args:
            task_id: 任务ID
            
        Returns:
            Dict: 任务状态信息，包含状态计数等
        """
        # 获取任务状态计数
        counters = await self._get_task_status_counters(task_id)
        if not counters:
            return {"error": "任务状态不存在"}
            
        # 计算主任务状态
        main_status = self._calculate_main_status(counters)
        
        return {
            "task_id": task_id,
            "status": main_status,
            "counters": counters
        }
        
    async def sync_from_database(self, task_id: int) -> bool:
        """
        从数据库同步任务状态到缓存
        
        Args:
            task_id: 任务ID
            
        Returns:
            bool: 是否成功
        """
        try:
            db = SessionLocal()
            try:
                # 查询任务及其子任务
                task = db.query(Task).filter(Task.id == task_id).first()
                if not task:
                    logger.error(f"任务 {task_id} 不存在，无法同步状态")
                    return False
                    
                subtasks = db.query(SubTask).filter(SubTask.task_id == task_id).all()
                
                # 初始化计数器
                counters = {
                    0: 0,  # 未启动
                    1: 0,  # 运行中
                    2: 0,  # 已停止
                    3: 0,  # 已完成
                    4: 0,  # 出错
                }
                
                # 统计子任务状态
                for subtask in subtasks:
                    # 保存子任务状态
                    await self._set_subtask_status(subtask.id, subtask.status)
                    
                    # 增加计数
                    if subtask.status in counters:
                        counters[subtask.status] += 1
                    else:
                        counters[subtask.status] = 1
                
                # 保存任务状态计数
                await self._set_task_status_counters(task_id, counters)
                
                logger.info(f"已从数据库同步任务 {task_id} 状态，子任务数: {len(subtasks)}")
                return True
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"从数据库同步任务状态失败: {str(e)}")
            return False
            
    def _batch_update_worker(self):
        """批量更新工作线程"""
        logger.info("任务状态批处理线程已启动")
        
        while self.running:
            try:
                # 执行批量更新
                asyncio.run(self._perform_batch_update())
                
                # 等待下一次更新
                time.sleep(self.batch_update_interval)
                
            except Exception as e:
                logger.error(f"任务状态批处理线程出错: {str(e)}")
                
        logger.info("任务状态批处理线程已停止")
        
    async def _perform_batch_update(self):
        """执行批量更新操作"""
        # 复制待更新集合，避免处理过程中的修改
        with self.lock:
            task_ids = list(self.pending_updates)
            subtask_updates = self.pending_subtask_updates.copy()
            
            # 清空待更新集合
            self.pending_updates.clear()
            self.pending_subtask_updates.clear()
            
        if not task_ids:
            return
            
        logger.debug(f"开始批量更新 {len(task_ids)} 个任务的状态")
        
        try:
            db = SessionLocal()
            try:
                # 逐个更新任务状态
                for task_id in task_ids:
                    await self._update_task_in_database(db, task_id, subtask_updates.get(task_id, {}))
                    
                # 提交事务
                db.commit()
                logger.debug(f"批量更新完成，成功更新 {len(task_ids)} 个任务")
                
            except Exception as e:
                db.rollback()
                logger.error(f"批量更新任务状态失败: {str(e)}")
                
                # 将失败的任务重新加入队列
                with self.lock:
                    self.pending_updates.update(task_ids)
                    for task_id, updates in subtask_updates.items():
                        if task_id not in self.pending_subtask_updates:
                            self.pending_subtask_updates[task_id] = {}
                        self.pending_subtask_updates[task_id].update(updates)
                        
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"执行批量更新时出错: {str(e)}")
            
    async def _update_task_in_database(self, db: Session, task_id: int, subtask_updates: Dict[str, int]):
        """
        在数据库中更新任务状态
        严格遵循MQTT响应机制更新状态
        
        Args:
            db: 数据库会话
            task_id: 任务ID
            subtask_updates: 子任务状态更新字典
        """
        try:
            # 获取任务
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                logger.warning(f"任务 {task_id} 不存在，无法更新状态")
                return
                
            # 获取状态计数
            counters = await self._get_task_status_counters(task_id)
            if not counters:
                logger.warning(f"任务 {task_id} 的状态计数器不存在")
                return
                
            # 更新子任务状态
            for subtask_id_str, status in subtask_updates.items():
                try:
                    subtask_id = int(subtask_id_str)
                    subtask = db.query(SubTask).filter(SubTask.id == subtask_id).first()
                    if subtask:
                        subtask.status = status
                        subtask.updated_at = datetime.now()
                except (ValueError, Exception) as e:
                    logger.error(f"更新子任务 {subtask_id_str} 状态失败: {str(e)}")
                
            # 计算主任务状态
            main_status = self._calculate_main_status(counters)
            
            # 获取活跃子任务数
            active_subtasks = counters.get(1, 0)  # 状态为1表示运行中
            
            # 获取总子任务数
            total_subtasks = sum(counters.values())
            
            # 更新主任务状态 - 严格按照MQTT响应模式
            logger.debug(f"任务 {task_id} 当前状态: {task.status}, 计算状态: {main_status}, 运行中子任务: {active_subtasks}/{total_subtasks}")
            
            # 更新任务状态
            task.status = main_status
            
            # 更新活跃子任务数量
            task.active_subtasks = active_subtasks
            task.total_subtasks = total_subtasks
            task.updated_at = datetime.now()
            
            # 根据主任务状态更新错误消息
            if main_status == 2 and active_subtasks == 0:
                # 所有子任务都不是运行中状态，且主任务为停止状态
                task.error_message = "所有子任务已停止，任务已完成"
                task.completed_at = datetime.now()
                logger.info(f"任务 {task_id} 所有子任务已停止，已更新主任务状态为已停止")
            elif main_status == 1:
                # 主任务运行中
                if task.error_message == "所有子任务已停止，任务已完成":
                    task.error_message = None  # 清除之前的停止消息
            
            logger.debug(f"更新任务 {task_id} 状态为 {task.status}，活跃子任务: {active_subtasks}/{total_subtasks}")
            
        except Exception as e:
            logger.error(f"更新任务 {task_id} 状态到数据库失败: {str(e)}")
            raise
            
    def _calculate_main_status(self, counters: Dict[int, int]) -> int:
        """
        根据子任务状态计数计算主任务状态
        遵循严格的MQTT响应机制：
        - 如果有任何运行中的子任务，主任务状态为运行中(1)
        - 如果没有运行中的子任务，主任务状态为已停止(2)
        
        Args:
            counters: 状态计数字典
            
        Returns:
            int: 主任务状态
        """
        # 获取运行中的子任务数量
        running_count = counters.get(1, 0)  # 状态为1表示运行中
        
        if running_count > 0:
            # 只要有运行中的子任务，主任务状态为运行中
            return 1
        else:
            # 如果没有运行中的子任务，主任务状态为已停止
            return 2
            
    async def _get_task_status_counters(self, task_id: int) -> Dict[int, int]:
        """
        获取任务状态计数
        
        Args:
            task_id: 任务ID
            
        Returns:
            Dict: 状态计数字典
        """
        key = f"{self.task_status_prefix}{task_id}"
        value = await self.redis.get_value(key, as_json=True)
        if value and isinstance(value, dict):
            # 将字符串键转为整数键
            return {int(k): v for k, v in value.items()}
        return {}
        
    async def _set_task_status_counters(self, task_id: int, counters: Dict[int, int]):
        """
        设置任务状态计数
        
        Args:
            task_id: 任务ID
            counters: 状态计数字典
        """
        key = f"{self.task_status_prefix}{task_id}"
        await self.redis.set_value(key, counters)
        
    async def _get_subtask_status(self, subtask_id: int) -> Optional[int]:
        """
        获取子任务状态
        
        Args:
            subtask_id: 子任务ID
            
        Returns:
            int: 子任务状态
        """
        key = f"{self.subtask_status_prefix}{subtask_id}"
        value = await self.redis.get_value(key)
        return int(value) if value is not None else None
        
    async def _set_subtask_status(self, subtask_id: int, status: int):
        """
        设置子任务状态
        
        Args:
            subtask_id: 子任务ID
            status: 状态值
        """
        key = f"{self.subtask_status_prefix}{subtask_id}"
        await self.redis.set_value(key, str(status))
        
    async def _initialize_task_counters(self, task_id: int) -> Dict[int, int]:
        """
        初始化任务状态计数
        
        Args:
            task_id: 任务ID
            
        Returns:
            Dict: 初始状态计数字典
        """
        # 创建默认计数器
        counters = {
            0: 0,  # 未启动
            1: 0,  # 运行中
            2: 0,  # 已停止
            3: 0,  # 已完成
            4: 0,  # 出错
        }
        
        # 保存到Redis
        await self._set_task_status_counters(task_id, counters)
        
        return counters

    @classmethod
    def get_instance(cls) -> 'TaskStatusManager':
        """获取任务状态管理器单例实例"""
        if not hasattr(cls, '_instance'):
            cls._instance = TaskStatusManager()
        return cls._instance 