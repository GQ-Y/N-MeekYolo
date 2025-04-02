"""
任务处理器
负责执行分析任务并处理结果
"""
import asyncio
import json
import httpx
import os
from typing import Optional, Dict, Any, Set
import logging
from datetime import datetime, timedelta
from analysis_service.core.task_queue import TaskQueue, TaskStatus
from analysis_service.core.detector import YOLODetector
from analysis_service.core.config import settings
import shutil
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

class TaskProcessor:
    """任务处理器"""
    def __init__(self):
        self.task_queue = TaskQueue()
        self.detector = YOLODetector()
        self.is_running = False
        self.results_dir = settings.STORAGE.results_dir
        
        # 并发控制
        self.max_concurrent_tasks = settings.TASK_QUEUE.max_concurrent
        self.running_tasks: Set[str] = set()
        self.task_semaphore = asyncio.Semaphore(self.max_concurrent_tasks)
        
        # CPU密集型任务线程池
        self.thread_pool = ThreadPoolExecutor(
            max_workers=settings.TASK_QUEUE.max_workers,
            thread_name_prefix="TaskWorker"
        )
        
        # 确保结果目录存在
        os.makedirs(self.results_dir, exist_ok=True)
        
    async def start(self):
        """启动处理器"""
        if self.is_running:
            return
            
        self.is_running = True
        logger.info(f"任务处理器启动，最大并发数: {self.max_concurrent_tasks}")
        
        # 启动任务处理循环
        asyncio.create_task(self._process_loop())
        # 启动清理任务
        asyncio.create_task(self.task_queue.start_cleanup_task())
        # 启动监控任务
        asyncio.create_task(self._monitor_tasks())
        
    async def stop(self):
        """停止处理器"""
        self.is_running = False
        logger.info("任务处理器停止")
        
        # 等待所有运行中的任务完成
        if self.running_tasks:
            logger.info(f"等待 {len(self.running_tasks)} 个运行中的任务完成")
            try:
                await asyncio.wait_for(self._wait_running_tasks(), timeout=30)
            except asyncio.TimeoutError:
                logger.warning("等待任务完成超时")
        
        # 关闭线程池
        self.thread_pool.shutdown(wait=True)
        
        # 取消所有运行中的任务
        running_tasks = await self.task_queue.get_running_tasks()
        for task_id in running_tasks:
            await self.task_queue.cancel_task(task_id, "处理器停止")
            
    async def _wait_running_tasks(self):
        """等待所有运行中的任务完成"""
        while self.running_tasks:
            await asyncio.sleep(1)
        
    async def _process_loop(self):
        """任务处理循环"""
        while self.is_running:
            try:
                # 检查是否可以接受新任务
                if len(self.running_tasks) >= self.max_concurrent_tasks:
                    await asyncio.sleep(1)
                    continue
                    
                # 获取下一个任务
                task_data = await self.task_queue.get_next_task()
                if not task_data:
                    await asyncio.sleep(1)
                    continue
                    
                # 使用信号量控制并发
                async with self.task_semaphore:
                    # 处理任务
                    task_id = task_data['id']
                    self.running_tasks.add(task_id)
                    asyncio.create_task(self._handle_task_wrapper(task_data))
                
            except Exception as e:
                logger.error(f"任务处理循环异常: {str(e)}")
                await asyncio.sleep(1)
                
    async def _handle_task_wrapper(self, task_data: Dict[str, Any]):
        """任务处理包装器，确保任务状态正确更新"""
        task_id = task_data['id']
        try:
            await self._handle_task(task_data)
        except Exception as e:
            logger.error(f"任务处理异常: {task_id}, 错误: {str(e)}")
        finally:
            self.running_tasks.remove(task_id)
            
    async def _monitor_tasks(self):
        """监控任务执行状态"""
        while self.is_running:
            try:
                # 检查运行中的任务状态
                for task_id in list(self.running_tasks):
                    task_data = await self.task_queue.get_task(task_id)
                    if not task_data:
                        self.running_tasks.remove(task_id)
                        continue
                        
                    # 检查任务是否超时
                    if self._is_task_timeout(task_data):
                        logger.warning(f"任务执行超时: {task_id}")
                        await self.task_queue.fail_task(
                            task_id,
                            "任务执行超时",
                            task_data
                        )
                        self.running_tasks.remove(task_id)
                        
                # 更新任务处理器状态
                await self._update_processor_status()
                
                await asyncio.sleep(settings.TASK_QUEUE.monitor_interval)
                
            except Exception as e:
                logger.error(f"任务监控异常: {str(e)}")
                await asyncio.sleep(5)
                
    def _is_task_timeout(self, task_data: Dict[str, Any]) -> bool:
        """检查任务是否超时"""
        if not task_data.get('start_time'):
            return False
            
        start_time = datetime.fromisoformat(task_data['start_time'])
        timeout = task_data.get('timeout') or settings.TASK_QUEUE.default_timeout
        return (datetime.now() - start_time).total_seconds() > timeout
        
    async def _update_processor_status(self):
        """更新处理器状态"""
        try:
            status = {
                'running_tasks': len(self.running_tasks),
                'max_concurrent': self.max_concurrent_tasks,
                'is_running': self.is_running,
                'updated_at': datetime.now().isoformat()
            }
            await self.task_queue.update_processor_status(status)
        except Exception as e:
            logger.error(f"更新处理器状态失败: {str(e)}")
            
    async def _handle_task(self, task_data: Dict[str, Any]):
        """处理单个任务"""
        task_id = task_data['id']
        start_time = None
        result_path = None
        
        try:
            # 更新任务开始时间
            start_time = datetime.now()
            task_data['start_time'] = start_time.isoformat()
            await self.task_queue.update_task_status(
                task_id,
                TaskStatus.PROCESSING,
                task_data
            )
            
            logger.info(f"开始处理任务: {task_id}, 任务名称: {task_data.get('task_name', '未命名')}")
            
            # 获取任务参数
            analysis_type = task_data.get('analysis_type')
            model_code = task_data.get('model_code')
            config = task_data.get('config', {})
            
            # 验证必要参数
            if not model_code:
                raise ValueError("模型代码不能为空")
                
            # 执行分析
            result = await self._execute_analysis(analysis_type, task_data)
            
            # 处理结果
            if result:
                # 是否需要保存结果
                if task_data.get('save_result'):
                    result_path = await self._save_result(task_id, result, task_data)
                    task_data['result_path'] = result_path
                    
                # 推送结果
                if task_data.get('enable_callback'):
                    await self._send_callback(task_data, result)
                
                # 更新任务完成状态
                stop_time = datetime.now()
                task_data['stop_time'] = stop_time.isoformat()
                task_data['duration'] = (stop_time - start_time).total_seconds()
                
                await self.task_queue.complete_task(task_id, result, task_data)
                logger.info(f"任务处理完成: {task_id}, 耗时: {task_data['duration']}秒")
            else:
                raise Exception("分析结果为空")
                
        except Exception as e:
            error_msg = str(e)
            logger.error(f"任务处理失败: {task_id}, 错误: {error_msg}")
            
            # 更新失败状态
            if start_time:
                task_data['stop_time'] = datetime.now().isoformat()
                task_data['duration'] = (datetime.now() - start_time).total_seconds()
            task_data['error_message'] = error_msg
            
            await self.task_queue.fail_task(task_id, error_msg, task_data)
            
    async def _execute_analysis(self, analysis_type: str, task_data: Dict[str, Any]) -> Optional[Dict]:
        """执行分析"""
        try:
            config = task_data.get('config', {})
            
            # 提取通用配置
            roi = config.get('roi')  # 感兴趣区域
            categories = config.get('categories')  # 目标类别
            confidence = config.get('confidence', 0.5)  # 置信度阈值
            
            # 更新任务进度
            await self._update_task_progress(task_data['id'], "开始执行分析", 0)
            
            # 使用线程池执行CPU密集型分析任务
            loop = asyncio.get_event_loop()
            if analysis_type == 'image':
                result = await loop.run_in_executor(
                    self.thread_pool,
                    self._run_image_analysis,
                    task_data, roi, categories, confidence
                )
            elif analysis_type == 'video':
                result = await loop.run_in_executor(
                    self.thread_pool,
                    self._run_video_analysis,
                    task_data, roi, categories, confidence
                )
            elif analysis_type == 'stream':
                result = await loop.run_in_executor(
                    self.thread_pool,
                    self._run_stream_analysis,
                    task_data, roi, categories, confidence
                )
            else:
                raise ValueError(f"不支持的分析类型: {analysis_type}")
                
            # 更新任务进度
            await self._update_task_progress(task_data['id'], "分析完成", 100)
            
            return result
                
        except Exception as e:
            logger.error(f"执行分析失败: {str(e)}")
            raise
            
    def _run_image_analysis(self, task_data: Dict, roi: Dict, categories: list, confidence: float) -> Dict:
        """在线程池中执行图片分析"""
        image_url = task_data.get('stream_url')
        if not image_url:
            raise ValueError("图片URL不能为空")
            
        analysis_params = {
            'roi': roi,
            'categories': categories,
            'confidence': confidence,
            'model_code': task_data.get('model_code'),
            **task_data.get('config', {})
        }
            
        result = self.detector.analyze_image_sync(image_url, analysis_params)
        
        return {
            'type': 'image',
            'url': image_url,
            'result': result,
            'config': analysis_params,
            'model_code': task_data.get('model_code'),
            'timestamp': datetime.now().isoformat()
        }
        
    def _run_video_analysis(self, task_data: Dict, roi: Dict, categories: list, confidence: float) -> Dict:
        """在线程池中执行视频分析"""
        video_url = task_data.get('stream_url')
        if not video_url:
            raise ValueError("视频URL不能为空")
            
        analysis_params = {
            'roi': roi,
            'categories': categories,
            'confidence': confidence,
            'model_code': task_data.get('model_code'),
            'output_url': task_data.get('output_url'),
            **task_data.get('config', {})
        }
            
        result = self.detector.analyze_video_sync(video_url, analysis_params)
        
        return {
            'type': 'video',
            'url': video_url,
            'result': result,
            'config': analysis_params,
            'model_code': task_data.get('model_code'),
            'output_url': task_data.get('output_url'),
            'timestamp': datetime.now().isoformat()
        }
        
    def _run_stream_analysis(self, task_data: Dict, roi: Dict, categories: list, confidence: float) -> Dict:
        """在线程池中执行流分析"""
        stream_url = task_data.get('stream_url')
        if not stream_url:
            raise ValueError("流URL不能为空")
            
        analysis_params = {
            'roi': roi,
            'categories': categories,
            'confidence': confidence,
            'model_code': task_data.get('model_code'),
            'output_url': task_data.get('output_url'),
            **task_data.get('config', {})
        }
            
        result = self.detector.analyze_stream_sync(stream_url, analysis_params)
        
        return {
            'type': 'stream',
            'url': stream_url,
            'result': result,
            'config': analysis_params,
            'model_code': task_data.get('model_code'),
            'output_url': task_data.get('output_url'),
            'timestamp': datetime.now().isoformat()
        }
        
    async def _update_task_progress(self, task_id: str, message: str, progress: int):
        """更新任务进度"""
        try:
            await self.task_queue.update_task_progress(task_id, {
                'message': message,
                'progress': progress,
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            logger.warning(f"更新任务进度失败: {task_id}, 错误: {str(e)}")
            
    async def _send_callback(self, task_data: Dict[str, Any], result: Dict):
        """发送回调"""
        callback_urls = task_data.get('callback_urls', '').split(',')
        if not callback_urls:
            return
            
        for url in callback_urls:
            if not url.strip():
                continue
                
            try:
                async with httpx.AsyncClient() as client:
                    callback_data = {
                        'task_id': task_data['id'],
                        'task_name': task_data.get('task_name'),
                        'model_code': task_data.get('model_code'),
                        'analysis_type': task_data.get('analysis_type'),
                        'status': TaskStatus.COMPLETED,
                        'result': result,
                        'start_time': task_data.get('start_time'),
                        'stop_time': task_data.get('stop_time'),
                        'duration': task_data.get('duration'),
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    response = await client.post(
                        url.strip(),
                        json=callback_data,
                        timeout=10.0
                    )
                    
                    if response.status_code != 200:
                        logger.warning(f"回调请求失败: {url}, 状态码: {response.status_code}")
                        
            except Exception as e:
                logger.error(f"发送回调失败: {url}, 错误: {str(e)}")
                # 继续处理下一个回调地址
                continue
            
    async def _save_result(self, task_id: str, result: Dict, task_data: Dict) -> str:
        """保存分析结果"""
        try:
            # 生成结果目录路径
            date_str = datetime.now().strftime("%Y%m%d")
            task_dir = os.path.join(self.results_dir, date_str, task_id)
            os.makedirs(task_dir, exist_ok=True)
            
            # 保存结果元数据
            meta_data = {
                'task_id': task_id,
                'task_name': task_data.get('task_name'),
                'model_code': task_data.get('model_code'),
                'analysis_type': task_data.get('analysis_type'),
                'config': task_data.get('config'),
                'stream_url': task_data.get('stream_url'),
                'start_time': task_data.get('start_time'),
                'stop_time': task_data.get('stop_time'),
                'duration': task_data.get('duration'),
                'created_at': datetime.now().isoformat()
            }
            
            meta_path = os.path.join(task_dir, 'meta.json')
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(meta_data, f, ensure_ascii=False, indent=2)
                
            # 保存分析结果
            result_path = os.path.join(task_dir, 'result.json')
            with open(result_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
                
            # 如果有输出文件，保存文件路径信息
            if task_data.get('output_url'):
                output_meta = {
                    'output_url': task_data['output_url'],
                    'created_at': datetime.now().isoformat()
                }
                output_path = os.path.join(task_dir, 'output.json')
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(output_meta, f, ensure_ascii=False, indent=2)
                    
            logger.info(f"分析结果已保存: {task_dir}")
            return task_dir
            
        except Exception as e:
            logger.error(f"保存分析结果失败: {str(e)}")
            raise
            
    async def _get_result(self, task_id: str) -> Optional[Dict]:
        """获取分析结果"""
        try:
            # 先从Redis缓存获取
            result = await self.task_queue.get_result(task_id)
            if result:
                return result
                
            # 如果缓存中没有，尝试从文件系统获取
            task_data = await self.task_queue.get_task(task_id)
            if not task_data or not task_data.get('result_path'):
                return None
                
            result_path = os.path.join(task_data['result_path'], 'result.json')
            if not os.path.exists(result_path):
                return None
                
            with open(result_path, 'r', encoding='utf-8') as f:
                result = json.load(f)
                
            return result
            
        except Exception as e:
            logger.error(f"获取分析结果失败: {str(e)}")
            return None
            
    async def _cleanup_old_results(self):
        """清理过期的结果文件"""
        try:
            # 获取保留天数配置
            retention_days = settings.STORAGE.result_retention_days
            if retention_days <= 0:
                return
                
            # 计算过期日期
            expire_date = datetime.now() - timedelta(days=retention_days)
            expire_date_str = expire_date.strftime("%Y%m%d")
            
            # 遍历结果目录
            for date_dir in os.listdir(self.results_dir):
                if date_dir <= expire_date_str:
                    dir_path = os.path.join(self.results_dir, date_dir)
                    if os.path.isdir(dir_path):
                        shutil.rmtree(dir_path)
                        logger.info(f"已清理过期结果目录: {dir_path}")
                        
        except Exception as e:
            logger.error(f"清理过期结果失败: {str(e)}") 