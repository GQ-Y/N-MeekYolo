"""
任务队列管理
"""
import asyncio
from typing import Optional, Tuple, Dict
from datetime import datetime, timedelta
import uuid
from sqlalchemy.orm import Session
from analysis_service.models.database import Task, TaskQueue
from analysis_service.core.resource import ResourceMonitor
from analysis_service.core.detector import YOLODetector
from shared.utils.logger import setup_logger
from analysis_service.crud import task as task_crud
from analysis_service.models.analysis_type import AnalysisType
from analysis_service.services.database import get_db

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
                    asyncio.create_task(self._process_task(task.id))
                    
        except Exception as e:
            logger.error(f"Task recovery failed: {str(e)}")
            
    async def add_task(
        self, 
        task: Task,
        parent_task_id: str = None,
        analyze_interval: int = None,
        alarm_interval: int = None,
        random_interval: Tuple[int, int] = None,
        confidence_threshold: float = None,
        push_interval: int = None
    ) -> TaskQueue:
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
        
        # 保存任务ID而不是对象
        task_id = queue_task.id
        
        # 检查当前运行任务数
        if len(self.running_tasks) >= self.max_concurrent:
            logger.warning("Max concurrent tasks reached, waiting...")
            return queue_task
            
        # 立即启动任务，传递task_id而不是对象
        if self.is_running:  # 只有在管理器运行时才启动新任务
            asyncio.create_task(self._process_task(
                task_id,  # 传递ID而不是对象
                analyze_interval=analyze_interval,
                alarm_interval=alarm_interval,
                random_interval=random_interval,
                confidence_threshold=confidence_threshold,
                push_interval=push_interval
            ))
        
        return queue_task
        
    async def _process_task(
        self,
        task_id: str,  # 修改参数类型为str
        analyze_interval: int = None,
        alarm_interval: int = None,
        random_interval: Tuple[int, int] = None,
        confidence_threshold: float = None,
        push_interval: int = None
    ):
        """处理单个任务"""
        db = None
        try:
            # 使用新的session处理数据库操作
            db = get_db()
            
            # 获取任务对象
            queue_task = db.query(TaskQueue).filter(
                TaskQueue.id == task_id
            ).first()
            if not queue_task:
                logger.error(f"找不到队列任务: {task_id}")
                return
            
            task = db.query(Task).filter(Task.id == queue_task.task_id).first()
            if not task:
                logger.error(f"找不到关联的任务记录: {queue_task.task_id}")
                return
            
            # 更新状态
            queue_task.status = 1
            queue_task.started_at = datetime.now()
            db.commit()
            
            # 记录到运行中的任务
            self.running_tasks[task_id] = queue_task.task_id
            
            # 构建配置字典
            config = {}
            if confidence_threshold is not None:
                config['confidence_threshold'] = confidence_threshold
            
            # 执行任务
            await self.detector.start_stream_analysis(
                task_id=task_id,
                stream_url=task.stream_url,
                model_code=task.model_code,
                callback_urls=task.callback_urls,
                analyze_interval=analyze_interval,
                alarm_interval=alarm_interval,
                random_interval=random_interval,
                config=config,
                push_interval=push_interval
            )
            
            # 更新状态
            queue_task = db.query(TaskQueue).filter(
                TaskQueue.id == task_id
            ).first()
            if queue_task:
                queue_task.status = 2
                queue_task.completed_at = datetime.now()
                db.commit()
                
        except Exception as e:
            logger.error(f"任务处理失败: {str(e)}", exc_info=True)
            if task_id:
                try:
                    if not db:
                        db = get_db()
                    queue_task = db.query(TaskQueue).filter(
                        TaskQueue.id == task_id
                    ).first()
                    if queue_task:
                        queue_task.status = -1
                        queue_task.error_message = str(e)
                        db.commit()
                except Exception as inner_e:
                    logger.error(f"更新任务状态失败: {str(inner_e)}", exc_info=True)
        
        finally:
            # 关闭数据库连接
            if db:
                db.close()
            
            # 清理运行中的任务记录
            if task_id and task_id in self.running_tasks:
                del self.running_tasks[task_id]
            
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
                asyncio.create_task(self._process_task(task.id))

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
        
        # 重新添加队列以更新优先级
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

    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        try:
            # 1. 确认任务是否在运行
            if not await self.is_task_running(task_id):
                logger.warning(f"任务 {task_id} 不在运行状态")
                return True
            
            # 2. 停止检测任务
            stop_result = await self.detector.stop_task(task_id)
            if not stop_result:
                raise Exception(f"停止检测任务失败")
            
            # 3. 等待任务实际停止
            for _ in range(10):  # 最多等待5秒
                if not await self.is_task_running(task_id):
                    break
                await asyncio.sleep(0.5)
            
            # 4. 从运行中任务列表移除
            self.running_tasks.pop(task_id, None)
            logger.info(f"任务 {task_id} 已从运行列表移除")
            
            return True
        
        except Exception as e:
            logger.error(f"取消任务失败: {str(e)}", exc_info=True)
            raise

    async def is_task_running(self, task_id: str) -> bool:
        """检查任务是否在运行"""
        return task_id in self.running_tasks

    async def stop_task(self, task_id: str) -> bool:
        """停止任务（cancel_task的别名）"""
        return await self.cancel_task(task_id)

    async def create_stream_task(
        self,
        task_id: str,
        model_code: str,
        stream_url: str,
        analysis_type: AnalysisType,
        callback_urls: Optional[str] = None,
        config: Optional[Dict] = None,
        task_name: Optional[str] = None,
        enable_callback: bool = True,
        save_result: bool = False
    ) -> Task:
        """创建流分析任务
        
        Args:
            task_id: 任务ID
            model_code: 模型代码
            stream_url: 流URL
            analysis_type: 分析类型
            callback_urls: 回调地址，多个用逗号分隔
            config: 分析配置
            task_name: 任务名称
            enable_callback: 是否启用回调
            save_result: 是否保存结果
            
        Returns:
            Task: 创建的任务对象
        """
        try:
            # 检查资源
            if not self.resource_monitor.has_available_resource():
                raise Exception("资源不足")
            
            # 创建任务记录
            task = task_crud.create_task(
                db=self.db,
                task_id=task_id,
                model_code=model_code,
                stream_url=stream_url,
                callback_urls=callback_urls if enable_callback else None
            )
            
            # 更新任务信息
            task.task_name = task_name or f"流分析-{task_id}"
            task.analysis_type = analysis_type
            task.config = config
            task.enable_callback = enable_callback
            task.save_result = save_result
            task.status = 0  # 等待中
            task.start_time = datetime.now()
            self.db.commit()
            
            # 创建队列任务
            queue_task = await self.add_task(
                task=task,
                analyze_interval=config.get("analyze_interval") if config else None,
                alarm_interval=config.get("alarm_interval") if config else None,
                random_interval=config.get("random_interval") if config else None,
                confidence_threshold=config.get("confidence") if config else None,
                push_interval=config.get("push_interval") if config else None
            )
            
            logger.info(f"流分析任务创建成功: {task_id}")
            return task
            
        except Exception as e:
            logger.error(f"创建流分析任务失败: {str(e)}", exc_info=True)
            raise
