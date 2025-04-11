"""
任务管理器模块
实现任务的创建、更新、取消和删除
"""
import time
import json
import uuid
import asyncio
from typing import Dict, List, Any, Optional, Set, Tuple, Union
from datetime import datetime
from sqlalchemy.orm import Session
from core.database import SessionLocal
from core.redis_manager import RedisManager
from core.task_status_manager import TaskStatusManager
from models.database import Task, SubTask, Stream, Model, Node
from services.node.node_manager import NodeManager
from services.mqtt.mqtt_client import MQTTClient
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class TaskManager:
    """
    任务管理器
    
    负责:
    1. 任务创建和初始化
    2. 任务状态更新和管理
    3. 任务取消和删除
    4. 与分析节点交互
    """
    
    def __init__(self):
        """初始化任务管理器"""
        # 节点管理器
        self.node_manager = NodeManager.get_instance()
        
        # 任务状态管理器
        self.status_manager = TaskStatusManager.get_instance()
        
        # MQTT客户端
        # 注意：MQTT客户端可能在运行时才可用，需要在使用时获取
        self._mqtt_client: Optional[MQTTClient] = None
        
        # Redis管理器
        self.redis = RedisManager.get_instance()
        
        # 任务锁（用于控制对同一任务的并发操作）
        self.task_locks: Dict[int, asyncio.Lock] = {}
        
        # 内部锁（用于保护task_locks字典）
        self.internal_lock = asyncio.Lock()
        
    async def get_mqtt_client(self) -> Optional[MQTTClient]:
        """获取MQTT客户端实例"""
        if self._mqtt_client is None:
            # 尝试从全局状态或其他方式获取MQTT客户端
            # 假设有一个全局函数 get_mqtt_client() 可以获取实例
            from main import get_mqtt_client # 假设在main.py中有此函数
            self._mqtt_client = get_mqtt_client()
            if not self._mqtt_client:
                logger.warning("无法获取MQTT客户端实例")
        return self._mqtt_client

    async def _get_task_lock(self, task_id: int) -> asyncio.Lock:
        """获取或创建任务锁"""
        async with self.internal_lock:
            if task_id not in self.task_locks:
                self.task_locks[task_id] = asyncio.Lock()
            return self.task_locks[task_id]

    async def create_task(self, db: Session, task_data: Dict[str, Any]) -> Tuple[Optional[Task], str]:
        """
        创建新任务
        
        Args:
            db: 数据库会话
            task_data: 任务创建数据
            
        Returns:
            Tuple[Optional[Task], str]: 创建的任务对象和消息
        """
        logger.info(f"开始创建新任务: {task_data.get('name', '未命名')}")
        
        # 验证输入数据
        if not task_data.get("analysis_type") or not task_data.get("config"):
            logger.error("创建任务失败：缺少 analysis_type 或 config")
            return None, "缺少 analysis_type 或 config"
            
        # 获取分析类型和源类型
        analysis_type = task_data["analysis_type"] # 1:图像, 2:视频, 3:流
        source_type = task_data.get("source_type", "stream") # 默认为stream

        # 获取关联的模型和流
        model_ids = task_data.get("model_ids", [])
        stream_ids = task_data.get("stream_ids", [])
        image_urls = task_data.get("image_urls", [])
        video_urls = task_data.get("video_urls", [])

        # 验证模型是否存在
        models = db.query(Model).filter(Model.id.in_(model_ids)).all()
        if len(models) != len(model_ids):
            logger.error(f"创建任务失败：部分模型ID无效")
            return None, "部分模型ID无效"

        # 验证流是否存在 (仅流任务需要)
        streams = []
        if analysis_type == 3: # 流任务
            if not stream_ids:
                logger.error("创建流任务失败：缺少 stream_ids")
                return None, "流任务需要提供 stream_ids"
            streams = db.query(Stream).filter(Stream.id.in_(stream_ids)).all()
            if len(streams) != len(stream_ids):
                logger.error(f"创建任务失败：部分流ID无效")
                return None, "部分流ID无效"
        elif analysis_type == 1: # 图像任务
             if not image_urls:
                 logger.error("创建图像任务失败：缺少 image_urls")
                 return None, "图像任务需要提供 image_urls"
        elif analysis_type == 2: # 视频任务
             if not video_urls:
                 logger.error("创建视频任务失败：缺少 video_urls")
                 return None, "视频任务需要提供 video_urls"

        try:
            # 创建主任务记录
            new_task = Task(
                name=task_data.get("name", f"任务_{int(time.time())}"),
                description=task_data.get("description"),
                analysis_type=analysis_type,
                analysis_interval=task_data.get("analysis_interval"),
                config=task_data.get("config", {}),
                save_result=task_data.get("save_result", False),
                save_images=task_data.get("save_images", False),
                status=0,  # 初始状态：未启动
                created_at=datetime.now(),
                updated_at=datetime.now(),
                user_id=task_data.get("user_id"), # 假设有用户ID
                active_subtasks=0,
                total_subtasks=0 # 稍后更新
            )
            
            # 关联模型
            new_task.models.extend(models)
            
            # 关联流 (仅流任务)
            if analysis_type == 3:
                new_task.streams.extend(streams)

            db.add(new_task)
            db.flush() # 获取新任务的ID

            logger.info(f"主任务记录已创建，ID: {new_task.id}")

            # 创建子任务
            subtasks_to_create = []
            total_subtasks = 0

            if analysis_type == 1: # 图像任务
                # 每个模型对应一个子任务
                for model in models:
                    subtask = SubTask(
                        task_id=new_task.id,
                        type=1, # 图像
                        status=0,
                        config=task_data.get("config", {}), # 使用主任务配置
                        analysis_type=task_data.get("analysis_type_detail", "detection"), # 更详细的分析类型，如 detection, classification
                        model_id=model.id,
                        image_urls=image_urls # 图像URL列表
                    )
                    subtasks_to_create.append(subtask)
                total_subtasks = len(models)
            elif analysis_type == 2: # 视频任务
                 # 每个模型对应一个子任务 (也可以按视频文件拆分，这里简化处理)
                for model in models:
                    subtask = SubTask(
                        task_id=new_task.id,
                        type=2, # 视频
                        status=0,
                        config=task_data.get("config", {}),
                        analysis_type=task_data.get("analysis_type_detail", "detection"),
                        model_id=model.id,
                        video_urls=video_urls # 视频URL列表
                    )
                    subtasks_to_create.append(subtask)
                total_subtasks = len(models)
            elif analysis_type == 3: # 流任务
                # 每个流和每个模型的组合创建一个子任务
                for stream in streams:
                    for model in models:
                        subtask = SubTask(
                            task_id=new_task.id,
                            type=3, # 流
                            status=0,
                            config=task_data.get("config", {}),
                            analysis_type=task_data.get("analysis_type_detail", "detection"),
                            stream_id=stream.id,
                            model_id=model.id,
                        )
                        subtasks_to_create.append(subtask)
                total_subtasks = len(streams) * len(models)

            # 更新主任务的总子任务数
            new_task.total_subtasks = total_subtasks
            
            # 批量添加子任务
            if subtasks_to_create:
                db.add_all(subtasks_to_create)
                db.flush() # 获取子任务ID
                logger.info(f"为任务 {new_task.id} 创建了 {len(subtasks_to_create)} 个子任务")
            else:
                 logger.warning(f"任务 {new_task.id} 没有创建任何子任务")
                 db.rollback()
                 return None, "未创建任何子任务"

            # 初始化任务状态计数器
            await self.status_manager.sync_from_database(new_task.id)

            db.commit()
            logger.info(f"任务 {new_task.id} 创建成功")
            
            # 异步启动任务分配
            asyncio.create_task(self.start_task(db, new_task.id))

            return new_task, "任务创建成功"

        except Exception as e:
            db.rollback()
            logger.error(f"创建任务时发生错误: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None, f"创建任务失败: {str(e)}"

    async def start_task(self, db: Session, task_id: int) -> Tuple[bool, str]:
        """
        启动任务，分配子任务到节点
        
        Args:
            db: 数据库会话 (注意：这里传入的db可能是旧的，建议在方法内部创建新的会话)
            task_id: 任务ID
            
        Returns:
            Tuple[bool, str]: 是否成功启动和消息
        """
        task_lock = await self._get_task_lock(task_id)
        async with task_lock:
            # 使用新的数据库会话保证数据最新
            db_session = SessionLocal()
            try:
                task = db_session.query(Task).filter(Task.id == task_id).first()
                if not task:
                    logger.error(f"启动任务失败：任务 {task_id} 不存在")
                    return False, f"任务 {task_id} 不存在"
                    
                # 检查任务状态
                if task.status == 1: # 运行中
                    logger.info(f"任务 {task_id} 已经在运行中")
                    return True, "任务已在运行中"
                if task.status == 2: # 已停止
                     logger.warning(f"任务 {task_id} 已停止，无法启动")
                     return False, "任务已停止，无法启动"
                if task.status == 3: # 已完成
                     logger.warning(f"任务 {task_id} 已完成，无法启动")
                     return False, "任务已完成，无法启动"

                logger.info(f"开始启动任务 {task_id}")
                
                # 获取需要启动的子任务（状态为0：未启动）
                subtasks_to_start = db_session.query(SubTask).filter(
                    SubTask.task_id == task_id,
                    SubTask.status == 0
                ).all()

                if not subtasks_to_start:
                    logger.info(f"任务 {task_id} 没有需要启动的子任务")
                    # 检查是否所有子任务都已完成或出错
                    all_subtasks = db_session.query(SubTask).filter(SubTask.task_id == task_id).all()
                    if all(s.status in [3, 4] for s in all_subtasks): # 3:完成, 4:出错
                         task.status = 3 if all(s.status == 3 for s in all_subtasks) else 4
                         db_session.commit()
                         await self.status_manager.sync_from_database(task_id) # 更新缓存
                         logger.info(f"任务 {task_id} 所有子任务已处理，更新主任务状态为 {task.status}")
                         return True, "任务所有子任务已处理"
                    elif all(s.status == 2 for s in all_subtasks): # 2:已停止
                        task.status = 2
                        db_session.commit()
                        await self.status_manager.sync_from_database(task_id)
                        logger.info(f"任务 {task_id} 所有子任务已停止，更新主任务状态为 {task.status}")
                        return True, "任务所有子任务已停止"
                    else:
                        # 可能有子任务正在运行中，或者状态不一致
                        logger.warning(f"任务 {task_id} 状态异常，没有未启动的子任务，但主任务状态不是运行/完成/停止")
                        # 强制同步一次状态
                        await self.status_manager.sync_from_database(task_id)
                        task_status_info = await self.status_manager.get_task_status(task_id)
                        task.status = task_status_info.get("status", task.status)
                        db_session.commit()
                        return False, "任务状态异常，已尝试同步"

                logger.info(f"任务 {task_id} 有 {len(subtasks_to_start)} 个子任务需要启动")

                # 获取MQTT客户端
                mqtt_client = await self.get_mqtt_client()
                if not mqtt_client or not mqtt_client.is_connected():
                    logger.error(f"启动任务 {task_id} 失败：MQTT客户端未连接")
                    # 可以在这里将任务标记为错误或等待状态
                    task.status = 4 # 出错
                    task.error_message = "MQTT客户端未连接"
                    db_session.commit()
                    await self.status_manager.sync_from_database(task_id)
                    return False, "MQTT客户端未连接"

                # 更新主任务状态为运行中
                task.status = 1
                task.error_message = None # 清除之前的错误信息
                task.started_at = datetime.now()
                db_session.commit()
                # 立即更新缓存中的状态计数器(虽然批处理会做，但这里先更新主状态)
                await self.status_manager.update_subtask_status(task_id, -1, 1) # 用-1表示更新主任务

                successful_starts = 0
                failed_starts = 0

                # 分配子任务到节点
                for subtask in subtasks_to_start:
                    subtask_id = subtask.id
                    subtask_type_str = "stream"
                    if subtask.type == 1: subtask_type_str = "image"
                    elif subtask.type == 2: subtask_type_str = "video"
                    
                    # 获取可用节点
                    node, node_info = await self.node_manager.get_available_node(subtask_type_str, db_session)

                    if not node:
                        logger.warning(f"子任务 {subtask_id} 无法找到可用节点")
                        # 暂时不更新子任务状态，等待下次健康检查时分配
                        failed_starts += 1
                        continue

                    logger.info(f"为子任务 {subtask_id} 分配到节点 {node.id}")
                    
                    # 更新子任务的节点信息
                    subtask.node_id = node.id
                    subtask.analysis_task_id = f"subtask_{subtask_id}_{uuid.uuid4().hex[:8]}" # 生成唯一分析任务ID
                    subtask.started_at = datetime.now()
                    db_session.flush() # 确保节点ID等信息写入

                    # 构建任务配置
                    task_config = self._build_subtask_config(subtask, task, node)

                    # 发送任务到节点
                    # 注意：这里可以选择等待节点确认，或直接发送后依赖状态更新
                    # 为了提高吞吐量，我们先直接发送，通过MQTT消息更新状态
                    success = mqtt_client.publish(
                        topic=f"{mqtt_client.config['topic_prefix']}/{node.mac_address}/task",
                        payload={
                            "task_id": str(task_id),
                            "subtask_id": subtask.analysis_task_id,
                            "config": task_config,
                            "timestamp": time.time()
                        },
                        qos=1 # 确保消息至少送达一次
                    )

                    if success:
                        # 更新子任务状态为运行中 (本地先更新，等待节点确认)
                        # 使用 status_manager 更新，触发批处理
                        await self.status_manager.update_subtask_status(task_id, subtask_id, 1)
                        successful_starts += 1
                        logger.info(f"子任务 {subtask_id} 已发送到节点 {node.id}")
                    else:
                        logger.error(f"发送子任务 {subtask_id} 到节点 {node.id} 失败")
                        # 将节点信息清除，等待下次分配
                        subtask.node_id = None
                        subtask.analysis_task_id = None
                        subtask.started_at = None
                        # 无需更新状态，保持为0（未启动）
                        # 释放之前占用的节点资源
                        await self.node_manager.release_node(node.id, subtask_type_str)
                        failed_starts += 1
                
                db_session.commit()
                logger.info(f"任务 {task_id} 启动完成: 成功启动 {successful_starts} 个子任务，失败 {failed_starts} 个")
                
                # 如果有失败的子任务，主任务可能需要标记为部分失败或继续运行
                if failed_starts > 0 and successful_starts == 0:
                     task.status = 4 # 如果一个都没成功启动，标记为错误
                     task.error_message = f"所有 {failed_starts} 个子任务启动失败"
                     db_session.commit()
                     await self.status_manager.sync_from_database(task_id) # 强制同步状态
                     return False, "所有子任务启动失败"
                elif failed_starts > 0:
                     task.error_message = f"部分子任务启动失败 ({failed_starts}/{len(subtasks_to_start)})"
                     db_session.commit()
                     # 状态仍然是运行中(1)
                     
                return True, f"任务启动完成，成功 {successful_starts}，失败 {failed_starts}"

            except Exception as e:
                db_session.rollback()
                logger.error(f"启动任务 {task_id} 时发生错误: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                # 尝试将任务标记为错误
                try:
                    task = db_session.query(Task).filter(Task.id == task_id).first()
                    if task:
                         task.status = 4
                         task.error_message = f"启动任务时出错: {str(e)}"
                         db_session.commit()
                         await self.status_manager.sync_from_database(task_id)
                except Exception as finalize_e:
                     logger.error(f"标记任务 {task_id} 为错误状态时失败: {finalize_e}")
                     
                return False, f"启动任务时出错: {str(e)}"
            finally:
                db_session.close()


    def _build_subtask_config(self, subtask: SubTask, task: Task, node: Node) -> Dict[str, Any]:
         """构建发送给节点的子任务配置"""
         config = {
            "source": {},
            "config": subtask.config or {}, # 使用子任务自己的配置优先
            "result_config": {
                "save_result": task.save_result,
                "save_images": task.save_images,
                # 回调主题，节点处理完结果后发到这里
                "callback_topic": f"{self._mqtt_client.config['topic_prefix']}/{node.mac_address}/result"
            }
         }

         # 填充源信息
         if subtask.type == 1: # 图像
             config["source"] = {
                 "type": "image",
                 "urls": subtask.image_urls or []
             }
         elif subtask.type == 2: # 视频
             config["source"] = {
                 "type": "video",
                 "urls": subtask.video_urls or []
             }
         elif subtask.type == 3: # 流
             stream = subtask.stream # 获取关联的流对象
             if stream:
                 config["source"] = {
                     "type": "stream",
                     "urls": [stream.url]
                 }
             else:
                  logger.warning(f"子任务 {subtask.id} 缺少关联的流信息")
                  config["source"] = {"type": "stream", "urls": []}
         
         # 填充模型信息
         model = subtask.model
         if model:
              config["config"]["model_code"] = model.code
              config["config"]["model_name"] = model.name # 可以加入模型名称等信息
              
         # 填充分析类型和间隔
         config["config"]["analysis_type"] = subtask.analysis_type
         if task.analysis_interval:
              config["config"]["analysis_interval"] = task.analysis_interval

         return config

    async def cancel_task(self, db: Session, task_id: int, user_initiated: bool = True) -> Tuple[bool, str]:
        """
        取消任务
        
        Args:
            db: 数据库会话 (建议内部创建新会话)
            task_id: 任务ID
            user_initiated: 是否由用户发起
            
        Returns:
            Tuple[bool, str]: 是否成功取消和消息
        """
        task_lock = await self._get_task_lock(task_id)
        async with task_lock:
            db_session = SessionLocal()
            try:
                task = db_session.query(Task).filter(Task.id == task_id).first()
                if not task:
                    logger.error(f"取消任务失败：任务 {task_id} 不存在")
                    return False, f"任务 {task_id} 不存在"
                    
                current_status = task.status
                logger.info(f"开始取消任务 {task_id}，当前状态: {current_status}")
                
                # 检查是否可以取消
                if current_status in [2, 3]: # 2:已停止, 3:已完成
                    logger.info(f"任务 {task_id} 状态为 {current_status}，无需取消")
                    return True, f"任务已{('停止' if current_status == 2 else '完成')}"
                    
                # 更新主任务状态为已停止 (2)
                task.status = 2
                task.stopped_at = datetime.now()
                if user_initiated:
                    task.error_message = "任务由用户手动停止"
                else:
                    task.error_message = "任务被系统取消"
                
                # 查找正在运行的子任务 (状态 1)
                running_subtasks = db_session.query(SubTask).filter(
                    SubTask.task_id == task_id,
                    SubTask.status == 1
                ).all()
                
                logger.info(f"任务 {task_id} 有 {len(running_subtasks)} 个运行中的子任务需要停止")

                # 获取MQTT客户端
                mqtt_client = await self.get_mqtt_client()
                if not mqtt_client or not mqtt_client.is_connected():
                     logger.warning(f"MQTT客户端未连接，无法向节点发送停止命令，仅更新数据库状态")
                     # 即使MQTT未连接，也要继续更新数据库状态并将子任务标记为停止

                stopped_count = 0
                for subtask in running_subtasks:
                    node_id = subtask.node_id
                    analysis_task_id = subtask.analysis_task_id # 节点侧的任务ID
                    
                    # 1. 向节点发送停止命令 (如果MQTT可用)
                    if mqtt_client and mqtt_client.is_connected() and node_id and analysis_task_id:
                        node = db_session.query(Node).filter(Node.id == node_id).first()
                        if node and node.mac_address:
                            logger.info(f"向节点 {node.id} ({node.mac_address}) 发送停止子任务 {subtask.id} (分析ID: {analysis_task_id}) 的命令")
                            # 发送停止命令，不强制等待响应
                            mqtt_client.publish(
                                topic=f"{mqtt_client.config['topic_prefix']}/{node.mac_address}/command",
                                payload={
                                    "command": "stop_subtask",
                                    "params": {"subtask_id": analysis_task_id},
                                    "timestamp": time.time()
                                },
                                qos=1
                            )
                        else:
                            logger.warning(f"无法找到子任务 {subtask.id} 关联的节点 {node_id} 或节点MAC地址")

                    # 2. 更新子任务状态为停止 (2) - 使用状态管理器
                    await self.status_manager.update_subtask_status(task_id, subtask.id, 2)
                    
                    # 3. 释放节点资源
                    if node_id:
                        subtask_type_str = "stream"
                        if subtask.type == 1: subtask_type_str = "image"
                        elif subtask.type == 2: subtask_type_str = "video"
                        await self.node_manager.release_node(node_id, subtask_type_str)
                        logger.info(f"已释放子任务 {subtask.id} 占用的节点 {node_id} 资源")
                        
                    stopped_count += 1

                # 处理非运行状态的子任务（例如未启动0, 出错4），也标记为停止2
                other_subtasks = db_session.query(SubTask).filter(
                    SubTask.task_id == task_id,
                    SubTask.status.in_([0, 4]) # 0:未启动, 4:出错
                ).all()
                for subtask in other_subtasks:
                    await self.status_manager.update_subtask_status(task_id, subtask.id, 2)
                    stopped_count += 1

                # 提交数据库更改
                db_session.commit()
                
                # 确保状态管理器执行一次批处理以更新主任务状态
                await self.status_manager._perform_batch_update()

                logger.info(f"任务 {task_id} 已成功取消，共停止 {stopped_count} 个子任务")
                return True, "任务已成功取消"

            except Exception as e:
                db_session.rollback()
                logger.error(f"取消任务 {task_id} 时发生错误: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                return False, f"取消任务时出错: {str(e)}"
            finally:
                db_session.close()

    async def delete_task(self, db: Session, task_id: int) -> Tuple[bool, str]:
        """
        删除任务及其所有子任务
        
        Args:
            db: 数据库会话 (建议内部创建新会话)
            task_id: 任务ID
            
        Returns:
            Tuple[bool, str]: 是否成功删除和消息
        """
        task_lock = await self._get_task_lock(task_id)
        async with task_lock:
            db_session = SessionLocal()
            try:
                task = db_session.query(Task).filter(Task.id == task_id).first()
                if not task:
                    logger.error(f"删除任务失败：任务 {task_id} 不存在")
                    return True, f"任务 {task_id} 不存在或已被删除" # 认为不存在也是成功删除
                    
                logger.info(f"开始删除任务 {task_id}，当前状态: {task.status}")

                # 安全策略：不允许删除正在运行的任务，需要先取消
                if task.status == 1:
                    logger.warning(f"无法删除运行中的任务 {task_id}，请先取消任务")
                    return False, "无法删除运行中的任务，请先取消"
                
                # 1. 删除所有子任务
                subtasks = db_session.query(SubTask).filter(SubTask.task_id == task_id).all()
                num_subtasks = len(subtasks)
                if num_subtasks > 0:
                     logger.info(f"准备删除任务 {task_id} 的 {num_subtasks} 个子任务")
                     for subtask in subtasks:
                          db_session.delete(subtask)
                     db_session.flush() # 应用删除

                # 2. 删除主任务
                logger.info(f"删除主任务 {task_id}")
                db_session.delete(task)
                
                # 提交数据库更改
                db_session.commit()
                logger.info(f"任务 {task_id} 及其 {num_subtasks} 个子任务已从数据库删除")

                # 3. 清理Redis缓存
                try:
                    # 删除任务状态计数器
                    await self.redis.delete_key(f"{self.status_manager.task_status_prefix}{task_id}")
                    # 删除子任务状态 (需要获取子任务ID列表)
                    subtask_ids = [s.id for s in subtasks]
                    keys_to_delete = [f"{self.status_manager.subtask_status_prefix}{sid}" for sid in subtask_ids]
                    if keys_to_delete:
                         await self.redis.delete_keys(keys_to_delete)
                    logger.info(f"已清理任务 {task_id} 的Redis缓存")
                except Exception as redis_e:
                    logger.error(f"清理任务 {task_id} 的Redis缓存时出错: {redis_e}")
                    # 即使缓存清理失败，删除操作也算成功

                # 4. 清理任务锁
                async with self.internal_lock:
                    self.task_locks.pop(task_id, None)
                    
                return True, "任务及其子任务已成功删除"

            except Exception as e:
                db_session.rollback()
                logger.error(f"删除任务 {task_id} 时发生错误: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                return False, f"删除任务时出错: {str(e)}"
            finally:
                db_session.close()

    # TODO: 实现 update_task 方法
    
    @classmethod
    def get_instance(cls) -> 'TaskManager':
        """获取任务管理器单例实例"""
        if not hasattr(cls, '_instance'):
            cls._instance = TaskManager()
        return cls._instance
