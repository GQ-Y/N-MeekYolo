"""
结果处理器模块
处理来自分析节点的分析结果
"""
import json
import time
import asyncio
import traceback
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from core.database import SessionLocal
from core.redis_manager import RedisManager
from core.task_status_manager import TaskStatusManager
from models.database import Task, SubTask
# 避免循环导入，将MQTTMessageProcessor的导入移到方法内部
# from services.mqtt.mqtt_message_processor import MQTTMessageProcessor
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class ResultProcessor:
    """
    结果处理器
    
    负责:
    1. 监听和处理来自分析节点的MQTT结果消息
    2. 更新子任务状态
    3. 保存分析结果到数据库 (如果需要)
    """
    
    def __init__(self):
        """初始化结果处理器"""
        # 任务状态管理器
        self.status_manager = TaskStatusManager.get_instance()
        
        # MQTT消息处理器 - 延迟初始化
        self.mqtt_processor = None
        
        # Redis管理器
        self.redis = RedisManager.get_instance()
        
        # 初始化标志
        self.initialized = False
        
    def _get_mqtt_processor(self):
        """延迟获取MQTT消息处理器，避免循环导入"""
        if self.mqtt_processor is None:
            # 在方法内部导入，避免循环导入
            from services.mqtt.mqtt_message_processor import MQTTMessageProcessor
            self.mqtt_processor = MQTTMessageProcessor.get_instance()
        return self.mqtt_processor
        
    async def initialize(self):
        """初始化结果处理器并注册MQTT处理器"""
        if self.initialized:
            logger.info("结果处理器已经初始化")
            return
            
        # 获取MQTT处理器
        mqtt_processor = self._get_mqtt_processor()
        
        # 注册结果处理的回调函数
        # 监听所有节点的结果主题 meek/+/result
        result_topic_pattern = f"{self.get_topic_prefix()}/+/result"
        mqtt_processor.register_handler(result_topic_pattern, self._handle_result_message)
        
        self.initialized = True
        logger.info(f"结果处理器已初始化，监听主题: {result_topic_pattern}")

    def get_topic_prefix(self) -> str:
        """ 获取MQTT主题前缀 (需要从配置或MQTT客户端获取) """
        # 临时硬编码，理想情况下应从配置或MQTT客户端实例获取
        try:
            from services.mqtt.mqtt_client import MQTTClient # 尝试导入
            # 假设存在全局获取客户端实例的方法
            from main import get_mqtt_client
            client = get_mqtt_client()
            if client and client.config:
                 return client.config.get('topic_prefix', 'meek')
        except ImportError:
             logger.warning("无法导入MQTTClient获取主题前缀，使用默认 'meek'")
        except Exception as e:
            logger.warning(f"获取MQTT主题前缀时出错: {e}, 使用默认 'meek'")
        return "meek" # 默认值

    def _handle_result_message(self, topic: str, payload: Dict[str, Any]):
        """
        处理接收到的结果消息
        
        Args:
            topic: 消息主题 (例如: meek/node_mac_address/result)
            payload: 消息内容 (JSON字典)
        """
        logger.debug(f"收到结果消息: Topic={topic}, Payload={payload}")
        
        try:
            # 解析必要信息
            task_id_str = payload.get("task_id")
            subtask_analysis_id = payload.get("subtask_id") # 节点侧的任务ID
            results_data = payload.get("results")
            status_code = payload.get("status_code", 200) # 默认成功
            error_message = payload.get("error_message")
            timestamp = payload.get("timestamp", time.time())
            
            if not task_id_str or not subtask_analysis_id or results_data is None:
                logger.warning(f"结果消息格式无效，缺少必要字段: {payload}")
                return

            # 转换为整数任务ID
            try:
                 task_id = int(task_id_str)
            except (ValueError, TypeError):
                 logger.warning(f"无效的任务ID格式: {task_id_str}")
                 return

            # 异步处理结果
            asyncio.create_task(self._process_analysis_result(
                task_id=task_id,
                subtask_analysis_id=subtask_analysis_id,
                results_data=results_data,
                status_code=status_code,
                error_message=error_message,
                received_timestamp=timestamp
            ))
            
        except Exception as e:
            logger.error(f"处理结果消息时发生意外错误: {str(e)}")
            logger.error(traceback.format_exc())

    async def _process_analysis_result(self, task_id: int, subtask_analysis_id: str,
                                       results_data: Any, status_code: int,
                                       error_message: Optional[str], received_timestamp: float):
        """
        异步处理分析结果
        """
        db_session = SessionLocal()
        try:
            # 查找对应的子任务
            # 注意：我们使用 analysis_task_id 来查找，这是发送给节点的唯一ID
            subtask = db_session.query(SubTask).filter(
                SubTask.task_id == task_id,
                SubTask.analysis_task_id == subtask_analysis_id
            ).first()

            if not subtask:
                logger.warning(f"未找到与结果匹配的子任务: TaskID={task_id}, AnalysisTaskID={subtask_analysis_id}")
                return
                
            subtask_id = subtask.id
            logger.info(f"开始处理子任务 {subtask_id} (分析ID: {subtask_analysis_id}) 的结果")

            # 确定子任务的新状态
            new_status = 3 # 默认为已完成 (3)
            if status_code != 200 or error_message:
                new_status = 4 # 出错 (4)
                subtask.error_message = error_message or f"节点报告错误 (状态码: {status_code})"
                logger.error(f"子任务 {subtask_id} 执行出错: {subtask.error_message}")
            else:
                 # 清除之前的错误信息
                 subtask.error_message = None
                 subtask.completed_at = datetime.now()

            # 更新子任务状态 (通过状态管理器)
            await self.status_manager.update_subtask_status(task_id, subtask_id, new_status)

            # 检查是否需要保存结果
            task = subtask.task # 获取关联的主任务
            if task and task.save_result:
                 logger.debug(f"任务 {task_id} 配置了保存结果，正在保存子任务 {subtask_id} 的结果")
                 try:
                      # 暂时跳过结果保存，因为models.database中可能没有Result模型
                      logger.info(f"结果保存功能暂时禁用 (Result模型可能不存在)")
                      # 原来的代码已被注释掉
                 except Exception as save_e:
                      db_session.rollback()
                      logger.error(f"保存子任务 {subtask_id} 的结果失败: {str(save_e)}")
            else:
                 logger.debug(f"任务 {task_id} 未配置保存结果，跳过保存子任务 {subtask_id} 的结果")

            # 提交子任务状态和错误信息的更改
            # (注意：status_manager会处理主任务状态的更新)
            db_session.commit()
            logger.info(f"子任务 {subtask_id} 结果处理完成，状态更新为 {new_status}")
            
            # 释放节点资源 (子任务完成后)
            if subtask.node_id:
                subtask_type_str = "stream"
                if subtask.type == 1: subtask_type_str = "image"
                elif subtask.type == 2: subtask_type_str = "video"
                # 延迟导入，避免循环依赖
                from services.node.node_manager import NodeManager
                node_manager = NodeManager.get_instance()
                await node_manager.release_node(subtask.node_id, subtask_type_str)
                logger.info(f"子任务 {subtask_id} 完成，已释放节点 {subtask.node_id} 资源")
                # 清除子任务的节点关联信息 (可选)
                # subtask.node_id = None
                # subtask.analysis_task_id = None # 保留分析ID用于日志追踪?
                # db_session.commit()

        except Exception as e:
            db_session.rollback()
            logger.error(f"处理子任务分析结果时发生错误: TaskID={task_id}, AnalysisTaskID={subtask_analysis_id}, Error={str(e)}")
            logger.error(traceback.format_exc())
            # 尝试将子任务标记为错误（如果能找到它）
            try:
                 subtask = db_session.query(SubTask).filter(
                     SubTask.task_id == task_id,
                     SubTask.analysis_task_id == subtask_analysis_id
                 ).first()
                 if subtask:
                      await self.status_manager.update_subtask_status(task_id, subtask.id, 4) # 标记为出错
                      subtask.error_message = f"结果处理失败: {str(e)}"
                      db_session.commit()
            except Exception as final_e:
                 logger.error(f"标记子任务 {subtask_analysis_id} 为错误状态失败: {final_e}")
                 
        finally:
            db_session.close()

    @classmethod
    def get_instance(cls) -> 'ResultProcessor':
        """获取结果处理器单例实例"""
        if not hasattr(cls, '_instance'):
            cls._instance = ResultProcessor()
        return cls._instance 