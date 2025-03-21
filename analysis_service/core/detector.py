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
                x1, y1 = bbox[0], bbox[1]
                x2, y2 = bbox[2], bbox[3]
                
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
        """执行检测"""
        try:
            if self.model is None:
                # 如果模型未加载，使用请求中指定的模型代码
                model_code = self.current_model_code
                if not model_code:
                    raise Exception("No model code specified")
                await self.load_model(model_code)
            
            # 执行推理 - 修改这里的配置访问方式
            results = self.model(
                image,
                conf=settings.ANALYSIS.confidence,  # 使用点号访问
                iou=settings.ANALYSIS.iou,         # 使用点号访问
                max_det=settings.ANALYSIS.max_det  # 使用点号访问
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
                    
                    detections.append({
                        "bbox": bbox.tolist(),
                        "confidence": conf,
                        "class_id": cls,
                        "class_name": name
                    })
            
            return detections
            
        except Exception as e:
            logger.error(f"检测失败: {str(e)}")
            raise
            
    async def _send_callbacks(self, callback_urls: str, callback_data: Dict[str, Any]):
        """发送回调请求"""
        if not callback_urls:
            return
            
        try:
            # 转换为标准格式
            if isinstance(callback_data, dict) and "detections" in callback_data:
                image = None
                stream_url = callback_data.get("stream_url", "")
                task_id = callback_data.get("task_id", "")
                
                # 如果有原始图片数据，先解码
                if "image" in callback_data:
                    image = callback_data["image"]
                    if isinstance(image, np.ndarray):
                        logger.debug("成功获取原始图片数据")
                    else:
                        logger.warning("图片数据格式不正确")
                        image = None
                
                standard_data = await self._convert_to_standard_format(
                    callback_data["detections"],
                    image=image,
                    stream_url=stream_url,
                    task_id=task_id
                )
                callback_data = standard_data.to_dict()
            
            # 发送回调
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

    async def _convert_to_standard_format(self, detections: List[Dict], image: np.ndarray = None, stream_url: str = "", task_id: str = "") -> CallbackData:
        """转换为标准格式"""
        try:
            # 生成时间戳和文件名
            current_time = datetime.now()
            timestamp = int(current_time.timestamp())
            date_str = current_time.strftime("%Y%m%d")
            time_str = current_time.strftime("%Y%m%d%H%M%S")
            random_num = ''.join(random.choices('0123456789', k=6))
            
            # 生成文件名 - 使用task_id作为camera_id
            base_filename = f"{time_str}_{random_num}_{task_id}_{task_id}"  # 修改这里，使用task_id替代camera_id
            src_pic_name = f"{base_filename}_src.jpg"
            alarm_pic_name = f"{base_filename}_alarm.jpg"
            
            # 生成唯一数据ID (11位16进制)
            data_id = ''.join(random.choices('0123456789abcdef', k=11))
            
            # 获取图像尺寸
            if image is not None:
                height, width = image.shape[:2]
            else:
                height, width = 1080, 1920
            
            # 生成带目标框的结果图片
            result_image_base64 = ""
            result_image = None
            if image is not None and detections:
                try:
                    # 使用_encode_result_image方法生成带目标框的图片
                    result_image = await self._encode_result_image(image, detections, return_image=True)
                    if result_image is not None:
                        # 保存图片到本地
                        save_path = os.path.join(settings.STORAGE.base_dir, "picture", date_str)
                        os.makedirs(save_path, exist_ok=True)
                        alarm_pic_path = os.path.join(save_path, alarm_pic_name)
                        cv2.imwrite(alarm_pic_path, result_image)
                        logger.info(f"已保存结果图片到: {alarm_pic_path}")
                        
                        # 生成base64
                        encode_params = [cv2.IMWRITE_JPEG_QUALITY, 95]
                        _, buffer = cv2.imencode('.jpg', result_image, encode_params)
                        if buffer is not None:
                            result_image_base64 = base64.b64encode(buffer).decode('utf-8')
                            logger.debug(f"成功生成结果图片base64，长度: {len(result_image_base64)}")
                except Exception as e:
                    logger.error(f"生成或保存结果图片失败: {str(e)}")
            
            # 构造检测结果数据
            result_data = {
                'classId': 0,  # 默认类别ID，不再使用第一个目标的类别
                'score': 0.0,  # 默认得分，不再使用第一个目标的得分
                'objectList': []
            }
            
            # 处理检测结果 - 返回所有检测到的目标
            if detections:
                # 遍历所有检测结果
                for det in detections:
                    confidence = det.get('confidence', 0)
                    class_id = det.get('class_id', 0)
                    class_name = det.get('class_name', '')
                    
                    # 转换检测框格式
                    box = det['bbox']
                    obj = {
                        'classId': class_id,
                        'className': class_name,  # 类别名称
                        'score': confidence,  # 置信度得分
                        'scoreList': [confidence],  # 得分列表
                        'rect': {
                            'x': int(box[0]),
                            'y': int(box[1]),
                            'width': int(box[2] - box[0]),
                            'height': int(box[3] - box[1])
                        },
                        'polygonList': [],
                        'multiPointList': []
                    }
                    result_data['objectList'].append(obj)
            
            # 获取任务信息和模型信息
            device_name = ""
            algorithm_name = self.current_model_code or ""
            algorithm_name_en = ""
            camera_group = "全部"
            
            try:
                # 修改数据库会话的获取方式
                db = get_db()
                db_session = next(db)
                task_info = task_crud.get_task(db_session, task_id)
                
                if task_info:
                    # 获取设备信息
                    if hasattr(task_info, 'stream') and task_info.stream:
                        device_name = task_info.stream.name or ""
                        stream_url = task_info.stream.url or stream_url
                        if hasattr(task_info.stream, 'group'):
                            camera_group = f"全部,{task_info.stream.group}"
                    
                    # 获取算法信息
                    if hasattr(task_info, 'model') and task_info.model:
                        algorithm_name = task_info.model.name or algorithm_name
                        algorithm_name_en = task_info.model.code or ""
                
                logger.info(f"获取到任务信息 - 设备: {device_name}, 算法: {algorithm_name}")
                
            except Exception as e:
                logger.error(f"获取任务信息失败: {str(e)}")
            
            # 构造文件路径
            picture = f"picture/{date_str}/{alarm_pic_name}"
            src = f"originPicture/{date_str}/{src_pic_name}"
            alarm = picture
            result = f"resultJson/{date_str}/{base_filename}_result.json"
            
            # 构造URL
            server_uuid = "3f16a3b113234807b81f6f8d0f268232"  # 从配置中获取
            src_url = f"http://192.168.110.183:8081/files/{src}?serverUUID={server_uuid}"
            alarm_url = f"http://192.168.110.183:8081/files/{picture}"
            
            # 创建回调数据
            callback_data = CallbackData(
                camera_device_type=1,
                camera_device_stream_url=stream_url,
                camera_device_status=1,
                camera_device_group=camera_group,
                camera_device_gps="",
                camera_device_id=task_id,
                camera_device_name=device_name,
                algorithm_id=task_id,
                algorithm_name=algorithm_name,
                algorithm_name_en=algorithm_name_en,
                data_id=data_id,
                parameter={"roiList": ["POLYGON((0.08506 0.01411,0.98324 0.02016,0.92994 0.80645,0.12702 0.83871))"]},
                picture=picture,
                src_url=src_url,
                alarm_url=alarm_url,
                task_id=task_id,
                camera_id=task_id,  # 使用task_id作为camera_id
                camera_url=stream_url,
                camera_name=device_name,
                timestamp=timestamp,
                image_width=width,
                image_height=height,
                src_pic_data="",
                src_pic_name=src_pic_name,
                alarm_pic_name=alarm_pic_name,
                src=src,
                alarm=alarm,
                alarm_pic_data=result_image_base64,
                other="",
                result=result,
                extra_info=[],
                result_data=result_data,
                degree=3
            )
            
            return callback_data
            
        except Exception as e:
            logger.error(f"转换标准格式失败: {str(e)}")
            raise

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
        model_code: str,
        callback_urls: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        analyze_interval: int = 1,
        alarm_interval: int = 60,
        random_interval: Tuple[int, int] = (0, 0),
        confidence_threshold: float = 0.8,
        push_interval: int = 5
    ):
        """启动流分析任务"""
        cap = None  # 初始化cap变量
        try:
            logger.info(f"Starting stream analysis task: {task_id}")
            logger.info(f"Model code: {model_code}")
            logger.info(f"Stream URL: {stream_url}")
            
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
            
            # 初始化时间记录 - 使用当前时间初始化
            current_time = time.time()
            last_analyze_time = current_time
            last_alarm_time = current_time
            last_push_time = current_time
            
            while not self.stop_flags.get(task_id, False):
                current_time = time.time()
                
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
                    detections = await self.detect(frame)
                    
                    # 过滤低置信度目标
                    detections = [d for d in detections if d["confidence"] >= confidence_threshold]
                    
                    if detections:
                        # 检查报警间隔
                        if current_time - last_alarm_time >= alarm_interval:
                            last_alarm_time = current_time
                            
                            # 检查推送间隔
                            if current_time - last_push_time >= push_interval:
                                last_push_time = current_time
                                
                                # 发送回调
                                await self._send_callbacks(callback_urls, {
                                    "task_id": task_id,
                                    "parent_task_id": parent_task_id,
                                    "detections": detections,
                                    "stream_url": stream_url,
                                    "image": frame,  # 添加原始图片数据
                                    "timestamp": current_time
                                })
                
                except Exception as e:
                    logger.error(f"Frame processing error: {str(e)}")
                    continue
                
                last_analyze_time = current_time
                await asyncio.sleep(0.01)
                
        except Exception as e:
            logger.error(f"Stream analysis failed: {str(e)}")
            raise
            
        finally:
            if cap is not None:  # 检查cap是否已初始化
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
