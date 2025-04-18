"""
分析服务
"""
import httpx
import uuid
from typing import List, Optional, Dict, Any
from core.config import settings
from shared.utils.logger import setup_logger
from crud.node import NodeCRUD
from core.database import SessionLocal

logger = setup_logger(__name__)

class AnalysisService:
    """分析服务"""
    
    def __init__(self):
        """初始化分析服务"""
        # 不再使用默认URL，完全依赖动态节点选择
        logger.info("初始化分析服务，将使用动态节点选择")
    
    def _get_api_url(self, path: str) -> str:
        """获取完整的API URL - 已废弃，保留仅用于兼容"""
        logger.warning("_get_api_url方法已废弃，应直接使用完整URL")
        return f"{path}"
    
    async def analyze_image(
        self,
        model_code: str,
        image_urls: List[str],
        callback_url: Optional[str] = None,
        is_base64: bool = False
    ) -> tuple:
        """图片分析
        
        注意：此方法已被弃用，仅保留用于向后兼容。
        请使用动态节点选择的方式处理图片分析。
        """
        logger.warning("analyze_image方法已弃用，请改用动态节点选择方式")
        
        # 为这个特定子任务选择一个节点
        node_id = None
        node_url = None
        
        # 获取数据库会话
        from core.database import SessionLocal
        db = SessionLocal()
        try:
            # 选择一个在线的分析服务节点
            node = NodeCRUD.get_available_node(db)
            if node:
                node_id = node.id
                node_url = f"http://{node.ip}:{node.port}/api/v1/analyze/image"
                # 更新节点任务计数
                node.image_task_count += 1
                db.commit()
            else:
                raise ValueError("未找到可用的分析服务节点")
        finally:
            db.close()
        
        task_id = str(uuid.uuid4())
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    node_url,
                    json={
                        "task_id": task_id,
                        "model_code": model_code,
                        "image_urls": image_urls,
                        "callback_url": callback_url,
                        "is_base64": is_base64,
                        "node_id": node_id
                    }
                )
                response.raise_for_status()
                
            return task_id, node_id
        except Exception as e:
            # 如果失败，减少节点任务计数
            self._decrease_node_image_task_count(node_id)
            raise
    
    async def analyze_video(
        self,
        model_code: str,
        video_url: str,
        callback_url: Optional[str] = None
    ) -> tuple:
        """视频分析
        
        注意：此方法已被弃用，仅保留用于向后兼容。
        请使用动态节点选择的方式处理视频分析。
        """
        logger.warning("analyze_video方法已弃用，请改用动态节点选择方式")
        
        # 为这个特定子任务选择一个节点
        node_id = None
        node_url = None
        
        # 获取数据库会话
        from core.database import SessionLocal
        db = SessionLocal()
        try:
            # 选择一个在线的分析服务节点
            node = NodeCRUD.get_available_node(db)
            if node:
                node_id = node.id
                node_url = f"http://{node.ip}:{node.port}/api/v1/analyze/video"
                # 更新节点任务计数
                node.video_task_count += 1
                db.commit()
            else:
                raise ValueError("未找到可用的分析服务节点")
        finally:
            db.close()
        
        task_id = str(uuid.uuid4())
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    node_url,
                    json={
                        "task_id": task_id,
                        "model_code": model_code,
                        "video_url": video_url,
                        "callback_url": callback_url,
                        "node_id": node_id
                    }
                )
                response.raise_for_status()
                
            return task_id, node_id
        except Exception as e:
            # 如果失败，减少节点任务计数
            self._decrease_node_video_task_count(node_id)
            raise
    
    async def analyze_stream(
        self,
        model_code: str,
        stream_url: str,
        task_name: str,
        callback_urls: str = None,
        callback_url: str = None,
        enable_callback: bool = False,
        save_result: bool = True,
        config: dict = None,
        analysis_task_id: str = None,
        analysis_type: str = "detection"
    ) -> Optional[tuple]:
        """分析视频流
        
        Args:
            model_code: 模型代码
            stream_url: 流URL
            task_name: 任务名称
            callback_urls: 回调地址，多个用逗号分隔
            callback_url: 单独的回调URL，优先级高于callback_urls
            enable_callback: 是否启用用户回调
            save_result: 是否保存结果
            config: 分析配置
            analysis_task_id: 分析任务ID，如果不提供将自动生成
            analysis_type: 分析类型，可选值：detection, segmentation, tracking, counting
            
        Returns:
            (task_id, node_id): 任务ID和节点ID组成的元组
        """
        # 为这个特定子任务选择一个节点
        from crud.node import NodeCRUD
        from core.database import SessionLocal
        from models.database import Node
        
        # 获取数据库会话
        node_id = None  # 用于保存节点ID
        node_ip = None
        node_port = None
        request_url = None
        db = SessionLocal()
        try:
            # 为这个特定子任务选择一个在线的分析服务节点
            node = NodeCRUD.get_available_node(db)
            if node:
                # 保存节点信息，但不立即增加计数
                node_id = node.id
                node_ip = node.ip
                node_port = node.port
                request_url = f"http://{node_ip}:{node_port}/api/v1/analyze/stream"
                logger.info(f"为子任务选择节点: {node_id} ({node_ip}:{node_port})")
            else:
                logger.error("未找到可用的分析服务节点，任务无法启动")
                return None, None
                
        finally:
            db.close()
        
        # 如果没有找到节点ID，返回错误
        if node_id is None:
            logger.error("节点选择失败，任务无法启动")
            return None, None
        
        # 构建系统回调URL
        system_callback_url = callback_url
        if not system_callback_url:
            # 使用配置中的API服务URL创建系统回调
            api_host = settings.SERVICE.host
            api_port = settings.SERVICE.port
            system_callback_url = f"http://{api_host}:{api_port}/api/v1/callback"
            logger.info(f"使用系统回调URL: {system_callback_url}")
            
        # 如果有单独的回调URL，添加到回调列表
        combined_callback_urls = callback_urls or ""
        if callback_url and callback_url not in combined_callback_urls:
            if combined_callback_urls:
                combined_callback_urls = f"{combined_callback_urls},{callback_url}"
            else:
                combined_callback_urls = callback_url
        
        # 构建请求参数
        request_data = {
            "model_code": model_code,
            "stream_url": stream_url,
            "task_name": task_name,
            "callback_urls": combined_callback_urls,
            "callback_url": system_callback_url,
            "enable_callback": enable_callback,
            "save_result": save_result,
            "config": config or {},
            "analysis_type": analysis_type,
            "task_id": analysis_task_id,
            "node_id": node_id
        }

        logger.info(f"准备向分析服务发送请求: URL={request_url}")
        logger.info(f"请求参数: 任务={task_name}, 模型={model_code}, 流={stream_url}")
                
        try:
            # 使用较短的超时时间（10秒），避免长时间等待不响应的节点
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    request_url,
                    json=request_data
                )
                
                status_code = response.status_code
                logger.info(f"分析服务响应状态码: {status_code}")
                
                if status_code != 200:
                    logger.error(f"分析服务响应错误: {response.text}")
                    response.raise_for_status()
                
                data = response.json()
                logger.info(f"分析服务响应数据: {data}")
                
                task_id = data.get("data", {}).get("task_id")
                logger.info(f"获取到分析任务ID: {task_id}")
                
                # 请求成功，现在才增加节点任务计数
                db = SessionLocal()
                try:
                    node = db.query(Node).filter(Node.id == node_id).first()
                    if node:
                        node.stream_task_count += 1
                        db.commit()
                        logger.info(f"节点 {node_id} 任务计数+1")
                finally:
                    db.close()
                
                return task_id, node_id
                
        except httpx.ReadTimeout as e:
            # 专门处理连接超时异常
            logger.error(f"节点 {node_id} ({node_ip}:{node_port}) 连接超时: {str(e)}")
            # 修改节点状态为离线
            try:
                db = SessionLocal()
                node = db.query(Node).filter(Node.id == node_id).first()
                if node:
                    node.service_status = "offline"
                    db.commit()
                    logger.warning(f"已将节点 {node_id} 标记为离线状态")
            except Exception as ex:
                logger.error(f"更新节点状态失败: {str(ex)}")
            finally:
                db.close()
            # 返回None表示任务启动失败，子任务状态将保持为0（未启动）
            return None, None
        except Exception as e:
            logger.error(f"向分析服务发送请求失败: {str(e)}", exc_info=True)
            # 请求失败，不修改节点任务计数
            # 返回None表示任务启动失败，子任务状态将保持为0（未启动）
            return None, None
            
    def _decrease_node_task_count(self, node_id: int):
        """减少节点任务计数"""
        if not node_id:
            logger.warning("尝试减少节点计数但节点ID为空")
            return
        
        try:
            from core.database import SessionLocal
            db = SessionLocal()
            try:
                # 查询节点
                from models.database import Node
                node = db.query(Node).filter(Node.id == node_id).first()
                if node:
                    if node.stream_task_count > 0:
                        node.stream_task_count -= 1
                        db.commit()
                        logger.info(f"节点 {node_id} 任务计数-1")
                    else:
                        logger.warning(f"节点 {node_id} 的任务计数已为0，无法减少")
                else:
                    logger.warning(f"找不到节点 {node_id}，无法减少任务计数")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"减少节点 {node_id} 任务计数失败: {str(e)}")
    
    async def stop_task(self, task_id: str, node_id: int = None):
        """停止分析任务
        
        Args:
            task_id: 分析任务ID
            node_id: 节点ID，如果提供则直接使用该节点停止任务
        """
        try:
            # 如果没有提供node_id，尝试从数据库中查找
            if not node_id:
                from core.database import SessionLocal
                from models.database import SubTask
                
                db = SessionLocal()
                try:
                    # 查找与此分析任务关联的子任务
                    subtask = db.query(SubTask).filter(SubTask.analysis_task_id == task_id).first()
                    if subtask and subtask.node_id:
                        node_id = subtask.node_id
                        logger.info(f"找到任务 {task_id} 关联的节点ID: {node_id}")
                finally:
                    db.close()
                
            # 如果提供了node_id或成功查找到了node_id，使用该节点
            if node_id:
                # 查询节点信息
                from core.database import SessionLocal
                from models.database import Node
                
                db = SessionLocal()
                try:
                    node = db.query(Node).filter(Node.id == node_id).first()
                    if node:
                        stop_url = f"http://{node.ip}:{node.port}/api/v1/analyze/task/stop"
                        logger.info(f"使用节点 {node_id} 停止任务 {task_id}")
                    else:
                        logger.error(f"找不到节点 {node_id}，无法停止任务 {task_id}")
                        raise ValueError(f"找不到节点 {node_id}")
                finally:
                    db.close()
            else:
                logger.error(f"无法找到任务 {task_id} 关联的节点，无法停止任务")
                raise ValueError(f"无法找到任务 {task_id} 关联的节点")
            
            request_data = {"task_id": task_id}
            
            logger.info(f"发送停止请求: task_id={task_id}, URL={stop_url}")
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    stop_url,
                    json=request_data
                )
                
                if response.status_code != 200:
                    logger.error(f"停止任务请求失败: {response.status_code}")
                    response.raise_for_status()
                
                response_data = response.json()
                logger.info(f"任务 {task_id} 已停止")
                
                # 如果提供了节点ID，减少节点任务计数
                if node_id:
                    self._decrease_node_task_count(node_id)
                
                return response_data
        except Exception as e:
            logger.error(f"停止任务 {task_id} 失败: {str(e)}")
            raise 

    def _decrease_node_image_task_count(self, node_id: int):
        """减少节点图片任务计数"""
        try:
            from core.database import SessionLocal
            db = SessionLocal()
            try:
                # 查询节点
                from models.database import Node
                node = db.query(Node).filter(Node.id == node_id).first()
                if node and node.image_task_count > 0:
                    node.image_task_count -= 1
                    db.commit()
                    logger.info(f"节点 {node_id} 图片任务计数-1")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"减少节点 {node_id} 图片任务计数失败")
        
    def _decrease_node_video_task_count(self, node_id: int):
        """减少节点视频任务计数"""
        try:
            from core.database import SessionLocal
            db = SessionLocal()
            try:
                # 查询节点
                from models.database import Node
                node = db.query(Node).filter(Node.id == node_id).first()
                if node and node.video_task_count > 0:
                    node.video_task_count -= 1
                    db.commit()
                    logger.info(f"节点 {node_id} 视频任务计数-1")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"减少节点 {node_id} 视频任务计数失败") 