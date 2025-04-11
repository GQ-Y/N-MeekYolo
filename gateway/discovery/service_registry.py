"""
服务注册中心
"""
from typing import Dict, Optional, List
import asyncio
import aiohttp
from datetime import datetime
from shared.models.base import ServiceInfo
from core.config import settings
from shared.utils.logger import setup_logger
# 导入数据库会话、模型和异常
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import func, update
from core.models.admin import RegisteredService
from core.exceptions import GatewayException
from core.database import engine
from core.database import SessionLocal

logger = setup_logger(__name__)

# 创建一个独立的 SessionLocal 工厂供后台任务使用
# 注意：这假设 SessionLocal 在 core.database 中没有被显式导出
# 如果 core.database 导出了 SessionLocal，应该直接导入使用
# SessionLocal_BG = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# 更好的方式：直接从 core.database 导入 SessionLocal

class ServiceRegistry:
    """服务注册中心 (数据库持久化)"""
    
    def __init__(self):
        # self.services: Dict[str, ServiceInfo] = {} # 不再使用内存字典存储服务信息
        self.stats: Dict[str, Dict] = {} # 统计信息暂时保留在内存中
        self.is_running = False
        # 添加一个用于管理后台任务的锁，防止并发问题 (可选但推荐)
        self._health_check_lock = asyncio.Lock()
    
    # 修改：改为同步方法，添加 db 参数，操作数据库
    def register_service(self, service: ServiceInfo, db: Session) -> bool:
        """注册服务到数据库 (存在则更新)"""
        logger.info(f"尝试注册/更新服务到数据库: {service.name} ({service.url})")
        try:
            # 查找是否已存在
            existing_service = db.query(RegisteredService).filter(RegisteredService.name == service.name).first()
            
            now = datetime.now()

            if existing_service:
                # 更新现有记录
                logger.debug(f"服务 {service.name} 已存在，执行更新操作。")
                updated = False
                if existing_service.url != service.url:
                    existing_service.url = service.url
                    updated = True
                if existing_service.description != service.description:
                    existing_service.description = service.description
                    updated = True
                
                # 每次重新注册/更新时，重置状态为 unknown，强制重新检查
                if existing_service.status != RegisteredService.STATUS_UNKNOWN:
                    existing_service.status = RegisteredService.STATUS_UNKNOWN
                    existing_service.last_status_change = now
                    updated = True
                
                # 也可以考虑更新 last_check 时间戳？暂时不更新
                # existing_service.last_check = now 

                if updated:
                     logger.info(f"更新服务 {service.name} 的信息。")
                else:
                     logger.info(f"服务 {service.name} 信息无变化，仅确认注册。")
            else:
                # 创建新记录
                logger.debug(f"服务 {service.name} 不存在，创建新记录。")
                new_service_db = RegisteredService(
                    name=service.name,
                    url=service.url,
                    description=service.description,
                    status=RegisteredService.STATUS_UNKNOWN, # 初始状态为 unknown
                    created_at=now,
                    last_status_change=now
                )
                db.add(new_service_db)
                logger.info(f"服务 {service.name} 已添加到数据库会话。")
            
            db.commit() # 提交更改
            logger.info(f"服务 {service.name} 注册/更新成功。")
            return True
        except Exception as e:
            db.rollback() # 发生错误时回滚
            logger.error(f"注册服务 {service.name} 到数据库时失败: {str(e)}", exc_info=True)
            # 可以考虑抛出 GatewayException
            # raise GatewayException(f"注册服务 {service.name} 失败", code=500)
            return False
    
    # 修改：改为同步方法，添加 db 参数，操作数据库
    def deregister_service(self, service_name: str, db: Session) -> bool:
        """从数据库注销服务"""
        logger.info(f"尝试从数据库注销服务: {service_name}")
        try:
            service_to_delete = db.query(RegisteredService).filter(RegisteredService.name == service_name).first()
            
            if service_to_delete:
                db.delete(service_to_delete)
                db.commit()
                logger.info(f"成功从数据库注销服务: {service_name}")
                # 可选：同时移除内存中的统计信息
                if service_name in self.stats:
                    del self.stats[service_name]
                return True
            else:
                logger.warning(f"尝试注销的服务在数据库中不存在: {service_name}")
                return False
        except Exception as e:
            db.rollback()
            logger.error(f"从数据库注销服务 {service_name} 时失败: {str(e)}", exc_info=True)
            # raise GatewayException(f"注销服务 {service_name} 失败", code=500)
            return False
            
    # 修改：改为同步方法，添加 db 参数，从数据库查询
    def get_all_services(self, db: Session) -> List[Dict]:
        """获取数据库中所有服务的信息及内存中的统计数据"""
        logger.debug("尝试从数据库获取所有服务列表")
        try:
            services_db = db.query(RegisteredService).order_by(RegisteredService.name.asc()).all()
            logger.debug(f"从数据库查询到 {len(services_db)} 个服务。")
            
            services_list = []
            for service_db in services_db:
                # 获取内存中的服务统计信息
                stats = self.stats.get(service_db.name, {
                    "total_requests": 0,
                    "success_rate": 1.0,
                    "avg_response_time": 0.0
                })
                
                # 构建服务响应
                service_info = {
                    "name": service_db.name,
                    "url": service_db.url,
                    "status": service_db.status_name, # 使用 status_name 获取字符串状态
                    "uptime": None, # Uptime 逻辑需要重新考虑，数据库没有 started_at
                    "total_requests": stats["total_requests"],
                    "success_rate": stats["success_rate"],
                    "avg_response_time": stats["avg_response_time"]
                }
                services_list.append(service_info)
                
            logger.debug(f"成功构建服务列表，包含 {len(services_list)} 个服务。")
            return services_list
            
        except Exception as e:
            logger.error(f"从数据库获取服务列表时失败: {str(e)}", exc_info=True)
            raise GatewayException("获取服务列表失败", code=500) # 向上层抛出异常
    
    # 修改：改为同步方法，添加 db 参数，从数据库查询
    def get_service(self, service_name: str, db: Session) -> Optional[RegisteredService]:
        """从数据库获取单个服务信息 (返回 ORM 对象)"""
        logger.debug(f"尝试从数据库获取服务: {service_name}")
        try:
            service_db = db.query(RegisteredService).filter(RegisteredService.name == service_name).first()
            if service_db:
                logger.debug(f"在数据库中找到服务: {service_name}")
            else:
                logger.debug(f"在数据库中未找到服务: {service_name}")
            return service_db
        except Exception as e:
            logger.error(f"从数据库获取服务 {service_name} 时失败: {str(e)}", exc_info=True)
            raise GatewayException(f"获取服务 {service_name} 失败", code=500)
    
    async def get_service_stats(self, service_name: str) -> Dict:
        """获取服务统计信息 (保持内存存储)"""
        # TODO: 考虑将统计信息也持久化到数据库或 Redis
        return self.stats.get(service_name, {
            "total_requests": 0,
            "success_requests": 0,
            "failed_requests": 0,
            "avg_response_time": 0.0,
            "status": "unknown",
            "uptime": None
        })

    # 修改：discover_services 现在需要数据库会话
    async def discover_services(self, db: Session):
        """发现并检查数据库中已注册的服务，并更新数据库状态"""
        logger.debug("开始从数据库获取服务列表进行健康检查...")
        try:
            # 从数据库获取所有已注册的服务
            services_to_check = db.query(RegisteredService).all()
        except Exception as e:
            logger.error(f"健康检查：查询数据库服务列表失败: {e}", exc_info=True)
            return # 无法继续检查
            
        if not services_to_check:
            logger.debug("数据库中没有服务需要检查。")
            return
            
        logger.debug(f"准备检查 {len(services_to_check)} 个数据库中注册的服务...")
        
        # 准备批量更新的数据
        updates_to_commit = []
        now = datetime.now()
        health_check_timeout = getattr(settings.DISCOVERY, 'timeout', 5)
        
        # 使用 aiohttp session 进行异步检查
        async with aiohttp.ClientSession() as session:
            tasks = []
            for service_db in services_to_check:
                tasks.append(self._check_single_service(session, service_db, health_check_timeout))
            
            # 并发执行所有检查
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理检查结果并准备数据库更新
            for i, result in enumerate(results):
                service_db = services_to_check[i]
                new_status = RegisteredService.STATUS_UNKNOWN # 默认为 unknown
                error_message = None
                
                if isinstance(result, Exception):
                    new_status = RegisteredService.STATUS_UNHEALTHY
                    error_message = f"{result.__class__.__name__}: {str(result)}"
                    logger.warning(f"健康检查失败 (异常) for {service_db.name}: {error_message}")
                elif isinstance(result, int): # _check_single_service 返回状态码
                    if result == 200:
                        new_status = RegisteredService.STATUS_HEALTHY
                    else:
                        new_status = RegisteredService.STATUS_UNHEALTHY
                        error_message = f"HTTP Status {result}"
                        logger.warning(f"健康检查失败 (状态码) for {service_db.name}: {error_message}")
                else: # 未知结果
                     new_status = RegisteredService.STATUS_UNHEALTHY
                     error_message = f"未知检查结果: {result}"
                     logger.error(f"健康检查返回未知结果 for {service_db.name}: {result}")

                # 准备更新数据库记录
                update_info = {
                    'id': service_db.id,
                    'new_status': new_status,
                    'last_check': now
                }
                updates_to_commit.append(update_info)
        
        # 批量更新数据库状态
        if updates_to_commit:
            logger.debug(f"准备批量更新 {len(updates_to_commit)} 条服务状态到数据库...")
            try:
                for update_item in updates_to_commit:
                    # 判断状态是否真的改变，仅在改变时更新 last_status_change
                    service_record = db.query(RegisteredService).filter(RegisteredService.id == update_item['id']).first()
                    if service_record:
                        status_changed = service_record.status != update_item['new_status']
                        service_record.status = update_item['new_status']
                        service_record.last_check = update_item['last_check']
                        if status_changed:
                            service_record.last_status_change = now
                            logger.info(f"服务 {service_record.name} 状态变更为: {service_record.status_name}")
                db.commit()
                logger.debug("数据库服务状态批量更新完成。")
            except Exception as e:
                db.rollback()
                logger.error(f"健康检查：更新数据库服务状态失败: {e}", exc_info=True)

    async def _check_single_service(self, session: aiohttp.ClientSession, service: RegisteredService, timeout: int) -> int:
        """异步检查单个服务的健康状态，返回 HTTP 状态码或抛出异常"""
        url = service.url
        health_url = f"{url.rstrip('/')}/health"
        try:
            async with session.get(health_url, timeout=timeout) as response:
                # logger.debug(f"Health check for {service.name} at {health_url} returned {response.status}")
                return response.status
        except asyncio.TimeoutError:
            # logger.warning(f"Health check timed out for {service.name} at {health_url}")
            raise # 重新抛出 TimeoutError
        except aiohttp.ClientError as e:
            # logger.warning(f"Health check connection error for {service.name} at {health_url}: {e}")
            raise # 重新抛出 ClientError
        except Exception as e:
             # logger.error(f"Unexpected error during health check for {service.name} at {health_url}: {e}")
             raise # 重新抛出其他异常
    
    # 修改：start_health_check 需要管理数据库会话
    async def start_health_check(self):
        """启动后台健康检查循环 (使用独立数据库会话)"""
        if self.is_running:
            logger.warning("健康检查已在运行中。")
            return
            
        self.is_running = True
        logger.info("启动后台健康检查循环...")
        
        while self.is_running:
            async with self._health_check_lock: # 获取锁，确保只有一个检查在运行
                logger.debug("开始新一轮健康检查...")
                db: Optional[Session] = None
                try:
                    # 为本次检查创建新的数据库会话
                    db = SessionLocal()
                    await self.discover_services(db=db) # 传递会话
                    logger.debug("本轮健康检查完成。")
                except Exception as e:
                    logger.error(f"健康检查循环出错: {str(e)}", exc_info=True)
                finally:
                    if db:
                        db.close() # 确保关闭会话
                        logger.debug("健康检查数据库会话已关闭。")
            
            # 在锁之外进行 sleep
            if self.is_running: # 再次检查运行状态，避免停止后仍然 sleep
                interval = getattr(settings.DISCOVERY, 'interval', 60)
                logger.debug(f"健康检查暂停 {interval} 秒...")
                await asyncio.sleep(interval)
                
        logger.info("后台健康检查循环已停止。")
    
    # stop 方法保持不变
    async def stop(self):
        """停止服务"""
        logger.info("正在请求停止后台健康检查循环...")
        self.is_running = False
        # 可以考虑添加等待任务结束的逻辑
        # await asyncio.sleep(1) # 等待循环退出
        logger.info("后台健康检查循环应该很快会停止。")

# 创建全局实例
service_registry = ServiceRegistry() 