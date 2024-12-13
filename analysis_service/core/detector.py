"""
检测器模块
封装YOLO模型的检测功能
"""
import os
import base64
from pathlib import Path
import cv2
import numpy as np
import aiohttp
import torch
from ultralytics import YOLO
from typing import List, Dict, Any, Optional, Union
from shared.utils.logger import setup_logger
from analysis_service.core.config import settings
import time
import asyncio
from analysis_service.services.database import get_db
from analysis_service.crud import task as task_crud

logger = setup_logger(__name__)

class YOLODetector:
    """YOLO检测器"""
    
    def __init__(self):
        self.model = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.stop_flags = {}
        
        # 构建model_service_url
        self.model_service_url = f"http://{settings.SERVICES['model']['host']}:{settings.SERVICES['model']['port']}"
        
        # 获取项目根目录和模型存储目录
        self.root_dir = Path(__file__).parent.parent.parent
        self.model_store_dir = self.root_dir / "model_service/store"
        
        # 打印详细的路径
        logger.info(f"使用设备: {self.device}")
        logger.info(f"Model service URL: {self.model_service_url}")
        logger.info(f"Current file: {__file__}")
        logger.info(f"Current file parent: {Path(__file__).parent}")
        logger.info(f"Current file parent.parent: {Path(__file__).parent.parent}")
        logger.info(f"Project root directory: {self.root_dir}")
        logger.info(f"Model store directory: {self.model_store_dir}")
        logger.info(f"Model store directory (absolute): {self.model_store_dir.absolute()}")
        logger.info(f"Model store directory exists: {os.path.exists(self.model_store_dir)}")
        if os.path.exists(self.model_store_dir):
            logger.info(f"Model store directory contents: {os.listdir(self.model_store_dir)}")
        
    async def get_model_path(self, model_code: str) -> str:
        """获取模型文件路径"""
        try:
            # 如果是默认模型，使用项目根目录下的路径
            if model_code == "default":
                default_path = self.root_dir / settings.MODEL["default_model"].lstrip('/')
                logger.info(f"Using default model path: {default_path}")
                logger.info(f"Default model absolute path: {default_path.absolute()}")
                return str(default_path)
                
            # 直接从本地store目录获取模型
            # 使用绝对路径构建模型目录
            model_dir = os.path.join(str(self.model_store_dir.absolute()), model_code)
            logger.info(f"Model store directory (absolute): {self.model_store_dir.absolute()}")
            logger.info(f"Model code: {model_code}")
            logger.info(f"Looking for model in directory: {model_dir}")
            logger.info(f"Model directory exists: {os.path.exists(model_dir)}")
            
            if os.path.exists(model_dir):
                logger.info(f"Model directory contents: {os.listdir(model_dir)}")
                
                # 构建模型文件路径
                model_path = os.path.join(model_dir, "best.pt")
                logger.info(f"Checking model file: {model_path}")
                logger.info(f"Model file exists: {os.path.exists(model_path)}")
                
                # 验证模型文件是否存在
                if os.path.exists(model_path):
                    logger.info(f"Found model at: {model_path}")
                    return model_path
                else:
                    logger.error(f"Model file not found at: {model_path}")
                    raise ValueError(f"Model file not found at: {model_path}")
            else:
                logger.error(f"Model directory not found: {model_dir}")
                raise ValueError(f"Model directory not found: {model_dir}")
                    
        except Exception as e:
            logger.error(f"Error getting model path: {str(e)}")
            # 如果获取失败，使用默认模型
            default_path = self.root_dir / settings.MODEL["default_model"].lstrip('/')
            logger.info(f"Fallback to default model path: {default_path}")
            logger.info(f"Default model absolute path: {default_path.absolute()}")
            return str(default_path)

    async def load_model(self, model_code: str):
        """加载模型"""
        try:
            # 获取模型路径
            model_path = await self.get_model_path(model_code)
            logger.info(f"Loading model from: {model_path}")
            logger.info(f"Current working directory: {os.getcwd()}")
            
            # 检查文件是否存在
            if not os.path.exists(model_path):
                logger.error(f"Model file not found at: {model_path}")
                # 列出目录内容
                current_dir = os.path.dirname(model_path)
                if os.path.exists(current_dir):
                    logger.info(f"Contents of directory {current_dir}:")
                    for item in os.listdir(current_dir):
                        logger.info(f"- {item}")
                else:
                    logger.error(f"Directory does not exist: {current_dir}")
                    # 尝试创建目录
                    os.makedirs(current_dir, exist_ok=True)
                    logger.info(f"Created directory: {current_dir}")
                raise FileNotFoundError(f"Model file not found: {model_path}")
                
            self.model = YOLO(model_path)
            self.model.to(self.device)
            logger.info(f"Model loaded successfully from {model_path}")
            
        except Exception as e:
            logger.error(f"Failed to load model: {str(e)}")
            # 如果加载失败且不是默认模型，尝试加载默认模型
            if model_code != "default":
                logger.info("Attempting to load default model")
                await self.load_model("default")
            else:
                raise
            
    async def _download_image(self, url: str) -> Optional[np.ndarray]:
        """
        下载图片
        
        Args:
            url: 图片URL
            
        Returns:
            np.ndarray: OpenCV格式的图像(BGR)，如果下载失败返回None
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        # 读取图片数据
                        image_data = await response.read()
                        # 转换为numpy数组
                        nparr = np.frombuffer(image_data, np.uint8)
                        # 解码为OpenCV图像
                        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        return image
                    else:
                        logger.error(f"下载图片失败: {url}, 状态码: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"下载图片出错: {url}, 错误: {str(e)}")
            return None
            
    async def _encode_result_image(self, image: np.ndarray, detections: List[Dict]) -> Optional[str]:
        """
        将检测结果绘制到图片上并编码为base64
        
        Args:
            image: OpenCV格式的图像(BGR)
            detections: 检测结果列表
            
        Returns:
            str: base64编码的图片，如果失败返回None
        """
        try:
            # 复制图片以免修改原图
            result_image = image.copy()
            
            # 图片上绘制检测结果
            for det in detections:
                bbox = det['bbox']
                x1, y1 = bbox['x1'], bbox['y1']
                x2, y2 = bbox['x2'], bbox['y2']
                
                # 绘制边界框
                cv2.rectangle(result_image, (x1, y1), (x2, y2), (0, 255, 0), 2)
                
                # 绘制标签
                label = f"{det['class_name']} {det['confidence']:.2f}"
                cv2.putText(result_image, label, (x1, y1 - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            
            # 将图片编码为base64
            _, buffer = cv2.imencode('.jpg', result_image)
            image_base64 = base64.b64encode(buffer).decode('utf-8')
            
            return image_base64
            
        except Exception as e:
            logger.error(f"处理结果图片失败: {str(e)}")
            return None

    async def detect(self, image) -> List[Dict[str, Any]]:
        """
        执行检测
        
        Args:
            image: OpenCV格式的图像(BGR)
            
        Returns:
            List[Dict]: 检测结果列表，每个结果包含:
                - bbox: [x1, y1, x2, y2]
                - confidence: float
                - class_id: int
                - class_name: str
        """
        try:
            if self.model is None:
                # 如果模型未加载，使用默认模型
                await self.load_model("default")
            
            # 执行推理
            results = self.model(
                image,
                conf=settings.ANALYSIS["confidence"],
                iou=settings.ANALYSIS["iou"],
                max_det=settings.ANALYSIS["max_det"]
            )
            
            # 处理结果
            detections = []
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    # 获取边界框坐标
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    
                    # 获取类别信息
                    class_id = int(box.cls[0].item())
                    class_name = result.names[class_id]
                    
                    # 获取置信度
                    confidence = float(box.conf[0].item())
                    
                    detections.append({
                        "bbox": {
                            "x1": int(x1),
                            "y1": int(y1),
                            "x2": int(x2),
                            "y2": int(y2)
                        },
                        "confidence": confidence,
                        "class_id": class_id,
                        "class_name": class_name
                    })
            
            return detections
            
        except Exception as e:
            logger.error(f"检测失败: {str(e)}")
            raise
            
    async def _send_callbacks(self, callback_urls: str, data: Dict[str, Any], parent_task_id: str = None):
        """发送回调请求"""
        if not callback_urls:
            return
            
        # 分割多个回调地址    
        urls = callback_urls.split(',')  # 改用逗号分隔
        logger.info(f"准备发送回调到以下地址: {urls}")
        
        # 添加父任务ID到回调数据
        if parent_task_id:
            data["parent_task_id"] = parent_task_id
        
        try:
            async with aiohttp.ClientSession() as session:
                for url in urls:
                    url = url.strip()
                    if not url:
                        continue
                        
                    try:
                        logger.info(f"正在发送回调到: {url}")
                        async with session.post(url, json=data, timeout=5) as response:
                            if response.status == 200:
                                logger.info(f"回调成功: {url}")
                            else:
                                logger.warning(f"回调失败: {url}, 状态码: {response.status}")
                    except asyncio.TimeoutError:
                        logger.warning(f"回调超时: {url}")
                    except Exception as e:
                        logger.warning(f"回调请求失败: {url}, 错误: {str(e)}")
                    
        except Exception as e:
            logger.warning(f"创建回调会话失败: {str(e)}")
            pass

    async def detect_images(self, model_code: str, image_urls: List[str], callback_urls: str = None, is_base64: bool = False) -> Dict[str, Any]:
        """
        检测图片
        
        Args:
            model_code: 模型代码
            image_urls: 图片URL列表
            callback_urls: 回调URL
            is_base64: 是否返回base64编码的结果图片
            
        Returns:
            Dict[str, Any]: 检测结果，包含：
                - detections: List[Dict] 检测结果列表
                - result_image: Optional[str] base64编码的结果图片
        """
        try:
            # 加载模型
            if not self.model:
                await self.load_model(model_code)  # 使用 model_code 获取模型路径
                
            results = []
            for url in image_urls:
                # 下载图片
                image = await self._download_image(url)
                if image is None:
                    continue
                    
                # 执行检测
                detections = await self.detect(image)
                
                # 处理结果图片
                result_image = None
                if is_base64:
                    result_image = await self._encode_result_image(image, detections)
                    
                results.append({
                    'detections': detections,
                    'result_image': result_image
                })
                
            logger.info(f"Detection results: {results}")
            
            result = results[0] if results else {'detections': [], 'result_image': None}
            
            # 发送回调
            if callback_urls:
                await self._send_callbacks(callback_urls, result)
                
            return result
            
        except Exception as e:
            logger.error(f"Image detection failed: {str(e)}")
            raise

    async def start_stream_analysis(
        self,
        task_id: str,
        stream_url: str,
        callback_urls: Optional[str] = None,
        parent_task_id: Optional[str] = None
    ):
        """启动流分析任务"""
        try:
            # 初始化停止标志
            self.stop_flags[task_id] = False
            
            # 打开视频流
            cap = cv2.VideoCapture(stream_url)
            if not cap.isOpened():
                raise Exception(f"Cannot open stream: {stream_url}")
            
            while not self.stop_flags.get(task_id, False):
                ret, frame = cap.read()
                if not ret:
                    logger.warning("Failed to read frame")
                    cap.release()
                    cap = cv2.VideoCapture(stream_url)
                    continue
                
                try:
                    # 执行检测
                    detections = await self.detect(frame)
                    
                    # 处理结果图片
                    result_frame = None
                    if settings.OUTPUT.get("return_base64", False):
                        result_frame = await self._encode_result_image(frame, detections)
                    
                    # 发送回调
                    if callback_urls:
                        callback_data = {
                            "task_id": task_id,
                            "status": "processing",
                            "detections": detections,
                            "result_frame": result_frame,
                            "timestamp": time.time()
                        }
                        await self._send_callbacks(callback_urls, callback_data, parent_task_id)
                    
                except Exception as e:
                    logger.error(f"Frame processing error: {str(e)}")
                    continue
                
                await asyncio.sleep(0.01)
                
        except Exception as e:
            logger.error(f"Stream analysis failed: {str(e)}")
            raise
            
        finally:
            if cap:
                cap.release()

    async def stop_stream_analysis(self, task_id: str) -> Dict[str, Any]:
        """
        停止流分析任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            Dict[str, Any]: 任务状态
        """
        try:
            if task_id in self.stop_flags:
                self.stop_flags[task_id] = True
                logger.info(f"发送停止信号到任务 {task_id}")
                return {
                    "task_id": task_id,
                    "status": "stopping",
                    "message": "Stop signal sent"
                }
            else:
                raise Exception(f"任务 {task_id} 不存在")
        except Exception as e:
            logger.error(f"停止任务失败: {str(e)}")
            raise
            
    async def stop_task(self, task_id: str) -> bool:
        """停止指定任务"""
        try:
            if task_id not in self.stop_flags:
                logger.warning(f"任务 {task_id} 不存在")
                return False
            
            # 设置停止标志
            self.stop_flags[task_id] = True
            logger.info(f"已发送停止信号到任务 {task_id}")
            
            # 等待任务实际停止
            for _ in range(10):  # 最多等待5秒
                if task_id not in self.stop_flags:
                    break
                await asyncio.sleep(0.5)
            
            return True
        
        except Exception as e:
            logger.error(f"停止任务失败: {str(e)}", exc_info=True)
            return False
