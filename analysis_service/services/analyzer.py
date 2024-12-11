"""
分析服务
处理图片、视频、流的分析逻辑
"""
import cv2
import numpy as np
import uuid
import os
import asyncio
import base64
from datetime import datetime
from fastapi import UploadFile
from typing import Dict, Any, List, Tuple
from shared.utils.logger import setup_logger
from analysis_service.core.config import settings
from analysis_service.core.detector import YOLODetector

logger = setup_logger(__name__)

class AnalyzerService:
    """分析服务"""
    
    def __init__(self):
        self.detector = YOLODetector()
        self.tasks = {}
        
        # 确保输出目录存在
        os.makedirs(settings.OUTPUT["save_dir"], exist_ok=True)
        os.makedirs(f"{settings.OUTPUT['save_dir']}/images", exist_ok=True)
        os.makedirs(f"{settings.OUTPUT['save_dir']}/videos", exist_ok=True)
        
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