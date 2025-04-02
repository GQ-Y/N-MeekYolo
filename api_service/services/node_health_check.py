"""节点健康检查服务"""
import asyncio
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from api_service.crud.node import NodeCRUD
from api_service.core.database import SessionLocal
from shared.utils.logger import setup_logger

# 配置日志
logger = setup_logger(__name__)

class NodeHealthChecker:
    def __init__(self, check_interval: int = 300):
        """
        初始化节点健康检查器
        :param check_interval: 检查间隔时间（秒）
        """
        self.check_interval = check_interval
        self.is_running = False
        self.check_count = 0

    async def start(self):
        """启动健康检查服务"""
        logger.info("节点健康检查服务启动")
        self.is_running = True
        while self.is_running:
            try:
                self.check_count += 1
                logger.info(f"开始第 {self.check_count} 次节点健康检查...")
                start_time = datetime.now()
                
                await self.check_nodes_health()
                
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                logger.info(f"第 {self.check_count} 次节点健康检查完成，耗时: {duration:.2f} 秒")
                
            except Exception as e:
                logger.error(f"节点健康检查失败: {str(e)}")
            
            logger.debug(f"等待 {self.check_interval} 秒后进行下一次检查...")
            await asyncio.sleep(self.check_interval)

    def stop(self):
        """停止健康检查服务"""
        logger.info("节点健康检查服务停止")
        self.is_running = False

    async def check_nodes_health(self):
        """执行节点健康检查"""
        db = SessionLocal()
        try:
            try:
                # 先检查是否有节点表
                db.execute("SELECT 1 FROM nodes LIMIT 1")
            except SQLAlchemyError:
                logger.debug("节点表不存在或为空，跳过健康检查")
                return

            # 获取当前在线节点数量
            online_count = db.query(NodeCRUD).filter_by(service_status="online").count()
            logger.info(f"当前在线节点数: {online_count}")

            # 检查节点健康状态
            before_check = datetime.now()
            NodeCRUD.check_nodes_health(db)
            after_check = datetime.now()

            # 获取更新后的在线节点数量
            new_online_count = db.query(NodeCRUD).filter_by(service_status="online").count()
            offline_count = online_count - new_online_count

            if offline_count > 0:
                logger.warning(f"发现 {offline_count} 个节点离线")
            else:
                logger.info("所有节点状态正常")

            logger.debug(f"健康检查耗时: {(after_check - before_check).total_seconds():.2f} 秒")

        except Exception as e:
            logger.error(f"节点健康检查出错: {str(e)}")
            raise
        finally:
            db.close()

# 创建健康检查器实例
health_checker = NodeHealthChecker()

# 启动健康检查服务的协程函数
async def start_health_checker():
    """启动节点健康检查服务"""
    await health_checker.start()

# 停止健康检查服务的函数
def stop_health_checker():
    """停止节点健康检查服务"""
    health_checker.stop() 