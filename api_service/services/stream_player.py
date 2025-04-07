"""
视频流播放服务

负责将RTSP/RTMP流转换为HLS以便在浏览器中播放
"""
import os
import re
import uuid
import shutil
import asyncio
import logging
import subprocess
from typing import Dict, Optional, Tuple, List
from fastapi import HTTPException, Request
from sqlalchemy.orm import Session
from models.database import Stream
from shared.utils.logger import setup_logger
from core.config import settings
from datetime import datetime
from services.database import SessionLocal

logger = setup_logger(__name__)

# 全局变量，保存当前正在转换的流程
active_conversions: Dict[int, Dict] = {}

class StreamPlayerService:
    """流播放服务，负责将RTSP/RTMP流转换为HLS格式，供Web播放器使用"""
    
    def __init__(self):
        """初始化服务"""
        # 基本配置
        self.output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "hls")
        os.makedirs(self.output_dir, exist_ok=True)
        # 确保目录权限
        try:
            os.chmod(self.output_dir, 0o777)  # 确保目录有读写权限
        except Exception as e:
            logger.warning(f"设置HLS目录权限失败: {e}")
        
        # 清理可能存在的旧转换目录
        self._cleanup_old_conversions()
    
    def _cleanup_old_conversions(self):
        """清理可能存在的旧转换目录"""
        try:
            if os.path.exists(self.output_dir):
                for item in os.listdir(self.output_dir):
                    item_path = os.path.join(self.output_dir, item)
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                        logger.info(f"已清理旧转换目录: {item_path}")
        except Exception as e:
            logger.error(f"清理旧转换目录失败: {e}")
            
    async def get_playable_url(self, request: Request, db: Session, stream_id: int) -> Dict:
        """获取可播放的URL
        
        Args:
            request: HTTP请求对象，用于获取主机信息
            db: 数据库会话
            stream_id: 流ID
            
        Returns:
            Dict: 包含原URL和可播放URL的字典
        """
        # 获取流信息
        stream = db.query(Stream).filter(Stream.id == stream_id).first()
        if not stream:
            raise HTTPException(status_code=404, detail=f"流 {stream_id} 不存在")
            
        # 获取基础URL，用于构建完整播放URL
        base_server_url = self._get_base_url(request)
            
        # 检查URL类型
        url_type = self._get_url_type(stream.url)
        logger.info(f"流 {stream_id} ({stream.name}) URL类型: {url_type}, 地址: {stream.url}")
        
        # 不支持RTMP流，直接返回错误信息
        if url_type == "rtmp":
            logger.warning(f"流 {stream_id} 使用了不支持的RTMP协议: {stream.url}")
            return {
                "original_url": stream.url,
                "playable_url": "",
                "protocol": url_type,
                "converted": False,
                "error": "暂不支持RTMP流，请使用RTSP或HLS格式"
            }
            
        if url_type == "hls" or url_type == "http":
            # 已经是HLS或HTTP直接可播放的流，直接返回原URL
            logger.info(f"流 {stream_id} 已经是可播放格式: {url_type}")
            return {
                "original_url": stream.url,
                "playable_url": stream.url,
                "protocol": url_type,
                "converted": False
            }
        
        # 检查是否已经有活跃的转换任务
        if stream_id in active_conversions:
            conversion_info = active_conversions[stream_id]
            # 检查进程是否还活着
            if conversion_info["process"].poll() is None:
                logger.info(f"流 {stream_id} 已有转换任务运行中")
                # 构建完整URL
                full_url = f"{base_server_url}{conversion_info['hls_url']}"
                return {
                    "original_url": stream.url,
                    "playable_url": full_url,
                    "protocol": "hls",
                    "converted": True
                }
            else:
                # 进程已结束，移除记录
                logger.warning(f"流 {stream_id} 转换进程已结束，将重新启动")
                self._stop_conversion(stream_id)
        
        # 开始新的转换流程
        return await self._start_conversion(request, stream_id, stream.url)
    
    def _get_base_url(self, request: Request) -> str:
        """获取基础URL
        
        Args:
            request: HTTP请求对象
            
        Returns:
            str: 基础URL，如 http://localhost:8001
        """
        host = request.headers.get("host", "localhost:8001")
        scheme = request.headers.get("x-forwarded-proto", "http")
        return f"{scheme}://{host}"
    
    def _get_url_type(self, url: str) -> str:
        """获取URL的类型"""
        url = url.lower()
        if url.startswith("rtsp://"):
            return "rtsp"
        elif url.startswith("rtmp://"):
            return "rtmp"
        elif url.endswith(".m3u8") or "m3u8" in url:
            return "hls"
        elif url.startswith("http://") or url.startswith("https://"):
            return "http"
        else:
            return "unknown"
    
    async def _collect_process_output(self, process, max_lines: int = 100) -> List[str]:
        """收集进程的输出"""
        lines = []
        try:
            for _ in range(max_lines):
                line = await asyncio.get_event_loop().run_in_executor(
                    None, process.stderr.readline
                )
                if not line:
                    break
                line = line.strip()
                if line:
                    lines.append(line)
                    logger.debug(f"FFmpeg输出: {line}")
        except Exception as e:
            logger.error(f"读取FFmpeg输出时出错: {e}")
        return lines
    
    async def _start_conversion(self, request: Request, stream_id: int, url: str) -> Dict:
        """启动转换流程
        
        Args:
            request: HTTP请求对象，用于获取主机信息
            stream_id: 流ID
            url: 原始流URL
            
        Returns:
            Dict: 包含转换信息的字典
        """
        try:
            # 获取基础URL
            base_server_url = self._get_base_url(request)
            
            # 创建转换目录
            stream_output_dir = os.path.join(self.output_dir, f"stream_{stream_id}")
            if os.path.exists(stream_output_dir):
                shutil.rmtree(stream_output_dir)
            os.makedirs(stream_output_dir, exist_ok=True)
            # 确保目录权限
            os.chmod(stream_output_dir, 0o777)
            
            # 生成输出文件路径
            output_path = os.path.join(stream_output_dir, "index.m3u8")
            
            # 构建FFmpeg命令 - 使用简单可靠的转换命令，与成功的命令行参数保持一致
            cmd = [
                "ffmpeg",
                "-i", url,
                "-c:v", "h264",
                "-c:a", "aac",
                "-hls_time", "2",
                "-hls_list_size", "6",
                "-hls_flags", "delete_segments+append_list",
                "-f", "hls",
                output_path
            ]
            
            cmd_str = ' '.join(cmd)
            logger.info(f"启动流 {stream_id} 的转换: {cmd_str}")
            
            # 启动进程
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1  # 行缓冲
            )
            
            # 生成相对URL路径
            relative_url = f"/static/hls/stream_{stream_id}/index.m3u8"
            # 生成完整URL
            full_url = f"{base_server_url}{relative_url}"
            
            # 保存转换信息
            active_conversions[stream_id] = {
                "process": process,
                "output_dir": stream_output_dir,
                "hls_url": relative_url,
                "command": cmd_str
            }
            
            # 异步收集一些输出
            output_task = asyncio.create_task(self._collect_process_output(process))
            
            # 等待初始化完成（等待m3u8文件生成）
            wait_time = 30  # 增加等待时间到30秒
            logger.info(f"等待流 {stream_id} 的m3u8文件生成，最多等待 {wait_time} 秒")
            
            for i in range(wait_time):
                if os.path.exists(output_path):
                    # 读取m3u8文件内容，确认不是空文件
                    try:
                        with open(output_path, 'r') as f:
                            content = f.read().strip()
                            if content and "#EXTM3U" in content:
                                logger.info(f"流 {stream_id} 转换初始化完成，耗时 {i+1} 秒")
                                # 检查是否有ts文件生成
                                ts_files = [f for f in os.listdir(stream_output_dir) if f.endswith('.ts')]
                                if ts_files:
                                    logger.info(f"已生成 {len(ts_files)} 个ts分片文件")
                                    break
                                else:
                                    logger.warning("m3u8文件已生成，但尚未生成ts分片文件，继续等待")
                            else:
                                logger.warning(f"m3u8文件已创建但内容异常: {content}")
                    except Exception as e:
                        logger.error(f"读取m3u8文件时出错: {e}")
                
                # 检查进程是否还在运行
                if process.poll() is not None:
                    exit_code = process.poll()
                    stderr_output = process.stderr.read() if process.stderr else "无法获取错误输出"
                    logger.error(f"FFmpeg进程已退出，退出码: {exit_code}, 错误输出: {stderr_output}")
                    raise HTTPException(status_code=500, detail=f"视频流转换失败，FFmpeg错误码: {exit_code}")
                
                await asyncio.sleep(1)
            else:
                # 收集进程输出
                ffmpeg_output = await output_task
                error_msg = "\n".join(ffmpeg_output[-10:]) if ffmpeg_output else "无输出"
                
                # 打印调试信息
                logger.error(f"流 {stream_id} 转换初始化超时，FFmpeg输出: {error_msg}")
                
                # 尝试检查FFmpeg版本和支持的格式
                try:
                    version_info = subprocess.check_output(["ffmpeg", "-version"], universal_newlines=True)
                    logger.info(f"FFmpeg版本信息: {version_info.split(chr(10))[0]}")  # 使用chr(10)代替'\n'
                except Exception as e:
                    logger.error(f"获取FFmpeg版本失败: {e}")
                
                self._stop_conversion(stream_id)
                raise HTTPException(status_code=500, detail=f"视频流转换初始化超时，FFmpeg输出: {error_msg}")
            
            # 获取数据库会话并更新视频流状态为在线(1)
            db = SessionLocal()
            try:
                stream = db.query(Stream).filter(Stream.id == stream_id).first()
                if stream:
                    stream.status = 1  # 在线状态
                    stream.updated_at = datetime.now()
                    db.commit()
                    logger.info(f"视频流 {stream_id} 转换成功，已更新状态为在线")
            except Exception as e:
                db.rollback()
                logger.error(f"更新视频流 {stream_id} 状态失败: {str(e)}")
            finally:
                db.close()
            
            # 转换成功
            return {
                "original_url": url,
                "playable_url": full_url,
                "protocol": "hls",
                "converted": True
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"流 {stream_id} 转换失败: {str(e)}")
            # 清理资源
            self._stop_conversion(stream_id)
            raise HTTPException(status_code=500, detail=f"视频流转换失败: {str(e)}")
    
    def _stop_conversion(self, stream_id: int):
        """停止转换流程
        
        Args:
            stream_id: 流ID
        """
        if stream_id in active_conversions:
            conversion_info = active_conversions[stream_id]
            
            # 终止进程
            try:
                if conversion_info["process"].poll() is None:
                    logger.info(f"正在终止流 {stream_id} 的转换进程")
                    conversion_info["process"].terminate()
                    try:
                        conversion_info["process"].wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        logger.warning(f"进程未能在5秒内终止，尝试强制终止")
                        conversion_info["process"].kill()
                        conversion_info["process"].wait(timeout=5)
            except Exception as e:
                logger.error(f"终止流 {stream_id} 转换进程失败: {str(e)}")
            
            # 清理目录
            try:
                output_dir = conversion_info["output_dir"]
                if os.path.exists(output_dir):
                    shutil.rmtree(output_dir)
                    logger.info(f"已清理流 {stream_id} 的转换目录: {output_dir}")
            except Exception as e:
                logger.error(f"清理流 {stream_id} 转换目录失败: {str(e)}")
            
            # 移除记录
            del active_conversions[stream_id]
            logger.info(f"已停止流 {stream_id} 的转换")
    
    async def stop_all_conversions(self):
        """停止所有转换流程"""
        logger.info(f"停止所有转换流程，当前有 {len(active_conversions)} 个转换任务")
        for stream_id in list(active_conversions.keys()):
            self._stop_conversion(stream_id) 