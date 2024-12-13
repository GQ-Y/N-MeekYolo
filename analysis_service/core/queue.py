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
        self.queue = asyncio.PriorityQueue()
        self.is_running = False
        self._task = None
        self.resource_monitor = ResourceMonitor()
        self.detector = YOLODetector()
        self.db = db
        
        # 任务处理超时时间(分钟)
        self.task_timeout = 30
        
    async def add_task(self, task: Task) -> TaskQueue:
        """添加任务到队列"""
        # 检查资源
        if not self.resource_monitor.has_available_resource():
            raise Exception("No available resources")
            
        # 创建队列任务记录
        queue_task = TaskQueue(
            id=str(uuid.uuid4()),
            task_id=task.id,
            priority=0,  # 默认优先级
            status=0,    # 等待中
            retry_count=0,
            created_at=datetime.now()
        )
        
        self.db.add(queue_task)
        self.db.commit()
        
        # 加入队列
        await self.queue.put((-queue_task.priority, queue_task.id))
        logger.info(f"Task {task.id} added to queue with queue_id {queue_task.id}")
        
        return queue_task
        
    async def start(self):
        """启动队列处理"""
        if not self.is_running:
            self.is_running = True
            self._task = asyncio.create_task(self._process_queue())
            # 启动监控任务
            asyncio.create_task(self._monitor_tasks())
            logger.info("Task queue started")
            
    async def stop(self):
        """停止队列处理"""
        if self.is_running:
            self.is_running = False
            if self._task:
                self._task.cancel()
            logger.info("Task queue stopped")
            
    async def _process_queue(self):
        """处理队列中的任务"""
        while self.is_running:
            try:
                if self.queue.empty():
                    await asyncio.sleep(1)
                    continue
                    
                # 获取队列中优先级最高的任务
                _, queue_task_id = await self.queue.get()
                queue_task = self.db.query(TaskQueue).filter(TaskQueue.id == queue_task_id).first()
                if not queue_task:
                    continue
                    
                # 获取原始任务
                task = self.db.query(Task).filter(Task.id == queue_task.task_id).first()
                if not task:
                    continue
                    
                # 更新状态为运行中
                queue_task.status = 1
                queue_task.started_at = datetime.now()
                self.db.commit()
                
                # 执行任务
                try:
                    await self.detector._process_stream(
                        task_id=queue_task.id,
                        stream_url=task.stream_url,
                        callback_urls=task.callback_urls
                    )
                    
                    # 更新资源使用情况
                    usage = self.resource_monitor.get_resource_usage()
                    queue_task.cpu_usage = usage["cpu_percent"]
                    queue_task.memory_usage = usage["memory_percent"]
                    queue_task.gpu_usage = usage["gpu_memory_percent"]
                    
                    # 任务完成
                    queue_task.status = 2
                    queue_task.completed_at = datetime.now()
                    
                except Exception as e:
                    # 任务失败
                    queue_task.status = -1
                    queue_task.error_message = str(e)
                    
                    # 检查是否需要重试
                    if RetryPolicy.should_retry(queue_task):
                        queue_task.retry_count = (queue_task.retry_count or 0) + 1
                        await RetryPolicy.wait_before_retry(queue_task.retry_count)
                        # 重新加入队列
                        await self.queue.put((-queue_task.priority, queue_task.id))
                        logger.info(f"Task {queue_task.id} scheduled for retry #{queue_task.retry_count}")
                    else:
                        logger.error(f"Task {queue_task.id} failed: {str(e)}")
                    
                finally:
                    self.db.commit()
                    
            except Exception as e:
                logger.error(f"Queue processing error: {str(e)}")
                await asyncio.sleep(1)
                
    async def _monitor_tasks(self):
        """监控任务状态"""
        while self.is_running:
            try:
                # 检查超时任务
                timeout_threshold = datetime.now() - timedelta(minutes=self.task_timeout)
                running_tasks = self.db.query(TaskQueue).filter(
                    TaskQueue.status == 1,
                    TaskQueue.started_at < timeout_threshold
                ).all()
                
                for task in running_tasks:
                    logger.warning(f"Task {task.id} timed out")
                    task.status = -1
                    task.error_message = "Task timed out"
                    
                    # 检查是否需要重试
                    if RetryPolicy.should_retry(task):
                        task.retry_count = (task.retry_count or 0) + 1
                        await RetryPolicy.wait_before_retry(task.retry_count)
                        # 重新加入队列
                        await self.queue.put((-task.priority, task.id))
                        logger.info(f"Timed out task {task.id} scheduled for retry #{task.retry_count}")
                        
                self.db.commit()
                
                # 更新资源使用统计
                self._update_resource_stats()
                
                await asyncio.sleep(60)  # 每分钟检查一次
                
            except Exception as e:
                logger.error(f"Task monitoring error: {str(e)}")
                await asyncio.sleep(60)
                
    def _update_resource_stats(self):
        """更新资源使用统计"""
        try:
            usage = self.resource_monitor.get_resource_usage()
            
            # 更新所有运行中任务的资源使用情况
            running_tasks = self.db.query(TaskQueue).filter(TaskQueue.status == 1).all()
            for task in running_tasks:
                task.cpu_usage = usage["cpu_percent"]
                task.memory_usage = usage["memory_percent"]
                task.gpu_usage = usage["gpu_memory_percent"]
                
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Update resource stats error: {str(e)}")
        
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

    async def cancel_task(self, queue_task_id: str):
        """取消任务"""
        queue_task = self.db.query(TaskQueue).filter(TaskQueue.id == queue_task_id).first()
        if not queue_task:
            raise Exception("Task not found")
            
        if queue_task.status == 0:  # 等待中
            # 从队列中移除
            queue_items = list(self.queue._queue)
            self.queue._queue = [item for item in queue_items if item[1] != queue_task_id]
            queue_task.status = -1
            queue_task.error_message = "Task cancelled"
            self.db.commit()
            logger.info(f"Cancelled pending task {queue_task_id}")
            
        elif queue_task.status == 1:  # 运行中
            # 停止检测任务
            await self.detector.stop_task(queue_task_id)
            queue_task.status = -1
            queue_task.error_message = "Task cancelled"
            self.db.commit()
            logger.info(f"Stopped running task {queue_task_id}")
