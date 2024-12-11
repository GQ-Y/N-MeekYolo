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
from typing import List, Dict, Any, Optional
from shared.utils.logger import setup_logger
from analysis_service.core.config import settings
import time
import asyncio

logger = setup_logger(__name__)

class YOLODetector:
    """YOLO检测器"""
    
    def __init__(self):
        self.model = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.stop_flags = {}  # 添加停止标志字典
        logger.info(f"使用设备: {self.device}")
        
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
            
            # 在图片上绘制检测结果
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

    async def load_model(self, model_path: str):
        """加载模型"""
        try:
            # 获取项目根目录
            root_dir = Path(__file__).parent.parent.parent
            # 构建完整的模型路径
            full_model_path = root_dir / model_path
            
            logger.info(f"加载模型: {full_model_path}")
            
            if not full_model_path.exists():
                raise FileNotFoundError(f"Model file not found: {full_model_path}")
                
            self.model = YOLO(str(full_model_path))
            self.model.to(self.device)
            logger.info("模型加载成功")
            
        except Exception as e:
            logger.error(f"模型加载失败: {str(e)}")
            raise
            
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
                await self.load_model("/models/yolo/yolov11.pt")
            
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
            
    async def _send_callback(self, callback_url: str, result: Dict[str, Any]):
        """
        发送回调请求
        
        Args:
            callback_url: 回调URL
            result: 检测结果
        """
        if not callback_url:
            return
            
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(callback_url, json=result) as response:
                    if response.status == 200:
                        logger.info(f"回调成功: {callback_url}")
                    else:
                        logger.error(f"回调失败: {callback_url}, 状态码: {response.status}")
        except Exception as e:
            logger.error(f"发送回调请求���败: {callback_url}, 错误: {str(e)}")
            
    async def detect_images(self, model_code: str, image_urls: List[str], callback_url: str = None, is_base64: bool = False) -> Dict[str, Any]:
        """
        检测图片
        
        Args:
            model_code: 模型代码
            image_urls: 图片URL列表
            callback_url: 回调URL
            is_base64: 是否返回base64编码的结果图片
            
        Returns:
            Dict[str, Any]: 检测结果，包含：
                - detections: List[Dict] 检测结果列表
                - result_image: Optional[str] base64编码的结果图片
        """
        try:
            # 加载模型
            if not self.model:
                await self.load_model(f"models/{model_code}/best.pt")
                
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
                
            # 添加日志输出
            logger.info(f"Detection results: {results}")
            
            result = results[0] if results else {'detections': [], 'result_image': None}
            
            # 发送回调
            if callback_url:
                await self._send_callback(callback_url, result)
                
            return result
            
        except Exception as e:
            logger.error(f"Image detection failed: {str(e)}")
            raise

    async def start_stream_analysis(
        self, 
        model_code: str, 
        stream_url: str,
        callback_url: str = None,
        output_url: str = None,
        callback_interval: int = 1
    ) -> Dict[str, Any]:
        """
        开始流分析
        
        Args:
            model_code: 模型代码
            stream_url: 流地址
            callback_url: 回调URL
            output_url: 输出流地址
            callback_interval: 回调间隔(秒)
            
        Returns:
            Dict[str, Any]: 任务信息
        """
        try:
            # 加载模型
            if not self.model:
                await self.load_model(f"models/{model_code}/best.pt")
                
            # 创建任务ID
            task_id = f"stream_{int(time.time())}"
            
            # 启动流分析任务
            asyncio.create_task(self._process_stream(
                task_id,
                stream_url,
                callback_url,
                output_url,
                callback_interval
            ))
            
            return {
                "task_id": task_id,
                "status": "started",
                "stream_url": stream_url,
                "output_url": output_url
            }
            
        except Exception as e:
            logger.error(f"Start stream analysis failed: {str(e)}")
            raise

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
            
    async def _process_stream(
        self,
        task_id: str,
        stream_url: str,
        callback_url: str = None,
        output_url: str = None,
        callback_interval: int = 1
    ):
        """处理流分析"""
        try:
            # 初始化停止标志
            self.stop_flags[task_id] = False
            
            # 打开视频流
            cap = cv2.VideoCapture(stream_url)
            if not cap.isOpened():
                raise Exception(f"Cannot open stream: {stream_url}")
            
            # 获取视频信息
            fps = int(cap.get(cv2.CAP_PROP_FPS))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            # 初始化输出
            writer = None
            if output_url:
                # 设置输出编码器
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                writer = cv2.VideoWriter(output_url, fourcc, fps, (width, height))
            
            last_callback_time = 0
            while True:
                # 检查停止标志
                if self.stop_flags.get(task_id, False):
                    logger.info(f"任务 {task_id} 收到停止信号")
                    break
                    
                ret, frame = cap.read()
                if not ret:
                    break
                    
                # 执行检测
                detections = await self.detect(frame)
                
                # 处理结果图片
                result_frame = frame.copy()
                for det in detections:
                    bbox = det['bbox']
                    x1, y1 = bbox['x1'], bbox['y1']
                    x2, y2 = bbox['x2'], bbox['y2']
                    
                    # 绘制边界框
                    cv2.rectangle(result_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    
                    # 绘制标签
                    label = f"{det['class_name']} {det['confidence']:.2f}"
                    cv2.putText(result_frame, label, (x1, y1 - 10),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                
                # 写入输出视频
                if writer:
                    writer.write(result_frame)
                
                # 发送回调
                current_time = time.time()
                if callback_url and (current_time - last_callback_time) >= callback_interval:
                    # 编码结果帧
                    _, buffer = cv2.imencode('.jpg', result_frame)
                    frame_base64 = base64.b64encode(buffer).decode('utf-8')
                    
                    # 准备回调数据
                    callback_data = {
                        "task_id": task_id,
                        "status": "processing",
                        "stream_url": stream_url,
                        "output_url": output_url,
                        "detections": detections,
                        "result_frame": frame_base64,
                        "timestamp": current_time
                    }
                    
                    await self._send_callback(callback_url, callback_data)
                    last_callback_time = current_time
                    
            # 发送停止回调
            if callback_url:
                await self._send_callback(callback_url, {
                    "task_id": task_id,
                    "status": "stopped",
                    "stream_url": stream_url,
                    "output_url": output_url,
                    "stopped_at": time.time()
                })
                
        except Exception as e:
            logger.error(f"Process stream failed: {str(e)}")
            if callback_url:
                await self._send_callback(callback_url, {
                    "task_id": task_id,
                    "status": "failed",
                    "error": str(e),
                    "stream_url": stream_url
                })
                
        finally:
            # 清理资源
            if task_id in self.stop_flags:
                del self.stop_flags[task_id]
            cap.release()
            if writer:
                writer.release()