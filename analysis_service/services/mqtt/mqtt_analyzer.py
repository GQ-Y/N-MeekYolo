"""
MQTT协议的分析服务
处理MQTT协议的图像分析、视频分析和流分析请求
"""
import os
import json
import uuid
import base64
from typing import Dict, Any, List, Optional
import asyncio
from asyncio import Queue
from paho.mqtt import client as mqtt_client

from shared.utils.logger import setup_logger
from core.task_manager import TaskManager
from core.task_processor import TaskProcessor
from core.config import settings
from services.base_analyzer import BaseAnalyzerService

logger = setup_logger(__name__)

class MQTTAnalyzerService(BaseAnalyzerService):
    """基于MQTT协议的分析服务类，处理图像和视频分析请求"""
    
    def __init__(self):
        """初始化MQTT分析服务"""
        super().__init__()
        self.task_manager = TaskManager.get_instance()
        self.task_processor = TaskProcessor()
        
        # MQTT客户端配置
        self.broker = settings.MQTT.broker_host
        self.port = settings.MQTT.broker_port
        self.client_id = f"analysis-service-{uuid.uuid4().hex}"
        self.username = settings.MQTT.username
        self.password = settings.MQTT.password
        
        # 订阅和发布主题
        self.topic_prefix = settings.MQTT.topic_prefix
        self.command_topic = f"{self.topic_prefix}command"
        self.response_topic = f"{self.topic_prefix}response"
        
        # MQTT客户端
        self.client = None
        self.connected = False
        
        # 命令队列
        self.command_queue = Queue()
        
        # 确保输出目录存在
        os.makedirs(settings.OUTPUT.save_dir, exist_ok=True)
        os.makedirs(f"{settings.OUTPUT.save_dir}/images", exist_ok=True)
        os.makedirs(f"{settings.OUTPUT.save_dir}/videos", exist_ok=True)
        os.makedirs(f"{settings.OUTPUT.save_dir}/streams", exist_ok=True)
        
        logger.info("MQTT分析服务已初始化")
        
    async def connect(self):
        """连接到MQTT代理服务器"""
        try:
            # 创建MQTT客户端
            self.client = mqtt_client.Client(self.client_id)
            self.client.username_pw_set(self.username, self.password)
            
            # 设置回调
            self.client.on_connect = self._on_connect
            self.client.on_message = self._on_message
            self.client.on_disconnect = self._on_disconnect
            
            # 连接到代理服务器
            logger.info(f"正在连接到MQTT代理服务器: {self.broker}:{self.port}")
            self.client.connect(self.broker, self.port)
            
            # 启动MQTT客户端循环
            self.client.loop_start()
            
            # 启动命令处理循环
            asyncio.create_task(self._process_commands())
            
            return True
            
        except Exception as e:
            logger.error(f"连接到MQTT代理服务器时出错: {str(e)}", exc_info=True)
            return False
            
    def disconnect(self):
        """断开MQTT连接"""
        if self.client and self.connected:
            try:
                self.client.disconnect()
                self.client.loop_stop()
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
                self.client.reconnect()
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
            self.client.publish(self.response_topic, response_json)
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