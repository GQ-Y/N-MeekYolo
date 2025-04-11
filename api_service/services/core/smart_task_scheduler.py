#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import asyncio
import logging
import random
from typing import Dict, List, Optional, Tuple, Any, Set
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import func

from models.database import MQTTNode, SubTask, Task, Model
from core.database import SessionLocal

# 从其他服务导入
from services.task.task_priority_manager import task_priority_manager

# 配置日志
logger = logging.getLogger(__name__)

class SmartTaskScheduler:
    """
    智能任务调度器
    分析节点负载情况和任务复杂度，智能分配任务
    """
    
    def __init__(self):
        """初始化智能任务调度器"""
        self.node_scores: Dict[str, float] = {}  # 节点得分缓存 {mac_address: 得分}
        self.node_capabilities: Dict[str, Dict[str, Any]] = {}  # 节点能力缓存
        self.task_complexity: Dict[str, float] = {}  # 任务复杂度缓存 {task_type: 复杂度得分}
        self.lock = asyncio.Lock()  # 异步锁
        self.last_node_sync = 0  # 上次节点同步时间
        
        # 初始化任务复杂度评分
        self._init_task_complexity()
        
    def _init_task_complexity(self):
        """初始化默认任务复杂度评分"""
        self.task_complexity = {
            "image_detection": 1.0,      # 图像检测（标准复杂度）
            "video_detection": 1.5,      # 视频检测（较高复杂度）
            "stream_detection": 2.0,     # 实时流检测（高复杂度）
            "vehicle_counting": 1.3,     # 车辆计数
            "human_detection": 1.2,      # 人体检测
            "face_recognition": 1.8,     # 人脸识别
            "license_plate": 1.5,        # 车牌识别
            "object_tracking": 1.7,      # 物体跟踪
            "activity_recognition": 2.0, # 活动识别
            "anomaly_detection": 1.9,    # 异常检测
            "thermal_imaging": 1.3,      # 热成像分析
            "pose_estimation": 1.6,      # 姿态估计
            "scene_classification": 1.1, # 场景分类
            "text_recognition": 1.4,     # 文本识别
            "default": 1.0               # 默认复杂度
        }
    
    async def sync_nodes_from_db(self, force: bool = False) -> None:
        """
        从数据库同步节点信息
        
        Args:
            force: 是否强制同步，忽略时间限制
        """
        # 限制同步频率，每30秒最多同步一次，除非强制同步
        current_time = time.time()
        if not force and (current_time - self.last_node_sync) < 30:
            return
            
        self.last_node_sync = current_time
        
        db = SessionLocal()
        try:
            # 查询所有在线且活跃的节点
            nodes = db.query(MQTTNode).filter(
                MQTTNode.status == "online",
                MQTTNode.is_active == True
            ).all()
            
            async with self.lock:
                # 清除旧的节点缓存
                self.node_scores = {}
                self.node_capabilities = {}
                
                # 更新节点缓存
                for node in nodes:
                    # 计算节点得分（负载情况）
                    score = self._calculate_node_score(node)
                    self.node_scores[node.mac_address] = score
                    
                    # 提取节点能力信息
                    capabilities = self._extract_node_capabilities(node)
                    self.node_capabilities[node.mac_address] = capabilities
                    
            logger.info(f"已同步 {len(nodes)} 个节点信息")
        finally:
            db.close()
    
    def _calculate_node_score(self, node: MQTTNode) -> float:
        """
        计算节点得分，用于任务分配优先级
        得分越高，说明节点负载越低，越适合分配任务
        
        Args:
            node: MQTT节点对象
            
        Returns:
            float: 节点得分
        """
        # 基础分数
        score = 10.0
        
        # 根据当前任务数减分
        task_ratio = node.task_count / max(node.max_tasks, 1)
        score -= task_ratio * 5.0  # 任务数越多，扣分越多
        
        # 根据CPU使用率减分
        if node.cpu_usage is not None:
            cpu_penalty = (node.cpu_usage / 100.0) * 3.0
            score -= cpu_penalty
            
        # 根据内存使用率减分
        if node.memory_usage is not None:
            memory_penalty = (node.memory_usage / 100.0) * 2.0
            score -= memory_penalty
            
        # 如果有GPU信息，根据GPU使用率减分
        if node.gpu_usage is not None:
            gpu_penalty = (node.gpu_usage / 100.0) * 4.0  # GPU更重要，权重更高
            score -= gpu_penalty
            
        # 任务多样性加分（处理不同类型任务的能力）
        has_image_tasks = node.image_task_count > 0
        has_video_tasks = node.video_task_count > 0
        has_stream_tasks = node.stream_task_count > 0
        diversity_score = sum([has_image_tasks, has_video_tasks, has_stream_tasks]) * 0.5
        score += diversity_score
        
        # 如果节点元数据中有额外信息，可以进一步调整得分
        if node.node_metadata:
            # 如果节点支持GPU加速，加分
            if node.node_metadata.get('has_gpu', False):
                score += 2.0
                
            # 如果节点支持多模型并行处理，加分
            if node.node_metadata.get('multi_model_support', False):
                score += 1.0
                
            # 根据节点稳定性得分调整
            stability = node.node_metadata.get('stability_score', 0.5)
            score += stability * 2.0
        
        # 确保得分范围在0-10之间
        return max(0.0, min(10.0, score))
    
    def _extract_node_capabilities(self, node: MQTTNode) -> Dict[str, Any]:
        """
        提取节点能力信息
        
        Args:
            node: MQTT节点对象
            
        Returns:
            Dict[str, Any]: 节点能力信息
        """
        capabilities = {
            "max_tasks": node.max_tasks,
            "current_tasks": node.task_count,
            "service_type": node.service_type,
            "has_gpu": False,
            "gpu_model": None,
            "supported_models": [],
            "supported_tasks": []
        }
        
        # 从节点元数据中提取更多信息
        if node.node_metadata:
            # GPU信息
            capabilities["has_gpu"] = node.node_metadata.get('has_gpu', False)
            capabilities["gpu_model"] = node.node_metadata.get('gpu_model')
            
            # 支持的模型和任务类型
            capabilities["supported_models"] = node.node_metadata.get('supported_models', [])
            capabilities["supported_tasks"] = node.node_metadata.get('supported_tasks', [])
            
            # 性能参数
            capabilities["performance"] = {
                "cpu_benchmark": node.node_metadata.get('cpu_benchmark'),
                "gpu_benchmark": node.node_metadata.get('gpu_benchmark'),
                "memory_size": node.node_metadata.get('memory_size'),
                "network_bandwidth": node.node_metadata.get('network_bandwidth')
            }
        
        return capabilities
    
    async def get_best_node_for_task(self, task_type: str, model_code: str = None, 
                                    min_score: float = 3.0) -> Optional[str]:
        """
        为指定任务找到最佳节点
        
        Args:
            task_type: 任务类型
            model_code: 模型代码
            min_score: 最低节点得分要求
            
        Returns:
            Optional[str]: 最佳节点的MAC地址，如果找不到合适节点则返回None
        """
        # 确保节点信息已同步
        await self.sync_nodes_from_db()
        
        if not self.node_scores:
            logger.warning("节点信息为空，无法分配任务")
            return None
            
        suitable_nodes = []
        
        async with self.lock:
            for mac_address, score in self.node_scores.items():
                # 检查节点得分是否达到最低要求
                if score < min_score:
                    continue
                    
                # 检查节点能力是否满足任务要求
                capabilities = self.node_capabilities.get(mac_address, {})
                
                # 检查是否已达到最大任务数
                current_tasks = capabilities.get("current_tasks", 0)
                max_tasks = capabilities.get("max_tasks", 20)
                if current_tasks >= max_tasks:
                    continue
                
                # 检查是否支持所需模型
                if model_code and capabilities.get("supported_models"):
                    if model_code not in capabilities["supported_models"]:
                        continue
                
                # 检查是否支持任务类型
                if capabilities.get("supported_tasks") and task_type not in capabilities["supported_tasks"]:
                    # 如果未明确支持该任务类型，但支持列表不为空，则跳过
                    if capabilities["supported_tasks"]:
                        continue
                
                # 计算该节点对此任务的适应度分数
                task_complexity_score = self.task_complexity.get(task_type, self.task_complexity["default"])
                
                # 如果是高复杂度任务，且节点有GPU，增加得分
                if task_complexity_score > 1.5 and capabilities.get("has_gpu", False):
                    score += 2.0
                
                # 任务负载比例加权
                load_ratio = current_tasks / max(max_tasks, 1)
                final_score = score * (1 - (0.7 * load_ratio))
                
                suitable_nodes.append((mac_address, final_score))
        
        if not suitable_nodes:
            logger.warning(f"找不到适合任务类型 {task_type} 的节点")
            return None
            
        # 按最终得分排序
        suitable_nodes.sort(key=lambda x: x[1], reverse=True)
        
        # 在得分最高的几个节点中随机选择，引入一定随机性避免所有任务集中在同一个节点
        top_count = min(3, len(suitable_nodes))
        selected_idx = 0
        
        if top_count > 1:
            # 80%概率选择得分最高的节点，20%概率选择其他高分节点
            if random.random() > 0.8:
                selected_idx = random.randint(1, top_count - 1)
                
        best_node = suitable_nodes[selected_idx][0]
        logger.info(f"为任务类型 {task_type} 选择节点 {best_node}，得分: {suitable_nodes[selected_idx][1]:.2f}")
        
        return best_node
    
    async def get_node_for_subtask(self, subtask_id: int, db: Session = None) -> Optional[str]:
        """
        为指定子任务找到合适的节点
        
        Args:
            subtask_id: 子任务ID
            db: 数据库会话（可选）
            
        Returns:
            Optional[str]: 合适节点的MAC地址，如果找不到则返回None
        """
        should_close_db = False
        if db is None:
            db = SessionLocal()
            should_close_db = True
            
        try:
            # 查询子任务信息
            subtask = db.query(SubTask).filter(SubTask.id == subtask_id).first()
            if not subtask:
                logger.warning(f"未找到子任务: {subtask_id}")
                return None
                
            # 查询主任务和模型信息
            task = subtask.task
            model = subtask.model
            
            if not task or not model:
                logger.warning(f"子任务 {subtask_id} 缺少主任务或模型信息")
                return None
                
            # 确定任务类型
            analysis_type = subtask.analysis_type
            task_type = analysis_type
            
            # 根据流类型调整任务类型
            if task.stream_type == "image":
                task_type = "image_detection"
            elif task.stream_type == "video":
                task_type = "video_detection"
            elif task.stream_type == "stream":
                task_type = "stream_detection"
                
            # 基于任务类型和分析类型找到最佳节点
            return await self.get_best_node_for_task(task_type, model.code)
        finally:
            if should_close_db:
                db.close()
    
    async def update_node_task_load(self, mac_address: str, change: int = 1) -> None:
        """
        更新节点任务负载计数
        
        Args:
            mac_address: 节点MAC地址
            change: 任务数变化，正数表示增加，负数表示减少
        """
        db = SessionLocal()
        try:
            node = db.query(MQTTNode).filter(MQTTNode.mac_address == mac_address).first()
            if node:
                # 更新任务计数
                node.task_count = max(0, node.task_count + change)
                
                # 更新节点缓存的得分
                async with self.lock:
                    if mac_address in self.node_scores:
                        self.node_scores[mac_address] = self._calculate_node_score(node)
                        
                    if mac_address in self.node_capabilities:
                        self.node_capabilities[mac_address]["current_tasks"] = node.task_count
                
                db.commit()
                logger.info(f"已更新节点 {mac_address} 的任务负载: {node.task_count}")
            else:
                logger.warning(f"未找到要更新的节点: {mac_address}")
        finally:
            db.close()
    
    async def distribute_pending_tasks(self, max_tasks: int = 10) -> int:
        """
        分配等待中的任务到合适的节点
        
        Args:
            max_tasks: 一次最多分配的任务数
            
        Returns:
            int: 成功分配的任务数
        """
        # 从优先级队列获取待分配任务
        tasks_to_process = []
        for _ in range(max_tasks):
            task = await task_priority_manager.get_next_task()
            if not task:
                break
            tasks_to_process.append(task)
            
        if not tasks_to_process:
            return 0
            
        logger.info(f"从优先级队列获取到 {len(tasks_to_process)} 个待分配任务")
        
        # 确保节点信息已同步
        await self.sync_nodes_from_db(force=True)
        
        # 分配任务
        success_count = 0
        
        db = SessionLocal()
        try:
            for task_data in tasks_to_process:
                subtask_id = task_data["subtask_id"]
                
                # 查询子任务详细信息
                subtask = None
                if subtask_id.isdigit():
                    subtask = db.query(SubTask).filter(SubTask.id == int(subtask_id)).first()
                
                if not subtask:
                    logger.warning(f"未找到子任务 {subtask_id}，跳过分配")
                    continue
                    
                # 获取最佳节点
                best_node_mac = await self.get_node_for_subtask(int(subtask_id), db)
                
                if not best_node_mac:
                    logger.warning(f"找不到适合子任务 {subtask_id} 的节点，重新加入队列")
                    # 重新加入队列，但降低优先级
                    new_priority = max(0, task_data["priority"] - 1)
                    await task_priority_manager.add_task(
                        task_data["task_id"], 
                        subtask_id,
                        priority=new_priority,
                        task_data=task_data["data"]
                    )
                    continue
                
                # 尝试向该节点分配任务 (此处需要添加实际发送任务的代码)
                # ...
                # 这里需要使用mqtt_client.send_task_to_node函数发送任务
                # ...
                
                # 更新节点任务计数
                await self.update_node_task_load(best_node_mac, change=1)
                
                success_count += 1
                logger.info(f"成功将子任务 {subtask_id} 分配给节点 {best_node_mac}")
        finally:
            db.close()
            
        logger.info(f"分配任务完成，成功: {success_count}, 失败: {len(tasks_to_process) - success_count}")
        return success_count
    
    async def get_scheduler_status(self) -> Dict[str, Any]:
        """
        获取调度器状态信息
        
        Returns:
            Dict[str, Any]: 调度器状态
        """
        status = {
            "nodes_count": len(self.node_scores),
            "top_nodes": [],
            "task_types": list(self.task_complexity.keys()),
            "last_sync": self.last_node_sync
        }
        
        # 获取得分最高的几个节点
        top_nodes = sorted(
            [(mac, score) for mac, score in self.node_scores.items()],
            key=lambda x: x[1],
            reverse=True
        )[:5]  # 最多显示5个
        
        for mac, score in top_nodes:
            capabilities = self.node_capabilities.get(mac, {})
            status["top_nodes"].append({
                "mac_address": mac,
                "score": round(score, 2),
                "tasks": capabilities.get("current_tasks", 0),
                "max_tasks": capabilities.get("max_tasks", 0),
                "has_gpu": capabilities.get("has_gpu", False)
            })
            
        # 获取队列状态
        status["queue_status"] = await task_priority_manager.get_queue_status()
        
        return status

# 全局实例
smart_task_scheduler = SmartTaskScheduler()

# 获取智能任务调度器实例
def get_smart_task_scheduler() -> SmartTaskScheduler:
    """
    获取智能任务调度器实例
    
    Returns:
        SmartTaskScheduler: 智能任务调度器实例
    """
    return smart_task_scheduler 