"""
分析服务
"""
import httpx
import uuid
import json
import time
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
        save_images: bool = False,
        analysis_interval: int = 1,
        config: dict = None,
        analysis_task_id: str = None,
        analysis_type: str = "detection",
        specified_node_id: int = None
    ) -> Optional[tuple]:
        """分析视频流
        
        Args:
            model_code: 模型代码
            stream_url: 流URL
            task_name: 任务名称
            callback_urls: 回调地址，多个用逗号分隔
            callback_url: 单独的回调URL，优先级高于callback_urls
            enable_callback: 是否启用用户回调
            save_result: 是否保存结果数据
            save_images: 是否保存结果图片
            analysis_interval: 分析间隔(秒)
            config: 分析配置
            analysis_task_id: 分析任务ID，如果不提供将自动生成
            analysis_type: 分析类型，可选值：detection, segmentation, tracking, counting
            specified_node_id: 指定节点ID，如果提供则优先使用该节点
            
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
            # 如果指定了节点ID，则优先尝试使用该节点
            if specified_node_id:
                node = db.query(Node).filter(
                    Node.id == specified_node_id,
                    Node.service_status == "online",
                    Node.is_active == True
                ).first()
                
                if node:
                    # 保存节点信息
                    node_id = node.id
                    node_ip = node.ip
                    node_port = node.port
                    request_url = f"http://{node_ip}:{node_port}/api/v1/analyze/stream"
                    logger.info(f"使用指定节点: {node_id} ({node_ip}:{node_port})")
                else:
                    logger.warning(f"指定节点 {specified_node_id} 不可用，将尝试自动选择节点")
                    # 继续执行自动节点选择
            
            # 如果没有指定节点或指定节点不可用，则自动选择节点
            if not node_id:
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
        
        # 构建请求参数，包含新字段
        request_data = {
            "model_code": model_code,
            "stream_url": stream_url,
            "task_name": task_name,
            "callback_urls": combined_callback_urls,
            "callback_url": system_callback_url,
            "enable_callback": enable_callback,
            "save_result": save_result,
            "save_images": save_images,
            "analysis_interval": analysis_interval,
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
            # 如果没有提供node_id，尝试从数据库中查找所有关联子任务
            if not node_id:
                from core.database import SessionLocal
                from models.database import SubTask, MQTTNode, Task
                
                # 记录找到的节点和子任务
                http_node_subtasks = []  # 存储(subtask, node_id)
                mqtt_node_subtasks = []  # 存储(subtask, mqtt_node, mqtt_node_id)
                
                db = SessionLocal()
                try:
                    # 方法1: 通过analysis_task_id查找 - 处理直接使用analysis_task_id的情况
                    subtasks = db.query(SubTask).filter(SubTask.analysis_task_id == task_id).all()
                    
                    # 方法2: 通过任务ID查询所有子任务 - 处理停止整个主任务的情况
                    if not subtasks and task_id.isdigit():
                        # 尝试将task_id作为主任务ID查询
                        task = db.query(Task).filter(Task.id == int(task_id)).first()
                        if task:
                            logger.info(f"通过主任务ID {task_id} 查找所有子任务")
                            subtasks = task.sub_tasks
                    
                    if subtasks:
                        logger.info(f"找到与任务 {task_id} 关联的 {len(subtasks)} 个子任务")
                        
                        # 按节点类型分类子任务
                        for subtask in subtasks:
                            if subtask.status == 1:  # 只处理运行中的子任务
                                if subtask.node_id:
                                    # HTTP节点子任务
                                    http_node_subtasks.append((subtask, subtask.node_id))
                                    logger.info(f"子任务 {subtask.id} 运行在HTTP节点 {subtask.node_id}")
                                
                                elif subtask.mqtt_node_id:
                                    # MQTT节点子任务
                                    mqtt_node = db.query(MQTTNode).filter(MQTTNode.id == subtask.mqtt_node_id).first()
                                    if mqtt_node:
                                        mqtt_node_subtasks.append((subtask, mqtt_node, subtask.mqtt_node_id))
                                        logger.info(f"子任务 {subtask.id} 运行在MQTT节点 {mqtt_node.mac_address}")
                                    else:
                                        logger.warning(f"找不到子任务 {subtask.id} 关联的MQTT节点 {subtask.mqtt_node_id}")
                    else:
                        logger.warning(f"未找到与任务 {task_id} 关联的子任务")
                
                finally:
                    db.close()
                
                # 处理HTTP节点上的子任务
                if http_node_subtasks:
                    for subtask, node_id in http_node_subtasks:
                        logger.info(f"将使用HTTP方式停止子任务 {subtask.id} (节点ID: {node_id})")
                
                # 处理MQTT节点上的子任务
                mqtt_results = []
                if mqtt_node_subtasks:
                    # 获取共享的 AnalysisClient 实例
                    from app import app as fastapi_app
                    if not hasattr(fastapi_app.state, "analysis_client") or not fastapi_app.state.analysis_client:
                        logger.error("无法从应用状态获取共享的 analysis_client")
                        raise ValueError("共享的MQTT客户端不可用")
                    
                    analysis_client = fastapi_app.state.analysis_client
                    mqtt_client = None

                    # 检查MQTT连接
                    if analysis_client.mqtt_connected and analysis_client.mqtt_client:
                        mqtt_client = analysis_client.mqtt_client
                        logger.info("成功获取共享的MQTT客户端连接")
                    else:
                        # 尝试重新连接共享客户端
                        logger.warning("共享的MQTT客户端未连接，尝试重新连接...")
                        reconnected = await analysis_client.mqtt_client.connect() # 假设 connect 是 async
                        if reconnected and analysis_client.mqtt_connected:
                            mqtt_client = analysis_client.mqtt_client
                            logger.info("共享的MQTT客户端重新连接成功")
                        else:
                            logger.error("共享的MQTT客户端重新连接失败，无法发送停止命令")
                            raise ValueError("共享的MQTT客户端未连接")

                    # 向每个MQTT节点发送停止命令
                    for subtask, mqtt_node, mqtt_node_id in mqtt_node_subtasks:
                        try:
                            # 获取节点MAC地址
                            mac_address = mqtt_node.mac_address
                            logger.info(f"[停止MQTT子任务] 准备停止子任务 ID: {subtask.id} (分析任务 ID: {subtask.analysis_task_id})，目标节点 MAC: {mac_address}")

                            # 构建停止任务命令
                            message_id = int(time.time())
                            message_uuid = str(uuid.uuid4()).replace("-", "")[:16]
                            stop_command = {
                                "confirmation_topic": f"{settings.MQTT['topic_prefix']}device_config_reply", # 使用配置中的前缀
                                "message_id": message_id,
                                "message_uuid": message_uuid,
                                "request_type": "task_cmd",
                                "data": {
                                    "cmd_type": "stop_task",
                                    "task_id": subtask.analysis_task_id,  # 确认使用 analysis_task_id
                                    "subtask_id": str(subtask.id)
                                }
                            }
                            payload_json = json.dumps(stop_command)

                            # 确定目标主题
                            topic = f"{settings.MQTT['topic_prefix']}{mac_address}/request_setting" # 使用配置中的前缀
                            logger.info(f"[停止MQTT子任务] 目标主题: {topic}")
                            logger.info(f"[停止MQTT子任务] 消息内容: {payload_json}")

                            # 发送停止命令
                            logger.info(f"[停止MQTT子任务] 正在调用 publish 发送 MQTT 消息...")
                            result = mqtt_client.client.publish(
                                topic,
                                payload_json,
                                qos=settings.MQTT['qos'] # 使用配置中的 QoS
                            )
                            logger.info(f"[停止MQTT子任务] publish 调用完成，等待 MQTT Broker 确认...")

                            # result 对象通常包含 mid (message id) 和 rc (return code)
                            # rc=0 表示成功发送到 Broker
                            if hasattr(result, 'rc'):
                                logger.info(f"[停止MQTT子任务] MQTT Broker 返回码: {result.rc}")
                                if result.rc == 0:
                                    logger.info(f"[停止MQTT子任务] 停止命令已成功发送到 MQTT Broker (主题: {topic})，目标子任务 ID: {subtask.id}，节点 MAC: {mac_address}")

                                    # 减少节点任务计数 (仅在确认发送成功后执行)
                                    db_session = SessionLocal()
                                    try:
                                        # 重新查询以避免会话过期问题
                                        node_in_session = db_session.query(MQTTNode).filter(MQTTNode.id == mqtt_node_id).first()
                                        if node_in_session and node_in_session.task_count > 0:
                                            node_in_session.task_count -= 1
                                            db_session.commit()
                                            logger.info(f"[停止MQTT子任务] MQTT节点 {mqtt_node_id} ({mac_address}) 任务计数减1 (当前: {node_in_session.task_count})")
                                        elif node_in_session:
                                             logger.warning(f"[停止MQTT子任务] MQTT节点 {mqtt_node_id} ({mac_address}) 任务计数已为0，无需减少")
                                        else:
                                             logger.warning(f"[停止MQTT子任务] 在减少任务计数时未找到节点 {mqtt_node_id}")
                                    except Exception as db_err:
                                        logger.error(f"[停止MQTT子任务] 减少节点 {mqtt_node_id} 任务计数时数据库操作出错: {db_err}")
                                        db_session.rollback()
                                    finally:
                                        db_session.close()

                                    mqtt_results.append({
                                        "subtask_id": subtask.id,
                                        "node": mac_address,
                                        "status": "success",
                                        "message": "停止命令已成功发送至MQTT Broker"
                                    })
                                else:
                                    logger.error(f"[停止MQTT子任务] 发送停止命令到 MQTT Broker 失败 (主题: {topic})，返回码: {result.rc}，目标子任务 ID: {subtask.id}，节点 MAC: {mac_address}")
                                    mqtt_results.append({
                                        "subtask_id": subtask.id,
                                        "node": mac_address,
                                        "status": "error",
                                        "error": f"发送至 MQTT Broker 失败，返回码: {result.rc}"
                                    })
                            else:
                                # 如果 result 对象没有 rc 属性，记录警告
                                logger.warning(f"[停止MQTT子任务] publish 返回的对象没有 'rc' 属性: {result}，无法确认发送状态，目标子任务 ID: {subtask.id}，节点 MAC: {mac_address}")
                                # 假设发送可能成功，但无法确认
                                mqtt_results.append({
                                    "subtask_id": subtask.id,
                                    "node": mac_address,
                                    "status": "unknown",
                                    "error": "无法确认发送状态 (无返回码)"
                                })

                        except Exception as e:
                            logger.error(f"[停止MQTT子任务] 向 MQTT 节点 {mqtt_node.mac_address} 发送停止命令时发生异常: {str(e)}，子任务 ID: {subtask.id}")
                            import traceback
                            logger.error(traceback.format_exc())
                            mqtt_results.append({
                                "subtask_id": subtask.id,
                                "node": mqtt_node.mac_address if mqtt_node else "unknown",
                                "status": "error",
                                "error": f"发送过程中发生异常: {str(e)}"
                            })

                    # 如果有MQTT节点子任务，返回处理结果
                    if mqtt_results:
                        # 返回详细结果，包括每个子任务的发送状态
                        return {
                            "status": "partial_success" if any(r['status'] == 'success' for r in mqtt_results) else "failure",
                            "message": f"已尝试向 {len(mqtt_results)} 个MQTT节点发送停止命令",
                            "results": mqtt_results
                        }
                
                # 如果MQTT节点和HTTP节点都为空，抛出错误
                if not http_node_subtasks and not mqtt_node_subtasks:
                    logger.error(f"无法找到任务 {task_id} 关联的节点，无法停止任务")
                    raise ValueError(f"无法找到任务 {task_id} 关联的节点")
                
                # 如果找到了HTTP节点但没有MQTT节点，继续执行后面的HTTP节点停止逻辑
                if http_node_subtasks and not mqtt_node_subtasks:
                    node_id = http_node_subtasks[0][1]  # 取第一个HTTP节点ID继续处理

            # 如果已经在上面的新逻辑中处理了所有的MQTT节点子任务，这段代码不会执行
            # 这里保留用于向后兼容，处理单个MQTT节点的情况
            if 'mqtt_node_id' in locals() and mqtt_node_id and not mqtt_node_subtasks:
                logger.info(f"[MQTT Stop - Legacy] 使用单节点MQTT模式停止任务: {task_id}, Node ID: {mqtt_node_id}")

                try:
                    # 获取节点MAC地址
                    mac_address = None
                    # 需要重新查询 mqtt_node，因为它可能来自不同的作用域
                    db_legacy = SessionLocal()
                    try:
                         mqtt_node_legacy = db_legacy.query(MQTTNode).filter(MQTTNode.id == mqtt_node_id).first()
                         if mqtt_node_legacy:
                             mac_address = mqtt_node_legacy.mac_address
                             logger.info(f"[MQTT Stop - Legacy] 向节点 {mac_address} 发送停止任务命令: task_id={task_id}")
                         else:
                             logger.error(f"[MQTT Stop - Legacy] 找不到 MQTT 节点 {mqtt_node_id}")
                             raise ValueError(f"找不到 MQTT 节点 {mqtt_node_id}")
                    finally:
                         db_legacy.close()

                    # 创建一个独立的分析客户端用于发送MQTT命令
                    from services.http.analysis_client import AnalysisClient
                    from core.config import settings

                    # 使用系统配置创建客户端
                    analysis_client_legacy = AnalysisClient(settings.config)
                    mqtt_client_legacy = None

                    # 检查MQTT连接
                    if analysis_client_legacy.mqtt_connected and analysis_client_legacy.mqtt_client:
                        mqtt_client_legacy = analysis_client_legacy.mqtt_client
                        logger.info("[MQTT Stop - Legacy] 成功获取MQTT客户端连接")
                    else:
                        logger.error("[MQTT Stop - Legacy] MQTT客户端未连接，无法发送停止命令")
                        raise ValueError("MQTT客户端未连接")

                    # 构建停止任务命令
                    message_id_legacy = int(time.time())
                    message_uuid_legacy = str(uuid.uuid4()).replace("-", "")[:16]
                    # !! 注意：这里的 subtask 可能未定义，这是一个潜在错误 !!
                    # !! 假设 task_id 本身就是用来停止的标识 !!
                    stop_command_legacy = {
                        "confirmation_topic": f"meek/device_config_reply",
                        "message_id": message_id_legacy,
                        "message_uuid": message_uuid_legacy,
                        "request_type": "task_cmd",
                        "data": {
                            "cmd_type": "stop_task",
                            "task_id": task_id,
                            # "subtask_id": str(subtask.id) #  Legacy code might not have subtask here
                        }
                    }
                    payload_json_legacy = json.dumps(stop_command_legacy)

                    # 发送停止命令
                    topic_legacy = f"meek/{mac_address}/request_setting"
                    logger.info(f"[MQTT Stop - Legacy] 目标主题: {topic_legacy}")
                    logger.info(f"[MQTT Stop - Legacy] 消息内容: {payload_json_legacy}")
                    logger.info(f"[MQTT Stop - Legacy] 正在调用 publish 发送消息...")

                    result_legacy = mqtt_client_legacy.client.publish(
                        topic_legacy,
                        payload_json_legacy,
                        qos=1
                    )
                    logger.info(f"[MQTT Stop - Legacy] publish 调用完成，等待结果...")

                    if hasattr(result_legacy, 'rc'):
                        logger.info(f"[MQTT Stop - Legacy] 发送结果: rc={result_legacy.rc}")
                        if result_legacy.rc == 0:
                            logger.info(f"[MQTT Stop - Legacy] 停止命令已成功发送到节点 {mac_address} (主题: {topic_legacy})")

                            # 减少节点任务计数
                            db_session_legacy = SessionLocal()
                            try:
                                node_in_session_legacy = db_session_legacy.query(MQTTNode).filter(MQTTNode.id == mqtt_node_id).first()
                                if node_in_session_legacy and node_in_session_legacy.task_count > 0:
                                    node_in_session_legacy.task_count -= 1
                                    db_session_legacy.commit()
                                    logger.info(f"[MQTT Stop - Legacy] MQTT节点 {mqtt_node_id} ({mac_address}) 任务计数减1 (当前: {node_in_session_legacy.task_count})")
                                elif node_in_session_legacy:
                                     logger.warning(f"[MQTT Stop - Legacy] MQTT节点 {mqtt_node_id} ({mac_address}) 任务计数已为0，无需减少")
                                else:
                                     logger.warning(f"[MQTT Stop - Legacy] 在减少任务计数时未找到节点 {mqtt_node_id}")

                            except Exception as db_err_legacy:
                                logger.error(f"[MQTT Stop - Legacy] 减少节点 {mqtt_node_id} 任务计数时出错: {db_err_legacy}")
                                db_session_legacy.rollback()
                            finally:
                                db_session_legacy.close()

                            return {"status": "success", "message": "停止命令已发送"}
                        else:
                            logger.error(f"[MQTT Stop - Legacy] 发送停止命令到节点 {mac_address} (主题: {topic_legacy}) 失败，返回码: {result_legacy.rc}")
                            raise ValueError(f"发送停止命令失败，返回码: {result_legacy.rc}")
                    else:
                         logger.warning(f"[MQTT Stop - Legacy] publish 返回的对象没有 'rc' 属性: {result_legacy}")
                         # 假设发送可能成功
                         return {"status": "unknown", "message": "无法确认发送状态 (无返回码)"}

                except Exception as e:
                    logger.error(f"[MQTT Stop - Legacy] 通过单节点MQTT模式停止任务 {task_id} 失败: {str(e)}")
                    import traceback
                    logger.error(traceback.format_exc())
                    raise

            # 如果提供了node_id或成功查找到了node_id，使用HTTP方式通过该节点停止任务
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