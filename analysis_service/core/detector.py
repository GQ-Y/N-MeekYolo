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
from PIL import Image, ImageDraw, ImageFont

logger = setup_logger(__name__)

class YOLODetector:
    """YOLO检测器"""
    
    def __init__(self):
        self.model = None
        # 使用配置中的设备设置
        self.device = torch.device("cuda" if torch.cuda.is_available() and settings.ANALYSIS.device != "cpu" else "cpu")
        self.stop_flags = {}
        
        # 使用新的配置结构构建model_service_url
        self.model_service_url = settings.MODEL_SERVICE.url
        self.api_prefix = settings.MODEL_SERVICE.api_prefix
        
        # 使用配置中的存储目录
        self.base_dir = Path(settings.STORAGE.base_dir)
        self.model_dir = self.base_dir / settings.STORAGE.model_dir
        self.temp_dir = self.base_dir / settings.STORAGE.temp_dir
        
        # 创建必要的目录
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(self.model_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # 打印配置信息
        logger.info(f"使用设备: {self.device}")
        logger.info(f"Model service URL: {self.model_service_url}")
        logger.info(f"Model service API prefix: {self.api_prefix}")
        logger.info(f"Base directory: {self.base_dir}")
        logger.info(f"Model directory: {self.model_dir}")
        logger.info(f"Temp directory: {self.temp_dir}")
        
    def _get_api_url(self, path: str) -> str:
        """获取完整的API URL"""
        return f"{self.model_service_url}{self.api_prefix}{path}"
        
    async def get_model_path(self, model_code: str) -> str:
        """获取模型文件路径"""
        try:
            # 构建模型目录路径
            model_dir = self.model_dir / model_code
            model_path = model_dir / "best.pt"
            
            logger.info(f"Looking for model at: {model_path}")
            
            if model_path.exists():
                logger.info(f"Found model at: {model_path}")
                return str(model_path)
            
            # 如果模型不存在，从模型服务下载
            try:
                async with aiohttp.ClientSession() as session:
                    url = self._get_api_url(f"/models/{model_code}/download")
                    async with session.get(url) as response:
                        if response.status == 200:
                            # 确保目录存在
                            os.makedirs(model_dir, exist_ok=True)
                            # 保存模型文件
                            with open(model_path, 'wb') as f:
                                f.write(await response.read())
                            logger.info(f"Downloaded model to: {model_path}")
                            return str(model_path)
                        else:
                            raise Exception(f"Failed to download model: {response.status}")
            except Exception as e:
                logger.error(f"Failed to download model: {str(e)}")
                raise
                
        except Exception as e:
            logger.error(f"Error getting model path: {str(e)}")
            raise

    async def load_model(self, model_code: str):
        """加载模型"""
        try:
            # 获取模型路径
            model_path = await self.get_model_path(model_code)
            logger.info(f"Loading model from: {model_path}")
            
            # 加载模型
            self.model = YOLO(model_path)
            self.model.to(self.device)
            
            # 设置模型参数
            self.model.conf = settings.ANALYSIS.confidence
            self.model.iou = settings.ANALYSIS.iou
            self.model.max_det = settings.ANALYSIS.max_det
            
            logger.info(f"Model loaded successfully from {model_path}")
            
        except Exception as e:
            logger.error(f"Failed to load model: {str(e)}")
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
            
    async def _encode_result_image(self, image: np.ndarray, detections: List[Dict], return_image: bool = False) -> Union[str, np.ndarray, None]:
        """将检测结果绘制到图片上"""
        try:
            # 复制图片以免修改原图
            result_image = image.copy()
            
            # 使用 PIL 处理图片，以支持中文
            img_pil = Image.fromarray(cv2.cvtColor(result_image, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(img_pil)
            
            # 加载中文字体
            try:
                # 尝试加载系统中文字体
                font_size = 24  # 增大字体大小
                font_paths = [
                    "/System/Library/Fonts/PingFang.ttc",  # macOS
                    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",  # Linux
                    "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc",  # Linux 另一个位置
                    "C:/Windows/Fonts/simhei.ttf",  # Windows
                    "fonts/simhei.ttf",  # 项目本地字体
                ]
                
                font = None
                for font_path in font_paths:
                    if os.path.exists(font_path):
                        try:
                            font = ImageFont.truetype(font_path, font_size)
                            logger.debug(f"成功加载字体: {font_path}")
                            break
                        except Exception as e:
                            logger.warning(f"尝试加载字体失败 {font_path}: {str(e)}")
                
                if font is None:
                    logger.warning("未找到合适的中文字体，使用默认字体")
                    font = ImageFont.load_default()
                    
            except Exception as e:
                logger.warning(f"加载字体失败，使用默认字体: {str(e)}")
                font = ImageFont.load_default()
            
            # 图片上绘制检测结果
            for det in detections:
                bbox = det['bbox']
                x1, y1 = bbox['x1'], bbox['y1']
                x2, y2 = bbox['x2'], bbox['y2']
                
                # 绘制边界框 - 使用RGB颜色
                box_color = (0, 255, 0)  # 绿色
                draw.rectangle([(x1, y1), (x2, y2)], outline=box_color, width=3)  # 加粗边框
                
                # 绘制标签（支持中文）
                label = f"{det['class_name']} {det['confidence']:.2f}"
                
                # 计算文本大小
                text_bbox = draw.textbbox((0, 0), label, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
                
                # 确保标签不会超出图片顶部
                label_y = max(y1 - text_height - 4, 0)
                
                # 绘制标签背景 - 半透明效果
                background_shape = [(x1, label_y), (x1 + text_width + 4, label_y + text_height + 4)]
                draw.rectangle(background_shape, fill=(0, 200, 0))  # 浅绿色背景
                
                # 绘制文本 - 白色文字
                text_position = (x1 + 2, label_y + 2)  # 添加一点padding
                draw.text(
                    text_position,
                    label,
                    font=font,
                    fill=(255, 255, 255)  # 白色文字
                )
            
            # 转换回OpenCV格式
            result_image = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
            
            if return_image:
                return result_image
            
            try:
                # 将图片编码为base64，使用较高的图片质量
                encode_params = [cv2.IMWRITE_JPEG_QUALITY, 95]
                _, buffer = cv2.imencode('.jpg', result_image, encode_params)
                if buffer is None:
                    logger.error("图片编码失败")
                    return None
                image_base64 = base64.b64encode(buffer).decode('utf-8')
                logger.debug(f"成功生成base64图片，长度: {len(image_base64)}")
                return image_base64
                
            except Exception as e:
                logger.error(f"图片编码为base64失败: {str(e)}", exc_info=True)
                return None
                
        except Exception as e:
            logger.error(f"处理结果图片失败: {str(e)}", exc_info=True)
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
            
    async def _send_callbacks(self, callback_urls: str, callback_data: Dict[str, Any]):
        """发送回调请求"""
        if not callback_urls:
            return
        
        # 记录回调数据信息
        logger.debug(f"回调数据包含的键: {list(callback_data.keys())}")
        if "result_image" in callback_data:
            logger.debug(f"回调数据包含base64图片，长度: {len(callback_data['result_image']['data'])}")
        if "result_image_url" in callback_data:
            logger.debug(f"回调数据包含图片URL: {callback_data['result_image_url']}")

        # 发送回调
        try:
            async with aiohttp.ClientSession() as session:
                for url in callback_urls.split(','):
                    url = url.strip()
                    if not url:
                        continue
                    
                    try:
                        logger.info(f"正在发送回调到: {url}")
                        logger.debug(f"回调数据大小: {len(str(callback_data))}")
                        async with session.post(url, json=callback_data, timeout=5) as response:
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
                
                # 处理结果图
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
                    
                    # 只在检测到目标时发送回调
                    if detections and callback_urls:
                        try:
                            # 先生成带有检测框的图片
                            result_frame = await self._encode_result_image(frame, detections, return_image=True)
                            if result_frame is not None:
                                # 将结果图片编码为base64
                                try:
                                    _, buffer = cv2.imencode('.jpg', result_frame)
                                    if buffer is None:
                                        raise Exception("图片编码失败")
                                    base64_image = base64.b64encode(buffer).decode('utf-8')
                                    logger.debug(f"成功生成base64图片，长度: {len(base64_image)}")
                                except Exception as e:
                                    logger.error(f"图片编码为base64失败: {str(e)}", exc_info=True)
                                    continue
                                
                                # 构建回调数据
                                callback_data = {
                                    "task_id": task_id,
                                    "status": "processing",
                                    "detections": detections,
                                    "timestamp": time.time(),
                                    "result_image": {
                                        "format": "base64",
                                        "data": base64_image
                                    }
                                }
                                
                                # 如果需要保存图片
                                if settings.OUTPUT.get("save_img", False):
                                    try:
                                        save_dir = Path(settings.OUTPUT["save_dir"])
                                        save_dir.mkdir(parents=True, exist_ok=True)
                                        
                                        timestamp = int(time.time() * 1000)
                                        filename = f"{task_id}_{timestamp}.jpg"
                                        file_path = save_dir / filename
                                        
                                        cv2.imwrite(str(file_path), result_frame)
                                        callback_data["result_image_url"] = str(file_path)
                                        logger.debug(f"已保存图片到: {file_path}")
                                    except Exception as e:
                                        logger.error(f"保存图片失败: {str(e)}", exc_info=True)
                                
                                # 添加父任务ID
                                if parent_task_id:
                                    callback_data["parent_task_id"] = parent_task_id
                                    
                                # 发送回调前检查数据
                                logger.debug(f"回调数据包含的: {list(callback_data.keys())}")
                                logger.debug(f"回调数据中的base64图片长度: {len(callback_data['result_image']['data'])}")
                                
                                # 发送回调
                                await self._send_callbacks(callback_urls, callback_data)
                                
                        except Exception as e:
                            logger.error(f"处理回调数据失败: {str(e)}", exc_info=True)
                
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
            
            # 设置停止志
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
