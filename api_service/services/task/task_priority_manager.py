#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Any, Set
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from fastapi import Depends

from models.database import MQTTNode, SubTask, Task
from core.database import SessionLocal

# 配置日志
logger = logging.getLogger(__name__)

class TaskPriorityManager:
    """
    任务优先级管理器
    用于管理和分配MQTT任务的优先级，确保重要任务优先处理
    """
    
    def __init__(self):
        """初始化任务优先级管理器"""
        self.priority_queue: Dict[int, List[Dict[str, Any]]] = {
            0: [],  # 低优先级
            1: [],  # 正常优先级
            2: [],  # 高优先级
            3: []   # 紧急优先级
        }
        self.task_priorities: Dict[str, int] = {}  # 记录任务ID到优先级的映射
        self.waiting_tasks: Dict[str, Dict[str, Any]] = {}  # 等待分配的任务，键为subtask_id
        self.lock = asyncio.Lock()  # 异步锁，确保任务队列操作的原子性
        self.last_cleanup = time.time()
        
    async def add_task(self, task_id: str, subtask_id: str, priority: int = 1, 
                      task_data: Dict[str, Any] = None) -> None:
        """
        添加任务到优先级队列
        
        Args:
            task_id: 任务ID
            subtask_id: 子任务ID
            priority: 优先级(0=低, 1=正常, 2=高, 3=紧急)
            task_data: 任务相关数据
        """
        if priority not in self.priority_queue:
            logger.warning(f"无效的优先级: {priority}，使用默认优先级1")
            priority = 1
            
        # 规范化任务数据
        if task_data is None:
            task_data = {}
            
        task_entry = {
            "task_id": task_id,
            "subtask_id": subtask_id,
            "priority": priority,
            "timestamp": time.time(),
            "attempts": 0,
            "data": task_data
        }
        
        task_key = f"{task_id}_{subtask_id}"
        
        async with self.lock:
            # 检查任务是否已在队列中，如果是则移除旧条目
            if task_key in self.task_priorities:
                old_priority = self.task_priorities[task_key]
                self.priority_queue[old_priority] = [
                    t for t in self.priority_queue[old_priority] 
                    if t["task_id"] != task_id or t["subtask_id"] != subtask_id
                ]
            
            # 添加任务到相应的优先级队列
            self.priority_queue[priority].append(task_entry)
            self.task_priorities[task_key] = priority
            self.waiting_tasks[subtask_id] = task_entry
            
            logger.info(f"任务 {task_id}/{subtask_id} 已添加到优先级 {priority} 队列")
            
            # 定期清理过期任务
            await self._cleanup_old_tasks()
    
    async def get_next_task(self) -> Optional[Dict[str, Any]]:
        """
        获取下一个要处理的任务，按优先级从高到低
        
        Returns:
            Optional[Dict[str, Any]]: 任务数据，如果没有任务则返回None
        """
        async with self.lock:
            # 从高优先级到低优先级查找任务
            for priority in sorted(self.priority_queue.keys(), reverse=True):
                if self.priority_queue[priority]:
                    # 获取队列中最老的任务
                    task = self.priority_queue[priority][0]
                    self.priority_queue[priority].pop(0)
                    
                    # 从映射中移除
                    task_key = f"{task['task_id']}_{task['subtask_id']}"
                    if task_key in self.task_priorities:
                        del self.task_priorities[task_key]
                    
                    if task['subtask_id'] in self.waiting_tasks:
                        del self.waiting_tasks[task['subtask_id']]
                    
                    logger.info(f"选择优先级 {priority} 的任务 {task['task_id']}/{task['subtask_id']} 进行处理")
                    return task
                    
            # 所有队列都为空
            return None
    
    async def remove_task(self, task_id: str, subtask_id: str) -> bool:
        """
        从优先级队列中移除任务
        
        Args:
            task_id: 任务ID
            subtask_id: 子任务ID
            
        Returns:
            bool: 是否成功移除
        """
        task_key = f"{task_id}_{subtask_id}"
        removed = False
        
        async with self.lock:
            if task_key in self.task_priorities:
                priority = self.task_priorities[task_key]
                
                # 移除任务
                self.priority_queue[priority] = [
                    t for t in self.priority_queue[priority] 
                    if t["task_id"] != task_id or t["subtask_id"] != subtask_id
                ]
                
                # 移除映射
                del self.task_priorities[task_key]
                
                if subtask_id in self.waiting_tasks:
                    del self.waiting_tasks[subtask_id]
                    
                removed = True
                logger.info(f"任务 {task_id}/{subtask_id} 已从优先级 {priority} 队列移除")
            else:
                logger.warning(f"任务 {task_id}/{subtask_id} 不在优先级队列中")
                
        return removed
    
    async def update_task_priority(self, task_id: str, subtask_id: str, new_priority: int) -> bool:
        """
        更新任务的优先级
        
        Args:
            task_id: 任务ID
            subtask_id: 子任务ID
            new_priority: 新的优先级
            
        Returns:
            bool: 是否成功更新
        """
        if new_priority not in self.priority_queue:
            logger.warning(f"无效的优先级: {new_priority}")
            return False
            
        task_key = f"{task_id}_{subtask_id}"
        
        async with self.lock:
            if task_key in self.task_priorities:
                old_priority = self.task_priorities[task_key]
                
                # 找到并移除旧队列中的任务
                for idx, task in enumerate(self.priority_queue[old_priority]):
                    if task["task_id"] == task_id and task["subtask_id"] == subtask_id:
                        task_entry = self.priority_queue[old_priority].pop(idx)
                        
                        # 更新优先级并添加到新队列
                        task_entry["priority"] = new_priority
                        self.priority_queue[new_priority].append(task_entry)
                        self.task_priorities[task_key] = new_priority
                        
                        if subtask_id in self.waiting_tasks:
                            self.waiting_tasks[subtask_id] = task_entry
                            
                        logger.info(f"任务 {task_id}/{subtask_id} 优先级已从 {old_priority} 更新为 {new_priority}")
                        return True
                        
                logger.warning(f"在优先级 {old_priority} 队列中未找到任务 {task_id}/{subtask_id}")
            else:
                logger.warning(f"任务 {task_id}/{subtask_id} 不在优先级队列中")
                
        return False
    
    async def get_queue_status(self) -> Dict[str, Any]:
        """
        获取队列状态统计信息
        
        Returns:
            Dict[str, Any]: 队列状态信息
        """
        async with self.lock:
            status = {
                "total_tasks": sum(len(queue) for queue in self.priority_queue.values()),
                "queues": {
                    priority: len(queue) 
                    for priority, queue in self.priority_queue.items()
                },
                "oldest_task_age": None,
                "newest_task_age": None
            }
            
            # 计算最老和最新任务的年龄
            current_time = time.time()
            all_timestamps = [
                task["timestamp"] 
                for queue in self.priority_queue.values() 
                for task in queue
            ]
            
            if all_timestamps:
                oldest = min(all_timestamps)
                newest = max(all_timestamps)
                status["oldest_task_age"] = round(current_time - oldest, 2)
                status["newest_task_age"] = round(current_time - newest, 2)
                
        return status
    
    async def mark_task_attempt(self, task_id: str, subtask_id: str) -> int:
        """
        标记任务尝试次数，并返回更新后的尝试次数
        
        Args:
            task_id: 任务ID
            subtask_id: 子任务ID
            
        Returns:
            int: 更新后的尝试次数，如果任务不存在则返回-1
        """
        task_key = f"{task_id}_{subtask_id}"
        
        async with self.lock:
            if task_key in self.task_priorities:
                priority = self.task_priorities[task_key]
                
                # 查找并更新任务尝试次数
                for task in self.priority_queue[priority]:
                    if task["task_id"] == task_id and task["subtask_id"] == subtask_id:
                        task["attempts"] += 1
                        
                        if subtask_id in self.waiting_tasks:
                            self.waiting_tasks[subtask_id]["attempts"] = task["attempts"]
                            
                        logger.info(f"任务 {task_id}/{subtask_id} 尝试次数增加到 {task['attempts']}")
                        return task["attempts"]
            
            logger.warning(f"任务 {task_id}/{subtask_id} 不在优先级队列中，无法标记尝试")
            return -1
    
    async def is_task_in_queue(self, task_id: str, subtask_id: str) -> bool:
        """
        检查任务是否在队列中
        
        Args:
            task_id: 任务ID
            subtask_id: 子任务ID
            
        Returns:
            bool: 任务是否在队列中
        """
        task_key = f"{task_id}_{subtask_id}"
        
        async with self.lock:
            return task_key in self.task_priorities
    
    async def get_task_by_subtask_id(self, subtask_id: str) -> Optional[Dict[str, Any]]:
        """
        通过子任务ID获取任务信息
        
        Args:
            subtask_id: 子任务ID
            
        Returns:
            Optional[Dict[str, Any]]: 任务信息，如果不存在则返回None
        """
        async with self.lock:
            return self.waiting_tasks.get(subtask_id)
    
    async def _cleanup_old_tasks(self, max_age_hours: int = 24) -> None:
        """
        清理队列中的过期任务
        
        Args:
            max_age_hours: 最大任务年龄(小时)
        """
        # 每小时最多执行一次清理
        current_time = time.time()
        if current_time - self.last_cleanup < 3600:  # 3600秒 = 1小时
            return
            
        self.last_cleanup = current_time
        max_age = current_time - (max_age_hours * 3600)
        removed_count = 0
        
        for priority in self.priority_queue:
            # 找出过期任务
            expired_tasks = [
                (idx, task) for idx, task in enumerate(self.priority_queue[priority])
                if task["timestamp"] < max_age
            ]
            
            # 从后向前移除，避免索引变化问题
            for idx, task in sorted(expired_tasks, key=lambda x: x[0], reverse=True):
                task_key = f"{task['task_id']}_{task['subtask_id']}"
                self.priority_queue[priority].pop(idx)
                
                if task_key in self.task_priorities:
                    del self.task_priorities[task_key]
                    
                if task['subtask_id'] in self.waiting_tasks:
                    del self.waiting_tasks[task['subtask_id']]
                    
                removed_count += 1
                
        if removed_count > 0:
            logger.info(f"清理了 {removed_count} 个过期任务（超过 {max_age_hours} 小时）")

# 全局实例
task_priority_manager = TaskPriorityManager()

# 获取任务优先级管理器实例
def get_task_priority_manager() -> TaskPriorityManager:
    """
    获取任务优先级管理器实例
    
    Returns:
        TaskPriorityManager: 任务优先级管理器实例
    """
    return task_priority_manager 