import logging
import json
import uuid
import httpx
import time
from typing import Dict, Any, List, Optional, Union, Tuple
from services.mqtt.mqtt_client import MQTTClient
from crud.node import NodeCRUD
from core.database import SessionLocal
from models.database import Node
from datetime import datetime
import yaml
import traceback
from crud.task import TaskCRUD
from models.database import Task, Model
from crud.model import get_model_by_code

logger = logging.getLogger(__name__)

class AnalysisClient:
    """
    分析服务客户端适配器，支持HTTP和MQTT两种通信模式
    根据配置文件中的通信模式自动选择使用HTTP还是MQTT通信
    """
    
    def __init__(self, config: Dict[str, Any], mqtt_client=None):
        """
        初始化分析服务客户端
        
        Args:
            config: 配置信息，包含COMMUNICATION和MQTT部分
            mqtt_client: 可选的现有MQTT客户端实例，如果提供则使用该实例而不创建新实例
        """
        self.config = config
        self.mode = config.get('COMMUNICATION', {}).get('mode', 'http')
        
        # 初始化HTTP客户端 - 不再使用固定URL，而是动态选择节点
        self.http_client = None
        
        # 初始化MQTT客户端
        if self.mode == 'mqtt' or self.mode == 'both':
            if mqtt_client:
                # 使用已提供的MQTT客户端实例
                self.mqtt_client = mqtt_client
                self._mqtt_connected = self.mqtt_client.connected
                logger.info("使用已存在的MQTT客户端实例")
            else:
                # 创建新的MQTT客户端实例
                self.mqtt_client = MQTTClient(config.get('MQTT', {}))
                self._mqtt_connected = self.mqtt_client.connect()
                logger.info("创建了新的MQTT客户端实例")
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
                logger.warning("未找到可用的MQTT节点，将直接创建任务")
                # 不提前返回，继续创建任务
            
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
            
            # 创建数据库中的任务记录
            db = SessionLocal()
            try:
                # 创建主任务
                from models.database import Task
                task = Task(
                    name=task_name or f"图片分析-{task_id[:8]}",
                    status=0,  # 初始状态为"已创建"
                    callback_urls=callback_urls,
                    enable_callback=enable_callback,
                    save_result=save_result,
                    created_at=datetime.now()
                )
                db.add(task)
                db.flush()
                
                # 查找模型ID
                model = get_model_by_code(db, model_code)
                if not model:
                    # 如果找不到模型，记录错误并回滚事务
                    error_msg = f"找不到模型: {model_code}"
                    logger.error(error_msg)
                    db.rollback()
                    return {
                        "requestId": task_id,
                        "path": "/api/v1/analyze/image",
                        "success": False,
                        "message": error_msg,
                        "code": 400,
                        "data": None,
                        "timestamp": int(time.time())
                    }
                
                # 创建子任务记录，为MQTT通信生成一个唯一的analysis_task_id
                analysis_task_id = str(uuid.uuid4())
                
                from crud.subtask import SubTaskCRUD
                subtask = SubTaskCRUD.create_subtask(
                    db=db,
                    task_id=task.id,
                    model_id=model.id,
                    stream_id=None,
                    config=config,
                    analysis_task_id=analysis_task_id,
                    mqtt_node_id=mqtt_node.id if mqtt_node else None,
                    status=0  # 初始状态为未启动
                )
                
                if mqtt_node:
                    # 向选定的节点发送任务（不等待响应）
                    await self.mqtt_client.send_task_to_node(
                        mac_address=mqtt_node.mac_address,
                        task_id=str(task.id),
                        subtask_id=analysis_task_id,
                        config=task_config,
                        wait_for_response=False  # 设置为不等待响应
                    )
                    
                    # 更新主任务状态为"处理中"
                    task.status = 1  # 设置为"处理中"状态
                    task.started_at = datetime.now()
                    task.active_subtasks = 1
                    task.total_subtasks = 1
                    
                    # 更新子任务状态为"处理中"
                    subtask.status = 1  # 设置为"处理中"状态
                    subtask.started_at = datetime.now()
                    
                    # 更新MQTT节点任务计数
                    mqtt_node.task_count += 1
                    mqtt_node.image_task_count += 1
                    
                    logger.info(f"图片分析任务 {task.id} 已异步提交给MQTT节点 {mqtt_node.mac_address}")
                    logger.info(f"子任务 {analysis_task_id} 状态将通过MQTT消息更新")
                else:
                    # 未找到可用节点，仅创建任务
                    logger.warning(f"图片分析任务 {task.id} 已创建，但未找到可用MQTT节点分配")
                
                db.commit()
                
                # 返回成功响应
                return {
                    "requestId": task_id,
                    "path": "/api/v1/analyze/image",
                    "success": True,
                    "message": "图片分析任务已提交" + (" (未分配节点)" if not mqtt_node else ""),
                    "code": 200,
                    "data": {
                        "task_id": str(task.id),
                        "subtask_id": subtask.id,
                        "analysis_task_id": analysis_task_id,
                        "mqtt_node_id": mqtt_node.id if mqtt_node else None,
                        "mac_address": mqtt_node.mac_address if mqtt_node else None,
                        "status": "PROCESSING" if mqtt_node else "CREATED"
                    },
                    "timestamp": int(time.time())
                }
            except Exception as e:
                logger.error(f"保存图片分析任务到数据库失败: {e}")
                logger.error(traceback.format_exc())
                db.rollback()
                return {
                    "requestId": task_id,
                    "path": "/api/v1/analyze/image",
                    "success": False,
                    "message": f"保存图片分析任务到数据库失败: {str(e)}",
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
            if mqtt_node:
                # 使用异步方式发送任务，不等待响应
                subtask_id = f"{task_id}-1"  # 生成子任务ID
                
                # 发送任务消息（不等待响应）
                await self.mqtt_client.send_task_to_node(
                    mac_address=mqtt_node.mac_address,
                    task_id=task_id,
                    subtask_id=subtask_id,
                    config=task_config,
                    wait_for_response=False  # 设置为不等待响应
                )
                
                # 在数据库中更新主任务状态，但不更新子任务状态
                db = SessionLocal()
                try:
                    # 检查task_id是否为整数，如果是则直接使用；如果不是则提示错误
                    existing_task = None
                    try:
                        # 尝试将ID转换为整数，如果task_id是纯数字字符串格式，提取主任务ID部分（前面的数字）
                        if task_id.isdigit():
                            # 尝试从纯数字task_id中提取主任务ID部分
                            # 假设格式为：主任务ID + 子任务ID(+1000)
                            # 这里简单处理，取前几位作为主任务ID（根据实际ID长度确定）
                            main_task_id = task_id
                            # 如果ID长度大于5，可能是复合ID，尝试提取主任务ID
                            if len(task_id) > 5:
                                # 查找数据库中是否存在这样的任务ID
                                found = False
                                # 从左到右尝试不同的前缀长度
                                for i in range(1, min(5, len(task_id))):
                                    potential_id = int(task_id[:i])
                                    from models.database import Task
                                    task_check = db.query(Task).filter(Task.id == potential_id).first()
                                    if task_check:
                                        main_task_id = str(potential_id)
                                        found = True
                                        logger.info(f"从复合ID {task_id} 中提取到主任务ID: {main_task_id}")
                                        break
                                
                                if not found:
                                    logger.warning(f"无法从 {task_id} 提取有效的主任务ID，将使用整个ID")
                            
                            # 转换为整数
                            task_id_int = int(main_task_id)
                        else:
                            # 不是纯数字格式
                            task_id_int = int(task_id)
                        
                        from models.database import Task
                        existing_task = db.query(Task).filter(Task.id == task_id_int).first()
                        
                        if not existing_task:
                            logger.error(f"找不到ID为 {task_id_int} 的任务")
                            db.rollback()
                            return {
                                "requestId": task_id,
                                "path": "/api/v1/analyze/video",
                                "success": False,
                                "message": f"找不到ID为 {task_id_int} 的任务",
                                "code": 404,
                                "data": None,
                                "timestamp": int(time.time())
                            }
                        
                        logger.info(f"找到现有任务: ID={task_id_int}")
                    except ValueError:
                        # 如果不是整数ID，返回错误
                        error_msg = f"无效的任务ID格式：{task_id}，必须为整数"
                        logger.error(error_msg)
                        db.rollback()
                        return {
                            "requestId": task_id,
                            "path": "/api/v1/analyze/video",
                            "success": False,
                            "message": error_msg,
                            "code": 400,
                            "data": None,
                            "timestamp": int(time.time())
                        }
                    
                    # 使用现有任务
                    task = existing_task
                    # 更新任务状态为运行中
                    task.status = 1  # 运行中
                    task.started_at = datetime.now() if not task.started_at else task.started_at
                    task.active_subtasks = task.active_subtasks + 1
                    task.total_subtasks = task.total_subtasks + 1
                    logger.info(f"使用任务 ID={task.id}，更新为运行中状态")
                    
                    # 查找模型ID
                    from crud.model import get_model_by_code
                    model = get_model_by_code(db, model_code)
                    if not model:
                        # 如果找不到模型，记录错误并回滚事务
                        error_msg = f"找不到模型: {model_code}"
                        logger.error(error_msg)
                        db.rollback()
                        return {
                            "requestId": task_id,
                            "path": "/api/v1/analyze/video",
                            "success": False,
                            "message": error_msg,
                            "code": 400,
                            "data": None,
                            "timestamp": int(time.time())
                        }
                    
                    # 创建子任务记录，为MQTT通信生成一个唯一的analysis_task_id
                    # 使用UUID而不是复合ID格式
                    analysis_task_id = str(uuid.uuid4())
                    
                    from crud.subtask import SubTaskCRUD
                    subtask = SubTaskCRUD.create_subtask(
                        db=db,
                        task_id=task.id,
                        model_id=model.id,
                        stream_id=None,
                        config=config,
                        analysis_task_id=analysis_task_id,
                        mqtt_node_id=mqtt_node.id,
                        status=0,  # 初始状态为未启动，将通过MQTT消息更新
                        name=f"{model_code}-{task_name or f'视频分析-{task_id[:8]}'}"  # 设置子任务名称
                    )
                    
                    # 在关闭会话前提交事务并获取必要的数据
                    db.commit()
                    task_id_str = str(task.id)
                    subtask_id_int = subtask.id
                    logger.info(f"已创建主任务 {task.id} 和子任务 {subtask.id}，分析任务ID: {analysis_task_id}")
                    logger.info(f"子任务 {analysis_task_id} 状态将通过MQTT消息更新")
                    
                except Exception as e:
                    logger.error(f"创建任务记录时出错: {e}")
                    logger.error(traceback.format_exc())
                    db.rollback()
                finally:
                    db.close()
                
                # 直接返回成功，使用新创建的数据库任务ID
                return {
                    "requestId": task_id,
                    "path": "/api/v1/analyze/video",
                    "success": True,
                    "message": "任务已提交",
                    "code": 200,
                    "data": {
                        "task_id": task_id_str,
                        "subtask_id": subtask_id_int,
                        "mqtt_node_id": mqtt_node.id,
                        "mac_address": mqtt_node.mac_address
                    },
                    "timestamp": int(time.time())
                }
            else:
                # 即使没有找到MQTT节点，也创建一个任务（稍后可以通过健康检查重新分配）
                logger.warning(f"没有可用的MQTT节点，创建任务 {task_id} 但不分配节点")
                
                return {
                    "requestId": task_id,
                    "path": "/api/v1/analyze/video",
                    "success": True,
                    "message": "任务已创建，等待节点分配",
                    "code": 200,
                    "data": {
                        "task_id": task_id
                    },
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
                            analysis_type: str = "detection",
                            subtask_id: Optional[int] = None) -> Dict[str, Any]:
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
            subtask_id: 子任务ID，如果提供则不创建新的子任务
            
        Returns:
            Dict: 分析结果
        """
        # 生成一个请求ID，用于日志追踪
        request_id = str(uuid.uuid4())
        
        # 构建请求数据
        data = {
            "model_code": model_code,
            "stream_url": stream_url,
            "config": config or {},
            "task_name": task_name or f"流分析-{request_id[:8]}",
            "callback_urls": callback_urls,
            "callback_url": callback_url,
            "enable_callback": enable_callback,
            "save_result": save_result,
            "task_id": task_id,
            "analysis_type": analysis_type
        }
        
        # 从URL中提取stream_id（如果可能的话）
        stream_id = None
        try:
            # 尝试从URL中提取stream_id，假设格式为 "http://xxx/streams/12345" 或包含 "stream_id=12345"
            import re
            stream_match = re.search(r'/streams/(\d+)', stream_url)
            if stream_match:
                stream_id = int(stream_match.group(1))
            else:
                stream_param_match = re.search(r'stream_id=(\d+)', stream_url)
                if stream_param_match:
                    stream_id = int(stream_param_match.group(1))
            
            if stream_id:
                logger.info(f"从URL '{stream_url}' 中提取的stream_id: {stream_id}")
        except Exception as e:
            logger.warning(f"从URL提取stream_id失败: {e}，将继续处理")
        
        # 根据通信模式处理请求
        if self.mode == 'mqtt' and self.mqtt_connected:
            # 使用MQTT通信
            logger.info(f"使用MQTT模式发送流分析请求: request_id={request_id}")
            
            # 获取可用的MQTT节点
            mqtt_node = await self.mqtt_client.get_available_mqtt_node()
            if not mqtt_node:
                logger.warning("未找到可用的MQTT节点，将直接创建任务")
            
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
            
            # 在数据库中创建或更新任务
            db = SessionLocal()
            try:
                # 1. 处理主任务
                main_task = None
                main_task_id = None
                existing_subtask = None
                
                # 检查是否提供了有效的任务ID
                if task_id and task_id.isdigit():
                    # 尝试将提供的ID作为整数ID查找现有任务
                    task_id_int = int(task_id)
                    from models.database import Task, SubTask
                    main_task = db.query(Task).filter(Task.id == task_id_int).first()
                    
                    if main_task:
                        logger.info(f"找到现有任务: ID={task_id_int}")
                        main_task_id = task_id_int
                        # 更新任务状态为运行中（如果不是的话）
                        if main_task.status != 1:  # 1表示"处理中"
                            main_task.status = 1  # 运行中
                            main_task.started_at = datetime.now() if not main_task.started_at else main_task.started_at
                        
                        # 如果提供了子任务ID，查找该子任务
                        if subtask_id:
                            existing_subtask = db.query(SubTask).filter(
                                SubTask.id == subtask_id,
                                SubTask.task_id == main_task_id
                            ).first()
                            if existing_subtask:
                                logger.info(f"找到现有子任务: ID={subtask_id}, 任务ID={main_task_id}")
                
                # 如果没有找到现有任务且未指定任务ID，创建新任务
                if not main_task and not task_id:
                    logger.info("未找到现有任务且未指定有效的任务ID，创建新任务")
                    from models.database import Task
                    main_task = Task(
                        name=task_name or f"流分析-{request_id[:8]}",
                        status=0,  # 初始状态为"已创建"
                        save_result=save_result,
                        created_at=datetime.now(),
                        active_subtasks=0,
                        total_subtasks=0
                    )
                    db.add(main_task)
                    db.flush()  # 获取数据库生成的ID
                    main_task_id = main_task.id
                    logger.info(f"创建了新的主任务: ID={main_task_id}")
                elif not main_task and task_id:
                    # 指定了任务ID但找不到对应任务
                    logger.warning(f"指定的任务ID={task_id}不存在，但不会创建新任务以避免冲突")
                    return {
                        "requestId": request_id,
                        "path": "/api/v1/analyze/stream",
                        "success": False,
                        "message": f"指定的任务ID={task_id}不存在",
                        "code": 404,
                        "data": None,
                        "timestamp": int(time.time())
                    }
                
                # 2. 查找模型ID
                from crud.model import get_model_by_code
                model = get_model_by_code(db, model_code)
                if not model:
                    # 如果找不到模型，记录错误并回滚事务
                    error_msg = f"找不到模型: {model_code}"
                    logger.error(error_msg)
                    db.rollback()
                    return {
                        "requestId": request_id,
                        "path": "/api/v1/analyze/stream",
                        "success": False,
                        "message": error_msg,
                        "code": 400,
                        "data": None,
                        "timestamp": int(time.time())
                    }
                
                # 3. 检查是否已存在具有相同stream_id的子任务
                if not existing_subtask and stream_id:
                    from models.database import SubTask
                    existing_subtask = db.query(SubTask).filter(
                        SubTask.task_id == main_task_id,
                        SubTask.stream_id == stream_id,
                        SubTask.model_id == model.id
                    ).first()
                
                if existing_subtask:
                    logger.info(f"找到现有子任务: ID={existing_subtask.id}, stream_id={existing_subtask.stream_id}")
                    subtask = existing_subtask
                    # 如果子任务不是正在运行状态，更新状态
                    if subtask.status != 1:  # 1表示"处理中"
                        subtask.status = 0  # 重置为待处理状态
                        subtask.error_message = None  # 清除之前的错误信息
                    
                    # 如果提供了系统回调URL，更新它
                    if callback_url and not subtask.callback_url:
                        subtask.callback_url = callback_url
                        logger.info(f"更新子任务 {subtask.id} 的回调URL: {callback_url}")
                else:
                    # 获取模型名称和摄像头名称用于构建子任务名称
                    model_name = model.name if model else model_code
                    
                    # 尝试获取摄像头名称
                    stream_name = "未知摄像头"
                    if stream_id:
                        try:
                            # 查询摄像头信息
                            from models.database import Stream
                            stream = db.query(Stream).filter(Stream.id == stream_id).first()
                            if stream and stream.name:
                                stream_name = stream.name
                        except Exception as e:
                            logger.warning(f"获取摄像头名称失败: {e}")
                    
                    # 构建子任务名称：摄像头名称+算法名称
                    subtask_name = f"{stream_name}-{model_name}"
                    logger.info(f"构建子任务名称: {subtask_name}")
                    
                    # 创建新的子任务记录
                    from crud.subtask import SubTaskCRUD
                    subtask = SubTaskCRUD.create_subtask(
                        db=db,
                        task_id=main_task_id,
                        model_id=model.id,
                        stream_id=stream_id,
                        config=config,
                        analysis_task_id=str(main_task_id),  # 使用主任务ID作为分析任务ID，保持一致
                        mqtt_node_id=mqtt_node.id if mqtt_node else None,
                        status=0,  # 初始状态为未启动
                        name=subtask_name,  # 设置子任务名称为：摄像头名称-算法名称
                        enable_callback=enable_callback,
                        callback_url=callback_url
                    )
                    logger.info(f"创建了新的子任务: ID={subtask.id}, stream_id={stream_id}, name={subtask_name}")
                    
                    # 更新主任务的子任务计数
                    main_task.total_subtasks += 1
                
                # 4. 如果有可用的MQTT节点，将任务分配给节点
                if mqtt_node:
                    # 检查节点是否存在于nodes表中
                    from models.database import Node
                    node = db.query(Node).filter(Node.id == mqtt_node.id).first()
                    
                    # 只设置mqtt_node_id，不设置node_id
                    # MQTT模式下，子任务只关联到mqtt_nodes表，不关联到nodes表
                    logger.info(f"使用MQTT节点: ID={mqtt_node.id}, MAC={mqtt_node.mac_address}")
                    subtask.mqtt_node_id = mqtt_node.id
                    
                    # 发送任务消息（不等待响应）
                    await self.mqtt_client.send_task_to_node(
                        mac_address=mqtt_node.mac_address,
                        task_id=str(main_task_id),
                        subtask_id=str(subtask.id),
                        config=task_config,
                        wait_for_response=False
                    )
                    
                    # 更新子任务和主任务状态
                    subtask.status = 1  # 设置为"处理中"状态
                    subtask.started_at = datetime.now()
                    if subtask.error_message == "任务已创建，等待MQTT节点接收" or not subtask.error_message:
                        subtask.error_message = None  # 清除等待消息
                    
                    # 更新主任务状态
                    main_task.status = 1  # 设置为"处理中"状态
                    main_task.started_at = datetime.now() if not main_task.started_at else main_task.started_at
                    if not existing_subtask:
                        main_task.active_subtasks += 1
                    
                    # 更新MQTT节点任务计数
                    mqtt_node.task_count += 1
                    mqtt_node.stream_task_count += 1
                    
                    logger.info(f"子任务 {subtask.id} 已分配给MQTT节点 {mqtt_node.mac_address}")
                else:
                    # 未找到可用节点，设置等待消息
                    subtask.error_message = "任务已创建，等待MQTT节点接收"
                    logger.warning(f"子任务 {subtask.id} 已创建，但未找到可用MQTT节点分配")
                
                # 提交事务
                db.commit()
                
                # 如果找到了现有的子任务并且已经更新了它，直接返回现有子任务信息
                if existing_subtask:
                    logger.info(f"使用已存在的子任务: ID={existing_subtask.id}")
                    
                    # 如果使用现有子任务，更新它的配置
                    if config and existing_subtask.config != config:
                        existing_subtask.config = config
                        logger.info(f"更新子任务配置: ID={existing_subtask.id}")
                    
                    # 构建响应数据
                    task_data = {
                        "task_id": str(main_task_id),
                        "subtask_id": str(existing_subtask.id),
                        "model_code": model_code,
                        "stream_url": stream_url,
                        "mqtt_node_id": existing_subtask.mqtt_node_id,
                        "status": "success",
                        "message": "使用现有子任务，无需创建新任务"
                    }
                    
                    return {
                        "requestId": request_id,
                        "path": "/api/v1/analyze/stream",
                        "success": True,
                        "message": "使用现有子任务",
                        "code": 200,
                        "data": task_data,
                        "timestamp": int(time.time())
                    }
                
                # 返回成功响应
                return {
                    "requestId": request_id,
                    "path": "/api/v1/analyze/stream",
                    "success": True,
                    "message": "任务已提交" + (" (等待节点分配)" if not mqtt_node else ""),
                    "code": 200,
                    "data": {
                        "task_id": str(main_task_id),
                        "subtask_id": subtask.id,
                        "mqtt_node_id": mqtt_node.id if mqtt_node else None,
                        "mac_address": mqtt_node.mac_address if mqtt_node else None,
                        "status": "PROCESSING" if mqtt_node else "CREATED",
                        "stream_id": stream_id
                    },
                    "timestamp": int(time.time())
                }
            except Exception as e:
                logger.error(f"创建流分析任务时出错: {e}")
                logger.error(traceback.format_exc())
                db.rollback()
                
                # 优化错误消息，避免过长
                error_message = str(e)
                if len(error_message) > 500:
                    # 如果错误消息太长，只保留开头和结尾
                    error_message = f"{error_message[:200]}...{error_message[-200:]}"
                
                return {
                    "requestId": request_id,
                    "path": "/api/v1/analyze/stream",
                    "success": False,
                    "message": f"创建流分析任务失败: {error_message}",
                    "code": 500,
                    "data": None,
                    "timestamp": int(time.time())
                }
            finally:
                db.close()
        else:
            # 使用HTTP通信 - 使用现有的服务接口
            logger.info(f"使用HTTP模式发送流分析请求: request_id={request_id}")
            
            # 使用分析服务的现有实现，它已经包含动态节点选择
            from services.http.analysis import AnalysisService
            analysis_service = AnalysisService()
            
            try:
                # 调用现有的流分析方法，它会动态选择节点
                result_tuple = await analysis_service.analyze_stream(
                    model_code=model_code,
                    stream_url=stream_url,
                    task_name=task_name or f"流分析-{request_id[:8]}",
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
                        "requestId": request_id,
                        "path": "/api/v1/analyze/stream",
                        "success": True,
                        "message": "任务已提交",
                        "code": 200,
                        "data": {
                            "task_id": actual_task_id,
                            "node_id": node_id,
                            "stream_id": stream_id
                        },
                        "timestamp": int(time.time())
                    }
                else:
                    return {
                        "requestId": request_id,
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
                    "requestId": request_id,
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
                
                if not subtask:
                    return {
                        "requestId": str(uuid.uuid4()),
                        "path": "/api/v1/analyze/task/status",
                        "success": False,
                        "message": "找不到任务",
                        "code": 404,
                        "data": None,
                        "timestamp": int(time.time())
                    }
                
                # 获取节点信息
                if not subtask.node_id:
                    return {
                        "requestId": str(uuid.uuid4()),
                        "path": "/api/v1/analyze/task/status",
                        "success": False,
                        "message": "任务未关联节点",
                        "code": 404,
                        "data": None,
                        "timestamp": int(time.time())
                    }
                
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
            
            # 查询数据库中的任务
            db = SessionLocal()
            try:
                # 检查task_id是否为整数
                existing_task = None
                try:
                    # 尝试将ID转换为整数
                    if task_id.isdigit():
                        # 尝试从纯数字task_id中提取主任务ID部分
                        main_task_id = task_id
                        # 如果ID长度大于5，可能是复合ID，尝试提取主任务ID
                        if len(task_id) > 5:
                            # 查找数据库中是否存在这样的任务ID
                            found = False
                            # 从左到右尝试不同的前缀长度
                            for i in range(1, min(5, len(task_id))):
                                potential_id = int(task_id[:i])
                                from models.database import Task
                                task_check = db.query(Task).filter(Task.id == potential_id).first()
                                if task_check:
                                    main_task_id = str(potential_id)
                                    found = True
                                    logger.info(f"从复合ID {task_id} 中提取到主任务ID: {main_task_id}")
                                    break
                            
                            if not found:
                                logger.warning(f"无法从 {task_id} 提取有效的主任务ID，将使用整个ID")
                        
                        # 转换为整数
                        task_id_int = int(main_task_id)
                    else:
                        # 不是纯数字格式
                        task_id_int = int(task_id)
                    
                    from models.database import Task
                    existing_task = db.query(Task).filter(Task.id == task_id_int).first()
                    
                    if not existing_task:
                        logger.error(f"找不到ID为 {task_id_int} 的任务")
                        db.rollback()
                        return {
                            "requestId": task_id,
                            "path": "/api/v1/analyze/task/stop",
                            "success": False,
                            "message": f"找不到ID为 {task_id_int} 的任务",
                            "code": 404,
                            "data": None,
                            "timestamp": int(time.time())
                        }
                    
                    logger.info(f"找到现有任务: ID={task_id_int}")
                    
                except ValueError:
                    # 如果不是整数ID，返回错误
                    error_msg = f"无效的任务ID格式：{task_id}，必须为整数"
                    logger.error(error_msg)
                    db.rollback()
                    return {
                        "requestId": task_id,
                        "path": "/api/v1/analyze/task/stop",
                        "success": False,
                        "message": error_msg,
                        "code": 400,
                        "data": None,
                        "timestamp": int(time.time())
                    }
                
                # 找到关联的子任务
                from crud.task import TaskCRUD
                subtasks = TaskCRUD.get_subtasks_by_task_id(db, task_id_int)
                
                if subtasks:
                    logger.info(f"任务 {task_id} 共有 {len(subtasks)} 个子任务需要停止")
                    
                    stop_success_count = 0
                    stop_failure_count = 0
                    
                    for subtask in subtasks:
                        # 检查子任务是否通过MQTT分配
                        if subtask.mqtt_node_id and subtask.analysis_task_id:
                            logger.info(f"准备通过MQTT停止子任务 {subtask.analysis_task_id} (主任务 {task_id})，目标节点ID: {subtask.mqtt_node_id}")
                            
                            # 获取MQTT节点信息
                            from crud.node import NodeCRUD
                            node = NodeCRUD.get_node_by_id(db, subtask.mqtt_node_id)
                            if node and node.status == 'online':
                                mac_address = node.mac_address
                                
                                # 发送停止命令
                                try:
                                    # 发送停止命令到节点
                                    # 注意: 假设mqtt_client有publish_task_control方法，如果没有请替换为实际方法
                                    success = await self.mqtt_client.publish_task_control(
                                        task_id=subtask.analysis_task_id, 
                                        command="stop", 
                                        payload={}
                                    )
                                    if success:
                                        logger.info(f"成功向MQTT节点 {mac_address} 发送停止子任务 {subtask.analysis_task_id} 的命令")
                                        stop_success_count += 1
                                    else:
                                        logger.error(f"向MQTT节点 {mac_address} 发送停止子任务 {subtask.analysis_task_id} 的命令失败")
                                        stop_failure_count += 1
                                except Exception as e:
                                    logger.error(f"向MQTT节点 {mac_address} 发送停止子任务 {subtask.analysis_task_id} 命令时出错: {e}")
                                    stop_failure_count += 1
                            else:
                                logger.warning(f"子任务 {subtask.analysis_task_id} 的MQTT节点 {subtask.mqtt_node_id} 不存在或已离线，无法发送停止命令")
                                stop_failure_count += 1
                        else:
                            logger.info(f"子任务 {subtask.id} (主任务 {task_id}) 不是通过MQTT分配的，跳过MQTT停止命令")
                    
                    logger.info(f"任务 {task_id} MQTT停止命令发送完成: 成功 {stop_success_count} 个, 失败 {stop_failure_count} 个")
                else:
                    logger.info(f"任务 {task_id} 没有需要通过MQTT停止的子任务")
                
                # 使用现有任务
                task = existing_task
                # 更新任务状态为已停止
                task.status = 2  # 2表示"已停止"
                task.stopped_at = datetime.now()
                
                # 提交事务
                db.commit()
                
                # 返回成功响应
                return {
                    "requestId": task_id,
                    "path": "/api/v1/analyze/task/stop",
                    "success": True,
                    "message": "任务已停止",
                    "code": 200,
                    "data": None,
                    "timestamp": int(time.time())
                }
            except Exception as e:
                logger.error(f"停止任务失败: {e}")
                try:
                    db.rollback()
                except:
                    pass
                return {
                    "requestId": task_id,
                    "path": "/api/v1/analyze/task/stop",
                    "success": False,
                    "message": f"停止任务失败: {str(e)}",
                    "code": 500,
                    "data": None,
                    "timestamp": int(time.time())
                }
            finally:
                db.close()
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
                    "requestId": task_id,
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
                    "requestId": task_id,
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