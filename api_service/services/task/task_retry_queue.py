"""
任务重试队列模块
实现优先级重试队列和指数退避重试策略
"""
import time
import json
import asyncio
import threading
from typing import Dict, List, Any, Optional, Set, Tuple, Callable
from datetime import datetime, timedelta
import heapq
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class RetryTask:
    """重试任务对象"""
    
    def __init__(
        self,
        task_id: str,
        subtask_id: Optional[int] = None,
        priority: int = 5,
        retry_count: int = 0,
        max_retries: int = 3,
        retry_delay: float = 5.0,
        backoff_factor: float = 2.0,
        data: Optional[Dict[str, Any]] = None,
        next_retry_time: Optional[float] = None
    ):
        """
        初始化重试任务
        
        Args:
            task_id: 任务ID
            subtask_id: 子任务ID（可选）
            priority: 优先级（1-10，1为最高）
            retry_count: 当前重试次数
            max_retries: 最大重试次数
            retry_delay: 初始重试延迟（秒）
            backoff_factor: 退避因子，每次重试延迟时间乘以该因子
            data: 任务相关数据
            next_retry_time: 下次重试时间戳，为None表示立即重试
        """
        self.task_id = task_id
        self.subtask_id = subtask_id
        self.priority = priority
        self.retry_count = retry_count
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.backoff_factor = backoff_factor
        self.data = data or {}
        
        # 设置下次重试时间
        if next_retry_time is None:
            self.next_retry_time = time.time()
        else:
            self.next_retry_time = next_retry_time
            
        # 唯一ID
        self.id = f"{task_id}-{subtask_id}" if subtask_id else task_id
        
        # 创建时间
        self.created_at = time.time()
        
    def __lt__(self, other):
        """用于优先级队列排序"""
        if not isinstance(other, RetryTask):
            return NotImplemented
            
        # 首先按照下次重试时间排序
        if self.next_retry_time != other.next_retry_time:
            return self.next_retry_time < other.next_retry_time
            
        # 时间相同时按照优先级排序
        if self.priority != other.priority:
            return self.priority < other.priority
            
        # 优先级相同时按照创建时间排序
        return self.created_at < other.created_at
        
    def increment_retry(self) -> float:
        """
        增加重试计数并计算下次重试时间
        
        Returns:
            float: 下次重试时间戳
        """
        self.retry_count += 1
        
        # 计算指数退避延迟
        delay = self.retry_delay * (self.backoff_factor ** (self.retry_count - 1))
        
        # 设置下次重试时间
        self.next_retry_time = time.time() + delay
        
        return self.next_retry_time
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "subtask_id": self.subtask_id,
            "priority": self.priority,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "backoff_factor": self.backoff_factor,
            "next_retry_time": self.next_retry_time,
            "created_at": self.created_at,
            "data": self.data
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RetryTask':
        """从字典创建重试任务"""
        return cls(
            task_id=data.get("task_id", ""),
            subtask_id=data.get("subtask_id"),
            priority=data.get("priority", 5),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            retry_delay=data.get("retry_delay", 5.0),
            backoff_factor=data.get("backoff_factor", 2.0),
            data=data.get("data", {}),
            next_retry_time=data.get("next_retry_time")
        )
        
class TaskRetryQueue:
    """任务重试队列"""
    
    def __init__(
        self,
        check_interval: float = 1.0,
        persistence_interval: float = 30.0
    ):
        """
        初始化任务重试队列
        
        Args:
            check_interval: 检查间隔（秒）
            persistence_interval: 持久化间隔（秒）
        """
        # Redis管理器 - 延迟初始化
        self.redis = None
        
        # 优先级队列
        self.queue: List[RetryTask] = []
        
        # 任务ID到任务对象的映射
        self.task_map: Dict[str, RetryTask] = {}
        
        # 线程锁
        self.lock = threading.RLock()
        
        # 检查间隔
        self.check_interval = check_interval
        
        # 持久化间隔
        self.persistence_interval = persistence_interval
        
        # 上次持久化时间
        self.last_persistence = 0.0
        
        # 处理线程
        self.process_thread = None
        self.running = False
        
        # Redis键
        self.redis_key = "task_retry_queue"
        
        # 任务处理器
        self.task_handlers: Dict[str, Callable] = {}
        
    def _get_redis(self):
        """获取Redis管理器实例（延迟初始化）"""
        if self.redis is None:
            from core.redis_manager import RedisManager
            self.redis = RedisManager.get_instance()
        return self.redis
        
    async def start(self):
        """启动任务重试队列"""
        with self.lock:
            if self.running:
                logger.info("任务重试队列已经在运行中")
                return
                
            self.running = True
            
            # 启动处理线程，将加载操作移到处理线程内部执行
            self.process_thread = threading.Thread(
                target=self._process_worker,
                name="TaskRetryQueueProcessor",
                daemon=True
            )
            self.process_thread.start()
            
            logger.info(f"任务重试队列已启动，检查间隔: {self.check_interval}秒")
            
    async def stop(self):
        """停止任务重试队列"""
        with self.lock:
            if not self.running:
                return
                
            # 设置结束标志，处理线程会在下一次迭代中检测到并自行退出
            self.running = False
            
            # 等待处理线程结束
            if self.process_thread and self.process_thread.is_alive():
                logger.info("等待任务重试队列处理线程结束...")
                self.process_thread.join(timeout=2.0)
                
            logger.info("任务重试队列已停止")
            
    def register_handler(self, task_type: str, handler: Callable):
        """
        注册任务处理器
        
        Args:
            task_type: 任务类型
            handler: 处理函数，接收RetryTask作为参数
        """
        with self.lock:
            self.task_handlers[task_type] = handler
            logger.info(f"已注册任务处理器: {task_type}")
            
    def unregister_handler(self, task_type: str):
        """
        取消注册任务处理器
        
        Args:
            task_type: 任务类型
        """
        with self.lock:
            if task_type in self.task_handlers:
                self.task_handlers.pop(task_type)
                logger.info(f"已移除任务处理器: {task_type}")
                
    async def add_task(self, task: RetryTask) -> bool:
        """
        添加重试任务
        
        Args:
            task: 重试任务对象
            
        Returns:
            bool: 是否成功添加
        """
        with self.lock:
            # 检查是否已存在同ID任务
            if task.id in self.task_map:
                # 如果已存在，更新任务
                existing_task = self.task_map[task.id]
                
                # 如果新任务优先级更高，替换旧任务
                if task.priority < existing_task.priority:
                    # 移除旧任务
                    self.queue.remove(existing_task)
                    heapq.heapify(self.queue)
                    
                    # 添加新任务
                    heapq.heappush(self.queue, task)
                    self.task_map[task.id] = task
                    
                    logger.info(f"已更新任务优先级: {task.id}, 新优先级: {task.priority}")
                    
                return True
                
            # 添加新任务
            heapq.heappush(self.queue, task)
            self.task_map[task.id] = task
            
            logger.info(f"已添加重试任务: {task.id}, 优先级: {task.priority}, 计划重试时间: {datetime.fromtimestamp(task.next_retry_time).strftime('%Y-%m-%d %H:%M:%S')}")
            
            return True
            
    async def remove_task(self, task_id: str) -> bool:
        """
        移除重试任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            bool: 是否成功移除
        """
        with self.lock:
            if task_id in self.task_map:
                task = self.task_map[task_id]
                
                # 移除任务
                self.queue.remove(task)
                heapq.heapify(self.queue)
                
                # 从映射中移除
                self.task_map.pop(task_id)
                
                logger.info(f"已移除重试任务: {task_id}")
                
                return True
                
            return False
            
    async def get_task(self, task_id: str) -> Optional[RetryTask]:
        """
        获取重试任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            RetryTask: 重试任务对象
        """
        with self.lock:
            return self.task_map.get(task_id)
            
    async def get_all_tasks(self) -> List[RetryTask]:
        """
        获取所有重试任务
        
        Returns:
            List[RetryTask]: 重试任务列表
        """
        with self.lock:
            return list(self.queue)
            
    def _process_worker(self):
        """处理队列的工作线程"""
        logger.info("任务重试队列处理线程已启动")
        
        # 创建专用于此线程的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # 从Redis加载队列数据
            loop.run_until_complete(self._load_from_redis())
            
            # 标记首次持久化时间
            self.last_persistence = time.time()
            
            while self.running:
                try:
                    # 执行队列处理
                    loop.run_until_complete(self._process_queue())
                    
                    # 检查是否需要持久化
                    if time.time() - self.last_persistence > self.persistence_interval:
                        # 执行持久化
                        loop.run_until_complete(self._persist_to_redis())
                        self.last_persistence = time.time()
                    
                    # 等待下一次检查
                    time.sleep(self.check_interval)
                    
                except Exception as e:
                    logger.error(f"任务重试队列处理线程出错: {str(e)}")
        finally:
            # 线程结束前执行一次数据持久化
            try:
                loop.run_until_complete(self._persist_to_redis())
                logger.info("任务重试队列数据已在线程退出前持久化")
            except Exception as e:
                logger.error(f"线程退出时持久化队列数据失败: {str(e)}")
            
            # 确保关闭事件循环
            loop.close()
            
        logger.info("任务重试队列处理线程已停止")
        
    async def _process_queue(self):
        """处理队列中的任务"""
        current_time = time.time()
        
        with self.lock:
            # 没有任务，直接返回
            if not self.queue:
                return
                
            # 获取队首任务，但不移除
            task = self.queue[0]
            
            # 如果任务还没到重试时间，直接返回
            if task.next_retry_time > current_time:
                return
                
            # 弹出队首任务
            task = heapq.heappop(self.queue)
            
            # 从映射中移除
            self.task_map.pop(task.id, None)
            
        try:
            # 处理任务
            logger.info(f"处理重试任务: {task.id}, 重试次数: {task.retry_count}/{task.max_retries}")
            
            # 获取任务类型
            task_type = task.data.get("type", "default")
            
            # 查找处理器
            handler = self.task_handlers.get(task_type)
            
            if handler:
                # 调用处理器
                try:
                    result = handler(task)
                    # 如果处理器返回异步结果，等待完成
                    if asyncio.iscoroutine(result):
                        result = await result
                        
                    logger.info(f"任务处理成功: {task.id}")
                    
                except Exception as e:
                    logger.error(f"任务处理失败: {task.id}, 错误: {str(e)}")
                    
                    # 检查是否需要重试
                    if task.retry_count < task.max_retries:
                        # 增加重试计数并计算下次重试时间
                        next_retry_time = task.increment_retry()
                        
                        # 重新加入队列
                        with self.lock:
                            heapq.heappush(self.queue, task)
                            self.task_map[task.id] = task
                            
                        logger.info(f"任务已重新加入队列: {task.id}, 下次重试时间: {datetime.fromtimestamp(next_retry_time).strftime('%Y-%m-%d %H:%M:%S')}")
                    else:
                        logger.warning(f"任务已达到最大重试次数，放弃处理: {task.id}")
            else:
                logger.warning(f"未找到任务类型 '{task_type}' 的处理器，任务: {task.id}")
                
        except Exception as e:
            logger.error(f"处理任务出错: {str(e)}")
            
    async def _persist_to_redis(self):
        """将队列持久化到Redis"""
        try:
            with self.lock:
                # 将队列转换为列表
                tasks_data = []
                for task in self.queue:
                    tasks_data.append(task.to_dict())
                    
                # 保存到Redis (使用同步方法)
                success = self._get_redis().set_value_sync(self.redis_key, tasks_data)
                
                if success:
                    logger.debug(f"已将 {len(tasks_data)} 个任务持久化到Redis")
                else:
                    logger.error("持久化任务到Redis失败")
                
        except Exception as e:
            logger.error(f"持久化队列到Redis失败: {str(e)}")
            
    async def _load_from_redis(self):
        """从Redis加载队列"""
        try:
            # 从Redis获取数据 (使用同步方法)
            data = self._get_redis().get_value_sync(self.redis_key, as_json=True)
            
            if not data or not isinstance(data, list):
                logger.info("Redis中没有找到任务队列数据或数据无效")
                return
                
            # 清空当前队列
            with self.lock:
                self.queue = []
                self.task_map = {}
                
                # 加载任务
                for task_data in data:
                    task = RetryTask.from_dict(task_data)
                    heapq.heappush(self.queue, task)
                    self.task_map[task.id] = task
                    
                logger.info(f"从Redis加载了 {len(self.queue)} 个任务")
                
        except Exception as e:
            logger.error(f"从Redis加载队列失败: {str(e)}")
            
    @classmethod
    def get_instance(cls) -> 'TaskRetryQueue':
        """获取任务重试队列单例实例"""
        if not hasattr(cls, '_instance'):
            cls._instance = TaskRetryQueue()
        return cls._instance 