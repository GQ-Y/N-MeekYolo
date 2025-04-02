import asyncio
import aiohttp
import base64
import json
import time
from typing import Dict
import logging
from datetime import datetime

# 配置更详细的日志格式
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d - %(levelname)s - [任务%(task_id)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class TaskContext:
    def __init__(self, task_id: int):
        self.task_id = task_id
        self.extra = {'task_id': task_id if task_id else '主线程'}
        self._start_time = None
        
    def __enter__(self):
        self._start_time = time.time()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._start_time:
            duration = time.time() - self._start_time
            logger.info(f"任务耗时: {duration:.2f}秒", extra=self.extra)

async def analyze_single_image(session: aiohttp.ClientSession, image_path: str, model_code: str, task_id: int) -> Dict:
    """分析单张图片

    Args:
        session: aiohttp会话
        image_path: 图片路径
        model_code: 模型代码
        task_id: 任务ID

    Returns:
        Dict: 分析结果
    """
    extra = {'task_id': task_id}
    with TaskContext(task_id):
        try:
            # 读取图片并转换为base64
            logger.info("开始读取图片", extra=extra)
            with open(image_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
            
            # 准备请求数据
            data = {
                "model_code": model_code,
                "image_urls": [f"data:image/jpeg;base64,{image_data}"],
                "is_base64": True,
                "save_result": True
            }
            
            logger.info("开始发送分析请求", extra=extra)
            start_time = time.time()
            
            # 发送请求
            async with session.post('http://localhost:8002/api/v1/analyze/image', json=data) as response:
                if response.status != 200:
                    logger.error(f"请求失败: HTTP {response.status}", extra=extra)
                    return {"error": f"HTTP错误: {response.status}", "task_id": task_id}
                
                result = await response.json()
                process_time = time.time() - start_time
                logger.info(f"请求完成，服务端处理耗时: {process_time:.2f}秒", extra=extra)
                return {"result": result, "task_id": task_id, "process_time": process_time}
                
        except Exception as e:
            logger.error(f"发生错误: {str(e)}", extra=extra)
            return {"error": str(e), "task_id": task_id}

async def test_concurrent_analysis(image_path: str = "test.jpg", concurrent_count: int = 30):
    """并发测试图片分析

    Args:
        image_path: 测试图片路径
        concurrent_count: 并发请求数量
    """
    with TaskContext(None):
        logger.info(f"开始并发测试 - 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", extra={'task_id': '主线程'})
        logger.info(f"并发数量: {concurrent_count}, 测试图片: {image_path}", extra={'task_id': '主线程'})
        
        start_time = time.time()
        
        async with aiohttp.ClientSession() as session:
            # 创建多个并发任务
            tasks = [
                analyze_single_image(session, image_path, "model-gcc", i+1) 
                for i in range(concurrent_count)
            ]
            
            logger.info(f"已创建 {len(tasks)} 个任务，开始并发执行", extra={'task_id': '主线程'})
            results = await asyncio.gather(*tasks)
            
            # 统计结果
            success_count = sum(1 for r in results if "error" not in r)
            error_count = sum(1 for r in results if "error" in r)
            
            # 计算处理时间统计
            process_times = [r.get("process_time", 0) for r in results if "process_time" in r]
            avg_process_time = sum(process_times) / len(process_times) if process_times else 0
            max_process_time = max(process_times) if process_times else 0
            min_process_time = min(process_times) if process_times else 0
            
            # 输出统计信息
            total_time = time.time() - start_time
            logger.info(f"""
测试结果统计:
----------------------------------------
总请求数: {len(results)}
成功数量: {success_count}
失败数量: {error_count}
----------------------------------------
时间统计:
- 总耗时: {total_time:.2f}秒
- 平均处理时间: {avg_process_time:.2f}秒
- 最长处理时间: {max_process_time:.2f}秒
- 最短处理时间: {min_process_time:.2f}秒
- 实际并发吞吐量: {len(results)/total_time:.2f}请求/秒
----------------------------------------""", extra={'task_id': '主线程'})
            
            # 输出详细结果
            logger.info("各任务详细结果:", extra={'task_id': '主线程'})
            for result in results:
                task_id = result.get('task_id')
                if "error" in result:
                    logger.error(f"任务失败 - {result['error']}", extra={'task_id': task_id})
                else:
                    logger.info(
                        f"任务成功 - 处理时间: {result['process_time']:.2f}秒\n"
                        f"分析结果: {json.dumps(result['result'], indent=2, ensure_ascii=False)}",
                        extra={'task_id': task_id}
                    )

if __name__ == "__main__":
    asyncio.run(test_concurrent_analysis()) 