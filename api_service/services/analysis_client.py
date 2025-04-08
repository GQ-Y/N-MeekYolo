import logging
import json
import uuid
import httpx
import time
from typing import Dict, Any, List, Optional, Union, Tuple
from .mqtt_client import MQTTClient
from crud.node import NodeCRUD
from core.database import SessionLocal
from models.database import Node
from datetime import datetime
import yaml
import traceback

logger = logging.getLogger(__name__)

class AnalysisClient:
    """
    分析服务客户端适配器，支持HTTP和MQTT两种通信模式
    根据配置文件中的通信模式自动选择使用HTTP还是MQTT通信
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化分析服务客户端
        
        Args:
            config: 配置信息，包含COMMUNICATION和MQTT部分
        """
        self.config = config
        self.mode = config.get('COMMUNICATION', {}).get('mode', 'http')
        
        # 初始化HTTP客户端 - 不再使用固定URL，而是动态选择节点
        self.http_client = None
        
        # 初始化MQTT客户端
        if self.mode == 'mqtt' or self.mode == 'both':
            self.mqtt_client = MQTTClient(config.get('MQTT', {}))
            self._mqtt_connected = self.mqtt_client.connect()
        else:
            self.mqtt_client = None
            self._mqtt_connected = False
            
        logger.info(f"分析服务客户端初始化完成，通信模式: {self.mode}")
    
    @property
    def mqtt_connected(self):
        """获取MQTT连接状态"""
        # 优先检查客户端本身是否连接
        if self.mqtt_client:
            # 优先使用客户端的is_connected方法（如果可用）
            if hasattr(self.mqtt_client, "is_connected") and callable(getattr(self.mqtt_client, "is_connected")):
                is_connected = self.mqtt_client.is_connected()
                # 如果状态与缓存不一致，更新缓存
                if is_connected != self._mqtt_connected:
                    logger.info(f"更新MQTT连接状态缓存: {self._mqtt_connected} -> {is_connected}")
                    self._mqtt_connected = is_connected
                return is_connected
            # 否则使用mqtt_client.connected属性
            elif hasattr(self.mqtt_client, "connected"):
                return self.mqtt_client.connected
        # 如果无法检查，返回缓存状态
        return self._mqtt_connected
    
    async def _get_available_node(self, task_type: str = "image") -> Tuple[Optional[int], Optional[str]]:
        """
        获取可用的分析服务节点
        
        Args:
            task_type: 任务类型，用于增加对应的任务计数
            
        Returns:
            Tuple[Optional[int], Optional[str]]: 节点ID和URL
        """
        db = SessionLocal()
        try:
            # 使用动态节点选择获取可用节点
            node = NodeCRUD.get_available_node(db)
            if node:
                node_id = node.id
                node_url = f"http://{node.ip}:{node.port}"
                
                # 更新节点任务计数
                if task_type == "image":
                    node.image_task_count += 1
                elif task_type == "video":
                    node.video_task_count += 1
                elif task_type == "stream":
                    node.stream_task_count += 1
                
                db.commit()
                return node_id, node_url
            else:
                logger.error("未找到可用的分析服务节点")
                return None, None
        except Exception as e:
            logger.error(f"获取可用节点失败: {e}")
            return None, None
        finally:
            db.close()
    
    async def analyze_image(self, 
                           model_code: str, 
                           image_urls: List[str], 
                           config: Optional[Dict[str, Any]] = None,
                           task_name: Optional[str] = None,
                           callback_urls: Optional[str] = None,
                           enable_callback: bool = False,
                           save_result: bool = False,
                           is_base64: bool = False) -> Dict[str, Any]:
        """
        图片分析
        
        Args:
            model_code: 模型代码
            image_urls: 图片URL列表
            config: 分析配置
            task_name: 任务名称
            callback_urls: 回调URL
            enable_callback: 是否启用回调
            save_result: 是否保存结果
            is_base64: 是否使用Base64
            
        Returns:
            Dict: 分析结果
        """
        task_id = str(uuid.uuid4())
        
        # 构建请求数据
        data = {
            "model_code": model_code,
            "image_urls": image_urls,
            "config": config or {},
            "task_name": task_name or f"图片分析-{task_id[:8]}",
            "callback_urls": callback_urls,
            "enable_callback": enable_callback,
            "save_result": save_result,
            "is_base64": is_base64
        }
        
        # 根据通信模式处理请求
        if self.mode == 'mqtt' and self.mqtt_connected:
            # 使用MQTT通信
            logger.info(f"使用MQTT模式发送图片分析请求: task_id={task_id}")
            
            # 获取可用MQTT节点
            mqtt_node = await self.mqtt_client.get_available_mqtt_node()
            if not mqtt_node:
                return {
                    "requestId": task_id,
                    "path": "/api/v1/analyze/image",
                    "success": False,
                    "message": "未找到可用的MQTT分析节点",
                    "code": 500,
                    "data": None,
                    "timestamp": int(time.time())
                }
            
            # 生成子任务ID
            subtask_id = f"{task_id}-1"
            
            # 构建任务配置
            task_config = {
                "source": {
                    "type": "image",
                    "urls": image_urls,
                    "is_base64": is_base64
                },
                "config": {
                    "model_code": model_code,
                    **(config or {})
                },
                "save_result": save_result
            }
            
            # 向选定的节点发送任务
            success, response = await self.mqtt_client.send_task_to_node(
                mac_address=mqtt_node.mac_address,
                task_id=task_id,
                subtask_id=subtask_id,
                config=task_config
            )
            
            # 更新数据库中的子任务状态
            db = SessionLocal()
            try:
                # 先创建主任务
                from crud.task import TaskCRUD
                task = TaskCRUD.create_task(
                    db=db,
                    name=data["task_name"],
                    save_result=save_result
                )
                
                # 创建子任务并关联MQTT节点
                from crud.subtask import SubTaskCRUD
                subtask = SubTaskCRUD.create_subtask(
                    db=db,
                    task_id=task.id,
                    model_id=1,  # 假设默认模型ID为1
                    stream_id=None,
                    config=config,
                    analysis_task_id=subtask_id,
                    mqtt_node_id=mqtt_node.id if success else None,
                    status=1 if success else 0  # 成功则状态为运行中，失败则为未启动
                )
                
                if success:
                    # 更新主任务状态
                    task.status = 1  # 运行中
                    task.started_at = datetime.now()
                    task.active_subtasks = 1
                    task.total_subtasks = 1
                    
                    # 更新MQTT节点任务计数
                    mqtt_node.task_count += 1
                    mqtt_node.image_task_count += 1
                
                db.commit()
                
                return {
                    "requestId": task_id,
                    "path": "/api/v1/analyze/image",
                    "success": success,
                    "message": "任务已提交" if success else f"任务提交失败: {response.get('error', '未知错误')}",
                    "code": 200 if success else 500,
                    "data": {
                        "task_id": str(task.id),
                        "subtask_id": subtask.id
                    },
                    "timestamp": int(time.time())
                }
            except Exception as e:
                logger.error(f"保存任务到数据库失败: {e}")
                db.rollback()
                return {
                    "requestId": task_id,
                    "path": "/api/v1/analyze/image",
                    "success": False,
                    "message": f"保存任务到数据库失败: {str(e)}",
                    "code": 500,
                    "data": None,
                    "timestamp": int(time.time())
                }
            finally:
                db.close()
        else:
            # 使用HTTP通信
            logger.info(f"使用HTTP模式发送图片分析请求: task_id={task_id}")
            
            # 获取可用节点
            node_id, node_url = await self._get_available_node("image")
            if not node_id or not node_url:
                return {
                    "requestId": task_id,
                    "path": "/api/v1/analyze/image",
                    "success": False,
                    "message": "未找到可用的分析服务节点",
                    "code": 500,
                    "data": None,
                    "timestamp": int(time.time())
                }
            
            # 添加节点ID到请求数据
            data["node_id"] = node_id
            
            try:
                # 使用节点URL发送请求
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(f"{node_url}/api/v1/analyze/image", json=data)
                    return response.json()
            except Exception as e:
                logger.error(f"HTTP请求失败: {e}")
                # 减少节点任务计数
                await self._decrease_node_task_count(node_id, "image")
                return {
                    "requestId": task_id,
                    "path": "/api/v1/analyze/image",
                    "success": False,
                    "message": f"HTTP请求失败: {str(e)}",
                    "code": 500,
                    "data": None,
                    "timestamp": int(time.time())
                }
    
    async def analyze_video(self, 
                           model_code: str, 
                           video_url: str, 
                           config: Optional[Dict[str, Any]] = None,
                           task_name: Optional[str] = None,
                           callback_urls: Optional[str] = None,
                           enable_callback: bool = False,
                           save_result: bool = False) -> Dict[str, Any]:
        """
        视频分析
        
        Args:
            model_code: 模型代码
            video_url: 视频URL
            config: 分析配置
            task_name: 任务名称
            callback_urls: 回调URL
            enable_callback: 是否启用回调
            save_result: 是否保存结果
            
        Returns:
            Dict: 分析结果
        """
        task_id = str(uuid.uuid4())
        
        # 构建请求数据
        data = {
            "model_code": model_code,
            "video_url": video_url,
            "config": config or {},
            "task_name": task_name or f"视频分析-{task_id[:8]}",
            "callback_urls": callback_urls,
            "enable_callback": enable_callback,
            "save_result": save_result
        }
        
        # 根据通信模式处理请求
        if self.mode == 'mqtt' and self.mqtt_connected:
            # 使用MQTT通信
            logger.info(f"使用MQTT模式发送视频分析请求: task_id={task_id}")
            
            # 获取可用的MQTT节点
            mqtt_node = await self.mqtt_client.get_available_mqtt_node()
            if not mqtt_node:
                logger.warning("未找到可用的MQTT节点，将直接创建任务")
                # 不提前返回，继续尝试创建任务
            
            # 构建任务配置
            task_config = {
                "source": {
                    "type": "video",
                    "urls": [video_url]
                },
                "config": {
                    "model_code": model_code,
                    **(config or {})
                },
                "result_config": {
                    "save_result": save_result,
                    "callback_urls": callback_urls.split(",") if callback_urls else [],
                    "enable_callback": enable_callback
                }
            }
            
            # 如果找到节点，尝试通过MQTT发送任务
            success = False
            response = {"error": "未初始化"}
            
            if mqtt_node:
                # 使用正确的方法发送任务
                success, response = await self.mqtt_client.send_task_to_node(
                    mac_address=mqtt_node.mac_address,
                    task_id=task_id,
                    subtask_id=f"{task_id}-1",  # 生成子任务ID
                    config=task_config
                )
            else:
                # 即使没有找到MQTT节点，也创建一个任务（稍后可以通过健康检查重新分配）
                logger.warning(f"没有可用的MQTT节点，创建任务 {task_id} 但不分配节点")
                # 自己处理成功状态和响应
                success = True
                response = {}
            
            if success:
                return {
                    "requestId": task_id,
                    "path": "/api/v1/analyze/video",
                    "success": True,
                    "message": "任务已提交" + (" (未分配节点)" if not mqtt_node else ""),
                    "code": 200,
                    "data": {
                        "task_id": task_id
                    },
                    "timestamp": int(time.time())
                }
            else:
                return {
                    "requestId": task_id,
                    "path": "/api/v1/analyze/video",
                    "success": False,
                    "message": f"MQTT消息发送失败: {response.get('error', '未知错误')}",
                    "code": 500,
                    "data": None,
                    "timestamp": int(time.time())
                }
        else:
            # 使用HTTP通信
            logger.info(f"使用HTTP模式发送视频分析请求: task_id={task_id}")
            
            # 获取可用节点
            node_id, node_url = await self._get_available_node("video")
            if not node_id or not node_url:
                return {
                    "requestId": task_id,
                    "path": "/api/v1/analyze/video",
                    "success": False,
                    "message": "未找到可用的分析服务节点",
                    "code": 500,
                    "data": None,
                    "timestamp": int(time.time())
                }
            
            # 添加节点ID到请求数据
            data["node_id"] = node_id
            
            try:
                # 使用节点URL发送请求
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(f"{node_url}/api/v1/analyze/video", json=data)
                    return response.json()
            except Exception as e:
                logger.error(f"HTTP请求失败: {e}")
                # 减少节点任务计数
                await self._decrease_node_task_count(node_id, "video")
                return {
                    "requestId": task_id,
                    "path": "/api/v1/analyze/video",
                    "success": False,
                    "message": f"HTTP请求失败: {str(e)}",
                    "code": 500,
                    "data": None,
                    "timestamp": int(time.time())
                }
    
    async def analyze_stream(self, 
                            model_code: str, 
                            stream_url: str, 
                            config: Optional[Dict[str, Any]] = None,
                            task_name: Optional[str] = None,
                            callback_urls: Optional[str] = None,
                            callback_url: Optional[str] = None,
                            enable_callback: bool = False,
                            save_result: bool = False,
                            task_id: Optional[str] = None,
                            analysis_type: str = "detection") -> Dict[str, Any]:
        """
        流分析
        
        Args:
            model_code: 模型代码
            stream_url: 流URL
            config: 分析配置
            task_name: 任务名称
            callback_urls: 回调URL列表
            callback_url: 系统回调URL
            enable_callback: 是否启用回调
            save_result: 是否保存结果
            task_id: 任务ID
            analysis_type: 分析类型
            
        Returns:
            Dict: 分析结果
        """
        task_id = task_id or str(uuid.uuid4())
        
        # 构建请求数据
        data = {
            "model_code": model_code,
            "stream_url": stream_url,
            "config": config or {},
            "task_name": task_name or f"流分析-{task_id[:8]}",
            "callback_urls": callback_urls,
            "callback_url": callback_url,
            "enable_callback": enable_callback,
            "save_result": save_result,
            "task_id": task_id,
            "analysis_type": analysis_type
        }
        
        # 根据通信模式处理请求
        if self.mode == 'mqtt' and self.mqtt_connected:
            # 使用MQTT通信
            logger.info(f"使用MQTT模式发送流分析请求: task_id={task_id}")
            
            # 获取可用的MQTT节点
            mqtt_node = await self.mqtt_client.get_available_mqtt_node()
            if not mqtt_node:
                logger.warning("未找到可用的MQTT节点，将直接创建任务")
                # 不提前返回，继续尝试创建任务
            
            # 构建任务配置
            task_config = {
                "source": {
                    "type": "stream",
                    "urls": [stream_url]
                },
                "config": {
                    "model_code": model_code,
                    "analysis_type": analysis_type,
                    **(config or {})
                },
                "result_config": {
                    "save_result": save_result,
                    "callback_urls": callback_urls.split(",") if callback_urls else [],
                    "callback_url": callback_url,
                    "enable_callback": enable_callback
                }
            }
            
            # 如果找到节点，尝试通过MQTT发送任务
            success = False
            response = {"error": "未初始化"}
            
            if mqtt_node:
                # 使用正确的方法发送任务
                success, response = await self.mqtt_client.send_task_to_node(
                    mac_address=mqtt_node.mac_address,
                    task_id=task_id,
                    subtask_id=f"{task_id}-1",  # 生成子任务ID
                    config=task_config
                )
            else:
                # 即使没有找到MQTT节点，也创建一个任务（稍后可以通过健康检查重新分配）
                logger.warning(f"没有可用的MQTT节点，创建任务 {task_id} 但不分配节点")
                # 自己处理成功状态和响应
                success = True
                response = {}
            
            if success:
                return {
                    "requestId": task_id,
                    "path": "/api/v1/analyze/stream",
                    "success": True,
                    "message": "任务已提交" + (" (未分配节点)" if not mqtt_node else ""),
                    "code": 200,
                    "data": {
                        "task_id": task_id
                    },
                    "timestamp": int(time.time())
                }
            else:
                return {
                    "requestId": task_id,
                    "path": "/api/v1/analyze/stream",
                    "success": False,
                    "message": f"MQTT消息发送失败: {response.get('error', '未知错误')}",
                    "code": 500,
                    "data": None,
                    "timestamp": int(time.time())
                }
        else:
            # 使用HTTP通信 - 使用现有的服务接口
            logger.info(f"使用HTTP模式发送流分析请求: task_id={task_id}")
            
            # 使用分析服务的现有实现，它已经包含动态节点选择
            from services.analysis import AnalysisService
            analysis_service = AnalysisService()
            
            try:
                # 调用现有的流分析方法，它会动态选择节点
                result_tuple = await analysis_service.analyze_stream(
                    model_code=model_code,
                    stream_url=stream_url,
                    task_name=task_name or f"流分析-{task_id[:8]}",
                    callback_url=callback_url,
                    callback_urls=callback_urls,
                    enable_callback=enable_callback,
                    save_result=save_result,
                    config=config,
                    analysis_task_id=task_id,
                    analysis_type=analysis_type
                )
                
                if result_tuple:
                    actual_task_id, node_id = result_tuple
                    return {
                        "requestId": task_id,
                        "path": "/api/v1/analyze/stream",
                        "success": True,
                        "message": "任务已提交",
                        "code": 200,
                        "data": {
                            "task_id": actual_task_id,
                            "node_id": node_id
                        },
                        "timestamp": int(time.time())
                    }
                else:
                    return {
                        "requestId": task_id,
                        "path": "/api/v1/analyze/stream",
                        "success": False,
                        "message": "未找到可用的分析服务节点",
                        "code": 500,
                        "data": None,
                        "timestamp": int(time.time())
                    }
            except Exception as e:
                logger.error(f"分析服务调用失败: {e}")
                return {
                    "requestId": task_id,
                    "path": "/api/v1/analyze/stream",
                    "success": False,
                    "message": f"分析服务调用失败: {str(e)}",
                    "code": 500,
                    "data": None,
                    "timestamp": int(time.time())
                }
    
    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        获取任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            Dict: 任务状态信息
        """
        # 构建请求数据
        data = {
            "task_id": task_id
        }
        
        # 根据通信模式处理请求
        if self.mode == 'mqtt' and self.mqtt_connected:
            # 使用MQTT通信
            logger.info(f"使用MQTT模式获取任务状态: task_id={task_id}")
            
            # 从MQTT客户端缓存获取任务状态
            task_status = self.mqtt_client.get_task_status(task_id)
            
            if task_status:
                return {
                    "requestId": str(uuid.uuid4()),
                    "path": "/api/v1/analyze/task/status",
                    "success": True,
                    "message": "Success",
                    "code": 200,
                    "data": task_status,
                    "timestamp": int(time.time())
                }
            else:
                return {
                    "requestId": str(uuid.uuid4()),
                    "path": "/api/v1/analyze/task/status",
                    "success": False,
                    "message": "任务未找到",
                    "code": 404,
                    "data": None,
                    "timestamp": int(time.time())
                }
        else:
            # 使用HTTP通信 - 通过子任务表查找任务所在节点
            logger.info(f"使用HTTP模式获取任务状态: task_id={task_id}")
            
            db = SessionLocal()
            try:
                # 查找与此分析任务关联的子任务
                from models.database import SubTask
                subtask = db.query(SubTask).filter(SubTask.analysis_task_id == task_id).first()
                
                if not subtask or not subtask.node_id:
                    return {
                        "requestId": str(uuid.uuid4()),
                        "path": "/api/v1/analyze/task/status",
                        "success": False,
                        "message": "找不到任务或任务未关联节点",
                        "code": 404,
                        "data": None,
                        "timestamp": int(time.time())
                    }
                
                # 获取节点信息
                node = db.query(Node).filter(Node.id == subtask.node_id).first()
                if not node:
                    return {
                        "requestId": str(uuid.uuid4()),
                        "path": "/api/v1/analyze/task/status",
                        "success": False,
                        "message": "找不到任务关联的节点",
                        "code": 404,
                        "data": None,
                        "timestamp": int(time.time())
                    }
                
                # 构建请求URL
                node_url = f"http://{node.ip}:{node.port}/api/v1/analyze/task/status"
                
                # 发送状态查询请求
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(node_url, json=data)
                    return response.json()
                
            except Exception as e:
                logger.error(f"获取任务状态失败: {e}")
                return {
                    "requestId": str(uuid.uuid4()),
                    "path": "/api/v1/analyze/task/status",
                    "success": False,
                    "message": f"获取任务状态失败: {str(e)}",
                    "code": 500,
                    "data": None,
                    "timestamp": int(time.time())
                }
            finally:
                db.close()
    
    async def stop_task(self, task_id: str) -> Dict[str, Any]:
        """
        停止任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            Dict: 操作结果
        """
        # 构建请求数据
        data = {
            "task_id": task_id
        }
        
        # 根据通信模式处理请求
        if self.mode == 'mqtt' and self.mqtt_connected:
            # 使用MQTT通信
            logger.info(f"使用MQTT模式停止任务: task_id={task_id}")
            
            # 发布任务控制命令
            success = self.mqtt_client.publish_task_control(task_id, "stop", {})
            
            if success:
                return {
                    "requestId": str(uuid.uuid4()),
                    "path": "/api/v1/analyze/task/stop",
                    "success": True,
                    "message": "任务停止命令已发送",
                    "code": 200,
                    "data": None,
                    "timestamp": int(time.time())
                }
            else:
                return {
                    "requestId": str(uuid.uuid4()),
                    "path": "/api/v1/analyze/task/stop",
                    "success": False,
                    "message": "MQTT消息发送失败",
                    "code": 500,
                    "data": None,
                    "timestamp": int(time.time())
                }
        else:
            # 使用HTTP通信 - 使用现有的服务接口
            logger.info(f"使用HTTP模式停止任务: task_id={task_id}")
            
            # 使用分析服务的现有实现，它已经包含节点查找和通信逻辑
            from services.analysis import AnalysisService
            analysis_service = AnalysisService()
            
            try:
                # 调用现有的停止任务方法
                result = await analysis_service.stop_task(task_id)
                
                return {
                    "requestId": str(uuid.uuid4()),
                    "path": "/api/v1/analyze/task/stop",
                    "success": True,
                    "message": "任务已停止",
                    "code": 200,
                    "data": result,
                    "timestamp": int(time.time())
                }
            except Exception as e:
                logger.error(f"停止任务失败: {e}")
                return {
                    "requestId": str(uuid.uuid4()),
                    "path": "/api/v1/analyze/task/stop",
                    "success": False,
                    "message": f"停止任务失败: {str(e)}",
                    "code": 500,
                    "data": None,
                    "timestamp": int(time.time())
                }
    
    async def get_resource_status(self) -> Dict[str, Any]:
        """
        获取资源状态
        
        Returns:
            Dict: 资源状态信息
        """
        # 根据通信模式处理请求
        if self.mode == 'mqtt' and self.mqtt_connected:
            # 使用MQTT通信
            logger.info("使用MQTT模式获取资源状态")
            
            # 获取所有分析节点的状态
            nodes = self.mqtt_client.get_all_nodes()
            
            # 汇总资源状态
            resource_info = {
                "nodes": len([n for n in nodes.values() if n.get('status') == 'online']),
                "cpu_usage": 0,
                "memory_usage": 0,
                "gpu_usage": 0,
                "details": []
            }
            
            # 计算平均值
            online_nodes = [n for n in nodes.values() if n.get('status') == 'online']
            if online_nodes:
                for node in online_nodes:
                    resource = node.get('metadata', {}).get('resource', {})
                    resource_info['cpu_usage'] += resource.get('cpu_usage', 0)
                    resource_info['memory_usage'] += resource.get('memory_usage', 0)
                    resource_info['gpu_usage'] += resource.get('gpu_usage', 0)
                    resource_info['details'].append({
                        'node_id': node.get('node_id'),
                        'resource': resource
                    })
                
                # 计算平均值
                if len(online_nodes) > 0:
                    resource_info['cpu_usage'] /= len(online_nodes)
                    resource_info['memory_usage'] /= len(online_nodes)
                    resource_info['gpu_usage'] /= len(online_nodes)
            
            return {
                "requestId": str(uuid.uuid4()),
                "path": "/api/v1/analyze/resource",
                "success": True,
                "message": "Success",
                "code": 200,
                "data": resource_info,
                "timestamp": int(time.time())
            }
        else:
            # 使用HTTP通信 - 从数据库直接查询节点状态
            logger.info("使用HTTP模式获取资源状态")
            
            db = SessionLocal()
            try:
                # 查询在线节点
                nodes = db.query(Node).filter(
                    Node.service_status == "online",
                    Node.is_active == True,
                    Node.service_type == 1  # 分析服务
                ).all()
                
                # 构建资源状态信息
                resource_info = {
                    "nodes": len(nodes),
                    "cpu_usage": 0,
                    "memory_usage": 0,
                    "gpu_usage": 0,
                    "details": []
                }
                
                # 计算平均值和收集详情
                if nodes:
                    for node in nodes:
                        resource_info['cpu_usage'] += node.cpu_usage or 0
                        resource_info['memory_usage'] += node.memory_usage or 0
                        resource_info['gpu_usage'] += node.gpu_memory_usage or 0
                        
                        # 计算任务总数
                        total_tasks = (node.image_task_count or 0) + (node.video_task_count or 0) + (node.stream_task_count or 0)
                        
                        resource_info['details'].append({
                            'node_id': node.id,
                            'ip': node.ip,
                            'port': node.port,
                            'resource': {
                                'cpu_usage': node.cpu_usage or 0,
                                'memory_usage': node.memory_usage or 0,
                                'gpu_usage': node.gpu_memory_usage or 0,
                                'task_count': total_tasks,
                                'max_tasks': node.max_tasks
                            }
                        })
                    
                    # 计算平均值
                    if len(nodes) > 0:
                        resource_info['cpu_usage'] /= len(nodes)
                        resource_info['memory_usage'] /= len(nodes)
                        resource_info['gpu_usage'] /= len(nodes)
                
                return {
                    "requestId": str(uuid.uuid4()),
                    "path": "/api/v1/analyze/resource",
                    "success": True,
                    "message": "Success",
                    "code": 200,
                    "data": resource_info,
                    "timestamp": int(time.time())
                }
            except Exception as e:
                logger.error(f"获取资源状态失败: {e}")
                return {
                    "requestId": str(uuid.uuid4()),
                    "path": "/api/v1/analyze/resource",
                    "success": False,
                    "message": f"获取资源状态失败: {str(e)}",
                    "code": 500,
                    "data": None,
                    "timestamp": int(time.time())
                }
            finally:
                db.close()
    
    async def _decrease_node_task_count(self, node_id: int, task_type: str = "stream"):
        """
        减少节点任务计数
        
        Args:
            node_id: 节点ID
            task_type: 任务类型
        """
        if not node_id:
            return
        
        db = SessionLocal()
        try:
            node = db.query(Node).filter(Node.id == node_id).first()
            if node:
                if task_type == "image" and node.image_task_count > 0:
                    node.image_task_count -= 1
                elif task_type == "video" and node.video_task_count > 0:
                    node.video_task_count -= 1
                elif task_type == "stream" and node.stream_task_count > 0:
                    node.stream_task_count -= 1
                
                db.commit()
                logger.info(f"节点 {node_id} {task_type}任务计数-1")
        except Exception as e:
            logger.error(f"减少节点任务计数失败: {e}")
        finally:
            db.close()
    
    async def close(self):
        """
        关闭客户端连接
        """
        # 关闭HTTP客户端
        if hasattr(self, 'http_client') and self.http_client:
            await self.http_client.aclose()
        
        # 断开MQTT连接
        if self.mqtt_client and self.mqtt_connected:
            self.mqtt_client.disconnect()

    def __del__(self):
        """
        析构函数，确保资源被正确释放
        """
        # 断开MQTT连接
        if hasattr(self, 'mqtt_client') and self.mqtt_client and getattr(self, '_mqtt_connected', False):
            self.mqtt_client.disconnect() 