"""
视频源监控服务
"""
import asyncio
import cv2
from datetime import datetime
from sqlalchemy.orm import Session
from concurrent.futures import ThreadPoolExecutor
from api_service.models.database import Stream
from api_service.models.requests import StreamStatus
from api_service.services.database import SessionLocal
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class StreamMonitor:
    """视频源监控器"""
    
    def __init__(self):
        self.check_interval = 60  # 检查间隔60秒
        self.connect_timeout = 30  # 连接超时时间
        self.initial_delay = 5    # 添加初始延迟时间(秒)
        self.is_running = False
        self.task = None
        self.stats = {
            "total_checks": 0,
            "successful_reconnects": 0,
            "last_check_time": None
        }
        # 创建线程池
        self.thread_pool = ThreadPoolExecutor(max_workers=5)
    
    def _check_stream(self, url: str) -> bool:
        """在线程中执行的同步检查方法"""
        try:
            cap = cv2.VideoCapture(url)
            if not cap.isOpened():
                return False
            
            # 尝试读取多帧以确保连接稳定
            for _ in range(3):
                ret, _ = cap.read()
                if not ret:
                    cap.release()
                    return False
            
            cap.release()
            return True
        except Exception:
            return False

    async def check_stream_connection(self, url: str) -> bool:
        """异步检查视频源连接状态"""
        try:
            # 在线程池中执行耗时操作
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(self.thread_pool, self._check_stream, url)
        except Exception as e:
            logger.error(f"检查视频源连接失败: {url}, 错误: {str(e)}")
            return False
    
    async def update_stream_status(self, db: Session, stream: Stream, status: int):
        """更新视频源状态"""
        try:
            stream.status = status
            stream.updated_at = datetime.now()
            db.commit()
            logger.info(f"视频源 {stream.id} 状态更新为: {'在线' if status == StreamStatus.ONLINE else '离线'}")
        except Exception as e:
            db.rollback()
            logger.error(f"更新视频源状态失败: {str(e)}")
    
    async def monitor_streams(self):
        """监控视频源状态"""
        try:
            # 添加初始延迟,让API有时间看到初始状态
            logger.info(f"等待 {self.initial_delay} 秒后开始检查视频源...")
            await asyncio.sleep(self.initial_delay)
            
            while self.is_running:
                try:
                    check_start_time = datetime.now()
                    self.stats["last_check_time"] = check_start_time
                    self.stats["total_checks"] += 1
                    
                    db = SessionLocal()
                    try:
                        # 检查所有离线视频源
                        streams = db.query(Stream).filter(
                            Stream.status == StreamStatus.OFFLINE
                        ).all()
                        
                        if streams:
                            logger.info(f"开始第 {self.stats['total_checks']} 次检查，发现 {len(streams)} 个离线视频源")
                            
                            # 并发检查所有离线视频源
                            tasks = []
                            for stream in streams:
                                task = asyncio.create_task(self._check_single_stream(db, stream))
                                tasks.append(task)
                            
                            # 等待所有检查完成
                            await asyncio.gather(*tasks)
                            
                            check_duration = (datetime.now() - check_start_time).total_seconds()
                            logger.info(
                                f"第 {self.stats['total_checks']} 次检查完成:\n"
                                f"- 检查耗时: {check_duration:.2f} 秒\n"
                                f"- 本次检查视频源: {len(streams)} 个\n"
                                f"- 累计重连成功: {self.stats['successful_reconnects']} 次"
                            )
                    finally:
                        db.close()
                        
                except Exception as e:
                    logger.error(f"监控视频源失败: {str(e)}")
                
                # 等待下一次检查
                await asyncio.sleep(self.check_interval)
        except Exception as e:
            logger.error(f"监控任务异常退出: {str(e)}")
            self.is_running = False

    async def _check_single_stream(self, db: Session, stream: Stream):
        """检查单个视频源"""
        try:
            is_connected = await self.check_stream_connection(stream.url)
            if is_connected:
                await self.update_stream_status(db, stream, StreamStatus.ONLINE)
                self.stats["successful_reconnects"] += 1
                logger.info(f"视频源 {stream.id} ({stream.name}) 连接成功")
        except Exception as e:
            logger.error(f"检查视频源 {stream.id} 失败: {str(e)}")

    async def start(self):
        """启动监控服务"""
        if not self.is_running:
            self.is_running = True
            self.stats = {
                "total_checks": 0,
                "successful_reconnects": 0,
                "last_check_time": None
            }
            
            # 启动监控任务
            self.task = asyncio.create_task(self.monitor_streams())
            logger.info("视频源监控服务已启动")

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
            
            # 关闭线程池
            self.thread_pool.shutdown(wait=True)
            
            logger.info(
                f"视频源监控已停止。统计信息:\n"
                f"- 总检查次数: {self.stats['total_checks']}\n"
                f"- 累计重连成功: {self.stats['successful_reconnects']} 次"
            )
 