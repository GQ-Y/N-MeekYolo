"""
任务队列管理
"""
import asyncio
from typing import Optional
from datetime import datetime, timedelta
import uuid
from sqlalchemy.orm import Session
from analysis_service.models.database import Task, TaskQueue
from analysis_service.core.resource import ResourceMonitor
from analysis_service.core.detector import YOLODetector
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class RetryPolicy:
    """重试策略"""
    MAX_RETRIES = 3
    RETRY_DELAY = 5  # 秒
    
    @classmethod
    def should_retry(cls, task: TaskQueue) -> bool:
        """判断是否应该重试"""
        return (
            task.status == -1 and  # 失败状态
            (task.retry_count or 0) < cls.MAX_RETRIES
        )
        
    @classmethod
    async def wait_before_retry(cls, retry_count: int):
        """重试前等待"""
        delay = cls.RETRY_DELAY * (2 ** retry_count)  # 指数退避
        await asyncio.sleep(delay)

class TaskQueueManager:
    """任务队列管理器"""
    
    def __init__(self, db: Session):
        self.db = db
        self.detector = YOLODetector()
        self.resource_monitor = ResourceMonitor()
        self.running_tasks = {}  # 存储正在运行的任务
        self.max_concurrent = 3  # 最大并发数
        self.is_running = False  # 添加运行状态标志
        
    async def start(self):
        """启动队列管理器"""
        if not self.is_running:
            self.is_running = True
            # 检查并启动之前未完成的任务
            await self._recover_tasks()
            logger.info("Task queue manager started")
            
    async def stop(self):
        """停止队列管理器"""
        self.is_running = False
        # 停止所有运行中的任务
        for task_id in list(self.running_tasks.keys()):
            await self.cancel_task(task_id)
        logger.info("Task queue manager stopped")
        
    async def _recover_tasks(self):
        """恢复之前未完成的任务"""
        try:
            # 查找所有状态为运行中的任务
            running_tasks = self.db.query(TaskQueue).filter(
                TaskQueue.status == 1
            ).all()
            
            # 将这些任务状态重置为等待中
            for task in running_tasks:
                task.status = 0
                task.error_message = "Task reset after service restart"
            
            # 查找所有等待中的任务
            pending_tasks = self.db.query(TaskQueue).filter(
                TaskQueue.status == 0
            ).order_by(TaskQueue.created_at).all()
            
            self.db.commit()
            
            # 启动等待中的任务(考虑并发限制)
            for task in pending_tasks:
                if len(self.running_tasks) < self.max_concurrent:
                    asyncio.create_task(self._process_task(task))
                    
        except Exception as e:
            logger.error(f"Task recovery failed: {str(e)}")
            
    async def add_task(self, task: Task, parent_task_id: str = None) -> TaskQueue:
        """添加并立即执行任务"""
        # 检查资源
        if not self.resource_monitor.has_available_resource():
            raise Exception("No available resources")
            
        # 创建队列任务记录
        queue_task = TaskQueue(
            id=str(uuid.uuid4()),
            task_id=task.id,
            parent_task_id=parent_task_id,
            status=0,
            created_at=datetime.now()
        )
        self.db.add(queue_task)
        self.db.commit()
        
        # 检查当前运行任务数
        if len(self.running_tasks) >= self.max_concurrent:
            logger.warning("Max concurrent tasks reached, waiting...")
            return queue_task
            
        # 立即启动任务
        if self.is_running:  # 只有在管理器运行时才启动新任务
            asyncio.create_task(self._process_task(queue_task))
        
        return queue_task
        
    async def _process_task(self, queue_task: TaskQueue):
        """处理单个任务"""
        task_id = None
        try:
            if not queue_task:
                logger.error("队列任务对象为空")
                return
            
            task_id = queue_task.id
            
            # 重新获取任务对象，确保在当前session中
            queue_task = self.db.query(TaskQueue).filter(
                TaskQueue.id == task_id
            ).first()
            if not queue_task:
                logger.error(f"找不到队列任务: {task_id}")
                return
            
            task = self.db.query(Task).filter(Task.id == queue_task.task_id).first()
            if not task:
                logger.error(f"找不到关联的任务记录: {queue_task.task_id}")
                return
            
            # 更新状态
            queue_task.status = 1
            queue_task.started_at = datetime.now()
            self.db.commit()
            
            # 记录到运行中的任务，使用ID而不是对象
            self.running_tasks[task_id] = queue_task.task_id
            
            # 执行任务
            await self.detector.start_stream_analysis(
                task_id=task_id,
                stream_url=task.stream_url,
                callback_urls=task.callback_urls,
                parent_task_id=queue_task.parent_task_id
            )
            
            # 更新状态
            queue_task = self.db.query(TaskQueue).filter(
                TaskQueue.id == task_id
            ).first()
            if queue_task:
                queue_task.status = 2
                queue_task.completed_at = datetime.now()
                self.db.commit()
            
        except Exception as e:
            logger.error(f"任务处理失败: {str(e)}", exc_info=True)
            if task_id:
                queue_task = self.db.query(TaskQueue).filter(
                    TaskQueue.id == task_id
                ).first()
                if queue_task:
                    queue_task.status = -1
                    queue_task.error_message = str(e)
                    self.db.commit()
            
        finally:
            # 从运行中任务移除，使用安全的task_id
            if task_id:
                self.running_tasks.pop(task_id, None)
            
            # 检查等待中的任务
            try:
                await self._check_pending_tasks()
            except Exception as e:
                logger.error(f"检查待处理任务失败: {str(e)}", exc_info=True)
            
    async def _check_pending_tasks(self):
        """检查并启动等待中的任务"""
        if len(self.running_tasks) >= self.max_concurrent:
            return
            
        # 获取等待中的任务
        pending_tasks = self.db.query(TaskQueue).filter(
            TaskQueue.status == 0
        ).order_by(TaskQueue.created_at).limit(1).all()
        
        for task in pending_tasks:
            if len(self.running_tasks) < self.max_concurrent:
                asyncio.create_task(self._process_task(task))

    async def update_priority(self, queue_task_id: str, priority: int) -> TaskQueue:
        """更新任务优先级"""
        queue_task = self.db.query(TaskQueue).filter(TaskQueue.id == queue_task_id).first()
        if not queue_task:
            raise Exception("Task not found")
            
        # 只有等待中的任务可以修改优先级
        if queue_task.status != 0:
            raise Exception("Can only update priority for pending tasks")
            
        queue_task.priority = priority
        self.db.commit()
        
        # 重新加入队列以更新优先级
        await self.queue.put((-priority, queue_task_id))
        logger.info(f"Updated priority for task {queue_task_id} to {priority}")
        
        return queue_task

    async def get_task_status(self, queue_task_id: str) -> dict:
        """获取任务状态"""
        queue_task = self.db.query(TaskQueue).filter(TaskQueue.id == queue_task_id).first()
        if not queue_task:
            raise Exception("Task not found")
            
        # 获取队列中的位置
        position = None
        if queue_task.status == 0:  # 等待中
            queue_items = list(self.queue._queue)
            for i, (_, task_id) in enumerate(queue_items):
                if task_id == queue_task_id:
                    position = i + 1
                    break
                
        return {
            **queue_task.to_dict(),
            "queue_position": position
        }

    async def cancel_task(self, task_id: str):
        """取消任务"""
        try:
            # 停止检测任务
            await self.detector.stop_task(task_id)
            
            # 更新数据库状态
            queue_task = self.db.query(TaskQueue).filter(TaskQueue.id == task_id).first()
            if queue_task:
                # 如果是父任务，停止所有子任务
                if queue_task.parent_task_id is None:
                    sub_tasks = self.db.query(TaskQueue).filter(
                        TaskQueue.parent_task_id == queue_task.id
                    ).all()
                    for sub_task in sub_tasks:
                        await self.detector.stop_task(sub_task.id)
                        # 从运行中任务移除
                        self.running_tasks.pop(sub_task.id, None)
                        logger.info(f"子任务 {sub_task.id} 已停止")
                
                # 从运行中任务移除
                self.running_tasks.pop(task_id, None)
                logger.info(f"任务 {task_id} 已停止")
                
                # 检查等待中的任务
                await self._check_pending_tasks()
                
        except Exception as e:
            logger.error(f"停止任务失败: {str(e)}")
            raise
