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
import httpx
import colorsys
from analysis_service.core.tracker import create_tracker, BaseTracker

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
        """初始化检测器"""
        self.model = None
        self.current_model_code = None
        self.tracker: Optional[BaseTracker] = None
        self.device = torch.device("cuda" if torch.cuda.is_available() and settings.ANALYSIS.device != "cpu" else "cpu")
        self.stop_flags = {}
        self.tasks = {}
        
        # 模型服务配置
        self.model_service_url = settings.MODEL_SERVICE.url
        self.api_prefix = settings.MODEL_SERVICE.api_prefix
        
        # 默认配置
        self.default_confidence = settings.ANALYSIS.confidence
        self.default_iou = settings.ANALYSIS.iou
        self.default_max_det = settings.ANALYSIS.max_det
        
        # 设置保存目录
        self.project_root = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.results_dir = self.project_root / settings.OUTPUT.save_dir
        
        # 确保结果目录存在
        os.makedirs(self.results_dir, exist_ok=True)
        
        logger.info(f"使用设备: {self.device}")
        logger.info(f"Model service URL: {self.model_service_url}")
        logger.info(f"Model service API prefix: {self.api_prefix}")
        logger.info(f"Default confidence: {self.default_confidence}")
        logger.info(f"Results directory: {self.results_dir}")
        
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

    def _get_color_by_id(self, track_id: int) -> Tuple[int, int, int]:
        """根据跟踪ID生成固定的颜色
        
        Args:
            track_id: 跟踪ID
            
        Returns:
            Tuple[int, int, int]: RGB颜色值
        """
        # 使用黄金比例法生成不同的色相值
        golden_ratio = 0.618033988749895
        hue = (track_id * golden_ratio) % 1.0
        
        # 转换HSV到RGB（固定饱和度和明度以获得鲜艳的颜色）
        rgb = tuple(round(x * 255) for x in colorsys.hsv_to_rgb(hue, 0.8, 0.95))
        return rgb

    async def _encode_result_image(
        self,
        image: np.ndarray,
        detections: List[Dict],
        return_image: bool = False,
        draw_tracks: bool = False,  # 新增: 是否绘制轨迹
        draw_track_ids: bool = False  # 新增: 是否绘制跟踪ID
    ) -> Union[str, np.ndarray, None]:
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
                font_size = 16  # 字体大小
                font_paths = [
                    # macOS 系统字体
                    "/System/Library/Fonts/STHeiti Light.ttc",  # 华文细黑
                    "/System/Library/Fonts/STHeiti Medium.ttc", # 华文中黑
                    "/System/Library/Fonts/PingFang.ttc",       # 苹方
                    "/System/Library/Fonts/Hiragino Sans GB.ttc", # 冬青黑体
                    
                    # Windows 系统字体
                    "C:/Windows/Fonts/msyh.ttc",     # 微软雅黑
                    "C:/Windows/Fonts/simsun.ttc",   # 宋体
                    "C:/Windows/Fonts/simhei.ttf",   # 黑体
                    
                    # Linux 系统字体
                    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
                    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                    
                    # 项目本地字体（作为后备）
                    "fonts/simhei.ttf"
                ]
                
                font = None
                for font_path in font_paths:
                    if os.path.exists(font_path):
                        try:
                            font = ImageFont.truetype(font_path, font_size)
                            logger.info(f"成功加载字体: {font_path}")
                            break
                        except Exception as e:
                            logger.debug(f"尝试加载字体失败 {font_path}: {str(e)}")
                            continue
                
                if font is None:
                    logger.warning("未找到合适的中文字体，使用默认字体")
                    # 使用 PIL 默认字体，但增加字体大小以提高可读性
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
                nonlocal draw, img_pil  # 声明使用外部的draw和img_pil变量
                
                bbox = det['bbox']
                x1, y1 = bbox['x1'], bbox['y1']
                x2, y2 = bbox['x2'], bbox['y2']
                
                # 根据跟踪ID或层级选择颜色
                if "track_id" in det:
                    box_color = self._get_color_by_id(det["track_id"])
                else:
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
                
                # 准备标签文本
                label_parts = []
                label_parts.append(f"{det['class_name']} {det['confidence']:.2f}")
                if draw_track_ids and "track_id" in det:
                    label_parts.append(f"ID:{det['track_id']}")
                label = " | ".join(label_parts)
                
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
                
                # 如果启用了轨迹绘制，且有轨迹信息
                if draw_tracks and det.get("track_info", {}).get("trajectory"):
                    # 先转换回OpenCV格式处理轨迹
                    temp_image = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
                    
                    trajectory = det["track_info"]["trajectory"]
                    # 只绘制最近的N个点
                    max_trajectory_points = 30
                    if len(trajectory) > 1:
                        points = trajectory[-max_trajectory_points:]
                        for i in range(len(points) - 1):
                            pt1 = points[i]
                            pt2 = points[i + 1]
                            # 计算轨迹线的中心点
                            pt1_center = (
                                int((pt1[0] + pt1[2]) / 2),
                                int((pt1[1] + pt1[3]) / 2)
                            )
                            pt2_center = (
                                int((pt2[0] + pt2[2]) / 2),
                                int((pt2[1] + pt2[3]) / 2)
                            )
                            # 绘制轨迹线，使用半透明效果
                            alpha = 0.5
                            overlay = temp_image.copy()
                            cv2.line(
                                overlay,
                                pt1_center,
                                pt2_center,
                                box_color,
                                2
                            )
                            cv2.addWeighted(
                                overlay,
                                alpha,
                                temp_image,
                                1 - alpha,
                                0,
                                temp_image
                            )
                    
                    # 转换回PIL格式
                    img_pil = Image.fromarray(cv2.cvtColor(temp_image, cv2.COLOR_BGR2RGB))
                    draw = ImageDraw.Draw(img_pil)
            
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
            
            # 确保置信度和IoU阈值有效
            if conf is None:
                conf = self.default_confidence
            if iou is None:
                iou = self.default_iou
                
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
                        if i != j:  # 不与自己比较
                            child_bbox = child['bbox']
                            
                            # 计算重叠区域
                            overlap_x1 = max(parent_bbox['x1'], child_bbox['x1'])
                            overlap_y1 = max(parent_bbox['y1'], child_bbox['y1'])
                            overlap_x2 = min(parent_bbox['x2'], child_bbox['x2'])
                            overlap_y2 = min(parent_bbox['y2'], child_bbox['y2'])
                            
                            # 如果有重叠
                            if overlap_x1 < overlap_x2 and overlap_y1 < overlap_y2:
                                # 计算重叠区域面积
                                overlap_area = (overlap_x2 - overlap_x1) * (overlap_y2 - overlap_y1)
                                child_area = (child_bbox['x2'] - child_bbox['x1']) * (child_bbox['y2'] - child_bbox['y1'])
                                
                                # 如果子目标的90%以上区域在父目标内部
                                if overlap_area / child_area > 0.9:
                                    child['parent_idx'] = i
                                    parent['children'].append(child)
                
                # 只保留没有父目标的检测结果
                detections = [det for det in detections if det['parent_idx'] is None]
            
            return detections
                    
        except Exception as e:
            logger.error(f"检测失败: {str(e)}", exc_info=True)
            raise

    async def _save_result_image(self, image: np.ndarray, detections: List[Dict], task_name: Optional[str] = None) -> str:
        """保存带有检测结果的图片"""
        try:
            # 生成带检测结果的图片
            logger.info("开始生成检测结果图片...")
            result_image = await self._encode_result_image(image, detections, return_image=True)
            if result_image is None:
                logger.error("生成检测结果图片失败")
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
            success = cv2.imwrite(str(file_path), result_image)
            if not success:
                logger.error("保存图片失败")
                return None
            
            # 返回相对于项目根目录的路径
            relative_path = file_path.relative_to(self.project_root)
            logger.info(f"图片已保存: {relative_path}")
            return str(relative_path)
            
        except Exception as e:
            logger.error(f"保存结果图片失败: {str(e)}", exc_info=True)
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
        """检测图片"""
        try:
            # 记录开始时间
            start_time = time.time()
            logger.info(f"开始图片分析任务, save_result={save_result}")
            
            # 加载模型
            if not self.model:
                await self.load_model(model_code)
                
            results = []
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
                    logger.info("尝试保存检测结果图片...")
                    saved_path = await self._save_result_image(image, detections, task_name)
                    if saved_path:
                        logger.info(f"成功保存检测结果图片，路径: {saved_path}")
                    else:
                        logger.error("保存检测结果图片失败")
                    
                result_dict = {
                    'image_url': url,
                    'detections': detections,
                    'result_image': result_image,
                    'saved_path': saved_path
                }
                results.append(result_dict)
            
            # 计算分析耗时
            end_time = time.time()
            analysis_duration = end_time - start_time
            
            # 构建返回结果
            result = results[0] if results else {
                'image_url': image_urls[0] if image_urls else None,
                'detections': [],
                'result_image': None,
                'saved_path': None
            }
            
            # 添加时间信息和任务名称
            result.update({
                'task_name': task_name,
                'start_time': start_time,
                'end_time': end_time,
                'analysis_duration': analysis_duration
            })
            
            # 发送回调
            if enable_callback and callback_urls:
                logger.info(f"发送回调到: {callback_urls}")
                await self._send_callbacks(callback_urls, result)
            else:
                logger.info("回调已禁用或未提供回调地址，跳过回调")
                
            return result
            
        except Exception as e:
            logger.error(f"Image detection failed: {str(e)}", exc_info=True)
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
            
            # 使用配置参数或默认值
            config = config or {}
            conf = config.get('confidence', self.default_confidence)
            iou = config.get('iou', self.default_iou)
            
            # 确保置信度和IoU阈值有效
            if conf is None:
                conf = self.default_confidence
            if iou is None:
                iou = self.default_iou
            
            config['confidence'] = conf
            config['iou'] = iou
            
            # 打开视频流
            cap = cv2.VideoCapture(stream_url)
            if not cap.isOpened():
                raise Exception(f"Cannot open stream: {stream_url}")
            
            # 初始化时间记录
            current_time = time.time()
            last_analyze_time = current_time
            last_alarm_time = current_time
            last_push_time = current_time
            
            # 设置默认间隔
            if analyze_interval is None:
                analyze_interval = 0  # 不延迟
            if alarm_interval is None:
                alarm_interval = 0  # 不延迟
            if push_interval is None:
                push_interval = 0  # 不延迟
            if random_interval is None:
                random_interval = (0, 0)  # 不添加随机延迟
            
            # 如果需要保存结果，创建保存目录
            date_dir = None
            if save_result:
                date_dir = self.results_dir / datetime.now().strftime("%Y%m%d")
                os.makedirs(date_dir, exist_ok=True)
                logger.info(f"创建结果保存目录: {date_dir}")
            
            while not self.stop_flags.get(task_id, False):
                current_time = time.time()
                frame_start_time = current_time
                
                # 检查分析间隔
                if analyze_interval > 0 and current_time - last_analyze_time < analyze_interval:
                    await asyncio.sleep(0.1)
                    continue
                
                # 添加随机延迟
                if random_interval and random_interval[1] > random_interval[0]:
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
                                    # 生成文件名
                                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                    task_prefix = f"{task_name}_" if task_name else ""
                                    filename = f"{task_prefix}{timestamp}.jpg"
                                    file_path = date_dir / filename
                                    
                                    # 生成并保存结果图片
                                    result_frame = await self._encode_result_image(frame, detections, return_image=True)
                                    if result_frame is not None:
                                        cv2.imwrite(str(file_path), result_frame)
                                        saved_path = str(file_path.relative_to(self.project_root))
                                        logger.info(f"保存检测结果: {saved_path}")
                                
                                # 发送回调
                                if enable_callback and callback_urls:
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
                                    logger.debug("回调已禁用或未提供回调地址，跳过回调")
                
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

    async def get_video_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取视频分析任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务信息字典，包含以下字段：
            - task_name: 任务名称
            - status: 任务状态（waiting/processing/completed/failed）
            - video_url: 视频URL
            - saved_path: 保存路径
            - start_time: 开始时间
            - end_time: 结束时间
            - analysis_duration: 分析耗时
            - progress: 处理进度（0-100）
            - total_frames: 总帧数
            - processed_frames: 已处理帧数
        """
        task_info = self.tasks.get(task_id)
        if task_info:
            # 计算进度
            total_frames = task_info.get('total_frames', 0)
            processed_frames = task_info.get('processed_frames', 0)
            progress = (processed_frames / total_frames * 100) if total_frames > 0 else 0
            
            # 更新进度信息
            task_info.update({
                'progress': round(progress, 2),
                'total_frames': total_frames,
                'processed_frames': processed_frames
            })
            
        return task_info
        
    async def stop_video_task(self, task_id: str) -> bool:
        """停止视频分析任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            bool: 是否成功停止任务
        """
        if task_id in self.stop_flags:
            self.stop_flags[task_id] = True
            # 等待任务真正停止
            for _ in range(10):  # 最多等待5秒
                if task_id not in self.tasks or self.tasks[task_id]['status'] in ['completed', 'failed']:
                    break
                await asyncio.sleep(0.5)
            return True
        return False
        
    async def start_video_analysis(
        self,
        task_id: str,
        model_code: str,
        video_url: str,
        callback_urls: Optional[str] = None,
        config: Optional[Dict] = None,
        task_name: Optional[str] = None,
        enable_callback: bool = True,
        save_result: bool = False,
        enable_tracking: bool = False,  # 新增: 是否启用跟踪
        tracking_config: Optional[Dict] = None  # 新增: 跟踪配置
    ) -> Dict[str, Any]:
        """开始视频分析任务
        
        Args:
            task_id: 任务ID
            model_code: 模型代码
            video_url: 视频URL
            callback_urls: 回调URL
            config: 检测配置参数
            task_name: 任务名称
            enable_callback: 是否启用回调
            save_result: 是否保存分析结果
            enable_tracking: 是否启用目标跟踪
            tracking_config: 跟踪配置,包含以下参数:
                - tracker_type: 跟踪器类型,默认为"sort"
                - max_age: 最大跟踪帧数,默认为30
                - min_hits: 最小命中次数,默认为3
                - iou_threshold: IOU阈值,默认为0.3
                - visualization: 可视化配置
                    - show_tracks: 是否显示轨迹
                    - show_track_ids: 是否显示跟踪ID
        """
        try:
            # 记录任务开始时间
            start_time = time.time()
            logger.info(f"开始视频分析任务: {task_id}")
            
            # 初始化跟踪配置
            if enable_tracking:
                tracking_config = tracking_config or {}
                if "visualization" not in tracking_config:
                    tracking_config["visualization"] = {
                        "show_tracks": True,
                        "show_track_ids": True
                    }
            
            # 初始化任务信息
            self.tasks[task_id] = {
                'task_id': task_id,
                'task_name': task_name,
                'status': 'processing',
                'video_url': video_url,
                'saved_path': None,
                'start_time': start_time,
                'end_time': None,
                'analysis_duration': None,
                'progress': 0.0,
                'total_frames': 0,
                'processed_frames': 0,
                'tracking_enabled': enable_tracking,
                'tracking_config': tracking_config,  # 保存跟踪配置
                'tracking_stats': {
                    'total_tracks': 0,
                    'active_tracks': 0,
                    'avg_track_length': 0.0,
                    'tracker_type': tracking_config.get('tracker_type', 'sort') if enable_tracking else None,
                    'tracking_fps': 0.0
                } if enable_tracking else None
            }
            
            # 启动异步处理任务
            asyncio.create_task(self._process_video_analysis(
                task_id=task_id,
                model_code=model_code,
                video_url=video_url,
                callback_urls=callback_urls,
                config=config,
                task_name=task_name,
                enable_callback=enable_callback,
                save_result=save_result,
                enable_tracking=enable_tracking,
                tracking_config=tracking_config
            ))
            
            return self.tasks[task_id]
            
        except Exception as e:
            logger.error(f"启动视频分析任务失败: {str(e)}", exc_info=True)
            # 更新任务状态为失败
            if task_id in self.tasks:
                self.tasks[task_id].update({
                    'status': 'failed',
                    'end_time': time.time(),
                    'analysis_duration': time.time() - start_time
                })
            raise

    async def _download_video(self, url: str) -> Optional[str]:
        """下载视频到本地
        
        Args:
            url: 视频URL
            
        Returns:
            str: 本地视频文件路径
        """
        try:
            # 生成本地文件路径
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"video_{timestamp}.mp4"
            local_path = str(self.videos_dir / filename)
            
            logger.info(f"开始下载视频: {url}")
            logger.info(f"保存到: {local_path}")
            
            # 使用 httpx 下载视频
            async with httpx.AsyncClient() as client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    
                    # 打开本地文件
                    with open(local_path, "wb") as f:
                        # 分块下载
                        async for chunk in response.aiter_bytes():
                            f.write(chunk)
            
            logger.info(f"视频下载完成: {local_path}")
            return local_path
            
        except Exception as e:
            logger.error(f"下载视频失败: {str(e)}", exc_info=True)
            if os.path.exists(local_path):
                os.remove(local_path)
            raise

    async def _process_video_analysis(
        self,
        task_id: str,
        model_code: str,
        video_url: str,
        callback_urls: Optional[str] = None,
        config: Optional[Dict] = None,
        task_name: Optional[str] = None,
        enable_callback: bool = True,
        save_result: bool = False,
        enable_tracking: bool = False,  # 新增: 是否启用跟踪
        tracking_config: Optional[Dict] = None  # 新增: 跟踪配置
    ):
        """实际的视频处理逻辑"""
        cap = None
        video_writer = None
        local_video_path = None
        start_time = time.time()
        
        try:
            logger.info(f"开始处理视频分析任务: {task_id}")
            
            # 加载模型
            if not self.model:
                await self.load_model(model_code)
            
            # 初始化跟踪器（如果启用）
            if enable_tracking:
                tracking_config = tracking_config or {}
                self.tracker = create_tracker(
                    tracker_type=tracking_config.get("tracker_type", "sort"),
                    max_age=tracking_config.get("max_age", 30),
                    min_hits=tracking_config.get("min_hits", 3),
                    iou_threshold=tracking_config.get("iou_threshold", 0.3)
                )
                logger.info(f"初始化跟踪器: {tracking_config.get('tracker_type', 'sort')}")
            
            # 使用配置参数或默认值
            config_dict = config.dict() if hasattr(config, 'dict') else (config or {})
            conf = config_dict.get('confidence', self.default_confidence)
            iou = config_dict.get('iou', self.default_iou)
            
            # 确保置信度和IoU阈值有效
            if conf is None:
                conf = self.default_confidence
            if iou is None:
                iou = self.default_iou
            
            config_dict['confidence'] = conf
            config_dict['iou'] = iou
            
            # 下载视频到本地
            local_video_path = await self._download_video(video_url)
            
            # 打开视频
            cap = cv2.VideoCapture(local_video_path)
            if not cap.isOpened():
                raise Exception(f"无法打开视频: {local_video_path}")
            
            # 获取视频信息
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            frame_interval = 3  # 每3帧检测一次
            
            # 更新任务信息中的总帧数和跟踪状态
            if task_id in self.tasks:
                self.tasks[task_id].update({
                    'total_frames': total_frames,
                    'processed_frames': 0,
                    'tracking_enabled': enable_tracking,
                    'tracking_stats': {
                        'total_tracks': 0,
                        'active_tracks': 0,
                        'avg_track_length': 0.0,
                        'tracker_type': tracking_config.get('tracker_type', 'sort') if enable_tracking else None,
                        'tracking_fps': 0.0
                    } if enable_tracking else None
                })
            
            logger.info(f"视频信息 - FPS: {fps}, 尺寸: {frame_width}x{frame_height}, 总帧数: {total_frames}, 处理间隔: {frame_interval}（每{frame_interval}帧检测一次）")
            logger.info(f"目标跟踪: {'启用' if enable_tracking else '禁用'}")

            # 如果需要保存结果，创建视频写入器
            saved_path = None
            relative_saved_path = None
            if save_result:
                # 生成保存路径
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                task_prefix = f"{task_name}_" if task_name else ""
                filename = f"{task_prefix}{timestamp}.mp4"
                
                # 确保每天的结果保存在单独的目录中
                date_dir = self.results_dir / datetime.now().strftime("%Y%m%d")
                os.makedirs(date_dir, exist_ok=True)
                
                # 完整的保存路径
                saved_path = str(date_dir / filename)
                relative_saved_path = str(Path(saved_path).relative_to(self.project_root))
                logger.info(f"视频将保存到: {saved_path}")
                
                # 创建视频写入器，使用 H.264 编码
                if os.name == 'nt':  # Windows
                    fourcc = cv2.VideoWriter_fourcc(*'H264')
                else:  # macOS/Linux
                    fourcc = cv2.VideoWriter_fourcc(*'avc1')
                
                video_writer = cv2.VideoWriter(
                    saved_path,
                    fourcc,
                    fps,
                    (frame_width, frame_height)
                )
                
                if not video_writer.isOpened():
                    logger.error("无法创建视频写入器，尝试使用其他编码格式")
                    # 尝试其他编码格式
                    video_writer.release()
                    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                    video_writer = cv2.VideoWriter(
                        saved_path,
                        fourcc,
                        fps,
                        (frame_width, frame_height)
                    )
            
            frame_count = 0
            processed_count = 0
            last_progress_time = time.time()
            last_detections = None  # 存储上一次的检测结果
            frames_buffer = []  # 用于存储检测间隔内的所有帧
            tracking_start_time = time.time()
            total_tracking_time = 0
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                frame_count += 1
                frames_buffer.append(frame.copy())  # 将当前帧添加到缓冲区
                
                # 检查是否需要停止任务
                if self.stop_flags.get(task_id, False):
                    logger.info(f"任务 {task_id} 收到停止信号，开始处理剩余帧...")
                    # 如果需要保存结果，使用最后一次的检测结果处理剩余的所有帧
                    if save_result and video_writer is not None:
                        # 处理缓冲区中的帧
                        if last_detections is not None:
                            for buffered_frame in frames_buffer:
                                result_frame = await self._encode_result_image(
                                    buffered_frame, 
                                    last_detections,
                                    return_image=True,
                                    draw_tracks=enable_tracking and tracking_config.get('visualization', {}).get('show_tracks', True),
                                    draw_track_ids=enable_tracking and tracking_config.get('visualization', {}).get('show_track_ids', True)
                                )
                                if result_frame is not None:
                                    video_writer.write(result_frame)
                        
                        # 继续读取剩余的帧
                        while True:
                            ret, remaining_frame = cap.read()
                            if not ret:
                                break
                            frame_count += 1
                            # 使用最后一次的检测结果
                            if last_detections is not None:
                                result_frame = await self._encode_result_image(
                                    remaining_frame,
                                    last_detections,
                                    return_image=True,
                                    draw_tracks=enable_tracking and tracking_config.get('visualization', {}).get('show_tracks', True),
                                    draw_track_ids=enable_tracking and tracking_config.get('visualization', {}).get('show_track_ids', True)
                                )
                                if result_frame is not None:
                                    video_writer.write(result_frame)
                            else:
                                video_writer.write(remaining_frame)
                            # 更新进度
                            if task_id in self.tasks:
                                self.tasks[task_id]['processed_frames'] = frame_count
                                self.tasks[task_id]['progress'] = round(frame_count / total_frames * 100, 2)
                    break
                
                # 控制处理帧率
                if frame_count % frame_interval == 0:
                    processed_count += 1
                    current_time = time.time()
                    
                    try:
                        # 执行检测
                        detections = await self.detect(frame, config=config_dict)
                        
                        # 如果启用了跟踪，更新跟踪状态
                        if enable_tracking and self.tracker:
                            tracking_start = time.time()
                            tracked_objects = self.tracker.update(detections)
                            tracking_time = time.time() - tracking_start
                            total_tracking_time += tracking_time
                            
                            # 更新检测结果，添加跟踪信息
                            for det, track in zip(detections, tracked_objects):
                                det.update(track.to_dict())
                            
                            # 更新跟踪统计信息
                            if task_id in self.tasks and self.tasks[task_id].get('tracking_stats'):
                                stats = self.tasks[task_id]['tracking_stats']
                                stats.update({
                                    'total_tracks': self.tracker.next_track_id - 1,
                                    'active_tracks': len([t for t in tracked_objects if t.time_since_update == 0]),
                                    'avg_track_length': sum(t.age for t in tracked_objects) / len(tracked_objects) if tracked_objects else 0,
                                    'tracking_fps': processed_count / total_tracking_time if total_tracking_time > 0 else 0
                                })
                        
                        last_detections = detections
                        
                        # 更新处理进度
                        if task_id in self.tasks:
                            self.tasks[task_id]['processed_frames'] = frame_count
                            self.tasks[task_id]['progress'] = round(frame_count / total_frames * 100, 2)
                        
                        # 每秒最多更新一次进度日志
                        if current_time - last_progress_time >= 1.0:
                            progress = (frame_count / total_frames) * 100
                            logger.info(f"处理进度: {progress:.1f}% ({frame_count}/{total_frames})")
                            last_progress_time = current_time
                        
                        # 发送回调
                        if enable_callback and callback_urls:
                            await self._send_callbacks(callback_urls, {
                                "task_id": task_id,
                                "task_name": task_name,
                                "frame_index": frame_count,
                                "total_frames": total_frames,
                                "progress": progress,
                                "detections": last_detections,
                                "tracking_enabled": enable_tracking,
                                "tracking_stats": self.tasks[task_id].get('tracking_stats') if enable_tracking else None,
                                "timestamp": time.time()
                            })
                        
                        # 如果需要保存结果，处理缓冲区中的所有帧
                        if save_result and video_writer is not None and last_detections is not None:
                            for buffered_frame in frames_buffer:
                                # 获取可视化配置
                                vis_config = tracking_config.get('visualization', {}) if enable_tracking and tracking_config else {}
                                show_tracks = vis_config.get('show_tracks', True)
                                show_track_ids = vis_config.get('show_track_ids', True)
                                
                                result_frame = await self._encode_result_image(
                                    buffered_frame, 
                                    last_detections,
                                    return_image=True,
                                    draw_tracks=enable_tracking and show_tracks,
                                    draw_track_ids=enable_tracking and show_track_ids
                                )
                                if result_frame is not None:
                                    video_writer.write(result_frame)
                            
                            # 清空缓冲区
                            frames_buffer = []
                            
                    except Exception as e:
                        logger.error(f"处理第 {frame_count} 帧时出错: {str(e)}")
                        continue
                
                # 每处理5帧后让出控制权
                if frame_count % 5 == 0:
                    await asyncio.sleep(0.01)
            
            # 处理缓冲区中剩余的帧
            if save_result and video_writer is not None and frames_buffer:
                for buffered_frame in frames_buffer:
                    if last_detections is not None:
                        result_frame = await self._encode_result_image(
                            buffered_frame,
                            last_detections,
                            return_image=True,
                            draw_tracks=enable_tracking and tracking_config.get('visualization', {}).get('show_tracks', True),
                            draw_track_ids=enable_tracking and tracking_config.get('visualization', {}).get('show_track_ids', True)
                        )
                        if result_frame is not None:
                            video_writer.write(result_frame)
                    else:
                        # 如果没有检测结果，直接写入原始帧
                        video_writer.write(buffered_frame)
            
            # 计算分析耗时
            end_time = time.time()
            analysis_duration = end_time - start_time
            
            # 更新任务状态
            status = 'completed' if not self.stop_flags.get(task_id, False) else 'stopped'
            if task_id in self.tasks:
                self.tasks[task_id].update({
                    'status': status,
                    'saved_path': relative_saved_path if save_result else None,
                    'end_time': end_time,
                    'analysis_duration': analysis_duration,
                    'total_frames': total_frames,
                    'processed_frames': frame_count,
                    'progress': round(frame_count / total_frames * 100, 2)
                })
                
                # 如果启用了跟踪，更新最终的跟踪统计信息
                if enable_tracking and self.tracker:
                    self.tasks[task_id]['tracking_stats'].update({
                        'total_tracks': self.tracker.next_track_id - 1,
                        'tracking_fps': processed_count / total_tracking_time if total_tracking_time > 0 else 0
                    })
            
            logger.info(f"视频分析完成: {task_id}")
            logger.info(f"- 总帧数: {total_frames}")
            logger.info(f"- 处理帧数: {frame_count}")
            logger.info(f"- 分析耗时: {analysis_duration:.2f}秒")
            if enable_tracking:
                logger.info(f"- 跟踪目标数: {self.tracker.next_track_id - 1}")
                logger.info(f"- 跟踪处理帧率: {processed_count / total_tracking_time if total_tracking_time > 0 else 0:.2f} FPS")
            
            return self.tasks[task_id]
            
        except Exception as e:
            logger.error(f"视频分析失败: {str(e)}", exc_info=True)
            
            # 更新任务状态
            if task_id in self.tasks:
                self.tasks[task_id].update({
                    'status': 'failed',
                    'end_time': time.time(),
                    'analysis_duration': time.time() - start_time
                })
            
            # 发送错误回调
            if enable_callback and callback_urls:
                await self._send_callbacks(callback_urls, {
                    "task_id": task_id,
                    "task_name": task_name,
                    "status": "failed",
                    "error": str(e)
                })
            
            raise
            
        finally:
            # 清理资源
            if cap is not None:
                cap.release()
            if video_writer is not None:
                video_writer.release()
            if local_video_path and os.path.exists(local_video_path):
                try:
                    os.remove(local_video_path)
                except Exception as e:
                    logger.error(f"删除临时视频文件失败: {str(e)}")
            
            # 重置跟踪器
            self.tracker = None
