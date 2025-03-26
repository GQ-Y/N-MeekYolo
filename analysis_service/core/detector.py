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
from typing import List, Dict, Any, Optional, Union, Tuple
from shared.utils.logger import setup_logger
from analysis_service.core.config import settings
import time
import asyncio
from analysis_service.services.database import get_db
from analysis_service.crud import task as task_crud
from PIL import Image, ImageDraw, ImageFont
import random
from datetime import datetime
from loguru import logger

logger = setup_logger(__name__)

class CallbackData:
    """标准回调数据结构"""
    def __init__(self, 
                 camera_device_type: int = 1,
                 camera_device_stream_url: str = "",
                 camera_device_status: int = 1,
                 camera_device_group: str = "",
                 camera_device_gps: str = "",
                 camera_device_id: int = 0,
                 camera_device_name: str = "",
                 algorithm_id: int = 0,
                 algorithm_name: str = "",
                 algorithm_name_en: str = "",
                 data_id: str = "",
                 parameter: Dict = None,
                 picture: str = "",
                 src_url: str = "",
                 alarm_url: str = "",
                 task_id: int = 0,
                 camera_id: int = 0,
                 camera_url: str = "",
                 camera_name: str = "",
                 timestamp: int = 0,
                 image_width: int = 1920,
                 image_height: int = 1080,
                 src_pic_data: str = "",
                 src_pic_name: str = "",
                 alarm_pic_name: str = "",
                 src: str = "",
                 alarm: str = "",
                 alarm_pic_data: str = "",
                 other: str = "",
                 result: str = "",
                 extra_info: List = None,
                 result_data: Dict = None,
                 degree: int = 3):
        
        self.camera_device_type = camera_device_type
        self.camera_device_stream_url = camera_device_stream_url
        self.camera_device_status = camera_device_status
        self.camera_device_group = camera_device_group
        self.camera_device_gps = camera_device_gps
        self.camera_device_id = camera_device_id
        self.camera_device_name = camera_device_name
        self.algorithm_id = algorithm_id
        self.algorithm_name = algorithm_name
        self.algorithm_name_en = algorithm_name_en
        self.data_id = data_id
        self.parameter = parameter or {}
        self.picture = picture
        self.src_url = src_url
        self.alarm_url = alarm_url
        self.task_id = task_id
        self.camera_id = camera_id
        self.camera_url = camera_url
        self.camera_name = camera_name
        self.timestamp = timestamp or int(time.time())
        self.image_width = image_width
        self.image_height = image_height
        self.src_pic_data = src_pic_data
        self.src_pic_name = src_pic_name
        self.alarm_pic_name = alarm_pic_name
        self.src = src
        self.alarm = alarm
        self.alarm_pic_data = alarm_pic_data
        self.other = other
        self.result = result
        self.extra_info = extra_info or []
        self.result_data = result_data or {}
        self.degree = degree

    def to_dict(self) -> Dict:
        """转换为字典格式"""
        return {
            "cameraDeviceType": self.camera_device_type,
            "cameraDeviceStreamUrl": self.camera_device_stream_url,
            "cameraDeviceStatus": self.camera_device_status,
            "cameraDeviceGroup": self.camera_device_group,
            "cameraDeviceGps": self.camera_device_gps,
            "cameraDeviceId": self.camera_device_id,
            "cameraDeviceName": self.camera_device_name,
            "algorithmId": self.algorithm_id,
            "algorithmName": self.algorithm_name,
            "algorithmNameEn": self.algorithm_name_en,
            "dataID": self.data_id,
            "parameter": self.parameter,
            "picture": self.picture,
            "srcUrl": self.src_url,
            "alarmUrl": self.alarm_url,
            "taskId": self.task_id,
            "cameraId": self.camera_id,
            "cameraUrl": self.camera_url,
            "cameraName": self.camera_name,
            "timestamp": self.timestamp,
            "imageWidth": self.image_width,
            "imageHeight": self.image_height,
            "srcPicData": self.src_pic_data,
            "srcPicName": self.src_pic_name,
            "alarmPicName": self.alarm_pic_name,
            "src": self.src,
            "alarm": self.alarm,
            "alarmPicData": self.alarm_pic_data,
            "other": self.other,
            "result": self.result,
            "extraInfo": self.extra_info,
            "resultData": self.result_data,
            "degree": self.degree
        }

class YOLODetector:
    """YOLO检测器"""
    
    def __init__(self):
        self.model = None
        self.current_model_code = None
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
        self.results_dir = self.base_dir / "results"  # 添加结果保存目录
        
        # 创建必要的目录
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(self.model_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.results_dir, exist_ok=True)  # 创建结果保存目录
        
        # 保存默认配置
        self.default_confidence = settings.ANALYSIS.confidence
        self.default_iou = settings.ANALYSIS.iou
        self.default_max_det = settings.ANALYSIS.max_det
        
        # 打印配置信息
        logger.info(f"使用设备: {self.device}")
        logger.info(f"Model service URL: {self.model_service_url}")
        logger.info(f"Model service API prefix: {self.api_prefix}")
        logger.info(f"Base directory: {self.base_dir}")
        logger.info(f"Model directory: {self.model_dir}")
        logger.info(f"Temp directory: {self.temp_dir}")
        logger.info(f"Results directory: {self.results_dir}")
        logger.info(f"Default confidence: {self.default_confidence}")
        
    def _get_api_url(self, path: str) -> str:
        """获取完整的API URL"""
        return f"{self.model_service_url}{self.api_prefix}{path}"
        
    async def get_model_path(self, model_code: str) -> str:
        """获取模型路径"""
        try:
            # 检查本地模型
            model_dir = os.path.join("data", "models", model_code)
            model_path = os.path.join(model_dir, "best.pt")
            
            if os.path.exists(model_path):
                logger.info(f"Found local model at: {model_path}")
                return model_path
            
            # 如果本地不存在，从模型服务下载
            os.makedirs(model_dir, exist_ok=True)
            url = f"{settings.MODEL_SERVICE.url}{settings.MODEL_SERVICE.api_prefix}/models/{model_code}/download"
            
            logger.info(f"Trying to download model from: {url}")
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        if response.status == 200:
                            with open(model_path, "wb") as f:
                                f.write(await response.read())
                            logger.info(f"Model downloaded successfully to: {model_path}")
                            return model_path
                        else:
                            error_text = await response.text()
                            logger.error(f"Failed to download model. Status: {response.status}, Response: {error_text}")
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
            self.model.conf = self.default_confidence
            self.model.iou = self.default_iou
            self.model.max_det = self.default_max_det
            
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
            logger.info(f"开始下载图片: {url}")
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30) as response:
                    if response.status == 200:
                        # 读取图片数据
                        image_data = await response.read()
                        content_type = response.headers.get('content-type', '')
                        logger.info(f"图片下载成功，Content-Type: {content_type}, 数据大小: {len(image_data)} bytes")
                        
                        # 转换为numpy数组
                        nparr = np.frombuffer(image_data, np.uint8)
                        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        
                        if image is None:
                            logger.error("图片解码失败")
                            return None
                            
                        logger.info(f"图片解码成功，尺寸: {image.shape}")
                        return image
                    else:
                        logger.error(f"下载图片失败: {url}, 状态码: {response.status}")
                        response_text = await response.text()
                        logger.error(f"响应内容: {response_text[:200]}")  # 只记录前200个字符
                        return None
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络请求错误: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"下载图片出错: {url}, 错误: {str(e)}", exc_info=True)
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
            
            def draw_detection(det: Dict, level: int = 0):
                """递归绘制检测框及其子目标
                
                Args:
                    det: 检测结果
                    level: 嵌套层级，用于确定颜色
                """
                bbox = det['bbox']
                x1, y1 = bbox['x1'], bbox['y1']
                x2, y2 = bbox['x2'], bbox['y2']
                
                # 根据层级选择不同的颜色
                colors = [
                    (0, 255, 0),   # 绿色 - 父级
                    (255, 0, 0),   # 红色 - 一级子目标
                    (0, 0, 255),   # 蓝色 - 二级子目标
                    (255, 255, 0)  # 黄色 - 更深层级
                ]
                box_color = colors[min(level, len(colors) - 1)]
                
                # 绘制边界框
                draw.rectangle([(x1, y1), (x2, y2)], outline=box_color, width=3)  # 加粗边框
                
                # 绘制标签（支持中文）
                label = f"{det['class_name']} {det['confidence']:.2f}"
                
                # 计算文本大小
                text_bbox = draw.textbbox((0, 0), label, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
                
                # 确保标签不会超出图片顶部
                label_y = max(y1 - text_height - 4, 0)
                
                # 绘制标签背景
                background_shape = [(x1, label_y), (x1 + text_width + 4, label_y + text_height + 4)]
                draw.rectangle(background_shape, fill=box_color)
                
                # 绘制文本
                text_position = (x1 + 2, label_y + 2)
                draw.text(
                    text_position,
                    label,
                    font=font,
                    fill=(255, 255, 255)  # 白色文字
                )
                
                # 递归处理子目标
                for child in det.get('children', []):
                    draw_detection(child, level + 1)
            
            # 处理所有顶层检测结果
            for det in detections:
                draw_detection(det)
            
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

    async def detect(self, image, config: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """执行检测
        
        Args:
            image: 输入图片
            config: 检测配置，包含以下可选参数：
                - confidence: 置信度阈值
                - iou: IoU阈值
                - classes: 需要检测的类别ID列表
                - roi: 感兴趣区域，格式为{x1, y1, x2, y2}，值为0-1的归一化坐标
                - imgsz: 输入图片大小
                - nested_detection: 是否进行嵌套检测
        """
        try:
            if self.model is None:
                model_code = self.current_model_code
                if not model_code:
                    raise Exception("No model code specified")
                await self.load_model(model_code)
            
            # 使用配置参数或默认值
            config = config or {}
            conf = config.get('confidence', self.default_confidence)
            iou = config.get('iou', self.default_iou)
            classes = config.get('classes', None)
            roi = config.get('roi', None)
            imgsz = config.get('imgsz', None)
            nested_detection = config.get('nested_detection', False)
            
            logger.info(f"检测配置 - 置信度: {conf}, IoU: {iou}, 类别: {classes}, ROI: {roi}, 图片大小: {imgsz}, 嵌套检测: {nested_detection}")
            
            # 处理ROI
            original_shape = None
            if roi:
                h, w = image.shape[:2]
                original_shape = (h, w)
                x1 = int(roi['x1'] * w)
                y1 = int(roi['y1'] * h)
                x2 = int(roi['x2'] * w)
                y2 = int(roi['y2'] * h)
                image = image[y1:y2, x1:x2]
            
            # 处理图片大小
            if imgsz:
                image = cv2.resize(image, (imgsz, imgsz))
            
            # 执行推理
            results = self.model(
                image,
                conf=conf,
                iou=iou,
                classes=classes
            )
            
            # 处理检测结果
            detections = []
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    bbox = box.xyxy[0].cpu().numpy()
                    conf = float(box.conf[0])
                    cls = int(box.cls[0])
                    name = result.names[cls]
                    
                    # 如果使用了ROI，需要调整坐标
                    if roi and original_shape:
                        h, w = original_shape
                        bbox[0] = bbox[0] / w * (roi['x2'] - roi['x1']) * w + roi['x1'] * w
                        bbox[1] = bbox[1] / h * (roi['y2'] - roi['y1']) * h + roi['y1'] * h
                        bbox[2] = bbox[2] / w * (roi['x2'] - roi['x1']) * w + roi['x1'] * w
                        bbox[3] = bbox[3] / h * (roi['y2'] - roi['y1']) * h + roi['y1'] * h
                    
                    detection = {
                        "bbox": {
                            "x1": float(bbox[0]),
                            "y1": float(bbox[1]),
                            "x2": float(bbox[2]),
                            "y2": float(bbox[3])
                        },
                        "confidence": conf,
                        "class_id": cls,
                        "class_name": name,
                        "area": float((bbox[2] - bbox[0]) * (bbox[3] - bbox[1])),  # 计算面积
                        "parent_idx": None,  # 用于存储父目标的索引
                        "children": []  # 用于存储子目标列表
                    }
                    detections.append(detection)
            
            # 处理嵌套检测
            if nested_detection and len(detections) > 1:
                logger.info("开始处理嵌套检测...")
                
                # 按面积从大到小排序
                detections.sort(key=lambda x: x['area'], reverse=True)
                
                # 检查嵌套关系
                for i, parent in enumerate(detections):
                    parent_bbox = parent['bbox']
                    
                    # 检查其他目标是否在当前目标内部
                    for j, child in enumerate(detections):
                        if i == j or child['parent_idx'] is not None:  # 跳过自身和已有父级的目标
                            continue
                            
                        child_bbox = child['bbox']
                        
                        # 计算重叠区域
                        x_left = max(parent_bbox['x1'], child_bbox['x1'])
                        y_top = max(parent_bbox['y1'], child_bbox['y1'])
                        x_right = min(parent_bbox['x2'], child_bbox['x2'])
                        y_bottom = min(parent_bbox['y2'], child_bbox['y2'])
                        
                        if x_right > x_left and y_bottom > y_top:
                            overlap_area = (x_right - x_left) * (y_bottom - y_top)
                            overlap_ratio = overlap_area / child['area']
                            
                            # 判断嵌套关系：重叠面积占子目标面积的比例大于0.9
                            if overlap_ratio > 0.9:
                                logger.debug(f"发现嵌套关系: {parent['class_name']} 包含 {child['class_name']}, "
                                           f"重叠率: {overlap_ratio:.2f}")
                                child['parent_idx'] = i  # 记录父目标的索引
                                parent['children'].append(j)  # 记录子目标的索引
                
                # 构建最终的检测结果
                final_detections = []
                for i, det in enumerate(detections):
                    # 如果目标没有父级，则处理它及其子目标
                    if det['parent_idx'] is None:
                        # 处理子目标
                        if det['children']:
                            children_list = []
                            for child_idx in det['children']:
                                child = detections[child_idx].copy()
                                # 移除子目标中的不必要字段
                                child.pop('parent_idx', None)
                                child.pop('children', None)
                                child.pop('area', None)
                                children_list.append(child)
                            det['children'] = children_list
                        else:
                            det['children'] = []
                        
                        # 移除临时字段
                        det.pop('parent_idx', None)
                        det.pop('area', None)
                        
                        final_detections.append(det)
                
                logger.info(f"嵌套检测完成，共 {len(final_detections)} 个父目标")
                detections = final_detections
            else:
                # 如果不进行嵌套检测，清理所有检测结果中的临时字段
                for det in detections:
                    det.pop('parent_idx', None)
                    det.pop('area', None)
                    det['children'] = []
            
            return detections
            
        except Exception as e:
            logger.error(f"检测失败: {str(e)}")
            raise

    async def _save_result_image(self, image: np.ndarray, detections: List[Dict], task_name: Optional[str] = None) -> str:
        """保存带有检测结果的图片
        
        Args:
            image: 原始图片
            detections: 检测结果
            task_name: 任务名称
            
        Returns:
            str: 保存的文件路径
        """
        try:
            # 生成带检测结果的图片
            result_image = await self._encode_result_image(image, detections, return_image=True)
            if result_image is None:
                return None
                
            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            task_prefix = f"{task_name}_" if task_name else ""
            filename = f"{task_prefix}{timestamp}.jpg"
            
            # 确保每天的结果保存在单独的目录中
            date_dir = self.results_dir / datetime.now().strftime("%Y%m%d")
            os.makedirs(date_dir, exist_ok=True)
            
            # 保存图片
            file_path = date_dir / filename
            cv2.imwrite(str(file_path), result_image)
            
            logger.info(f"分析结果已保存到: {file_path}")
            return str(file_path)
            
        except Exception as e:
            logger.error(f"保存结果图片失败: {str(e)}")
            return None

    async def detect_images(
        self,
        model_code: str,
        image_urls: List[str],
        callback_urls: str = None,
        is_base64: bool = False,
        config: Optional[Dict] = None,
        task_name: Optional[str] = None,
        enable_callback: bool = True,
        save_result: bool = False
    ) -> Dict[str, Any]:
        """
        检测图片
        
        Args:
            model_code: 模型代码
            image_urls: 图片URL列表
            callback_urls: 回调URL
            is_base64: 是否返回base64编码的结果图片
            config: 检测配置参数
            task_name: 任务名称
            enable_callback: 是否启用回调
            save_result: 是否保存分析结果
        """
        try:
            # 记录开始时间
            start_time = time.time()
            
            # 加载模型
            if not self.model:
                await self.load_model(model_code)
                
            results = []
            saved_paths = []
            for url in image_urls:
                # 下载图片
                image = await self._download_image(url)
                if image is None:
                    continue
                    
                # 执行检测
                detections = await self.detect(image, config=config)
                
                # 处理结果图
                result_image = None
                if is_base64:
                    result_image = await self._encode_result_image(image, detections)
                
                # 保存结果
                saved_path = None
                if save_result:
                    saved_path = await self._save_result_image(image, detections, task_name)
                    if saved_path:
                        saved_paths.append(saved_path)
                    
                results.append({
                    'detections': detections,
                    'result_image': result_image,
                    'saved_path': saved_path
                })
            
            # 计算分析耗时
            end_time = time.time()
            analysis_duration = end_time - start_time
            
            result = results[0] if results else {'detections': [], 'result_image': None, 'saved_path': None}
            
            # 添加时间信息和任务名称
            result.update({
                'task_name': task_name,
                'start_time': start_time,
                'end_time': end_time,
                'analysis_duration': analysis_duration,
                'saved_paths': saved_paths if save_result else None
            })
            
            # 发送回调
            if enable_callback:
                if callback_urls:
                    logger.info(f"发送回调到: {callback_urls}")
                    await self._send_callbacks(callback_urls, result)
                else:
                    logger.info("回调已启用但未提供回调地址，跳过回调")
            else:
                logger.info("回调已禁用，跳过回调")
                
            return result
            
        except Exception as e:
            logger.error(f"Image detection failed: {str(e)}")
            raise

    async def start_stream_analysis(
        self,
        task_id: str,
        stream_url: str,
        model_code: str,
        callback_urls: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        analyze_interval: int = 1,
        alarm_interval: int = 60,
        random_interval: Tuple[int, int] = (0, 0),
        config: Optional[Dict] = None,
        push_interval: int = 5,
        task_name: Optional[str] = None,
        enable_callback: bool = True,
        save_result: bool = False
    ):
        """启动流分析任务"""
        cap = None
        try:
            # 记录任务开始时间
            task_start_time = time.time()
            
            logger.info(f"Starting stream analysis task: {task_id}")
            logger.info(f"Task name: {task_name}")
            logger.info(f"Model code: {model_code}")
            logger.info(f"Stream URL: {stream_url}")
            logger.info(f"Detection config: {config}")
            logger.info(f"Enable callback: {enable_callback}")
            logger.info(f"Save result: {save_result}")
            
            if enable_callback:
                if callback_urls:
                    logger.info(f"Callback URLs: {callback_urls}")
                else:
                    logger.info("回调已启用但未提供回调地址，将不会发送回调")
            else:
                logger.info("回调已禁用")
            
            # 设置当前模型代码
            self.current_model_code = model_code
            
            # 初始化停止标志
            self.stop_flags[task_id] = False
            
            # 确保模型已加载
            logger.info("Loading model...")
            await self.load_model(model_code)
            logger.info("Model loaded successfully")
            
            # 打开视频流
            cap = cv2.VideoCapture(stream_url)
            if not cap.isOpened():
                raise Exception(f"Cannot open stream: {stream_url}")
            
            # 初始化时间记录
            current_time = time.time()
            last_analyze_time = current_time
            last_alarm_time = current_time
            last_push_time = current_time
            
            while not self.stop_flags.get(task_id, False):
                current_time = time.time()
                frame_start_time = current_time
                
                # 检查分析间隔
                if current_time - last_analyze_time < analyze_interval:
                    await asyncio.sleep(0.1)
                    continue
                
                # 添加随机延迟
                if random_interval[1] > random_interval[0]:
                    delay = random.uniform(random_interval[0], random_interval[1])
                    await asyncio.sleep(delay)
                
                ret, frame = cap.read()
                if not ret:
                    logger.warning("Failed to read frame")
                    cap.release()
                    cap = cv2.VideoCapture(stream_url)
                    continue
                
                try:
                    # 执行检测
                    detections = await self.detect(frame, config=config)
                    
                    # 计算当前帧分析耗时
                    frame_end_time = time.time()
                    frame_duration = frame_end_time - frame_start_time
                    
                    if detections:
                        # 检查报警间隔
                        if current_time - last_alarm_time >= alarm_interval:
                            last_alarm_time = current_time
                            
                            # 检查推送间隔
                            if current_time - last_push_time >= push_interval:
                                last_push_time = current_time
                                
                                # 保存结果
                                saved_path = None
                                if save_result:
                                    saved_path = await self._save_result_image(frame, detections, task_name)
                                
                                # 发送回调
                                if enable_callback:
                                    if callback_urls:
                                        await self._send_callbacks(callback_urls, {
                                            "task_id": task_id,
                                            "task_name": task_name,
                                            "parent_task_id": parent_task_id,
                                            "detections": detections,
                                            "stream_url": stream_url,
                                            "image": frame,
                                            "timestamp": current_time,
                                            "task_start_time": task_start_time,
                                            "frame_start_time": frame_start_time,
                                            "frame_end_time": frame_end_time,
                                            "frame_duration": frame_duration,
                                            "total_duration": frame_end_time - task_start_time,
                                            "saved_path": saved_path
                                        })
                                    else:
                                        logger.debug("回调已启用但未提供回调地址，跳过回调")
                                else:
                                    logger.debug("回调已禁用，跳过回调")
                
                except Exception as e:
                    logger.error(f"Frame processing error: {str(e)}")
                    continue
                
                last_analyze_time = current_time
                await asyncio.sleep(0.01)
                
        except Exception as e:
            logger.error(f"Stream analysis failed: {str(e)}")
            raise
            
        finally:
            if cap is not None:
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
