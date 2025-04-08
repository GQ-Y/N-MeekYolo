"""
YOLO检测器模块
实现基于YOLOv8的物体检测功能
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
from core.config import settings
import time
import asyncio
from PIL import Image, ImageDraw, ImageFont
import colorsys
from datetime import datetime
from core.exceptions import (
    InvalidInputException,
    ModelLoadException,
    ProcessingException,
    ResourceNotFoundException
)

logger = setup_logger(__name__)

class YOLODetector:
    """YOLOv8检测器实现"""
    
    def __init__(self):
        """初始化检测器"""
        self.model = None
        self.current_model_code = None
        self.device = torch.device("cuda" if torch.cuda.is_available() and settings.ANALYSIS.device != "cpu" else "cpu")
        
        # 默认配置
        self.default_confidence = settings.ANALYSIS.confidence
        self.default_iou = settings.ANALYSIS.iou
        self.default_max_det = settings.ANALYSIS.max_det
        
        # 设置保存目录
        self.project_root = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        self.results_dir = self.project_root / settings.OUTPUT.save_dir
        
        # 确保结果目录存在
        os.makedirs(self.results_dir, exist_ok=True)
        
        logger.info(f"初始化YOLO检测器，使用设备: {self.device}")
        logger.info(f"默认置信度阈值: {self.default_confidence}")
        logger.info(f"结果保存目录: {self.results_dir}")
        
    async def get_model_path(self, model_code: str) -> str:
        """获取模型路径
        
        Args:
            model_code: 模型代码,例如'model-gcc'
            
        Returns:
            str: 本地模型文件路径
            
        Raises:
            Exception: 当模型下载或保存失败时抛出异常
        """
        try:
            # 检查本地缓存
            cache_dir = os.path.join("data", "models", model_code)
            model_path = os.path.join(cache_dir, "best.pt")
            
            if os.path.exists(model_path):
                logger.info(f"找到本地缓存模型: {model_path}")
                return model_path
            
            # 本地不存在,从模型服务下载
            logger.info(f"本地未找到模型 {model_code},准备从模型服务下载...")
            
            # 构建API URL
            model_service_url = settings.MODEL_SERVICE.url
            api_prefix = settings.MODEL_SERVICE.api_prefix
            api_url = f"{model_service_url}{api_prefix}/models/download?code={model_code}"
            
            logger.info(f"开始从模型服务下载: {api_url}")
            
            # 创建缓存目录
            os.makedirs(cache_dir, exist_ok=True)
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(api_url) as response:
                        if response.status == 200:
                            # 保存模型文件
                            with open(model_path, "wb") as f:
                                f.write(await response.read())
                            logger.info(f"模型下载成功并保存到: {model_path}")
                            return model_path
                        else:
                            error_msg = await response.text()
                            raise Exception(f"模型下载失败: HTTP {response.status} - {error_msg}")
                            
            except aiohttp.ClientError as e:
                raise Exception(f"请求模型服务失败: {str(e)}")
            
        except Exception as e:
            logger.error(f"获取模型路径时出错: {str(e)}")
            raise Exception(f"获取模型失败: {str(e)}")

    async def load_model(self, model_code: str):
        """加载模型"""
        try:
            # 获取模型路径
            model_path = await self.get_model_path(model_code)
            logger.info(f"正在加载模型: {model_path}")
            
            # 加载模型
            self.model = YOLO(model_path)
            self.model.to(self.device)
            
            # 设置模型参数
            self.model.conf = self.default_confidence
            self.model.iou = self.default_iou
            self.model.max_det = self.default_max_det
            
            # 更新当前模型代码
            self.current_model_code = model_code
            
            logger.info(f"模型加载成功: {model_code}")
            
        except Exception as e:
            logger.error(f"模型加载失败: {str(e)}")
            raise ModelLoadException(f"模型加载失败: {str(e)}")

    def _get_color_by_id(self, obj_id: int) -> Tuple[int, int, int]:
        """根据对象ID生成固定的颜色
        
        Args:
            obj_id: 对象ID
            
        Returns:
            Tuple[int, int, int]: RGB颜色值
        """
        # 使用黄金比例法生成不同的色相值
        golden_ratio = 0.618033988749895
        hue = (obj_id * golden_ratio) % 1.0
        
        # 转换HSV到RGB（固定饱和度和明度以获得鲜艳的颜色）
        rgb = tuple(round(x * 255) for x in colorsys.hsv_to_rgb(hue, 0.8, 0.95))
        return rgb

    async def _encode_result_image(
        self,
        image: np.ndarray,
        detections: List[Dict],
        return_image: bool = False
    ) -> Union[str, np.ndarray, None]:
        """将检测结果绘制到图片上"""
        try:
            # 复制图片以免修改原图
            result_image = image.copy()
            
            # 使用 PIL 处理图片，以支持中文
            img_pil = Image.fromarray(cv2.cvtColor(result_image, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(img_pil)
            
            # 加载字体
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
                            logger.debug(f"成功加载字体: {font_path}")
                            break
                        except Exception as e:
                            logger.debug(f"尝试加载字体失败 {font_path}: {str(e)}")
                            continue
                
                if font is None:
                    logger.warning("未找到合适的中文字体，使用默认字体")
                    # 使用 PIL 默认字体
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
                
                # 根据对象ID或层级选择颜色
                if "obj_id" in det:
                    box_color = self._get_color_by_id(det["obj_id"])
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
                label = f"{det['class_name']} {det['confidence']:.2f}"
                if "obj_id" in det:
                    label += f" ID:{det['obj_id']}"
                
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
                logger.error(f"图片编码为base64失败: {str(e)}")
                return None
                
        except Exception as e:
            logger.error(f"处理结果图片失败: {str(e)}")
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
                model_code = config.get("model_code", self.current_model_code)
                if not model_code:
                    raise Exception("未指定模型代码")
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
            logger.error(f"检测失败: {str(e)}")
            raise ProcessingException(f"检测失败: {str(e)}")

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
            logger.error(f"保存结果图片失败: {str(e)}")
            return None 