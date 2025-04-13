#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MQTT消息处理器
实现消息路由和处理机制
"""
import json
import time
import asyncio
import threading
import logging
import queue
from typing import Dict, List, Any, Optional, Set, Tuple, Callable, Union
from datetime import datetime
from core.redis_manager import RedisManager
# 避免循环导入，将MessageQueue的导入移到方法内部
# from services.core.message_queue import MessageQueue
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class MQTTMessageProcessor:
    """
    MQTT消息处理器
    
    负责：
    1. 消息路由和分发
    2. 消息处理器注册
    3. 消息队列管理
    """
    
    def __init__(self):
        """初始化MQTT消息处理器"""
        # Redis管理器
        self.redis = RedisManager.get_instance()
        
        # 消息队列 - 延迟初始化
        self._message_queue = None
        
        # 处理器映射：topic -> handler
        self.handlers: Dict[str, List[Callable]] = {}
        
        # 通配符处理器映射
        self.wildcard_handlers: Dict[str, List[Callable]] = {}
        
        # 消息缓存（用于处理消息重复和顺序）
        self.message_cache: Dict[str, Dict[str, Any]] = {}
        
        # 初始化标志
        self.initialized = False
        
        # 线程锁
        self.lock = threading.RLock()
        
        # 消息处理线程
        self.processing_thread = None
        self.running = False
        
    def _get_message_queue(self):
        """延迟获取消息队列，避免循环导入"""
        if self._message_queue is None:
            # 在方法内部导入，避免循环导入
            from services.core.message_queue import MessageQueue
            self._message_queue = MessageQueue.get_instance()
        return self._message_queue
    
    def initialize(self):
        """初始化消息处理器"""
        with self.lock:
            if self.initialized:
                logger.info("MQTT消息处理器已初始化")
                return
                
            # 确保主线程有一个事件循环
            try:
                asyncio.get_event_loop()
            except RuntimeError:
                # 如果当前线程没有事件循环，创建一个新的
                logger.info("为主线程创建事件循环")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            # 启动消息处理线程
            self.running = True
            self.processing_thread = threading.Thread(
                target=self._message_processing_loop,
                name="MQTTMessageProcessor",
                daemon=True
            )
            self.processing_thread.start()
            
            self.initialized = True
            logger.info("MQTT消息处理器初始化完成")
    
    def stop(self):
        """停止消息处理器"""
        with self.lock:
            if not self.running:
                return
                
            self.running = False
            
            # 等待处理线程结束
            if self.processing_thread and self.processing_thread.is_alive():
                logger.info("等待MQTT消息处理线程结束...")
                self.processing_thread.join(timeout=2.0)
                
            logger.info("MQTT消息处理器已停止")
    
    def register_handler(self, topic: str, handler: Callable[[str, Any], None]):
        """
        注册消息处理器
        
        Args:
            topic: 主题，支持通配符 #（多级）和 +（单级）
            handler: 处理函数，接收主题和消息作为参数
        """
        with self.lock:
            if '#' in topic or '+' in topic:
                # 通配符主题
                if topic not in self.wildcard_handlers:
                    self.wildcard_handlers[topic] = []
                    
                if handler not in self.wildcard_handlers[topic]:
                    self.wildcard_handlers[topic].append(handler)
                    logger.info(f"已注册通配符主题处理器: {topic}")
            else:
                # 普通主题
                if topic not in self.handlers:
                    self.handlers[topic] = []
                    
                if handler not in self.handlers[topic]:
                    self.handlers[topic].append(handler)
                    logger.info(f"已注册主题处理器: {topic}")
    
    def unregister_handler(self, topic: str, handler: Optional[Callable] = None):
        """
        取消注册消息处理器
        
        Args:
            topic: 主题
            handler: 处理函数，为None时移除所有处理器
        """
        with self.lock:
            if '#' in topic or '+' in topic:
                # 通配符主题
                if topic in self.wildcard_handlers:
                    if handler is None:
                        # 移除所有处理器
                        self.wildcard_handlers.pop(topic)
                        logger.info(f"已移除主题 {topic} 的所有处理器")
                    elif handler in self.wildcard_handlers[topic]:
                        # 移除特定处理器
                        self.wildcard_handlers[topic].remove(handler)
                        logger.info(f"已移除主题 {topic} 的指定处理器")
            else:
                # 普通主题
                if topic in self.handlers:
                    if handler is None:
                        # 移除所有处理器
                        self.handlers.pop(topic)
                        logger.info(f"已移除主题 {topic} 的所有处理器")
                    elif handler in self.handlers[topic]:
                        # 移除特定处理器
                        self.handlers[topic].remove(handler)
                        logger.info(f"已移除主题 {topic} 的指定处理器")
    
    def process_message(self, topic: str, payload: Union[str, bytes, dict]) -> bool:
        """
        处理MQTT消息
        
        Args:
            topic: 消息主题
            payload: 消息内容
            
        Returns:
            bool: 是否成功加入处理队列
        """
        try:
            # 标准化消息格式
            message = self._normalize_payload(payload)
            
            # 检查是否需要去重
            if self._is_duplicate_message(topic, message):
                logger.debug(f"忽略重复消息: {topic}")
                return False
            
            # 添加到消息队列
            self._get_message_queue().add_message(topic, message)
            logger.debug(f"已将消息添加到队列: {topic}")
            return True
            
        except Exception as e:
            logger.error(f"处理MQTT消息时出错: {str(e)}")
            return False
    
    def _normalize_payload(self, payload: Union[str, bytes, dict]) -> Dict[str, Any]:
        """
        标准化消息内容
        
        Args:
            payload: 消息内容
            
        Returns:
            Dict: 标准化后的消息内容
        """
        if isinstance(payload, dict):
            return payload
            
        if isinstance(payload, bytes):
            payload = payload.decode('utf-8')
            
        if isinstance(payload, str):
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                return {"message": payload}
                
        return {"raw_data": str(payload)}
    
    def _is_duplicate_message(self, topic: str, message: Dict[str, Any]) -> bool:
        """
        检查是否是重复消息
        
        Args:
            topic: 消息主题
            message: 消息内容
            
        Returns:
            bool: 是否重复
        """
        # 获取消息ID
        message_id = message.get("message_id") or message.get("id")
        
        # 如果没有消息ID，不进行去重
        if not message_id:
            return False
            
        # 生成缓存键
        cache_key = f"{topic}:{message_id}"
        
        with self.lock:
            # 检查是否已处理过该消息
            if cache_key in self.message_cache:
                return True
                
            # 添加到缓存
            self.message_cache[cache_key] = {
                "timestamp": datetime.now(),
                "processed": False
            }
            
            # 清理过期缓存
            self._cleanup_message_cache()
            
            return False
    
    def _cleanup_message_cache(self):
        """清理过期的消息缓存"""
        now = datetime.now()
        # 设置缓存有效期为5分钟
        cache_ttl = 300  # 秒
        
        expired_keys = []
        for key, data in self.message_cache.items():
            if (now - data["timestamp"]).total_seconds() > cache_ttl:
                expired_keys.append(key)
                
        for key in expired_keys:
            self.message_cache.pop(key, None)
    
    def _message_processing_loop(self):
        """消息处理循环"""
        logger.info("MQTT消息处理循环已启动")
        
        while self.running:
            try:
                # 获取一条消息
                topic, message = self._get_message_queue().get_message()
                
                if topic and message:
                    # 处理消息
                    self._dispatch_message(topic, message)
                
                # 处理异步消息队列中的消息
                self._process_async_messages()
                    
                # 短暂休眠，避免CPU占用过高
                time.sleep(0.01)
                
            except Exception as e:
                logger.error(f"消息处理循环出错: {str(e)}")
                time.sleep(1)  # 出错时等待1秒
                
        logger.info("MQTT消息处理循环已停止")
    
    def _process_async_messages(self):
        """处理异步消息队列中的消息"""
        try:
            # 检查异步消息队列
            async_queue = self._get_async_message_queue()
            if async_queue.empty():
                return
                
            # 获取一条异步消息
            try:
                item = async_queue.get_nowait()
            except queue.Empty:
                return
                
            # 获取消息内容
            msg_id = item.get("id")
            topic = item.get("topic")
            payload = item.get("payload")
            handler = item.get("handler")
            
            if not topic or not payload or not handler:
                logger.warning(f"异步消息格式错误: {msg_id}")
                return
                
            # 尝试调用异步处理函数
            try:
                logger.debug(f"开始处理异步消息: {msg_id}, 处理函数: {handler.__name__}")
                
                # 获取或创建事件循环
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    # 如果当前线程没有事件循环，创建一个新的
                    logger.debug("当前线程没有事件循环，创建新循环")
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                # 安全地运行异步函数
                if loop.is_running():
                    # 如果循环正在运行，使用call_soon_threadsafe来安排任务
                    logger.debug("事件循环正在运行，使用call_soon_threadsafe方法")
                    future = asyncio.run_coroutine_threadsafe(handler(payload), loop)
                    # 可以添加回调来处理完成状态，但不等待结果
                    future.add_done_callback(
                        lambda f: logger.debug(f"异步消息 {msg_id} 处理完成: {'成功' if not f.exception() else f'失败({f.exception()})'}")
                    )
                else:
                    # 如果循环没有运行，直接运行协程
                    logger.debug("事件循环未运行，直接运行协程")
                    try:
                        result = loop.run_until_complete(handler(payload))
                        logger.debug(f"异步消息 {msg_id} 处理成功: {result}")
                    except Exception as e:
                        logger.error(f"异步消息 {msg_id} 处理失败: {e}")
                        
            except Exception as e:
                logger.error(f"处理异步消息 {msg_id} 时出错: {e}")
                
        except Exception as e:
            logger.error(f"处理异步消息队列时出错: {e}")
    
    def _dispatch_message(self, topic: str, message: Dict[str, Any]):
        """
        分发消息到对应的处理器
        
        Args:
            topic: 消息主题
            message: 消息内容
        """
        handlers_to_call = []
        
        # 1. 查找精确匹配的处理器
        if topic in self.handlers:
            handlers_to_call.extend(self.handlers[topic])
            
        # 2. 查找通配符匹配的处理器
        for pattern, pattern_handlers in self.wildcard_handlers.items():
            if self._match_topic(topic, pattern):
                handlers_to_call.extend(pattern_handlers)
                
        # 如果没有处理器，记录日志
        if not handlers_to_call:
            logger.debug(f"没有处理器匹配主题: {topic}")
            return
            
        # 调用所有匹配的处理器
        for handler in handlers_to_call:
            try:
                handler(topic, message)
            except Exception as e:
                logger.error(f"处理器处理消息 {topic} 时出错: {str(e)}")
                
        # 标记消息为已处理
        message_id = message.get("message_id") or message.get("id")
        if message_id:
            cache_key = f"{topic}:{message_id}"
            if cache_key in self.message_cache:
                self.message_cache[cache_key]["processed"] = True
    
    def _match_topic(self, topic: str, pattern: str) -> bool:
        """
        检查主题是否匹配模式
        
        Args:
            topic: 消息主题
            pattern: 模式，支持通配符 # 和 +
            
        Returns:
            bool: 是否匹配
        """
        # 分割主题和模式
        topic_parts = topic.split('/')
        pattern_parts = pattern.split('/')
        
        # 处理简单情况
        if '#' not in pattern and '+' not in pattern:
            return topic == pattern
            
        # 处理以 # 结尾的模式
        if pattern_parts[-1] == '#':
            # 检查前缀是否匹配
            prefix_pattern = pattern_parts[:-1]
            if len(topic_parts) < len(prefix_pattern):
                return False
                
            for i, part in enumerate(prefix_pattern):
                if part != '+' and part != topic_parts[i]:
                    return False
                    
            return True
            
        # 如果长度不同且不是通配符结尾，则不匹配
        if len(topic_parts) != len(pattern_parts):
            return False
            
        # 逐段比较
        for topic_part, pattern_part in zip(topic_parts, pattern_parts):
            if pattern_part != '+' and pattern_part != topic_part:
                return False
                
        return True
    
    @classmethod
    def get_instance(cls) -> 'MQTTMessageProcessor':
        """获取MQTT消息处理器单例实例"""
        if not hasattr(cls, '_instance'):
            cls._instance = MQTTMessageProcessor()
        return cls._instance 

    def add_message(self, topic: str, payload: Any, async_handler: Callable):
        """
        添加消息到处理队列，包含处理该消息的异步处理函数
        
        Args:
            topic: 消息主题
            payload: 消息内容
            async_handler: 异步处理函数
        """
        try:
            logger.debug(f"添加异步消息到处理队列: topic={topic}, message_id={payload.get('message_id', 'unknown')}")
            
            # 使用时间戳+随机数作为唯一标识
            msg_id = f"{int(time.time())}-{id(payload)}"
            
            # 添加到处理队列，仅存储在内存中，避免使用Redis异步操作
            item = {
                "id": msg_id,
                "topic": topic,
                "payload": payload,
                "handler": async_handler,
                "timestamp": time.time()
            }
            
            # 添加到本地队列，使用标准库的queue
            self._get_async_message_queue().put(item)
            logger.debug(f"异步消息已加入队列: {msg_id}")
            
        except Exception as e:
            logger.error(f"添加异步消息到处理队列失败: {e}")
    
    def _get_async_message_queue(self):
        """获取异步消息队列"""
        if not hasattr(self, "_async_queue"):
            self._async_queue = queue.Queue()
        return self._async_queue 