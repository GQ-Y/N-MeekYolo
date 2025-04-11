"""
消息队列模块
实现高性能的优先级消息队列
"""
import time
import queue
import threading
from typing import Dict, List, Any, Optional, Set, Tuple, Union
from datetime import datetime
import heapq
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class MessageQueue:
    """
    消息队列
    
    实现高性能的优先级消息队列，支持多级优先级和消息排序
    """
    
    def __init__(self, max_size: int = 10000):
        """
        初始化消息队列
        
        Args:
            max_size: 队列最大容量
        """
        # 主队列（使用优先级队列）
        self.queue = []
        
        # 队列大小限制
        self.max_size = max_size
        
        # 线程锁
        self.lock = threading.RLock()
        
        # 统计信息
        self.stats = {
            "enqueued": 0,
            "dequeued": 0,
            "dropped": 0,
            "high_priority": 0,
            "medium_priority": 0,
            "low_priority": 0
        }
        
        # 每个主题的最新消息
        self.latest_messages: Dict[str, Dict[str, Any]] = {}
        
        # 主题优先级配置
        self.topic_priorities: Dict[str, int] = {
            # 系统级主题（最高优先级）
            "meek/connection": 1,
            "meek/command": 1,
            "meek/stop": 1,
            "meek/error": 1,
            
            # 数据更新主题（中等优先级）
            "meek/result": 3,
            "meek/progress": 3,
            "meek/task": 3,
            
            # 状态更新主题（较低优先级）
            "meek/heartbeat": 5,
            "meek/status": 5,
            "meek/logs": 7,
            
            # 默认优先级
            "default": 5
        }
    
    def add_message(self, topic: str, message: Dict[str, Any]) -> bool:
        """
        添加消息到队列
        
        Args:
            topic: 消息主题
            message: 消息内容
            
        Returns:
            bool: 是否成功添加
        """
        with self.lock:
            # 检查队列是否已满
            if len(self.queue) >= self.max_size:
                # 队列已满，尝试丢弃低优先级消息
                if not self._drop_low_priority_message():
                    # 无法丢弃，队列已满且无法腾出空间
                    self.stats["dropped"] += 1
                    logger.warning(f"消息队列已满，丢弃消息: {topic}")
                    return False
            
            # 确定消息优先级
            priority = self._get_topic_priority(topic)
            
            # 记录消息创建时间
            timestamp = time.time()
            
            # 创建队列项
            item = (
                priority,          # 优先级（数字越小优先级越高）
                timestamp,         # 时间戳（用于同优先级的排序）
                topic,             # 主题
                message            # 消息内容
            )
            
            # 添加到优先级队列
            heapq.heappush(self.queue, item)
            
            # 更新最新消息映射
            self.latest_messages[topic] = message
            
            # 更新统计信息
            self.stats["enqueued"] += 1
            if priority <= 2:
                self.stats["high_priority"] += 1
            elif priority <= 5:
                self.stats["medium_priority"] += 1
            else:
                self.stats["low_priority"] += 1
                
            logger.debug(f"消息已加入队列: {topic}, 优先级: {priority}, 队列长度: {len(self.queue)}")
            return True
    
    def get_message(self) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        从队列获取一条消息
        
        Returns:
            Tuple: (主题, 消息内容)，无消息时返回(None, None)
        """
        with self.lock:
            if not self.queue:
                return None, None
                
            # 弹出优先级最高的消息
            priority, timestamp, topic, message = heapq.heappop(self.queue)
            
            # 更新统计信息
            self.stats["dequeued"] += 1
            
            return topic, message
    
    def get_latest_message(self, topic: str) -> Optional[Dict[str, Any]]:
        """
        获取指定主题的最新消息
        
        Args:
            topic: 消息主题
            
        Returns:
            Dict: 最新消息，不存在时返回None
        """
        with self.lock:
            return self.latest_messages.get(topic)
    
    def clear(self):
        """清空消息队列"""
        with self.lock:
            self.queue = []
            self.latest_messages = {}
            
            # 重置部分统计信息
            self.stats["dropped"] = 0
            self.stats["high_priority"] = 0
            self.stats["medium_priority"] = 0
            self.stats["low_priority"] = 0
            
            logger.info("消息队列已清空")
    
    def set_topic_priority(self, topic: str, priority: int):
        """
        设置主题的优先级
        
        Args:
            topic: 消息主题
            priority: 优先级值（1-10，1为最高）
        """
        with self.lock:
            # 验证优先级范围
            if priority < 1 or priority > 10:
                raise ValueError("优先级必须在1-10范围内")
                
            # 设置优先级
            self.topic_priorities[topic] = priority
            logger.info(f"已设置主题 {topic} 的优先级为 {priority}")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取队列统计信息
        
        Returns:
            Dict: 统计信息
        """
        with self.lock:
            # 复制统计信息并添加当前队列长度
            stats = self.stats.copy()
            stats["queue_length"] = len(self.queue)
            stats["topic_count"] = len(self.latest_messages)
            
            return stats
    
    def _get_topic_priority(self, topic: str) -> int:
        """
        获取主题的优先级
        
        Args:
            topic: 消息主题
            
        Returns:
            int: 优先级值（1-10，1为最高）
        """
        # 精确匹配
        if topic in self.topic_priorities:
            return self.topic_priorities[topic]
            
        # 前缀匹配
        for pattern, priority in self.topic_priorities.items():
            if pattern.endswith('#') and topic.startswith(pattern[:-1]):
                return priority
                
        # 默认优先级
        return self.topic_priorities.get("default", 5)
    
    def _drop_low_priority_message(self) -> bool:
        """
        丢弃队列中优先级最低的消息
        
        Returns:
            bool: 是否成功丢弃
        """
        # 如果队列为空，无需丢弃
        if not self.queue:
            return True
            
        # 找出优先级最低的消息的索引
        lowest_priority_index = self.queue.index(max(self.queue, key=lambda x: (x[0], x[1])))
        
        # 移除该消息
        self.queue.pop(lowest_priority_index)
        
        # 重新构建堆
        heapq.heapify(self.queue)
        
        # 更新统计信息
        self.stats["dropped"] += 1
        
        return True
    
    @classmethod
    def get_instance(cls) -> 'MessageQueue':
        """获取消息队列单例实例"""
        if not hasattr(cls, '_instance'):
            cls._instance = MessageQueue()
        return cls._instance 