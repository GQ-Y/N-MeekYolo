"""
视频源监控服务
"""
import asyncio
import cv2
from datetime import datetime
from sqlalchemy.orm import Session
from typing import List, Dict
import aiohttp
from api_service.models.database import Stream
from api_service.models.requests import StreamStatus
from api_service.services.database import SessionLocal
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class StreamMonitor:
    """视频源监控器"""
    
    def __init__(self):
        self.check_interval = 60  # 10分钟
        self.is_running = False
        self.task = None
        # 添加统计信息
        self.stats = {
            "total_checks": 0,
            "total_streams_checked": 0,
            "successful_reconnects": 0,
            "failed_reconnects": 0,
            "last_check_time": None,
            "last_check_duration": 0
        }
    
    async def check_stream_connection(self, url: str) -> bool:
        """检查视频源连接状态"""
        try:
            start_time = datetime.now()
            cap = cv2.VideoCapture(url)
            if not cap.isOpened():
                return False
                
            ret, _ = cap.read()
            cap.release()
            
            check_duration = (datetime.now() - start_time).total_seconds()
            logger.debug(f"Stream connection check took {check_duration:.2f} seconds")
            
            return ret
            
        except Exception as e:
            logger.error(f"Check stream connection failed: {url}, error: {str(e)}")
            return False
    
    async def update_stream_status(self, db: Session, stream: Stream, status: StreamStatus, error_message: str = None):
        """更新视频源状态"""
        try:
            stream.status = status
            stream.error_message = error_message
            stream.updated_at = datetime.now()
            db.commit()
            logger.info(f"Updated stream {stream.id} status to {status}")
            
        except Exception as e:
            db.rollback()
            logger.error(f"Update stream status failed: {str(e)}")
    
    def get_monitor_stats(self) -> Dict:
        """获取监控统计信息"""
        return {
            **self.stats,
            "is_running": self.is_running,
            "check_interval": self.check_interval,
            "uptime": (datetime.now() - self.stats["start_time"]).total_seconds() if self.stats.get("start_time") else 0
        }
    
    async def monitor_streams(self):
        """监控视频源状态"""
        self.stats["start_time"] = datetime.now()
        
        while self.is_running:
            try:
                check_start_time = datetime.now()
                self.stats["last_check_time"] = check_start_time
                self.stats["total_checks"] += 1
                
                db = SessionLocal()
                # 获取需要检查的视频源
                streams = db.query(Stream).filter(
                    Stream.status.in_([StreamStatus.ERROR, StreamStatus.DISCONNECTED])
                ).all()
                
                total_streams = len(streams)
                self.stats["total_streams_checked"] += total_streams
                
                logger.info(f"开始第 {self.stats['total_checks']} 次检查，发现 {total_streams} 个需要检查的视频源")
                
                successful = 0
                failed = 0
                
                for stream in streams:
                    try:
                        logger.info(f"正在检查视频源 {stream.id}: {stream.url}")
                        
                        # 检查连接状态
                        is_connected = await self.check_stream_connection(stream.url)
                        
                        if is_connected:
                            # 更新为在线状态
                            await self.update_stream_status(
                                db,
                                stream,
                                StreamStatus.ACTIVE
                            )
                            successful += 1
                            self.stats["successful_reconnects"] += 1
                        else:
                            # 更新错误信息
                            await self.update_stream_status(
                                db,
                                stream,
                                StreamStatus.ERROR,
                                "无法连接到视频源"
                            )
                            failed += 1
                            self.stats["failed_reconnects"] += 1
                            
                    except Exception as e:
                        logger.error(f"监控视频源 {stream.id} 失败: {str(e)}")
                        failed += 1
                        
                check_duration = (datetime.now() - check_start_time).total_seconds()
                self.stats["last_check_duration"] = check_duration
                
                # 打印本次检查的统计信息
                logger.info(
                    f"第 {self.stats['total_checks']} 次检查完成，耗时 {check_duration:.2f} 秒:\n"
                    f"- 检查的视频源总数: {total_streams}\n"
                    f"- 本次成功重连: {successful}\n"
                    f"- 本次重连失败: {failed}\n"
                    f"- 累计成功重连: {self.stats['successful_reconnects']}\n"
                    f"- 累计重连失败: {self.stats['failed_reconnects']}\n"
                    f"- 平均检查时间: {self.stats['last_check_duration'] / max(1, total_streams):.2f} 秒/个"
                )
                
                db.close()
                
            except Exception as e:
                logger.error(f"监控视频源失败: {str(e)}")
                
            finally:
                # 等待下一次检查
                await asyncio.sleep(self.check_interval)
    
    async def start(self):
        """启动监控"""
        if not self.is_running:
            self.is_running = True
            self.stats = {
                "total_checks": 0,
                "total_streams_checked": 0,
                "successful_reconnects": 0,
                "failed_reconnects": 0,
                "last_check_time": None,
                "last_check_duration": 0,
                "start_time": datetime.now()
            }
            self.task = asyncio.create_task(self.monitor_streams())
            logger.info("视频源监控已启动")
    
    async def stop(self):
        """停止监控"""
        if self.is_running:
            self.is_running = False
            if self.task:
                self.task.cancel()
                try:
                    await self.task
                except asyncio.CancelledError:
                    pass
                
            # 打印最终统计信息
            uptime = (datetime.now() - self.stats["start_time"]).total_seconds()
            logger.info(
                f"视频源监控已停止。最终统计信息:\n"
                f"- 总运行时间: {uptime:.2f} 秒\n"
                f"- 总检查次数: {self.stats['total_checks']}\n"
                f"- 检查的视频源总数: {self.stats['total_streams_checked']}\n"
                f"- 累计成功重连: {self.stats['successful_reconnects']}\n"
                f"- 累计重连失败: {self.stats['failed_reconnects']}\n"
                f"- 成功率: {(self.stats['successful_reconnects'] / max(1, self.stats['total_streams_checked']) * 100):.2f}%"
            )
 