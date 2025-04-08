"""
分析服务
处理图片、视频、流的分析逻辑
"""
import cv2
import numpy as np
import uuid
import os
import sys
import asyncio
import base64
import json
import time
from datetime import datetime
from fastapi import UploadFile
from typing import Dict, Any, List, Tuple, Optional, Callable
from shared.utils.logger import setup_logger

# 添加父级目录到sys.path以允许导入core模块
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from core.config import settings
from core.detector import YOLODetector
from services.detection import DetectionService
from services.mqtt_client import get_mqtt_client, MQTTClient
from services.model_service import ModelService

logger = setup_logger(__name__)

class AnalyzerService:
    """分析服务"""
    
    def __init__(self, service_mode: str = "http"):
        """
        初始化分析服务
        
        Args:
            service_mode: 服务模式，'http'或'mqtt'
        """
        logger.info(f"初始化分析服务，模式: {service_mode}")
        
        # 服务模式
        self.service_mode = service_mode
        self.mqtt_mode = service_mode.lower() == "mqtt"
        
        # 初始化检测服务
        self.detection_service = DetectionService()
        
        # 如果是MQTT模式，初始化MQTT客户端
        if self.mqtt_mode:
            self._init_mqtt_client()
            
        logger.info("分析服务初始化完成")
        
        self.detector = YOLODetector()
        self.tasks = {}
        
        # 确保输出目录存在
        os.makedirs(settings.OUTPUT["save_dir"], exist_ok=True)
        os.makedirs(f"{settings.OUTPUT['save_dir']}/images", exist_ok=True)
        os.makedirs(f"{settings.OUTPUT['save_dir']}/videos", exist_ok=True)
        
        # MQTT客户端
        self.mqtt_client = None
        
        # 初始化模型服务
        self.model_service = ModelService()
        
    def _init_mqtt_client(self):
        """初始化MQTT客户端并注册任务处理器"""
        try:
            logger.info("初始化MQTT客户端")
            
            # 获取MQTT客户端实例
            self.mqtt_client = get_mqtt_client()
            
            # 注册任务处理器
            self.mqtt_client.register_task_handler("image", self._handle_image_task)
            self.mqtt_client.register_task_handler("video", self._handle_video_task)
            self.mqtt_client.register_task_handler("stream", self._handle_stream_task)
            
            # 添加其他可能的任务类型
            self.mqtt_client.register_task_handler("detection", self._handle_image_task)  # 兼容detection类型任务
            self.mqtt_client.register_task_handler("segmentation", self._handle_image_task)  # 兼容segmentation类型任务
            self.mqtt_client.register_task_handler("tracking", self._handle_video_task)  # 兼容tracking类型任务
            
            # 设置节点ID和MAC地址
            import socket
            import uuid
            hostname = socket.gethostname()
            mac = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff) 
                          for elements in range(0, 8*6, 8)][::-1])
            
            logger.info(f"MQTT客户端节点信息: hostname={hostname}, mac={mac}")
            
            # 启动MQTT客户端
            if not self.mqtt_client.start():
                logger.error("MQTT客户端启动失败")
                raise Exception("MQTT客户端启动失败")
                
            logger.info("MQTT客户端初始化并启动成功")
            
            # 发送一次连接状态，确保API服务知道我们在线
            self._publish_connection_status()
            
        except Exception as e:
            logger.error(f"初始化MQTT客户端失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise
            
    def _publish_connection_status(self):
        """发布连接状态"""
        if not self.mqtt_client or not self.mqtt_client.is_connected:
            logger.warning("MQTT客户端未连接，无法发布连接状态")
            return False
            
        try:
            # 获取系统信息
            import platform
            import psutil
            import GPUtil
            
            # 获取CPU使用率
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # 获取内存使用情况
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # 获取GPU使用情况
            try:
                gpus = GPUtil.getGPUs()
                gpu_usage = f"{gpus[0].load * 100:.1f}%" if gpus else "N/A"
                gpu_memory = f"{gpus[0].memoryUsed}/{gpus[0].memoryTotal} MB" if gpus else "N/A"
                gpu_available = True
            except:
                gpu_usage = "N/A"
                gpu_memory = "N/A"
                gpu_available = False
            
            # 构建连接状态消息
            status_info = {
                "message_type": "connection",
                "status": "online",
                "mac_address": self.mqtt_client.mac_address,
                "node_id": self.mqtt_client.node_id,  # 使用MAC地址作为node_id
                "mqtt_node_id": self.mqtt_client.node_id,  # 确保mqtt_node_id与node_id一致
                "node_type": "analysis",
                "timestamp": int(time.time()),
                "metadata": {
                    "version": settings.VERSION,
                    "ip": self._get_local_ip(),
                    "port": settings.SERVICES.port,
                    "hostname": platform.node(),
                    "is_active": True,
                    "capabilities": {
                        "models": ["yolov8n"],  # 简化为默认模型
                        "gpu_available": gpu_available,
                        "max_tasks": 4,
                        "cpu_cores": psutil.cpu_count(),
                        "memory": round(psutil.virtual_memory().total / (1024**3))
                    },
                    "resources": {
                        "cpu": cpu_percent,
                        "memory": memory_percent,
                        "gpu": gpu_usage,
                        "gpu_memory": gpu_memory
                    },
                    "active_tasks": 0
                }
            }
            
            # 发布连接状态消息到正确的主题
            topic = f"{self.mqtt_client.topic_prefix}connection"
            self.mqtt_client._publish_message(topic, status_info, qos=1, retain=True)
            logger.info(f"已发布连接状态到主题: {topic}")
            return True
        
        except Exception as e:
            logger.error(f"发布连接状态失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False
            
    def _get_local_ip(self):
        """获取本地IP地址"""
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception as e:
            logger.warning(f"获取本地IP失败: {str(e)}")
            return "127.0.0.1"
            
    def _handle_image_task(self, task_id: str, subtask_id: str, source: Dict, config: Dict, should_stop: Callable) -> Dict:
        """处理MQTT图片任务"""
        try:
            logger.info(f"处理图片任务: {task_id}/{subtask_id}")
            
            # 提取图片路径或URL
            image_path = source.get("path")
            image_url = source.get("url")
            image_data = source.get("data")  # base64编码的图片数据
            
            if image_path:
                # 从本地路径读取图片
                if not os.path.exists(image_path):
                    raise ValueError(f"图片路径不存在: {image_path}")
                    
                image = cv2.imread(image_path)
                if image is None:
                    raise ValueError(f"无法读取图片: {image_path}")
                    
                filename = os.path.basename(image_path)
                
            elif image_url:
                # 从URL下载图片
                import requests
                resp = requests.get(image_url, timeout=10)
                if resp.status_code != 200:
                    raise ValueError(f"无法从URL下载图片: {image_url}, 状态码: {resp.status_code}")
                    
                nparr = np.frombuffer(resp.content, np.uint8)
                image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if image is None:
                    raise ValueError(f"无法解码从URL下载的图片: {image_url}")
                    
                filename = os.path.basename(image_url)
                
            elif image_data:
                # 从base64数据解码图片
                try:
                    image_bytes = base64.b64decode(image_data)
                    nparr = np.frombuffer(image_bytes, np.uint8)
                    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if image is None:
                        raise ValueError("无法解码base64图片数据")
                except Exception as e:
                    raise ValueError(f"base64图片数据解码失败: {str(e)}")
                    
                filename = f"{subtask_id}.jpg"
                
            else:
                raise ValueError("未提供有效的图片数据源")
                
            # 执行检测（同步版本）
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            detections = loop.run_until_complete(self.detector.detect(image))
            loop.close()
            
            # 处理结果图片
            if settings.OUTPUT["save_img"]:
                result_image = self.draw_detections(image, detections)
                
                # 保存结果图片
                save_dir = f"{settings.OUTPUT['save_dir']}/images/{task_id}"
                os.makedirs(save_dir, exist_ok=True)
                save_path = f"{save_dir}/{subtask_id}.jpg"
                cv2.imwrite(save_path, result_image)
                
                logger.info(f"结果图片已保存到: {save_path}")
                
                # 如果需要返回base64图片数据
                if config.get("return_image", False):
                    _, buffer = cv2.imencode('.jpg', result_image)
                    image_base64 = base64.b64encode(buffer).decode('utf-8')
                else:
                    image_base64 = None
            else:
                save_path = None
                image_base64 = None
            
            # 构建结果
            result = {
                "filename": filename,
                "detections": detections,
                "timestamp": int(time.time()),
                "task_id": task_id,
                "subtask_id": subtask_id
            }
            
            # 如果需要，添加图片数据
            if image_base64:
                result["image_base64"] = image_base64
                
            if save_path:
                result["save_path"] = save_path
                
            return result
            
        except Exception as e:
            logger.error(f"处理图片任务失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "error": str(e),
                "timestamp": int(time.time()),
                "task_id": task_id,
                "subtask_id": subtask_id
            }
            
    def _handle_video_task(self, task_id: str, subtask_id: str, source: Dict, config: Dict, should_stop: Callable) -> Dict:
        """处理MQTT视频任务"""
        try:
            logger.info(f"处理视频任务: {task_id}/{subtask_id}")
            
            # 提取视频路径或URL
            video_path = source.get("path")
            video_url = source.get("url")
            
            if video_path:
                # 检查本地视频路径
                if not os.path.exists(video_path):
                    raise ValueError(f"视频路径不存在: {video_path}")
                    
                video_source = video_path
                filename = os.path.basename(video_path)
                
            elif video_url:
                # 使用视频URL
                video_source = video_url
                filename = os.path.basename(video_url)
                
            else:
                raise ValueError("未提供有效的视频数据源")
                
            # 打开视频
            cap = cv2.VideoCapture(video_source)
            if not cap.isOpened():
                raise ValueError(f"无法打开视频: {video_source}")
                
            # 获取视频信息
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            # 处理结果视频
            save_path = None
            if settings.OUTPUT["save_vid"]:
                save_dir = f"{settings.OUTPUT['save_dir']}/videos/{task_id}"
                os.makedirs(save_dir, exist_ok=True)
                save_path = f"{save_dir}/{subtask_id}.mp4"
                
                # 创建视频写入器
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # 或者使用 'XVID'
                out = cv2.VideoWriter(save_path, fourcc, fps, (width, height))
            
            # 处理帧
            all_detections = []
            processed_frames = 0
            
            # 每N帧处理一次
            process_interval = config.get("process_interval", 1)
            
            # 处理帧限制，0表示处理所有帧
            max_frames = config.get("max_frames", 0)
            if max_frames <= 0:
                max_frames = frame_count
                
            while processed_frames < max_frames:
                # 检查是否应该停止
                if should_stop():
                    logger.info(f"任务 {task_id}/{subtask_id} 被请求停止")
                    break
                    
                # 读取一帧
                ret, frame = cap.read()
                if not ret:
                    break
                    
                # 只处理特定间隔的帧
                current_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
                if (current_frame - 1) % process_interval != 0:
                    continue
                    
                try:
                    # 执行检测
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    detections = loop.run_until_complete(self.detector.detect(frame))
                    loop.close()
                    
                    # 添加帧信息
                    frame_result = {
                        "frame": current_frame,
                        "timestamp": int(time.time()),
                        "detections": detections
                    }
                    all_detections.append(frame_result)
                    
                    # 处理输出视频
                    if settings.OUTPUT["save_vid"]:
                        result_frame = self.draw_detections(frame, detections)
                        out.write(result_frame)
                    
                    processed_frames += 1
                    
                    # 打印进度
                    if processed_frames % 10 == 0:
                        logger.info(f"已处理 {processed_frames}/{max_frames} 帧, 当前帧: {current_frame}/{frame_count}")
                    
                except Exception as e:
                    logger.error(f"处理视频帧 {current_frame} 失败: {str(e)}")
                    continue
            
            # 释放资源
            cap.release()
            if settings.OUTPUT["save_vid"]:
                out.release()
                
            logger.info(f"视频处理完成: {task_id}/{subtask_id}, 已处理 {processed_frames} 帧")
            
            # 构建结果
            result = {
                "filename": filename,
                "video_info": {
                    "fps": fps,
                    "frame_count": frame_count,
                    "width": width,
                    "height": height,
                    "processed_frames": processed_frames
                },
                "frame_results": all_detections,
                "timestamp": int(time.time()),
                "task_id": task_id,
                "subtask_id": subtask_id
            }
            
            if save_path:
                result["save_path"] = save_path
                
            return result
            
        except Exception as e:
            logger.error(f"处理视频任务失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "error": str(e),
                "timestamp": int(time.time()),
                "task_id": task_id,
                "subtask_id": subtask_id
            }
    
    def _handle_stream_task(self, task_id: str, subtask_id: str, source: Dict, config: Dict, should_stop: Callable) -> Dict:
        """处理MQTT流任务"""
        try:
            logger.info(f"处理流任务: {task_id}/{subtask_id}")
            
            # 提取RTSP URL
            rtsp_url = source.get("url")
            if not rtsp_url:
                raise ValueError("未提供有效的流URL")
                
            # 打开流
            cap = cv2.VideoCapture(rtsp_url)
            if not cap.isOpened():
                raise ValueError(f"无法打开流: {rtsp_url}")
                
            # 获取流信息
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            # 处理输出目录
            save_dir = f"{settings.OUTPUT['save_dir']}/streams/{task_id}"
            os.makedirs(save_dir, exist_ok=True)
            
            # 处理参数
            process_time = config.get("process_time", 60)  # 默认处理60秒
            frame_interval = config.get("frame_interval", 30)  # 默认每隔30帧处理一次
            save_interval = config.get("save_interval", 300)  # 默认每5分钟保存一次关键帧
            
            # 初始化变量
            start_time = time.time()
            frame_count = 0
            processed_frames = 0
            last_save_time = start_time
            all_detections = []
            latest_detections = None
            
            # 处理流
            while time.time() - start_time < process_time:
                # 检查是否应该停止
                if should_stop():
                    logger.info(f"任务 {task_id}/{subtask_id} 被请求停止")
                    break
                    
                # 读取一帧
                ret, frame = cap.read()
                if not ret:
                    logger.warning(f"读取流帧失败: {rtsp_url}")
                    time.sleep(1)  # 等待1秒后重试
                    continue
                    
                frame_count += 1
                
                # 只处理特定间隔的帧
                if frame_count % frame_interval != 0:
                    continue
                    
                try:
                    # 执行检测
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    detections = loop.run_until_complete(self.detector.detect(frame))
                    loop.close()
                    
                    # 更新最新检测结果
                    latest_detections = detections
                    
                    # 添加帧结果
                    frame_result = {
                        "frame": frame_count,
                        "timestamp": int(time.time()),
                        "detections": detections
                    }
                    all_detections.append(frame_result)
                    
                    # 保存关键帧
                    current_time = time.time()
                    if settings.OUTPUT["save_img"] and (current_time - last_save_time >= save_interval):
                        last_save_time = current_time
                        
                        # 绘制检测结果
                        result_frame = self.draw_detections(frame, detections)
                        
                        # 生成时间戳文件名
                        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                        save_path = f"{save_dir}/{timestamp}.jpg"
                        
                        # 保存图像
                        cv2.imwrite(save_path, result_frame)
                        logger.info(f"已保存流关键帧: {save_path}")
                    
                    processed_frames += 1
                    
                    # 打印进度
                    if processed_frames % 10 == 0:
                        elapsed = time.time() - start_time
                        logger.info(f"已处理 {processed_frames} 帧, 已用时间: {elapsed:.2f}秒")
                    
                except Exception as e:
                    logger.error(f"处理流帧 {frame_count} 失败: {str(e)}")
                    continue
                    
                # 简单流控，避免CPU占用过高
                time.sleep(0.01)
            
            # 释放资源
            cap.release()
            
            # 构建结果
            result = {
                "stream_url": rtsp_url,
                "stream_info": {
                    "width": width,
                    "height": height,
                    "processed_frames": processed_frames,
                    "total_frames": frame_count,
                    "process_time": time.time() - start_time
                },
                "latest_detections": latest_detections,
                "timestamp": int(time.time()),
                "task_id": task_id,
                "subtask_id": subtask_id
            }
            
            return result
            
        except Exception as e:
            logger.error(f"处理流任务失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "error": str(e),
                "timestamp": int(time.time()),
                "task_id": task_id,
                "subtask_id": subtask_id
            }
        
    def draw_detections(self, image: np.ndarray, detections: List[Dict]) -> np.ndarray:
        """绘制检测结果"""
        result = image.copy()
        
        for det in detections:
            bbox = det["bbox"]
            conf = det["confidence"]
            label = f"{det['class_name']} {conf:.2f}"
            
            # 绘制边界框
            cv2.rectangle(
                result,
                (bbox["x1"], bbox["y1"]),
                (bbox["x2"], bbox["y2"]),
                (0, 255, 0),
                2
            )
            
            # 绘制标签
            cv2.putText(
                result,
                label,
                (bbox["x1"], bbox["y1"] - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                2
            )
            
        return result
        
    async def analyze_image(self, file: UploadFile) -> Dict[str, Any]:
        """分析图片"""
        try:
            # 读取图片
            contents = await file.read()
            nparr = np.frombuffer(contents, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if image is None:
                raise ValueError("无法读取图片")
                
            # 执行检测
            detections = await self.detector.detect(image)
            
            # 处理结果图片
            if settings.OUTPUT["save_img"]:
                result_image = self.draw_detections(image, detections)
                
                # 保存结果图片
                save_path = f"{settings.OUTPUT['save_dir']}/images/{file.filename}"
                cv2.imwrite(save_path, result_image)
                
                # 转换为base64
                _, buffer = cv2.imencode('.jpg', result_image)
                image_base64 = base64.b64encode(buffer).decode('utf-8')
            else:
                image_base64 = None
            
            # 返回结果
            result = {
                "filename": file.filename,
                "detections": detections,
                "image_base64": image_base64,
                "save_path": save_path if settings.OUTPUT["save_img"] else None,
                "timestamp": datetime.now().isoformat()
            }
            
            return result
            
        except Exception as e:
            logger.error(f"图片分析失败: {str(e)}")
            raise
            
    async def start_video_analysis(self, file: UploadFile) -> str:
        """启动视频分析"""
        try:
            # 生成任务ID
            task_id = str(uuid.uuid4())
            
            # 保存视频文件
            video_path = f"{settings.OUTPUT['save_dir']}/videos/{task_id}.mp4"
            os.makedirs(os.path.dirname(video_path), exist_ok=True)
            
            with open(video_path, "wb") as f:
                content = await file.read()
                f.write(content)
                
            # 创建任务
            self.tasks[task_id] = {
                "type": "video",
                "status": "pending",
                "file_path": video_path,
                "created_at": datetime.now()
            }
            
            # 启动异步处理
            asyncio.create_task(self._process_video(task_id))
            
            return task_id
            
        except Exception as e:
            logger.error(f"启动视频分析失败: {str(e)}")
            raise
            
    async def start_stream_analysis(self, rtsp_url: str) -> str:
        """启动流分析"""
        try:
            # 生成任务ID
            task_id = str(uuid.uuid4())
            
            # 创建任务
            self.tasks[task_id] = {
                "type": "stream",
                "status": "pending",
                "rtsp_url": rtsp_url,
                "created_at": datetime.now().isoformat(),
                "last_frame": None,
                "last_detections": None,
                "error": None
            }
            
            # 创建输出目录
            os.makedirs(f"{settings.OUTPUT['save_dir']}/stream/{task_id}", exist_ok=True)
            
            # 启动异步处理
            asyncio.create_task(self._process_stream(task_id))
            
            return task_id
            
        except Exception as e:
            logger.error(f"启动流分析失败: {str(e)}")
            raise
            
    async def _process_stream(self, task_id: str):
        """处理RTSP流分析任务"""
        task = self.tasks[task_id]
        rtsp_url = task["rtsp_url"]
        
        try:
            # 更新任务状态
            task["status"] = "processing"
            
            # 打开RTSP流
            cap = cv2.VideoCapture(rtsp_url)
            if not cap.isOpened():
                raise ValueError(f"无法打开RTSP流: {rtsp_url}")
            
            # 读取和处理帧
            while True:
                # 检查任务是否被停止
                if task["status"] != "processing":
                    break
                
                # 读取一帧
                ret, frame = cap.read()
                if not ret:
                    logger.warning(f"读取帧失败: {rtsp_url}")
                    # 尝试重新连接
                    cap.release()
                    cap = cv2.VideoCapture(rtsp_url)
                    continue
                
                try:
                    # 执行检测
                    detections = await self.detector.detect(frame)
                    
                    # 处理检测结果
                    if settings.OUTPUT["save_img"]:
                        result_frame = self.draw_detections(frame, detections)
                        
                        # 保存结果帧
                        save_path = f"{settings.OUTPUT['save_dir']}/stream/{task_id}"
                        os.makedirs(save_path, exist_ok=True)
                        cv2.imwrite(f"{save_path}/latest.jpg", result_frame)
                    
                    # 更新任务结果
                    task["last_frame"] = datetime.now().isoformat()
                    task["last_detections"] = detections
                    
                except Exception as e:
                    logger.error(f"处理帧失败: {str(e)}")
                    continue
                
                # 控制处理速度
                await asyncio.sleep(0.01)  # 10ms
                
        except Exception as e:
            logger.error(f"流处理失败: {str(e)}")
            task["status"] = "failed"
            task["error"] = str(e)
            
        finally:
            # 释放资源
            if cap:
                cap.release()

    def stop(self):
        """停止分析服务"""
        logger.info("停止分析服务")
        
        # 停止MQTT客户端
        if self.mqtt_mode and self.mqtt_client:
            self.mqtt_client.stop()
            logger.info("MQTT客户端已停止")
            
        logger.info("分析服务已停止")

# 创建服务实例
analyzer_service = AnalyzerService(service_mode="mqtt")