"""
YOLO分割器模块
实现基于YOLOv8的图像分割功能，包括实例分割和语义分割
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

class YOLOSegmentor:
    """YOLOv8分割器实现，支持实例分割和语义分割"""
    
    def __init__(self):
        """初始化分割器"""
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
        
        logger.info(f"初始化YOLO分割器，使用设备: {self.device}")
        logger.info(f"默认置信度阈值: {self.default_confidence}")
        logger.info(f"结果保存目录: {self.results_dir}")
        
    async def get_model_path(self, model_code: str) -> str:
        """获取模型路径
        
        Args:
            model_code: 模型代码,例如'yolov8n-seg'
            
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
        """加载分割模型"""
        try:
            # 获取模型路径
            model_path = await self.get_model_path(model_code)
            logger.info(f"正在加载分割模型: {model_path}")
            
            # 加载模型
            self.model = YOLO(model_path)
            self.model.to(self.device)
            
            # 设置模型参数
            self.model.conf = self.default_confidence
            self.model.iou = self.default_iou
            self.model.max_det = self.default_max_det
            
            # 验证模型是否是分割模型
            if not hasattr(self.model, 'names') or not hasattr(self.model, 'task') or self.model.task != 'segment':
                raise Exception(f"模型 {model_code} 不是分割模型")
            
            # 更新当前模型代码
            self.current_model_code = model_code
            
            logger.info(f"分割模型加载成功: {model_code}")
            
        except Exception as e:
            logger.error(f"分割模型加载失败: {str(e)}")
            raise ModelLoadException(f"分割模型加载失败: {str(e)}")
            
    def _get_color_by_class_id(self, class_id: int) -> Tuple[int, int, int]:
        """根据类别ID生成固定的颜色
        
        Args:
            class_id: 类别ID
            
        Returns:
            Tuple[int, int, int]: RGB颜色值
        """
        # 使用黄金比例法生成不同的色相值
        golden_ratio = 0.618033988749895
        hue = (class_id * golden_ratio) % 1.0
        
        # 转换HSV到RGB（固定饱和度和明度以获得鲜艳的颜色）
        rgb = tuple(round(x * 255) for x in colorsys.hsv_to_rgb(hue, 0.8, 0.95))
        return rgb

    async def _encode_result_image(
        self,
        image: np.ndarray,
        segmentation_results: List[Dict],
        return_image: bool = False
    ) -> Union[str, np.ndarray, None]:
        """将分割结果绘制到图片上"""
        try:
            # 复制图片以免修改原图
            result_image = image.copy()
            overlay = image.copy()
            
            h, w = image.shape[:2]
            
            # 创建透明覆盖层
            for seg_result in segmentation_results:
                # 获取分割掩码
                mask = seg_result.get("mask")
                if mask is None:
                    continue
                    
                # 解码base64掩码
                if isinstance(mask, str):
                    try:
                        mask_bytes = base64.b64decode(mask)
                        mask_np = np.frombuffer(mask_bytes, dtype=np.uint8)
                        mask = cv2.imdecode(mask_np, cv2.IMREAD_GRAYSCALE)
                        mask = cv2.resize(mask, (w, h))
                    except Exception as e:
                        logger.error(f"解码掩码失败: {str(e)}")
                        continue
                
                # 获取类别颜色
                class_id = seg_result.get("class_id", 0)
                color = self._get_color_by_class_id(class_id)
                
                # 为掩码区域应用颜色
                color_mask = np.zeros_like(image)
                color_mask[mask > 0] = color
                
                # 将掩码与原图混合
                alpha = 0.5  # 透明度
                cv2.addWeighted(color_mask, alpha, overlay, 1 - alpha, 0, overlay)
            
            # 使用PIL添加文本标签
            img_pil = Image.fromarray(cv2.cvtColor(overlay, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(img_pil)
            
            # 尝试加载字体
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
                    font = ImageFont.load_default()
                    
            except Exception as e:
                logger.warning(f"加载字体失败，使用默认字体: {str(e)}")
                font = ImageFont.load_default()
            
            # 绘制标签
            for seg_result in segmentation_results:
                bbox = seg_result.get("bbox")
                if not bbox:
                    continue
                    
                class_name = seg_result.get("class_name", "Unknown")
                confidence = seg_result.get("confidence", 0.0)
                
                # 绘制边界框
                x1, y1 = bbox["x1"], bbox["y1"]
                x2, y2 = bbox["x2"], bbox["y2"]
                
                # 选择颜色
                class_id = seg_result.get("class_id", 0)
                box_color = self._get_color_by_class_id(class_id)
                
                # 绘制矩形
                draw.rectangle([(x1, y1), (x2, y2)], outline=box_color, width=2)
                
                # 准备标签文本
                label = f"{class_name} {confidence:.2f}"
                
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
            logger.error(f"处理分割结果图片失败: {str(e)}")
            return None

    async def segment(self, image, config: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """执行分割
        
        Args:
            image: 输入图片
            config: 分割配置，包含以下可选参数：
                - confidence: 置信度阈值
                - iou: IoU阈值
                - classes: 需要分割的类别ID列表
                - roi: 感兴趣区域，格式为{x1, y1, x2, y2}，值为0-1的归一化坐标
                - imgsz: 输入图片大小
                - retina_masks: 是否使用精细的视网膜掩码 (True提供更精确的掩码)
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
            retina_masks = config.get('retina_masks', True)  # 默认使用精细掩码
            
            # 确保置信度和IoU阈值有效
            if conf is None:
                conf = self.default_confidence
            if iou is None:
                iou = self.default_iou
                
            logger.info(f"分割配置 - 置信度: {conf}, IoU: {iou}, 类别: {classes}, ROI: {roi}, 图片大小: {imgsz}, 精细掩码: {retina_masks}")
            
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
                classes=classes,
                retina_masks=retina_masks
            )
            
            # 处理分割结果
            segmentation_results = []
            for result in results:
                masks = result.masks
                if masks is None or len(masks) == 0:
                    continue
                    
                boxes = result.boxes
                
                # 处理每个实例
                for i, (mask, box) in enumerate(zip(masks, boxes)):
                    # 获取边界框信息
                    bbox = box.xyxy[0].cpu().numpy()
                    conf = float(box.conf[0])
                    cls = int(box.cls[0])
                    name = result.names[cls]
                    
                    # 获取分割掩码
                    # 将掩码转换为二值图像
                    mask_tensor = mask.data
                    binary_mask = mask_tensor.cpu().numpy()
                    
                    # 如果使用了ROI，需要调整坐标
                    if roi and original_shape:
                        h, w = original_shape
                        bbox[0] = bbox[0] / w * (roi['x2'] - roi['x1']) * w + roi['x1'] * w
                        bbox[1] = bbox[1] / h * (roi['y2'] - roi['y1']) * h + roi['y1'] * h
                        bbox[2] = bbox[2] / w * (roi['x2'] - roi['x1']) * w + roi['x1'] * w
                        bbox[3] = bbox[3] / h * (roi['y2'] - roi['y1']) * h + roi['y1'] * h
                        
                        # 调整掩码大小并应用偏移
                        mask_img = (binary_mask * 255).astype(np.uint8)
                        mask_img = cv2.resize(mask_img, (int((roi['x2'] - roi['x1']) * w), int((roi['y2'] - roi['y1']) * h)))
                        
                        # 创建完整大小的掩码
                        full_mask = np.zeros((h, w), dtype=np.uint8)
                        x_offset = int(roi['x1'] * w)
                        y_offset = int(roi['y1'] * h)
                        # 把调整后的掩码放到正确的位置
                        mask_h, mask_w = mask_img.shape
                        full_mask[y_offset:y_offset+mask_h, x_offset:x_offset+mask_w] = mask_img
                        binary_mask = full_mask
                    
                    # 将掩码编码为base64字符串以便于传输
                    _, buffer = cv2.imencode('.png', binary_mask.astype(np.uint8) * 255)
                    mask_base64 = base64.b64encode(buffer).decode('utf-8')
                    
                    # 计算面积 (像素数)
                    area = float(np.sum(binary_mask))
                    
                    segmentation_result = {
                        "bbox": {
                            "x1": float(bbox[0]),
                            "y1": float(bbox[1]),
                            "x2": float(bbox[2]),
                            "y2": float(bbox[3])
                        },
                        "confidence": conf,
                        "class_id": cls,
                        "class_name": name,
                        "area": area,
                        "mask": mask_base64
                    }
                    segmentation_results.append(segmentation_result)
            
            return segmentation_results
                    
        except Exception as e:
            logger.error(f"分割失败: {str(e)}")
            raise ProcessingException(f"分割失败: {str(e)}")

    async def _save_result_image(self, image: np.ndarray, segmentation_results: List[Dict], task_name: Optional[str] = None) -> str:
        """保存带有分割结果的图片"""
        try:
            # 生成带分割结果的图片
            logger.info("开始生成分割结果图片...")
            result_image = await self._encode_result_image(image, segmentation_results, return_image=True)
            if result_image is None:
                logger.error("生成分割结果图片失败")
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