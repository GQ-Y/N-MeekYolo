"""
MQTT协议的分析服务
处理MQTT协议的图像分析、视频分析和流分析请求
"""
import os
import json
import uuid
import base64
from typing import Dict, Any, List, Optional, Callable
import asyncio
from asyncio import Queue
from paho.mqtt import client as mqtt_client
import time
import threading
import cv2
import numpy as np
import torch

from shared.utils.logger import setup_logger
from core.task_manager import TaskManager
from core.task_processor import TaskProcessor
from core.config import settings
from core.detection.yolo_detector import YOLODetector
from services.base_analyzer import BaseAnalyzerService
from services.mqtt_client import MQTTClient

logger = setup_logger(__name__)

# 添加StreamDetectionTask类定义
class StreamDetectionTask:
    """流检测任务类，用于处理流视频的实时检测"""
    
    def __init__(self, task_id, subtask_id, stream_url, model_config, result_config, mqtt_client, should_stop):
        """
        初始化流检测任务
        
        Args:
            task_id: 任务ID
            subtask_id: 子任务ID
            stream_url: 流URL
            model_config: 模型配置
            result_config: 结果配置
            mqtt_client: MQTT客户端
            should_stop: 停止检查函数
        """
        self.task_id = task_id
        self.subtask_id = subtask_id
        self.stream_url = stream_url
        self.model_config = model_config
        self.result_config = result_config
        self.mqtt_client = mqtt_client
        self.should_stop = should_stop
        self.running = False
        self.thread = None
        
        # 检测相关参数
        self.model_code = model_config.get("model_code", "yolo11n")
        self.confidence = model_config.get("confidence", 0.5)
        self.iou = model_config.get("iou", 0.5)
        self.classes = model_config.get("classes", None)
        self.imgsz = model_config.get("imgsz", 640)
        
        # 结果相关参数
        self.save_result = result_config.get("save_result", False)
        self.callback_topic = result_config.get("callback_topic", "")
        self.callback_interval = model_config.get("callback", {}).get("interval", 5)
        
        # 创建检测器实例
        self.detector = None
        
    def start(self):
        """启动任务"""
        if self.running:
            logger.warning(f"任务已在运行中: {self.task_id}/{self.subtask_id}")
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._run_task)
        self.thread.daemon = True
        self.thread.start()
        logger.info(f"已启动流检测任务: {self.task_id}/{self.subtask_id}")
        
    def stop(self):
        """停止任务"""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
            logger.info(f"已停止流检测任务: {self.task_id}/{self.subtask_id}")
            
    def _run_task(self):
        """执行任务"""
        try:
            logger.info(f"开始执行流检测任务: {self.task_id}/{self.subtask_id}")
            
            # 更新任务状态为处理中
            self._send_status("processing")
            
            # 初始化检测器
            self._init_detector()
            
            # 打开视频流
            cap = cv2.VideoCapture(self.stream_url)
            if not cap.isOpened():
                raise Exception(f"无法打开流 {self.stream_url}")
                
            # 创建输出目录（如果需要保存结果）
            if self.save_result:
                output_dir = os.path.join(settings.OUTPUT.save_dir, "streams", f"{self.task_id}_{self.subtask_id}")
                os.makedirs(output_dir, exist_ok=True)
                
            # 处理参数
            last_callback_time = 0
            frame_count = 0
            
            # 处理视频流
            while self.running and not self.should_stop():
                # 读取帧
                ret, frame = cap.read()
                if not ret:
                    logger.warning(f"无法从流中读取帧，尝试重新连接: {self.stream_url}")
                    # 尝试重新连接
                    cap.release()
                    time.sleep(1)
                    cap = cv2.VideoCapture(self.stream_url)
                    if not cap.isOpened():
                        logger.error(f"无法重新连接到流: {self.stream_url}")
                        break
                    continue
                    
                # 检测当前帧
                detections = self._detect_frame(frame)
                frame_count += 1
                
                # 保存结果（如果需要）
                if self.save_result and frame_count % 30 == 0:  # 每30帧保存一次
                    timestamp = int(time.time())
                    filename = f"{timestamp}_{frame_count}.jpg"
                    filepath = os.path.join(output_dir, filename)
                    cv2.imwrite(filepath, frame)
                    
                # 发送回调（如果需要）
                current_time = time.time()
                if self.callback_topic and (current_time - last_callback_time) >= self.callback_interval:
                    self._send_result(frame, detections)
                    last_callback_time = current_time
                    
                # 显示进度
                if frame_count % 100 == 0:
                    logger.info(f"任务 {self.task_id}/{self.subtask_id} 已处理 {frame_count} 帧")
                    
            # 关闭视频流
            cap.release()
            
            # 任务结束
            if not self.should_stop():
                self._send_status("completed")
                logger.info(f"流检测任务完成: {self.task_id}/{self.subtask_id}, 共处理 {frame_count} 帧")
            else:
                self._send_status("stopped")
                logger.info(f"流检测任务已停止: {self.task_id}/{self.subtask_id}, 共处理 {frame_count} 帧")
                
        except Exception as e:
            logger.error(f"流检测任务执行出错: {str(e)}")
            logger.exception(e)
            self._send_status("error", error=str(e))
            
    def _init_detector(self):
        """初始化检测器"""
        try:
            # 创建检测器实例
            self.detector = YOLODetector()
            
            # 加载模型 - 由于YOLODetector.load_model是异步的，我们需要使用同步方式调用
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self.detector.load_model(self.model_code))
            loop.close()
            
            logger.info(f"流检测任务 {self.task_id}/{self.subtask_id} 已加载模型: {self.model_code}")
            
        except Exception as e:
            logger.error(f"初始化检测器失败: {str(e)}")
            raise
            
    def _detect_frame(self, frame):
        """检测当前帧"""
        try:
            # 检测参数
            config = {
                "confidence": self.confidence,
                "iou": self.iou,
                "classes": self.classes
            }
            
            # 调用检测器 - 由于detector.detect是异步的，我们需要使用同步方式调用
            loop = asyncio.new_event_loop()
            detections = loop.run_until_complete(self.detector.detect(frame, config))
            loop.close()
            
            # 直接返回检测结果列表，YOLODetector.detect已经返回detections列表
            return detections
            
        except Exception as e:
            logger.error(f"检测帧时出错: {str(e)}")
            return []
            
    def _send_result(self, frame, detections):
        """发送检测结果"""
        if not self.callback_topic:
            return
            
        try:
            # 准备结果数据
            result = {
                "task_id": self.task_id,
                "subtask_id": self.subtask_id,
                "timestamp": int(time.time()),
                "detections": detections,
                "frame_size": {
                    "width": frame.shape[1],
                    "height": frame.shape[0]
                }
            }
            
            # 如果需要，添加帧图像
            if self.save_result:
                # 将图像编码为base64
                _, buffer = cv2.imencode('.jpg', frame)
                image_base64 = base64.b64encode(buffer).decode('utf-8')
                result["image"] = image_base64
                
            # 发送到MQTT主题
            if self.mqtt_client:
                self.mqtt_client._publish_message(self.callback_topic, result, qos=0)
                
        except Exception as e:
            logger.error(f"发送检测结果时出错: {str(e)}")
            
    def _send_status(self, status, error=None):
        """发送任务状态"""
        if self.mqtt_client:
            self.mqtt_client._send_task_status(self.task_id, self.subtask_id, status, error=error)

class MQTTAnalyzerService(BaseAnalyzerService):
    """MQTT分析服务"""

    def __init__(self, device_id, mqtt_config, model_configs=None):
        """
        初始化MQTT分析服务
        
        Args:
            device_id: 设备ID
            mqtt_config: MQTT配置
            model_configs: 模型配置
        """
        # 调用父类的__init__方法，不传递额外参数
        super().__init__()
        self.device_id = device_id
        self.mqtt_config = mqtt_config
        self.model_configs = model_configs or {}
        
        # 初始化任务管理器
        self.task_manager = TaskManager()
        
        # 初始化MQTT客户端
        self.mqtt_client = MQTTClient(
            device_id=device_id,
            broker_host=mqtt_config.get("host", "localhost"),
            broker_port=mqtt_config.get("port", 1883),
            username=mqtt_config.get("username"),
            password=mqtt_config.get("password"),
            command_topic=mqtt_config.get("command_topic"),
            response_topic=mqtt_config.get("response_topic"),
            status_topic=mqtt_config.get("status_topic")
        )
        
        logger.info(f"MQTT分析服务已初始化: 设备ID={device_id}")

    async def connect(self):
        """连接到MQTT服务器并注册任务处理器"""
        # 连接前确保注册所有任务处理器
        self._register_task_handlers()
        
        # 启动MQTT客户端
        if not self.mqtt_client.start():
            logger.error("MQTT客户端启动失败")
            return False
            
        logger.info("MQTT客户端启动成功")
        
        # 记录状态信息
        logger.info(f"MQTT客户端节点ID: {self.mqtt_client.node_id}")
        logger.info(f"MQTT客户端MAC地址: {self.mqtt_client.mac_address}")
        request_setting_topic = f"{self.mqtt_client.topic_prefix}{self.mqtt_client.node_id}/request_setting"
        logger.info(f"订阅的请求主题: {request_setting_topic}")
        
        # 所有处理器已注册，连接成功
        logger.info("成功连接到MQTT服务器")
        return True
            
    def _register_task_handlers(self):
        """注册任务处理器"""
        # 注册图像分析任务处理器
        self.mqtt_client.register_task_handler("image", self._handle_image_task)
        logger.info("已注册图像分析任务处理器")
        
        # 注册视频分析任务处理器
        self.mqtt_client.register_task_handler("video", self._handle_video_task)
        logger.info("已注册视频分析任务处理器")
        
        # 注册流分析任务处理器
        self.mqtt_client.register_task_handler("stream", self._handle_stream_task)
        logger.info("已注册流分析任务处理器")
        
        # 根据模型配置注册特定类型的处理器
        if self.model_configs:
            for model_code, config in self.model_configs.items():
                analysis_type = config.get("analysis_type")
                if analysis_type and analysis_type not in ["image", "video", "stream"]:
                    # 只为不同于基本类型的分析类型注册处理器
                    self.mqtt_client.register_task_handler(analysis_type, self._handle_detection_task)
                    logger.info(f"已注册{analysis_type}分析任务处理器")
                    
        # 注册通用检测任务处理器作为默认处理器
        self.mqtt_client.register_task_handler("detection", self._handle_detection_task)
        logger.info("已注册通用检测任务处理器")
        
        # 记录所有已注册的处理器
        available_handlers = list(self.mqtt_client.task_handlers.keys())
        logger.info(f"所有已注册的任务处理器: {available_handlers}")
            
    def _handle_stream_task(self, task_id, subtask_id, source, config, result_config, message_id=None, message_uuid=None, confirmation_topic=None):
        """
        处理流分析任务
        
        Args:
            task_id: 任务ID
            subtask_id: 子任务ID
            source: 源配置
            config: 任务配置
            result_config: 结果配置
            message_id: 消息ID
            message_uuid: 消息UUID
            confirmation_topic: 确认主题
        
        Returns:
            bool: 处理结果
        """
        logger.info(f"处理流分析任务: {task_id}/{subtask_id}")
        
        # 获取流URL
        url = source.get("url", "")
        if not url and "urls" in source and source["urls"]:
            url = source["urls"][0]
            
        if not url:
            error_msg = "未指定流URL"
            logger.error(error_msg)
            if confirmation_topic:
                self.mqtt_client._send_cmd_reply(message_id, message_uuid, confirmation_topic, "error", 
                                                data={"error_message": error_msg, "task_id": task_id, "subtask_id": subtask_id})
            return False
            
        logger.info(f"流URL: {url}")
        
        # 获取模型配置
        model_code = config.get("model_code", "default")
        model_config = self.model_configs.get(model_code, {})
        
        # 创建分析任务
        try:
            # 创建停止检查函数
            task_key = f"{task_id}_{subtask_id}"
            
            def should_stop():
                return task_key not in self.mqtt_client.active_tasks or self.mqtt_client.stop_event.is_set()
                
            # 记录任务
            with self.mqtt_client.active_tasks_lock:
                self.mqtt_client.active_tasks[task_key] = {
                    "start_time": time.time(),
                    "source": source,
                    "config": config,
                    "result_config": result_config
                }
                
            # 通知MQTT客户端已接受任务
            if confirmation_topic:
                self.mqtt_client._send_cmd_reply(message_id, message_uuid, confirmation_topic, "success", 
                                               data={"message": "任务已接受", "task_id": task_id, "subtask_id": subtask_id})
                
            # 创建任务
            detection_task = StreamDetectionTask(
                task_id=task_id,
                subtask_id=subtask_id,
                stream_url=url,
                model_config=config,  # 使用完整配置
                result_config=result_config,
                mqtt_client=self.mqtt_client,
                should_stop=should_stop
            )
            
            # 在TaskManager中创建任务记录
            combined_id = f"{task_id}_{subtask_id}"
            params = {
                "task_id": task_id,
                "subtask_id": subtask_id,
                "stream_url": url,
                "model_code": model_code,
                "config": config,
                "result_config": result_config
            }
            self.task_manager.update_task(combined_id, {
                "id": combined_id,
                "type": "stream",
                "params": params,
                "status": "pending",
                "protocol": "mqtt",
                "create_time": int(time.time()),
                "progress": 0,
                "detection_task": detection_task  # 保存任务对象
            })
            
            # 启动任务
            detection_task.start()
            
            # 更新任务状态为运行中
            self.task_manager.update_task(combined_id, {"status": "running"})
            
            logger.info(f"流分析任务已启动: {task_id}/{subtask_id}")
            return True
            
        except Exception as e:
            error_msg = f"启动流分析任务时出错: {str(e)}"
            logger.error(error_msg)
            logger.exception(e)
            
            # 移除任务
            with self.mqtt_client.active_tasks_lock:
                if task_key in self.mqtt_client.active_tasks:
                    del self.mqtt_client.active_tasks[task_key]
                    
            if confirmation_topic:
                self.mqtt_client._send_cmd_reply(message_id, message_uuid, confirmation_topic, "error", 
                                               data={"error_message": error_msg, "task_id": task_id, "subtask_id": subtask_id})
            return False
            
    def _handle_image_task(self, task_id, subtask_id, source, config, result_config, message_id=None, message_uuid=None, confirmation_topic=None):
        """处理图像分析任务"""
        logger.info(f"处理图像分析任务: {task_id}/{subtask_id}")
        # TODO: 实现图像分析逻辑
        return self._handle_detection_task(task_id, subtask_id, source, config, result_config, message_id, message_uuid, confirmation_topic)
        
    def _handle_video_task(self, task_id, subtask_id, source, config, result_config, message_id=None, message_uuid=None, confirmation_topic=None):
        """处理视频分析任务"""
        logger.info(f"处理视频分析任务: {task_id}/{subtask_id}")
        # TODO: 实现视频分析逻辑
        return self._handle_detection_task(task_id, subtask_id, source, config, result_config, message_id, message_uuid, confirmation_topic)
        
    def _handle_detection_task(self, task_id, subtask_id, source, config, result_config, message_id=None, message_uuid=None, confirmation_topic=None):
        """处理通用检测任务"""
        logger.info(f"处理通用检测任务: {task_id}/{subtask_id}")
        # 根据source类型选择合适的处理方法
        source_type = source.get("type", "")
        
        if source_type == "image":
            return self._handle_image_task(task_id, subtask_id, source, config, result_config, message_id, message_uuid, confirmation_topic)
        elif source_type == "video":
            return self._handle_video_task(task_id, subtask_id, source, config, result_config, message_id, message_uuid, confirmation_topic)
        elif source_type == "stream":
            return self._handle_stream_task(task_id, subtask_id, source, config, result_config, message_id, message_uuid, confirmation_topic)
        else:
            error_msg = f"不支持的数据源类型: {source_type}"
            logger.error(error_msg)
            if confirmation_topic:
                self.mqtt_client._send_cmd_reply(message_id, message_uuid, confirmation_topic, "error", 
                                               data={"error_message": error_msg, "task_id": task_id, "subtask_id": subtask_id})
            return False

    def disconnect(self):
        """断开MQTT连接"""
        if self.mqtt_client and self.connected:
            try:
                self.mqtt_client.disconnect()
                self.mqtt_client.loop_stop()
                self.connected = False
                logger.info("已断开与MQTT代理服务器的连接")
                return True
            except Exception as e:
                logger.error(f"断开MQTT连接时出错: {str(e)}", exc_info=True)
                return False
        return True
        
    def _on_connect(self, client, userdata, flags, rc):
        """MQTT连接回调"""
        if rc == 0:
            self.connected = True
            logger.info(f"已连接到MQTT代理服务器: {self.broker}:{self.port}")
            
            # 订阅命令主题
            client.subscribe(self.command_topic)
            logger.info(f"已订阅命令主题: {self.command_topic}")
        else:
            logger.error(f"连接MQTT代理服务器失败，返回码: {rc}")
            
    def _on_message(self, client, userdata, msg):
        """MQTT消息回调"""
        try:
            # 解析消息
            payload = msg.payload.decode("utf-8")
            logger.debug(f"收到MQTT消息: {payload}")
            
            # 解析JSON命令
            command = json.loads(payload)
            
            # 将命令添加到队列
            asyncio.run_coroutine_threadsafe(
                self.command_queue.put(command),
                asyncio.get_event_loop()
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误: {str(e)}", exc_info=True)
            self._publish_response({
                "success": False,
                "error": f"无效的JSON格式: {str(e)}"
            })
        except Exception as e:
            logger.error(f"处理MQTT消息时出错: {str(e)}", exc_info=True)
            self._publish_response({
                "success": False,
                "error": f"处理消息时出错: {str(e)}"
            })
            
    def _on_disconnect(self, client, userdata, rc):
        """MQTT断开连接回调"""
        self.connected = False
        if rc != 0:
            logger.warning(f"与MQTT代理服务器的连接意外断开，返回码: {rc}")
            # 尝试重新连接
            asyncio.create_task(self._reconnect())
        else:
            logger.info("已主动断开与MQTT代理服务器的连接")
            
    async def _reconnect(self, max_retries=5, retry_interval=5):
        """重新连接到MQTT代理服务器"""
        retries = 0
        while not self.connected and retries < max_retries:
            logger.info(f"尝试重新连接MQTT代理服务器，第 {retries+1} 次...")
            try:
                self.mqtt_client.reconnect()
                return
            except Exception as e:
                logger.error(f"重新连接失败: {str(e)}", exc_info=True)
                retries += 1
                await asyncio.sleep(retry_interval)
                
        if not self.connected:
            logger.error(f"重新连接MQTT代理服务器失败，已达到最大重试次数: {max_retries}")
            
    def _publish_response(self, response):
        """发布响应到MQTT主题"""
        if not self.connected:
            logger.error("未连接到MQTT代理服务器，无法发布响应")
            return False
            
        try:
            # 将响应对象转换为JSON字符串
            response_json = json.dumps(response)
            
            # 发布响应
            self.mqtt_client.publish(self.response_topic, response_json)
            logger.debug(f"已发布响应到主题 {self.response_topic}")
            return True
            
        except Exception as e:
            logger.error(f"发布MQTT响应时出错: {str(e)}", exc_info=True)
            return False
            
    async def _process_commands(self):
        """处理命令队列中的命令"""
        logger.info("开始处理MQTT命令队列")
        while True:
            try:
                # 从队列获取命令
                command = await self.command_queue.get()
                logger.info(f"正在处理命令: {command.get('action', 'unknown')}")
                
                # 解析命令类型
                action = command.get("action")
                if not action:
                    self._publish_response({
                        "success": False,
                        "command_id": command.get("command_id"),
                        "error": "无效的命令，缺少 'action' 字段"
                    })
                    continue
                    
                # 处理不同类型的命令
                if action == "analyze_image":
                    await self._handle_analyze_image(command)
                elif action == "start_video_analysis":
                    await self._handle_start_video_analysis(command)
                elif action == "start_stream_analysis":
                    await self._handle_start_stream_analysis(command)
                elif action == "stop_task":
                    await self._handle_stop_task(command)
                elif action == "get_task_status":
                    await self._handle_get_task_status(command)
                elif action == "get_tasks":
                    await self._handle_get_tasks(command)
                else:
                    self._publish_response({
                        "success": False,
                        "command_id": command.get("command_id"),
                        "error": f"未知的命令类型: {action}"
                    })
                    
            except Exception as e:
                logger.error(f"处理MQTT命令时出错: {str(e)}", exc_info=True)
                try:
                    self._publish_response({
                        "success": False,
                        "command_id": command.get("command_id") if "command" in locals() else None,
                        "error": f"处理命令时出错: {str(e)}"
                    })
                except Exception as e2:
                    logger.error(f"发送错误响应时出错: {str(e2)}", exc_info=True)
                    
    async def _handle_analyze_image(self, command):
        """处理图像分析命令"""
        try:
            # 获取命令参数
            command_id = command.get("command_id")
            model_code = command.get("model_code")
            image_data = command.get("image_data")  # Base64编码的图像数据
            image_path = command.get("image_path")  # 或者图像路径
            conf_threshold = command.get("conf_threshold", 0.25)
            save_result = command.get("save_result", True)
            include_image = command.get("include_image", False)
            
            # 验证参数
            if not model_code:
                self._publish_response({
                    "success": False,
                    "command_id": command_id,
                    "error": "缺少必需的参数: model_code"
                })
                return
                
            if not image_data and not image_path:
                self._publish_response({
                    "success": False,
                    "command_id": command_id,
                    "error": "缺少必需的参数: image_data 或 image_path"
                })
                return
                
            # 如果提供了图像数据，保存为文件
            if image_data:
                try:
                    # 解码Base64图像数据
                    image_bytes = base64.b64decode(image_data)
                    
                    # 保存为文件
                    filename = f"{uuid.uuid4().hex}.jpg"
                    file_path = f"{settings.OUTPUT.save_dir}/images/{filename}"
                    
                    with open(file_path, "wb") as f:
                        f.write(image_bytes)
                        
                    image_path = file_path
                except Exception as e:
                    self._publish_response({
                        "success": False,
                        "command_id": command_id,
                        "error": f"图像数据解码失败: {str(e)}"
                    })
                    return
                    
            # 创建任务
            task_id = self.task_manager.create_task(
                task_type="image",
                protocol="mqtt",
                params={
                    "image_path": image_path,
                    "model_code": model_code,
                    "conf_threshold": conf_threshold,
                    "save_result": save_result,
                    "include_image": include_image,
                    "command_id": command_id
                }
            )
            
            # 处理图像分析任务
            result = self.task_processor.process_image(task_id)
            
            # 添加命令ID到响应中
            result["command_id"] = command_id
            
            # 发布响应
            self._publish_response(result)
            
        except Exception as e:
            logger.error(f"处理图像分析命令时出错: {str(e)}", exc_info=True)
            self._publish_response({
                "success": False,
                "command_id": command.get("command_id"),
                "error": f"处理图像分析命令时出错: {str(e)}"
            })
            
    async def _handle_start_video_analysis(self, command):
        """处理视频分析命令"""
        try:
            # 获取命令参数
            command_id = command.get("command_id")
            model_code = command.get("model_code")
            video_path = command.get("video_path")
            conf_threshold = command.get("conf_threshold", 0.25)
            save_result = command.get("save_result", True)
            
            # 验证参数
            if not model_code:
                self._publish_response({
                    "success": False,
                    "command_id": command_id,
                    "error": "缺少必需的参数: model_code"
                })
                return
                
            if not video_path:
                self._publish_response({
                    "success": False,
                    "command_id": command_id,
                    "error": "缺少必需的参数: video_path"
                })
                return
                
            # 验证视频文件是否存在
            if not os.path.exists(video_path):
                self._publish_response({
                    "success": False,
                    "command_id": command_id,
                    "error": f"视频文件不存在: {video_path}"
                })
                return
                
            # 创建任务
            task_id = self.task_manager.create_task(
                task_type="video",
                protocol="mqtt",
                params={
                    "video_path": video_path,
                    "model_code": model_code,
                    "conf_threshold": conf_threshold,
                    "save_result": save_result,
                    "command_id": command_id
                }
            )
            
            # 启动视频分析任务
            result = self.task_processor.start_video_analysis(task_id)
            
            # 添加命令ID到响应中
            result["command_id"] = command_id
            
            # 发布响应
            self._publish_response(result)
            
        except Exception as e:
            logger.error(f"处理视频分析命令时出错: {str(e)}", exc_info=True)
            self._publish_response({
                "success": False,
                "command_id": command.get("command_id"),
                "error": f"处理视频分析命令时出错: {str(e)}"
            })
            
    async def _handle_start_stream_analysis(self, command):
        logger.info(f"打印全部命令数据: {command}")
        """处理流分析命令"""
        try:
            # 获取命令参数
            command_id = command.get("command_id")
            model_code = command.get("model_code")
            stream_url = command.get("stream_url")
            conf_threshold = command.get("conf_threshold", 0.25)
            save_interval = command.get("save_interval", 10)
            max_duration = command.get("max_duration", 3600)
            
            # 验证参数
            if not model_code:
                self._publish_response({
                    "success": False,
                    "command_id": command_id,
                    "error": "缺少必需的参数: model_code"
                })
                return
                
            if not stream_url:
                self._publish_response({
                    "success": False,
                    "command_id": command_id,
                    "error": "缺少必需的参数: stream_url"
                })
                return
                
            # 创建任务
            task_id = self.task_manager.create_task(
                task_type="stream",
                protocol="mqtt",
                params={
                    "stream_url": stream_url,
                    "model_code": model_code,
                    "conf_threshold": conf_threshold,
                    "save_interval": save_interval,
                    "max_duration": max_duration,
                    "command_id": command_id
                }
            )
            
            # 启动流分析任务
            result = self.task_processor.start_stream_analysis(task_id)
            
            # 添加命令ID到响应中
            result["command_id"] = command_id
            
            # 发布响应
            self._publish_response(result)
            
        except Exception as e:
            logger.error(f"处理流分析命令时出错: {str(e)}", exc_info=True)
            self._publish_response({
                "success": False,
                "command_id": command.get("command_id"),
                "error": f"处理流分析命令时出错: {str(e)}"
            })
            
    async def _handle_stop_task(self, command):
        """处理停止任务命令"""
        try:
            # 获取命令参数
            command_id = command.get("command_id")
            task_id = command.get("task_id")
            
            # 验证参数
            if not task_id:
                self._publish_response({
                    "success": False,
                    "command_id": command_id,
                    "error": "缺少必需的参数: task_id"
                })
                return
                
            # 停止任务
            result = self.task_processor.stop_task(task_id)
            
            # 添加命令ID到响应中
            result["command_id"] = command_id
            
            # 发布响应
            self._publish_response(result)
            
        except Exception as e:
            logger.error(f"处理停止任务命令时出错: {str(e)}", exc_info=True)
            self._publish_response({
                "success": False,
                "command_id": command.get("command_id"),
                "error": f"处理停止任务命令时出错: {str(e)}"
            })
            
    async def _handle_get_task_status(self, command):
        """处理获取任务状态命令"""
        try:
            # 获取命令参数
            command_id = command.get("command_id")
            task_id = command.get("task_id")
            
            # 验证参数
            if not task_id:
                self._publish_response({
                    "success": False,
                    "command_id": command_id,
                    "error": "缺少必需的参数: task_id"
                })
                return
                
            # 获取任务状态
            result = self.task_processor.get_task_status(task_id)
            
            # 添加命令ID到响应中
            result["command_id"] = command_id
            
            # 发布响应
            self._publish_response(result)
            
        except Exception as e:
            logger.error(f"处理获取任务状态命令时出错: {str(e)}", exc_info=True)
            self._publish_response({
                "success": False,
                "command_id": command.get("command_id"),
                "error": f"处理获取任务状态命令时出错: {str(e)}"
            })
            
    async def _handle_get_tasks(self, command):
        """处理获取任务列表命令"""
        try:
            # 获取命令参数
            command_id = command.get("command_id")
            
            # 获取所有任务
            tasks = self.task_manager.get_all_tasks()
            
            # 过滤出MQTT协议的任务
            mqtt_tasks = {
                task_id: task for task_id, task in tasks.items()
                if task.get("protocol") == "mqtt"
            }
            
            # 构建响应
            result = {
                "success": True,
                "command_id": command_id,
                "tasks": mqtt_tasks
            }
            
            # 发布响应
            self._publish_response(result)
            
        except Exception as e:
            logger.error(f"处理获取任务列表命令时出错: {str(e)}", exc_info=True)
            self._publish_response({
                "success": False,
                "command_id": command.get("command_id"),
                "error": f"处理获取任务列表命令时出错: {str(e)}"
            }) 