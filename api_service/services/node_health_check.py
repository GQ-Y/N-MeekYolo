"""节点健康检查服务"""
import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
from crud.node import NodeCRUD
from models.database import Node, MQTTNode, Task, SubTask
from core.database import SessionLocal
from shared.utils.logger import setup_logger
import httpx
from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload
from typing import List, Dict, Any, Optional, Tuple
import yaml
from crud.task import TaskCRUD, update_task_status_from_subtasks
import traceback
import time

# 配置日志
logger = setup_logger(__name__)

class NodeHealthChecker:
    def __init__(self, check_interval: int = 20):
        """
        初始化节点健康检查器
        :param check_interval: 检查间隔时间（秒），默认300秒
        """
        self.check_interval = check_interval
        self.is_running = False
        self.check_count = 0
        self.comm_mode = self._get_comm_mode()

    def _get_comm_mode(self) -> str:
        """获取当前通信模式"""
        try:
            with open("config/config.yaml", "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                return config.get('COMMUNICATION', {}).get('mode', 'http')
        except Exception as e:
            logger.error(f"读取配置文件失败: {e}")
            return "http"

    async def start(self):
        """启动健康检查服务"""
        logger.info("节点健康检查服务启动")
        self.is_running = True
        while self.is_running:
            try:
                self.check_count += 1
                logger.info(f"开始第 {self.check_count} 次节点健康检查...")
                start_time = datetime.now()
                
                # 重新读取通信模式，以防运行时配置更改
                self.comm_mode = self._get_comm_mode()
                logger.info(f"当前通信模式: {self.comm_mode}")
                
                # 明确根据通信模式执行对应的健康检查
                if self.comm_mode == "mqtt":
                    logger.info("MQTT模式：执行MQTT节点健康检查")
                    await self.check_mqtt_nodes_health()
                else:  # http 模式
                    logger.info("HTTP模式：执行HTTP节点健康检查")
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

    async def check_mqtt_nodes_health(self):
        """
        执行MQTT节点健康检查
        
        在MQTT模式下依赖MQTT的连接状态和节点发布的状态消息,
        但增加了基于最后活跃时间的超时离线检测和任务重新分配机制
        """
        db = SessionLocal()
        try:
            logger.info("==================== MQTT节点健康检查开始 ====================")
            
            # 检查MQTT节点表是否存在
            try:
                db.execute(text("SELECT 1 FROM mqtt_nodes LIMIT 1"))
            except SQLAlchemyError as e:
                logger.error(f"MQTT节点表不存在或数据库错误: {str(e)}")
                logger.info("==================== MQTT节点健康检查结束 ====================")
                return
            
            # 获取当前在线MQTT节点数量
            online_count = db.query(MQTTNode).filter_by(status="online").count()
            logger.info(f"当前在线MQTT节点数: {online_count}")
            
            # 获取所有节点
            nodes = db.query(MQTTNode).all()
            logger.info(f"数据库中共有 {len(nodes)} 个MQTT节点记录")
            
            if not nodes:
                logger.warning("数据库中没有MQTT节点记录，健康检查结束")
                logger.info("==================== MQTT节点健康检查结束 ====================")
                return
            
            # 根据last_active时间检查节点是否超时离线
            now = datetime.now()
            timeout_seconds = self.check_interval * 2  # 超时时间为检查间隔的2倍
            updated_nodes = []
            offline_nodes = []  # 记录所有处于离线状态的节点
            
            for node in nodes:
                logger.info(f"------- 检查MQTT节点 {node.id} ({node.mac_address}) -------")
                logger.info(f"节点 {node.id} 原状态: {node.status}")
                
                # 如果节点处于在线状态，检查最后活跃时间是否超时
                if node.status == "online" and node.last_active:
                    # 计算时间差
                    time_diff = (now - node.last_active).total_seconds()
                    
                    if time_diff > timeout_seconds:
                        logger.warning(f"MQTT节点 {node.id} ({node.mac_address}) 超时 {time_diff:.0f}秒未活跃，标记为离线")
                        node.status = "offline"
                        updated_nodes.append(node)
                        offline_nodes.append(node)  # 添加到离线节点列表
                elif node.status == "offline":
                    # 如果节点已经处于离线状态，也加入离线节点列表进行任务检查
                    offline_nodes.append(node)
                
                logger.info(f"节点 {node.id} 当前状态: {node.status}")
                logger.info(f"------- 节点 {node.id} 检查完成 -------")
            
            # 更新超时节点状态
            if updated_nodes:
                logger.info(f"更新 {len(updated_nodes)} 个超时离线的MQTT节点状态")
                db.commit()
                logger.info("节点状态更新成功")
                
                # 处理刚变为离线的节点的任务重新分配
                for node in updated_nodes:
                    await self._handle_mqtt_node_offline(db, node)
            else:
                logger.info("没有超时离线的MQTT节点")
            
            # 检查所有离线节点上是否仍有运行中的任务需要迁移
            if offline_nodes:
                logger.info(f"检查所有离线节点上的运行中任务，共 {len(offline_nodes)} 个离线节点")
                for node in offline_nodes:
                    # 查找该节点上运行中的子任务数量
                    running_tasks_count = db.query(SubTask).filter(
                        SubTask.mqtt_node_id == node.id,
                        SubTask.status == 1  # 运行中
                    ).count()
                    
                    if running_tasks_count > 0:
                        logger.warning(f"离线节点 {node.id} ({node.mac_address}) 上仍有 {running_tasks_count} 个运行中的子任务，需要迁移")
                        # 处理迁移
                        await self._handle_mqtt_node_offline(db, node)
                    else:
                        logger.info(f"离线节点 {node.id} ({node.mac_address}) 上没有运行中的子任务")
            else:
                logger.info("没有离线节点需要检查")
            
            # 处理待分配的任务
            await self._handle_mqtt_task_allocation(db)
            
            logger.info("所有MQTT节点状态正常")
            logger.info("==================== MQTT节点健康检查结束 ====================")
            
        except Exception as e:
            logger.error(f"MQTT节点健康检查出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            db.close()

    async def _handle_mqtt_node_offline(self, db: Session, node: MQTTNode):
        """处理MQTT节点离线情况，将该节点上运行的任务转移至其他在线节点"""
        try:
            logger.info(f"处理离线MQTT节点 {node.id} ({node.mac_address}) 的任务...")
            
            # 查找该节点上运行的子任务
            running_subtasks = db.query(SubTask).filter(
                SubTask.mqtt_node_id == node.id,
                SubTask.status == 1  # 运行中
            ).all()
            
            if not running_subtasks:
                logger.info(f"节点 {node.mac_address} 没有运行中的子任务")
                return
                
            logger.info(f"节点 {node.mac_address} 有 {len(running_subtasks)} 个运行中的子任务需要转移")
            
            # 查找可用的其他在线节点
            available_nodes = db.query(MQTTNode).filter(
                MQTTNode.status == "online",
                MQTTNode.is_active == True,
                MQTTNode.mac_address != node.mac_address,  # 排除当前离线节点
                MQTTNode.task_count < MQTTNode.max_tasks
            ).order_by(MQTTNode.task_count).all()
            
            if not available_nodes:
                logger.warning(f"没有可用的在线节点，所有子任务将重置为未启动状态等待后续分配")
                # 将子任务重置为未启动状态，等待有节点在线时再分配
                for subtask in running_subtasks:
                    subtask.status = 0  # 未启动
                    subtask.mqtt_node_id = None  # 清除节点关联
                    subtask.started_at = None
                    subtask.error_message = f"节点 {node.mac_address} 离线，等待重新分配"
                    
                    # 同时更新关联的主任务active_subtasks计数
                    task = subtask.task
                    if task and task.active_subtasks > 0:
                        task.active_subtasks -= 1
                
                db.commit()
                logger.info(f"已重置 {len(running_subtasks)} 个子任务为未启动状态")
                return
            
            # 使用应用级别的MQTT客户端
            from fastapi import FastAPI
            from app import app as fastapi_app
            
            mqtt_client = None
            try:
                if hasattr(fastapi_app.state, "analysis_client") and fastapi_app.state.analysis_client:
                    analysis_client = fastapi_app.state.analysis_client
                    mqtt_client = analysis_client.mqtt_client
                
                if not mqtt_client:
                    logger.warning("无法获取MQTT客户端，任务转移失败，将重置任务状态")
                    # 重置所有任务并返回
                    for subtask in running_subtasks:
                        subtask.status = 0  # 未启动
                        subtask.mqtt_node_id = None  # 清除节点关联
                        subtask.started_at = None
                        subtask.error_message = f"节点 {node.mac_address} 离线，无法获取MQTT客户端进行转移"
                        
                        # 更新主任务计数
                        task = subtask.task
                        if task and task.active_subtasks > 0:
                            task.active_subtasks -= 1
                    
                    db.commit()
                    return
            except Exception as e:
                logger.error(f"获取MQTT客户端时出错: {str(e)}")
                logger.error(traceback.format_exc())
                # 重置所有任务并返回
                for subtask in running_subtasks:
                    subtask.status = 0
                    subtask.mqtt_node_id = None
                    subtask.started_at = None
                    subtask.error_message = f"节点离线，获取MQTT客户端出错: {str(e)}"
                db.commit()
                return
            
            # 开始任务转移
            transferred_count = 0
            failed_count = 0
            node_index = 0  # 初始节点索引
            
            for subtask in running_subtasks:
                try:
                    # 获取子任务关联的主任务信息
                    task = subtask.task
                    if not task:
                        logger.warning(f"子任务 {subtask.id} 没有关联的主任务，跳过转移")
                        continue
                    
                    # 获取子任务使用的模型和流信息
                    model = subtask.model
                    stream = subtask.stream
                    
                    # 选择下一个节点 (循环分配)
                    target_node = available_nodes[node_index % len(available_nodes)]
                    node_index += 1
                    
                    logger.info(f"准备将子任务 {subtask.id} 从节点 {node.mac_address} 转移到节点 {target_node.mac_address}")
                    
                    # 构建任务配置
                    task_config = {
                        "source": {},
                        "config": subtask.config or {},
                        "result_config": {
                            "save_result": task.save_result if task else False,
                            "save_images": task.save_images if task else False,
                            "callback_topic": f"meek/{target_node.mac_address}/result"
                        }
                    }
                    
                    # 根据分析类型设置源数据
                    if stream:
                        # 视频流任务
                        task_config["source"] = {
                            "type": "stream",
                            "urls": [stream.url]
                        }
                    else:
                        # 假设是图像任务（从配置中提取）
                        urls = subtask.config.get("image_urls", []) if subtask.config else []
                        task_config["source"] = {
                            "type": "image",
                            "urls": urls
                        }
                    
                    # 设置模型和分析类型
                    if model:
                        task_config["config"]["model_code"] = model.code
                    
                    if subtask.analysis_type:
                        task_config["config"]["analysis_type"] = subtask.analysis_type
                    
                    if task.analysis_interval:
                        task_config["config"]["analysis_interval"] = task.analysis_interval
                    
                    # 如果任务ID不存在，使用纯数字ID
                    if not subtask.analysis_task_id:
                        # 生成纯数字ID: 主任务ID + (子任务ID+1000) 确保是纯数字格式
                        subtask.analysis_task_id = str(subtask.id + 1000)
                        logger.info(f"为子任务 {subtask.id} 生成纯数字分析任务ID: {subtask.analysis_task_id}")
                    
                    # 发送任务消息到新节点
                    success = False
                    try:
                        result = await mqtt_client.send_task_to_node(
                            mac_address=target_node.mac_address,
                            task_id=str(task.id),
                            subtask_id=subtask.analysis_task_id or str(subtask.id),
                            config=task_config,
                            wait_for_response=False
                        )
                        
                        if isinstance(result, tuple):
                            success = result[0]  # 如果返回元组，取第一个元素作为成功标志
                        else:
                            success = result
                    except Exception as e:
                        logger.error(f"发送任务到节点 {target_node.mac_address} 失败: {e}")
                        success = False
                    
                    if success:
                        # 更新子任务信息
                        subtask.mqtt_node_id = target_node.id
                        subtask.status = 1  # 保持运行中状态
                        subtask.error_message = f"已从节点 {node.mac_address} 自动转移到节点 {target_node.mac_address}"
                        
                        # 更新目标节点任务计数
                        target_node.task_count += 1
                        
                        transferred_count += 1
                        logger.info(f"成功将子任务 {subtask.id} 转移到节点 {target_node.mac_address}")
                        
                        # 如果节点任务数达到上限，从可用节点列表中移除
                        if target_node.task_count >= target_node.max_tasks:
                            available_nodes.remove(target_node)
                            logger.info(f"节点 {target_node.mac_address} 已达到最大任务数，从可用列表中移除")
                            # 如果没有可用节点了，跳出循环
                            if not available_nodes:
                                logger.warning("没有更多可用节点，停止转移")
                                break
                    else:
                        # 转移失败，重置子任务状态
                        subtask.status = 0  # 未启动
                        subtask.mqtt_node_id = None
                        subtask.started_at = None
                        subtask.error_message = f"从节点 {node.mac_address} 转移失败，等待重新分配"
                        
                        # 更新主任务active_subtasks计数
                        if task.active_subtasks > 0:
                            task.active_subtasks -= 1
                        
                        failed_count += 1
                
                except Exception as e:
                    logger.error(f"转移子任务 {subtask.id} 时出错: {e}")
                    logger.error(traceback.format_exc())
                    
                    # 转移出错，重置子任务状态
                    subtask.status = 0  # 未启动
                    subtask.mqtt_node_id = None
                    subtask.started_at = None
                    subtask.error_message = f"从节点 {node.mac_address} 转移出错: {str(e)}"
                    
                    # 更新主任务active_subtasks计数
                    task = subtask.task
                    if task and task.active_subtasks > 0:
                        task.active_subtasks -= 1
                    
                    failed_count += 1
            
            # 更新离线节点的任务计数
            node.task_count = max(0, node.task_count - (transferred_count + failed_count))
            
            db.commit()
            logger.info(f"节点 {node.mac_address} 的任务转移完成: 成功={transferred_count}, 失败={failed_count}")
            
        except Exception as e:
            logger.error(f"处理MQTT节点离线任务转移失败: {e}")
            logger.error(traceback.format_exc())

    async def _handle_mqtt_task_allocation(self, db: Session):
        """在MQTT模式下处理未分配任务的重新分配"""
        try:
            logger.info("处理MQTT模式下的任务分配...")
            
            # 获取所有活跃的MQTT节点
            active_nodes = db.query(MQTTNode).filter(
                MQTTNode.status == "online",
                MQTTNode.task_count < MQTTNode.max_tasks
            ).order_by(MQTTNode.task_count).all()  # 直接按任务数排序
            
            if not active_nodes:
                logger.warning("没有在线的MQTT节点，无法分配任务")
                return
            
            logger.info(f"发现 {len(active_nodes)} 个可用的MQTT节点")
            
            # 获取所有未启动状态的子任务
            unstarted_subtasks = db.query(SubTask).filter(
                SubTask.status == 0,  # 未启动
                SubTask.mqtt_node_id == None  # 未分配MQTT节点
            ).join(
                Task, SubTask.task_id == Task.id
            ).filter(
                Task.status == 1  # 主任务处于运行中状态
            ).order_by(
                SubTask.task_id,
                SubTask.id
            ).all()
            
            if not unstarted_subtasks:
                logger.info("没有待分配的子任务")
                return
            
            logger.info(f"发现 {len(unstarted_subtasks)} 个待分配的子任务")
            
            # 使用应用级别的MQTT客户端而不是创建新的
            from fastapi import FastAPI
            from app import app as fastapi_app
            
            mqtt_client = None
            try:
                if hasattr(fastapi_app.state, "analysis_client") and fastapi_app.state.analysis_client:
                    analysis_client = fastapi_app.state.analysis_client
                    mqtt_client = analysis_client.mqtt_client
                
                if not mqtt_client:
                    logger.warning("无法获取MQTT客户端，任务分配将延迟到下一次健康检查")
                    return
            except Exception as e:
                logger.error(f"获取MQTT客户端时出错: {str(e)}")
                logger.error(traceback.format_exc())
                return
            
            tasks_started = 0
            
            # 简单的循环分配：为每个未启动的子任务分配一个节点
            node_index = 0  # 初始节点索引
            
            for subtask in unstarted_subtasks:
                try:
                    # 检查是否还有可用节点
                    if not active_nodes:
                        logger.info("没有更多可用节点，停止分配")
                        break
                    
                    # 选择下一个节点 (简单的循环分配)
                    node = active_nodes[node_index % len(active_nodes)]
                    node_index += 1
                    
                    logger.info(f"为子任务 {subtask.id} 分配MQTT节点 {node.mac_address}")
                    
                    # 构建任务配置
                    task_config = {
                        "source": {},
                        "config": subtask.config or {},
                        "save_result": subtask.task.save_result if subtask.task else False
                    }
                    
                    # 根据分析类型设置源数据
                    if subtask.stream_id:
                        # 视频流任务
                        stream = subtask.stream
                        if stream:
                            task_config["source"] = {
                                "type": "stream",
                                "urls": [stream.url]
                            }
                    else:
                        # 假设是图像任务（从配置中提取）
                        urls = subtask.config.get("image_urls", []) if subtask.config else []
                        task_config["source"] = {
                            "type": "image",
                            "urls": urls
                        }
                    
                    # 如果任务ID不存在，使用纯数字ID
                    if not subtask.analysis_task_id:
                        # 生成纯数字ID: 主任务ID + (子任务ID+1000) 确保是纯数字格式
                        subtask.analysis_task_id = str(subtask.id + 1000)
                        logger.info(f"为子任务 {subtask.id} 生成纯数字分析任务ID: {subtask.analysis_task_id}")
                    
                    # 重要：更新节点关联 - 使用当前数据库会话中的节点ID
                    subtask.mqtt_node_id = node.id  # 这里node已经在当前会话中
                    subtask.node_id = None  # 显式清除HTTP节点ID
                    # 注意：我们只关联节点，不更新子任务状态（状态仍然为0/未启动）
                    # 子任务状态将根据MQTT消息由MQTT客户端更新
                    subtask.error_message = "任务已分配MQTT节点，等待节点接收"
                    
                    # 提前更新数据库，确保任务记录创建
                    db.flush()
                    
                    # 向节点发送任务，不等待响应
                    try:
                        await mqtt_client.send_task_to_node(
                            mac_address=node.mac_address,
                            task_id=str(subtask.task_id),
                            subtask_id=subtask.analysis_task_id,
                            config=task_config,
                            wait_for_response=False
                        )
                        
                        # 更新节点任务计数
                        node.task_count += 1
                        tasks_started += 1
                        
                        logger.info(f"子任务 {subtask.id} 已发送到MQTT节点 {node.mac_address}，等待节点响应")
                        
                        # 如果节点任务数达到上限，从可用节点列表中移除
                        if node.task_count >= node.max_tasks:
                            active_nodes.remove(node)
                            logger.info(f"节点 {node.mac_address} 已达到最大任务数，从可用列表中移除")
                    
                    except Exception as e:
                        logger.error(f"发送任务到节点时出错: {e}")
                        subtask.error_message = f"发送任务异常: {str(e)}"
                        logger.error(traceback.format_exc())
                
                except Exception as e:
                    logger.error(f"分配子任务 {subtask.id} 失败: {e}")
                    subtask.error_message = f"任务分配过程出错: {str(e)}"
                    logger.error(traceback.format_exc())
            
            db.commit()
            logger.info(f"共成功分配 {tasks_started} 个子任务到MQTT节点")
            
        except Exception as e:
            logger.error(f"处理MQTT任务分配出错: {str(e)}")
            logger.error(traceback.format_exc())

    async def check_nodes_health(self):
        """
        执行HTTP节点健康检查（仅在HTTP模式下使用）
        """
        db = SessionLocal()
        try:
            logger.info("==================== HTTP节点健康检查开始 ====================")
            try:
                # 先检查是否有节点表，使用text()函数包装SQL语句
                db.execute(text("SELECT 1 FROM nodes LIMIT 1"))
            except SQLAlchemyError as e:
                logger.error(f"节点表不存在或数据库错误: {str(e)}")
                return

            # 获取当前在线节点数量
            online_count = db.query(Node).filter_by(service_status="online").count()
            logger.info(f"当前在线节点数: {online_count}")

            # 检查节点健康状态
            before_check = datetime.now()
            
            # 获取所有节点
            nodes = db.query(Node).all()
            logger.info(f"数据库中共有 {len(nodes)} 个节点需要检查")
            
            if not nodes:
                logger.warning("数据库中没有节点记录，健康检查结束")
                logger.info("==================== HTTP节点健康检查结束 ====================")
                return
                
            updated_nodes = []
            offline_nodes = []
            recovered_nodes = []  # 新增：记录从离线恢复为在线的节点
            
            # 检查每个节点的健康状态
            for node in nodes:
                try:
                    logger.info(f"------- 开始检查节点 {node.id} ({node.ip}:{node.port}) -------")
                    old_status = node.service_status
                    logger.info(f"节点 {node.id} 原状态: {old_status}")
                    
                    is_healthy = False
                    try:
                        is_healthy = await self._check_node_health(node)
                    except Exception as e:
                        logger.error(f"检查节点 {node.id} 健康状态时发生异常: {str(e)}")
                        import traceback
                        logger.error(traceback.format_exc())
                    
                    logger.info(f"节点 {node.id} 健康检查结果: {'正常' if is_healthy else '异常'}")
                    
                    # 更新节点状态
                    if is_healthy:
                        node.service_status = "online"
                        node.last_heartbeat = datetime.now()
                        if old_status != "online":
                            logger.info(f"节点 {node.id} ({node.ip}:{node.port}) 从 {old_status} 状态恢复为在线状态")
                            updated_nodes.append(node)
                            # 记录节点恢复在线，后续需要处理恢复逻辑
                            recovered_nodes.append(node)
                    else:
                        if node.service_status != "offline":
                            node.service_status = "offline"
                            logger.warning(f"节点 {node.id} ({node.ip}:{node.port}) 标记为离线状态")
                            updated_nodes.append(node)
                            offline_nodes.append(node)
                    
                    logger.info(f"节点 {node.id} 当前状态: {node.service_status}")
                    logger.info(f"------- 节点 {node.id} 检查完成 -------")
                except Exception as e:
                    logger.error(f"检查节点 {node.id} 状态时出错: {str(e)}")
                    import traceback
                    logger.error(traceback.format_exc())
            
            # 提交所有节点状态更改
            try:
                if updated_nodes:
                    logger.info(f"提交 {len(updated_nodes)} 个节点的状态更新到数据库")
                    db.commit()
                    logger.info(f"数据库提交成功")
                else:
                    logger.info("没有节点状态变化，无需提交数据库")
            except Exception as e:
                logger.error(f"提交数据库更新失败: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
            
            # 处理离线节点上的任务
            task_count = 0
            migrated_count = 0
            
            for offline_node in offline_nodes:
                try:
                    logger.info(f"处理离线节点 {offline_node.id} 上的任务")
                    # 查找该节点上的所有子任务
                    subtasks = db.query(SubTask).options(
                        joinedload(SubTask.task)
                    ).filter(
                        SubTask.node_id == offline_node.id
                    ).all()
                    
                    if not subtasks:
                        logger.info(f"节点 {offline_node.id} 没有子任务需要迁移")
                        continue
                        
                    # 获取涉及的主任务ID列表
                    task_ids = {subtask.task_id for subtask in subtasks}
                    tasks = db.query(Task).options(
                        joinedload(Task.streams),
                        joinedload(Task.models),
                        joinedload(Task.sub_tasks)
                    ).filter(
                        Task.id.in_(task_ids)
                    ).all()
                    
                    task_count = len(tasks)
                    logger.warning(f"节点 {offline_node.id} ({offline_node.ip}:{offline_node.port}) 离线，发现 {task_count} 个任务的 {len(subtasks)} 个子任务需要迁移")
                    
                    # 更新所有子任务为未启动状态，但不处理用户手动停止的任务的子任务
                    for subtask in subtasks:
                        # 检查主任务状态，跳过用户手动停止的任务的子任务
                        task = db.query(Task).filter(Task.id == subtask.task_id).first()
                        if task and task.status == 2 and task.error_message == "任务由用户手动停止":
                            logger.info(f"子任务 {subtask.id} 属于用户手动停止的任务 {task.id}，不进行处理")
                            continue
                        
                        # 检查子任务是否是运行中状态(1)
                        if subtask.status == 1:
                            # 记录原始信息
                            old_analysis_task_id = subtask.analysis_task_id
                            old_status = subtask.status
                            
                            # 更新子任务状态 - 改为未启动(0)
                            subtask.status = 0  # 设为未启动状态(0)
                            subtask.error_message = f"节点 {offline_node.id} 离线，任务需要重新分配"
                            subtask.analysis_task_id = None  # 清除原始分析任务ID
                            
                            logger.info(f"子任务 {subtask.id} 状态从 {old_status} 改为未启动，待重新分配")
                    
                    # 减少离线节点任务计数
                    if offline_node.stream_task_count > 0:
                        offline_node.stream_task_count = 0
                    
                    # 提交更改
                    db.commit()
                    
                except Exception as e:
                    logger.error(f"处理离线节点 {offline_node.id} 上的任务时出错: {str(e)}")
                    import traceback
                    logger.error(traceback.format_exc())
            
            if task_count > 0:
                logger.info(f"总任务迁移情况：{migrated_count}/{task_count} 成功")
            
            # 检查是否有在线节点
            online_nodes = db.query(Node).filter(
                Node.service_status == "online",
                Node.is_active == True
            ).all()
            
            # 处理任务分配
            if online_nodes:  # 只要有在线节点，就尝试分配所有未启动的子任务
                logger.info(f"系统中有 {len(online_nodes)} 个在线节点，尝试分配所有未启动状态的子任务")
                await self._handle_node_recovery(db, online_nodes)
            else:
                logger.warning("没有在线节点，无法分配任务")
            
            # 如果有待处理的任务，尝试启动
            await self._start_pending_tasks(db)
            
            after_check = datetime.now()

            # 获取更新后的在线节点数量
            new_online_count = db.query(Node).filter_by(service_status="online").count()
            offline_count = online_count - new_online_count if online_count > new_online_count else 0
            online_increase = new_online_count - online_count if new_online_count > online_count else 0

            if offline_count > 0:
                logger.warning(f"发现 {offline_count} 个节点离线")
            if online_increase > 0:
                logger.info(f"发现 {online_increase} 个节点恢复在线")
            if offline_count == 0 and online_increase == 0:
                logger.info("所有节点状态正常")

            duration = (after_check - before_check).total_seconds()
            logger.info(f"健康检查耗时: {duration:.2f} 秒")
            logger.info("==================== HTTP节点健康检查结束 ====================")

        except Exception as e:
            logger.error(f"节点健康检查出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            db.close()
    
    async def _check_node_health(self, node: Node) -> bool:
        """
        检查单个节点的健康状态
        
        参数:
        - node: 节点对象
        
        返回:
        - 节点是否健康
        """
        try:
            db = SessionLocal()
            try:
                # 使用 NodeCRUD 类的实现
                logger.info(f"使用 NodeCRUD.check_node_health 检查节点 {node.id} ({node.ip}:{node.port})")
                is_healthy = await NodeCRUD.check_node_health(db, node)
                
                if is_healthy:
                    logger.info(f"节点 {node.id} 健康检查通过")
                else:
                    logger.warning(f"节点 {node.id} 健康检查未通过")
                    
                return is_healthy
                
            except Exception as e:
                logger.error(f"检查节点 {node.id} 健康状态时出错: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                return False
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"检查节点 {node.id} 健康状态时发生未预期的错误: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def _start_pending_tasks(self, db: Session):
        """启动处于未启动状态的任务"""
        try:
            logger.info("开始处理待启动的任务...")
            
            # 先查询所有任务状态，用于诊断
            task_status_counts = db.execute(text("""
                SELECT status, COUNT(*) as count 
                FROM tasks 
                GROUP BY status
            """)).fetchall()
            
            logger.info(f"当前任务状态分布: {', '.join([f'{status}: {count}' for status, count in task_status_counts])}" if task_status_counts else "没有任务")
            
            # 查找运行中(状态1)的主任务中有未启动(状态0)的子任务
            running_tasks_with_not_started_subtasks = db.query(Task).join(
                SubTask, Task.id == SubTask.task_id
            ).filter(
                Task.status == 1,  # 主任务状态为运行中(1)
                SubTask.status == 0,  # 子任务状态为未启动(0)
                Task.error_message != "任务由用户手动停止"  # 明确排除用户手动停止的任务
            ).options(
                joinedload(Task.streams),
                joinedload(Task.models),
                joinedload(Task.sub_tasks)
            ).distinct().all()
            
            if not running_tasks_with_not_started_subtasks:
                logger.info("没有待启动的任务")
                return
            
            logger.info(f"找到 {len(running_tasks_with_not_started_subtasks)} 个运行中但有未启动子任务的任务，任务ID: {[task.id for task in running_tasks_with_not_started_subtasks]}")
            
            # 获取可用节点
            available_nodes = db.query(Node).filter(
                Node.service_status == "online",
                Node.is_active == True,
                Node.service_type == 1  # 分析服务
            ).all()
            
            if not available_nodes:
                logger.warning("没有可用的分析服务节点，无法启动任务")
                return
            
            logger.info(f"可用节点: {[f'{node.id}({node.ip}:{node.port})' for node in available_nodes]}")
            
            # 导入task_crud
            from crud import task as task_crud
            
            started_count = 0
            for task in running_tasks_with_not_started_subtasks:
                try:
                    # 打印任务详情
                    logger.info(f"任务 {task.id} 信息: 状态={task.status}, 子任务数={len(task.sub_tasks)}, 错误消息={task.error_message}")
                    
                    # 打印子任务状态
                    subtask_status = {}
                    for subtask in task.sub_tasks:
                        status = subtask.status
                        if status not in subtask_status:
                            subtask_status[status] = 0
                        subtask_status[status] += 1
                    
                    logger.info(f"任务 {task.id} 的子任务状态分布: {subtask_status}")
                    
                    # 只有主任务为运行中状态(1)时才启动子任务
                    if task.status == 1:
                        logger.info(f"开始启动任务 {task.id}")
                        success, message = await task_crud.start_task(db, task.id)
                        if success:
                            logger.info(f"任务 {task.id} 启动成功: {message}")
                            started_count += 1
                        else:
                            logger.error(f"任务 {task.id} 启动失败: {message}")
                    else:
                        logger.info(f"任务 {task.id} 状态为 {task.status}，不是运行中状态，跳过启动")
                except Exception as e:
                    logger.error(f"启动任务 {task.id} 时出错: {str(e)}")
                    import traceback
                    logger.error(traceback.format_exc())
            
            logger.info(f"总启动情况：{started_count}/{len(running_tasks_with_not_started_subtasks)} 个任务启动成功")
            
        except Exception as e:
            logger.error(f"处理待启动任务时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

    async def _handle_node_recovery(self, db: Session, recovered_nodes: List[Node]):
        """
        处理节点恢复在线的情况，重新分配子任务
        
        参数:
        - db: 数据库会话
        - recovered_nodes: 可用的节点列表
        """
        try:
            logger.info(f"处理任务分配，当前有 {len(recovered_nodes)} 个可用节点...")
            
            # 从crud导入task模块
            from crud import task as task_crud
            
            # 查找所有需要处理的未启动状态子任务
            # 1. 连接Task表，只处理非用户手动停止的任务
            # 2. 过滤掉Task.status=2且错误消息='任务由用户手动停止'的子任务
            subtasks_to_handle = db.query(SubTask).join(
                Task, SubTask.task_id == Task.id
            ).filter(
                SubTask.status == 0,  # 子任务状态为未启动(0)
                or_(
                    Task.status != 2,  # 主任务非停止状态
                    # 如果主任务是停止状态，确保不是用户手动停止的
                    and_(
                        Task.status == 2,  # 主任务为已停止(2)
                        Task.error_message != "任务由用户手动停止"  # 排除用户手动停止的任务
                    )
                )
            ).all()
            
            if not subtasks_to_handle:
                logger.info("没有未启动状态的子任务需要处理")
                return
            
            logger.info(f"找到 {len(subtasks_to_handle)} 个未启动状态的子任务")
            
            # 对可用节点进行排序
            available_nodes = []
            for node in recovered_nodes:
                # 只选择分析服务节点
                if (node.service_status == "online" and 
                    node.is_active and 
                    node.service_type == 1):  # 1 表示分析服务
                    # 计算当前负载
                    total_tasks = node.image_task_count + node.video_task_count + node.stream_task_count
                    if total_tasks < node.max_tasks:
                        available_nodes.append(node)
            
            if not available_nodes:
                logger.warning("没有可用的分析服务节点，无法处理未启动的子任务")
                return
            
            logger.info(f"有 {len(available_nodes)} 个可用的分析服务节点用于任务分配")
            
            # 按任务分组处理子任务
            subtasks_by_task = {}
            for subtask in subtasks_to_handle:
                if subtask.task_id not in subtasks_by_task:
                    subtasks_by_task[subtask.task_id] = []
                subtasks_by_task[subtask.task_id].append(subtask)
            
            # 为每个任务调用start_task方法
            task_started_count = 0
            for task_id, subtasks in subtasks_by_task.items():
                try:
                    # 再次检查任务状态，确保不处理用户手动停止的任务
                    task = db.query(Task).filter(Task.id == task_id).first()
                    if not task:
                        logger.error(f"找不到任务 {task_id}，跳过")
                        continue
                    
                    # 如果是用户手动停止的任务，跳过处理
                    if task.status == 2 and task.error_message == "任务由用户手动停止":
                        logger.info(f"任务 {task_id} 是用户手动停止的，跳过处理")
                        continue
                    
                    logger.info(f"准备启动任务 {task_id}，包含 {len(subtasks)} 个未启动的子任务")
                    
                    # 只有当运行中状态(1)的主任务才尝试启动子任务
                    if task.status == 1:
                        # 直接启动任务
                        success, message = await task_crud.start_task(db, task_id)
                        if success:
                            logger.info(f"任务 {task_id} 启动成功: {message}")
                            task_started_count += 1
                        else:
                            logger.error(f"任务 {task_id} 启动失败: {message}")
                    else:
                        logger.info(f"任务 {task_id} 状态为 {task.status}，不是运行中状态，跳过启动")
                
                except Exception as e:
                    logger.error(f"处理任务 {task_id} 时发生错误: {str(e)}")
                    import traceback
                    logger.error(traceback.format_exc())
            
            logger.info(f"总计处理了 {len(subtasks_by_task)} 个任务，成功启动了 {task_started_count} 个")
            
        except Exception as e:
            logger.error(f"处理未启动子任务时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

# 创建健康检查器实例
health_checker = NodeHealthChecker()

# 启动健康检查服务的协程函数
async def start_health_checker():
    """启动节点健康检查服务"""
    global health_checker
    
    try:
        logger.info("正在启动节点健康检查服务...")
        # 从配置文件获取健康检查间隔时间，默认为5分钟
        from core.config import settings
        check_interval = int(settings.config.get('HEALTH_CHECK', {}).get('interval', 20))
        logger.info(f"节点健康检查间隔: {check_interval}秒")
        
        # 创建健康检查器
        health_checker = NodeHealthChecker(check_interval=check_interval)
        
        # 以非阻塞方式启动健康检查任务
        try:
            # 不使用await，避免阻塞启动过程
            asyncio.create_task(health_checker.start())
            logger.info("节点健康检查服务已启动")
        except Exception as e:
            logger.error(f"启动健康检查任务失败: {e}")
            logger.error(traceback.format_exc())
            # 即使启动任务失败，也返回健康检查器，允许手动调用方法
        
        return health_checker
    except Exception as e:
        logger.error(f"创建健康检查器失败: {e}")
        logger.error(traceback.format_exc())
        # 出现异常时创建一个基本的健康检查器，确保服务可以继续运行
        try:
            health_checker = NodeHealthChecker(check_interval=300)  # 默认5分钟
            logger.info("已创建基本健康检查器（由于错误回退）")
            return health_checker
        except:
            logger.critical("无法创建健康检查器，服务可能无法正常工作")
            raise

# 停止健康检查服务的函数
def stop_health_checker():
    """停止节点健康检查服务"""
    health_checker.stop() 