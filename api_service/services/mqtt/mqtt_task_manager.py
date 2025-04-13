#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import asyncio
import logging
import json
import uuid
from typing import Dict, List, Optional, Tuple, Any, Set, Callable
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from fastapi import Depends, BackgroundTasks

from models.database import MQTTNode, SubTask, Task, Model, Stream
from core.database import SessionLocal
from services.task.task_priority_manager import task_priority_manager, get_task_priority_manager
from services.core.smart_task_scheduler import smart_task_scheduler, get_smart_task_scheduler
from services.mqtt.mqtt_client import MQTTClient, get_mqtt_client
from shared.utils.logger import setup_logger

# 配置日志
logger = setup_logger(__name__)

class MQTTTaskManager:
    """
    MQTT任务管理器
    负责任务分配、重试和状态管理
    """
    
    def __init__(self, 
                mqtt_client: MQTTClient = None,
                priority_manager = None,
                task_scheduler = None):
        """
        初始化MQTT任务管理器
        
        Args:
            mqtt_client: MQTT客户端实例
            priority_manager: 任务优先级管理器实例
            task_scheduler: 智能任务调度器实例
        """
        self.mqtt_client = mqtt_client or get_mqtt_client()
        self.priority_manager = priority_manager or get_task_priority_manager()
        self.scheduler = task_scheduler or get_smart_task_scheduler()
        
        self.max_retries = 3  # 任务最大重试次数
        self.retry_delays = [5, 30, 120]  # 重试间隔（秒）
        
        self.task_status_cache = {}  # 任务状态缓存
        self.pending_tasks = set()  # 待处理任务集合 {subtask_id}
        
        # 初始化任务状态检查定时器
        self.task_check_interval = 60  # 60秒检查一次任务状态
        self.is_running = False
        self.scheduler_task = None
        
    async def start(self):
        """启动任务管理器"""
        if self.is_running:
            return
            
        self.is_running = True
        
        # 启动任务状态检查定时器
        self.scheduler_task = asyncio.create_task(self._task_status_check_loop())
        
        logger.info("MQTT任务管理器已启动")
        
    async def stop(self):
        """停止任务管理器"""
        self.is_running = False
        
        if self.scheduler_task:
            self.scheduler_task.cancel()
            
        logger.info("MQTT任务管理器已停止")
        
    async def dispatch_task(self, task_id: str, subtask_id: str, 
                           priority: int = 1, wait: bool = False) -> Tuple[bool, Dict[str, Any]]:
        """
        分发任务到MQTT节点
        
        Args:
            task_id: 任务ID
            subtask_id: 子任务ID
            priority: 任务优先级
            wait: 是否等待任务完成
            
        Returns:
            Tuple[bool, Dict[str, Any]]: (是否成功，结果信息)
        """
        # 检查子任务是否已存在于待处理集合
        if subtask_id in self.pending_tasks:
            logger.warning(f"子任务 {subtask_id} 已在待处理队列中")
            return False, {"error": "任务已在队列中"}
            
        # 获取子任务信息
        db = SessionLocal()
        try:
            # 查询子任务
            if not subtask_id.isdigit():
                return False, {"error": "无效的子任务ID"}
                
            subtask = db.query(SubTask).filter(SubTask.id == int(subtask_id)).first()
            if not subtask:
                return False, {"error": f"未找到子任务: {subtask_id}"}
                
            # 检查子任务状态
            if subtask.status not in [0, 3]:  # 只处理未开始或失败的任务
                return False, {"error": f"子任务状态({subtask.status})不适合分发"}
                
            # 获取主任务信息
            task = subtask.task
            if not task:
                return False, {"error": "子任务缺少主任务信息"}
                
            # 获取模型和流信息
            model = subtask.model
            stream = subtask.stream
            
            if not model or not stream:
                return False, {"error": "子任务缺少模型或流信息"}
                
            # 准备任务数据
            task_data = {
                "task_id": str(task.id),
                "subtask_id": str(subtask.id),
                "task_type": task.stream_type,
                "analysis_type": subtask.analysis_type,
                "model_code": model.code,
                "stream_url": stream.url,
                "config": subtask.config or {},
                "save_result": task.save_result,
                "save_images": task.save_images,
                "analysis_interval": task.analysis_interval
            }
            
            # 更新子任务状态为待分发
            subtask.status = 0  # 未启动/待分发
            subtask.error_message = "任务已加入分发队列"
            db.commit()
            
            # 添加到优先级队列
            await self.priority_manager.add_task(str(task.id), str(subtask.id), priority, task_data)
            
            # 添加到待处理集合
            self.pending_tasks.add(subtask_id)
            
            logger.info(f"任务 {task_id}/{subtask_id} 已加入分发队列，优先级: {priority}")
            
            # 如果不等待，立即返回
            if not wait:
                # 启动后台任务处理
                asyncio.create_task(self._process_pending_tasks())
                return True, {"success": True, "message": "任务已加入队列"}
                
            # 等待任务处理结果
            timeout = 30  # 等待超时时间（秒）
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                # 检查任务是否已完成
                if subtask_id not in self.pending_tasks:
                    # 查询最新状态
                    db.refresh(subtask)
                    status_map = {0: "未开始", 1: "运行中", 2: "已完成", 3: "失败"}
                    status_text = status_map.get(subtask.status, "未知")
                    
                    return subtask.status in [1, 2], {
                        "success": subtask.status in [1, 2],
                        "status": subtask.status,
                        "status_text": status_text,
                        "message": subtask.error_message or "任务已分发"
                    }
                    
                # 等待一段时间再检查
                await asyncio.sleep(1)
                
            # 超时但仍在队列中
            return False, {"error": "等待任务分发超时"}
            
        finally:
            db.close()
    
    async def retry_failed_task(self, subtask_id: str, 
                             priority: int = None) -> Tuple[bool, Dict[str, Any]]:
        """
        重试失败的任务
        
        Args:
            subtask_id: 子任务ID
            priority: 新的优先级（可选）
            
        Returns:
            Tuple[bool, Dict[str, Any]]: (是否成功，结果信息)
        """
        db = SessionLocal()
        try:
            # 查询子任务
            if not subtask_id.isdigit():
                return False, {"error": "无效的子任务ID"}
                
            subtask = db.query(SubTask).filter(SubTask.id == int(subtask_id)).first()
            if not subtask:
                return False, {"error": f"未找到子任务: {subtask_id}"}
                
            # 检查子任务状态，只有失败或未开始的任务可以重试
            if subtask.status not in [0, 3]:
                return False, {"error": f"子任务状态({subtask.status})不适合重试"}
                
            # 获取任务ID
            task_id = str(subtask.task_id)
            
            # 如果未指定优先级，使用高优先级
            if priority is None:
                priority = 2  # 重试任务使用高优先级
                
            # 分发任务
            return await self.dispatch_task(task_id, subtask_id, priority)
            
        finally:
            db.close()
    
    async def cancel_task(self, subtask_id: str) -> Tuple[bool, Dict[str, Any]]:
        """
        取消待处理的任务
        
        Args:
            subtask_id: 子任务ID
            
        Returns:
            Tuple[bool, Dict[str, Any]]: (是否成功，结果信息)
        """
        # 首先检查任务是否在待处理队列
        if subtask_id in self.pending_tasks:
            # 从待处理集合移除
            self.pending_tasks.remove(subtask_id)
            
            # 从优先级队列移除
            db = SessionLocal()
            try:
                if not subtask_id.isdigit():
                    return False, {"error": "无效的子任务ID"}
                    
                subtask = db.query(SubTask).filter(SubTask.id == int(subtask_id)).first()
                if subtask:
                    task_id = str(subtask.task_id)
                    
                    # 从优先级队列移除
                    await self.priority_manager.remove_task(task_id, subtask_id)
                    
                    # 更新子任务状态
                    subtask.status = 0  # 重置为未开始状态
                    subtask.error_message = "任务已取消"
                    db.commit()
                    
                    logger.info(f"任务 {task_id}/{subtask_id} 已取消")
                    return True, {"success": True, "message": "任务已取消"}
                else:
                    return False, {"error": f"未找到子任务: {subtask_id}"}
            finally:
                db.close()
        
        # 如果任务已经在处理中，尝试发送取消命令到节点
        db = SessionLocal()
        try:
            if not subtask_id.isdigit():
                return False, {"error": "无效的子任务ID"}
                
            subtask = db.query(SubTask).filter(SubTask.id == int(subtask_id)).first()
            if not subtask:
                return False, {"error": f"未找到子任务: {subtask_id}"}
                
            # 只有正在运行的任务需要发送取消命令
            if subtask.status != 1:
                return False, {"error": f"子任务状态({subtask.status})不需要取消"}
                
            # 获取节点信息
            node_id = subtask.mqtt_node_id
            if not node_id:
                return False, {"error": "子任务未关联MQTT节点"}
                
            mqtt_node = db.query(MQTTNode).filter(MQTTNode.id == node_id).first()
            if not mqtt_node:
                return False, {"error": "未找到关联的MQTT节点"}
                
            # 发送取消命令
            task_id = str(subtask.task_id)
            mac_address = mqtt_node.mac_address
            
            # 构建取消命令
            message_id = int(time.time())
            message_uuid = str(uuid.uuid4()).replace("-", "")[:16]
            
            payload = {
                "confirmation_topic": f"{self.mqtt_client.config['topic_prefix']}device_config_reply",
                "message_id": message_id,
                "message_uuid": message_uuid,
                "request_type": "task_cmd",
                "data": {
                    "cmd_type": "stop_task",
                    "task_id": task_id,
                    "subtask_id": str(subtask.id)
                }
            }
            
            # 发送取消命令
            topic = f"{self.mqtt_client.config['topic_prefix']}{mac_address}/request_setting"
            result = self.mqtt_client.client.publish(
                topic,
                json.dumps(payload),
                qos=self.mqtt_client.config.get('qos', 2)
            )
            
            if result.rc != 0:
                logger.error(f"发送取消命令失败: {result.rc}")
                return False, {"error": f"发送取消命令失败: {result.rc}"}
                
            # 更新子任务状态
            subtask.status = 0  # 重置为未开始状态
            subtask.error_message = "任务已取消"
            db.commit()
            
            # 更新节点任务计数
            await self.scheduler.update_node_task_load(mac_address, change=-1)
            
            logger.info(f"向节点 {mac_address} 发送了取消任务 {task_id}/{subtask_id} 的命令")
            return True, {"success": True, "message": "已发送取消命令"}
            
        finally:
            db.close()
    
    async def get_task_status(self, task_id: str, subtask_id: str) -> Dict[str, Any]:
        """
        获取任务状态
        
        Args:
            task_id: 任务ID
            subtask_id: 子任务ID
            
        Returns:
            Dict[str, Any]: 任务状态信息
        """
        # 首先检查任务是否在待处理队列
        is_pending = subtask_id in self.pending_tasks
        
        # 查询数据库获取最新状态
        db = SessionLocal()
        try:
            if not subtask_id.isdigit():
                return {"error": "无效的子任务ID"}
                
            subtask = db.query(SubTask).filter(SubTask.id == int(subtask_id)).first()
            if not subtask:
                return {"error": f"未找到子任务: {subtask_id}"}
                
            # 获取节点信息
            node_info = None
            if subtask.mqtt_node_id:
                mqtt_node = db.query(MQTTNode).filter(MQTTNode.id == subtask.mqtt_node_id).first()
                if mqtt_node:
                    node_info = {
                        "mac_address": mqtt_node.mac_address,
                        "status": mqtt_node.status,
                        "hostname": mqtt_node.hostname
                    }
            
            # 映射状态文本
            status_map = {0: "未开始", 1: "运行中", 2: "已完成", 3: "失败"}
            status_text = status_map.get(subtask.status, "未知")
            
            # 获取任务进度信息
            progress = 0
            if subtask.status == 1 and "progress" in (subtask.metadata or {}):
                progress = subtask.metadata.get("progress", 0)
                
            # 获取开始和完成时间
            started_at = subtask.started_at.isoformat() if subtask.started_at else None
            completed_at = subtask.completed_at.isoformat() if subtask.completed_at else None
            
            # 构建状态信息
            status_info = {
                "task_id": task_id,
                "subtask_id": subtask_id,
                "status": subtask.status,
                "status_text": status_text,
                "is_pending": is_pending,
                "error_message": subtask.error_message,
                "progress": progress,
                "started_at": started_at,
                "completed_at": completed_at,
                "node_info": node_info,
                "metadata": subtask.metadata
            }
            
            # 如果任务在优先级队列中，获取优先级信息
            if is_pending:
                task_info = await self.priority_manager.get_task_by_subtask_id(subtask_id)
                if task_info:
                    status_info["priority"] = task_info.get("priority", 1)
                    status_info["attempts"] = task_info.get("attempts", 0)
            
            return status_info
            
        finally:
            db.close()
    
    async def _process_pending_tasks(self, batch_size: int = 5) -> int:
        """
        处理待处理任务队列
        
        Args:
            batch_size: 一次处理的任务数量
            
        Returns:
            int: 处理的任务数量
        """
        # 使用智能调度器分配任务
        processed_count = await self.scheduler.distribute_pending_tasks(batch_size)
        
        # 更新待处理集合
        if processed_count > 0:
            # 通过数据库查询实际处理的任务，更新待处理集合
            db = SessionLocal()
            try:
                # 查询所有待处理的子任务ID
                subtask_ids = list(self.pending_tasks)
                if not subtask_ids:
                    return processed_count
                    
                # 获取已分配节点的子任务
                subtasks = db.query(SubTask).filter(
                    SubTask.id.in_([int(sid) for sid in subtask_ids if sid.isdigit()]),
                    SubTask.mqtt_node_id.isnot(None)  # 已分配节点的任务
                ).all()
                
                # 从待处理集合中移除已分配的任务
                for subtask in subtasks:
                    subtask_id = str(subtask.id)
                    if subtask_id in self.pending_tasks:
                        self.pending_tasks.remove(subtask_id)
                        logger.info(f"子任务 {subtask_id} 已处理，从待处理集合移除")
            finally:
                db.close()
                
        return processed_count
    
    async def _task_status_check_loop(self):
        """任务状态检查循环"""
        while self.is_running:
            try:
                # 处理一批待处理任务
                if self.pending_tasks:
                    await self._process_pending_tasks()
                    
                # 检查长时间运行的任务状态
                await self._check_running_tasks()
                
                # 等待下次检查
                await asyncio.sleep(self.task_check_interval)
            except Exception as e:
                logger.error(f"任务状态检查失败: {e}")
                await asyncio.sleep(10)  # 出错后等待较短时间再重试
    
    async def _check_running_tasks(self):
        """检查长时间运行的任务状态"""
        # 设定超时阈值
        timeout_threshold = datetime.now() - timedelta(hours=4)  # 4小时无更新视为超时
        
        db = SessionLocal()
        try:
            # 查询长时间运行的任务
            long_running_tasks = db.query(SubTask).filter(
                SubTask.status == 1,  # 运行中的任务
                SubTask.started_at < timeout_threshold,  # 开始时间超过阈值
                SubTask.mqtt_node_id.isnot(None)  # 已分配节点
            ).all()
            
            for subtask in long_running_tasks:
                # 查询节点状态
                node = db.query(MQTTNode).filter(MQTTNode.id == subtask.mqtt_node_id).first()
                
                # 如果节点离线或状态异常，将任务标记为失败并重新入队
                if not node or node.status != "online":
                    logger.warning(f"子任务 {subtask.id} 在离线节点上运行超时，标记为失败并重新入队")
                    
                    # 标记任务为失败
                    subtask.status = 2  # 已停止
                    subtask.error_message = f"节点离线或任务运行超时，已自动重新排队"
                    
                    # 添加重试计数
                    subtask.metadata = subtask.metadata or {}
                    retries = subtask.metadata.get("retry_count", 0) + 1
                    subtask.metadata["retry_count"] = retries
                    
                    # 如果重试次数小于最大重试次数，重新入队
                    if retries <= self.max_retries:
                        # 使用较低优先级重新入队
                        priority = max(0, 1 - (retries - 1))  # 优先级随重试次数降低
                        
                        # 更新数据库
                        db.commit()
                        
                        # 重新分发任务
                        await self.dispatch_task(str(subtask.task_id), str(subtask.id), priority)
                        logger.info(f"子任务 {subtask.id} 自动重试 ({retries}/{self.max_retries})")
                    else:
                        # 达到最大重试次数，标记为最终失败
                        subtask.error_message = f"达到最大重试次数 ({self.max_retries})，任务失败"
                        db.commit()
                        logger.warning(f"子任务 {subtask.id} 达到最大重试次数，不再重试")
            
        finally:
            db.close()

# 全局实例
mqtt_task_manager = None

def get_mqtt_task_manager() -> MQTTTaskManager:
    """
    获取MQTT任务管理器实例
    
    Returns:
        MQTTTaskManager: MQTT任务管理器实例
    """
    global mqtt_task_manager
    if mqtt_task_manager is None:
        # 使用全局MQTT客户端
        mqtt_client = get_mqtt_client()
        mqtt_task_manager = MQTTTaskManager(mqtt_client=mqtt_client)
        
        # 不再直接启动，而是由调用者在异步上下文中启动
        # 在这里只创建实例
        logger.info("MQTT任务管理器已创建，等待在异步上下文中启动")
    return mqtt_task_manager 