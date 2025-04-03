"""
数据库迁移脚本：将任务和子任务的字符串状态迁移为数字状态

任务状态对应关系：
- 未启动(0): created, pending, no_node, starting
- 运行中(1): running
- 已停止(2): stopped, completed, error

子任务状态对应关系：
- 未启动(0): created, pending, no_node
- 运行中(1): running
- 已停止(2): stopped, completed, error
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import SessionLocal
from sqlalchemy.sql import text
from sqlalchemy import update, Column, Integer
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    logger.info("开始迁移任务状态...")
    db = SessionLocal()
    
    try:
        # 检查是否已经是整数类型
        try:
            # 尝试查询任务表的第一条记录的status字段
            result = db.execute(text("SELECT status FROM tasks LIMIT 1")).fetchone()
            status_value = result[0] if result else None
            
            # 如果已经是整数类型，提示并退出
            if isinstance(status_value, int):
                logger.info("任务状态已经是整数类型，无需迁移")
                return
        except Exception as e:
            logger.warning(f"检查任务状态类型时出错: {str(e)}")
        
        # 先进行数据库类型迁移，修改列类型
        try:
            logger.info("更新任务表状态字段类型为INTEGER...")
            db.execute(text("""
                UPDATE tasks
                SET status = CASE 
                    WHEN status IN ('created', 'pending', 'no_node', 'starting') THEN 0
                    WHEN status = 'running' THEN 1
                    WHEN status IN ('stopped', 'completed', 'error') THEN 2
                    ELSE 0
                END
            """))
            
            db.execute(text("""
                ALTER TABLE tasks
                MODIFY COLUMN status INTEGER
            """))
            
            logger.info("更新子任务表状态字段类型为INTEGER...")
            db.execute(text("""
                UPDATE sub_tasks
                SET status = CASE 
                    WHEN status IN ('created', 'pending', 'no_node') THEN 0
                    WHEN status = 'running' THEN 1
                    WHEN status IN ('stopped', 'completed', 'error') THEN 2
                    ELSE 0
                END
            """))
            
            db.execute(text("""
                ALTER TABLE sub_tasks
                MODIFY COLUMN status INTEGER
            """))
            
            # 提交事务
            db.commit()
            logger.info("数据库表结构迁移完成")
            
        except Exception as e:
            db.rollback()
            logger.error(f"数据库表结构迁移失败: {str(e)}")
            raise
        
        # 数据清洗：确保所有记录都按照三态模型正确分类
        try:
            # 获取当前任务状态统计
            task_stats = db.execute(text("SELECT status, COUNT(*) FROM tasks GROUP BY status")).fetchall()
            logger.info(f"任务状态统计: {task_stats}")
            
            subtask_stats = db.execute(text("SELECT status, COUNT(*) FROM sub_tasks GROUP BY status")).fetchall()
            logger.info(f"子任务状态统计: {subtask_stats}")
            
            # 确保没有无效的状态值
            db.execute(text("UPDATE tasks SET status = 0 WHERE status NOT IN (0, 1, 2)"))
            db.execute(text("UPDATE sub_tasks SET status = 0 WHERE status NOT IN (0, 1, 2)"))
            
            # 用户手动停止的任务处理
            db.execute(text("""
                UPDATE tasks
                SET status = 2
                WHERE error_message = '任务由用户手动停止'
            """))
            
            # 子任务用户停止处理
            db.execute(text("""
                UPDATE sub_tasks
                SET status = 2
                WHERE error_message = '子任务由用户手动停止'
            """))
            
            # 再次检查状态统计
            task_stats_after = db.execute(text("SELECT status, COUNT(*) FROM tasks GROUP BY status")).fetchall()
            logger.info(f"迁移后任务状态统计: {task_stats_after}")
            
            subtask_stats_after = db.execute(text("SELECT status, COUNT(*) FROM sub_tasks GROUP BY status")).fetchall()
            logger.info(f"迁移后子任务状态统计: {subtask_stats_after}")
            
            # 提交事务
            db.commit()
            logger.info("数据清洗完成")
            
        except Exception as e:
            db.rollback()
            logger.error(f"数据清洗失败: {str(e)}")
            raise
        
        logger.info("迁移完成！所有任务和子任务状态已成功迁移到数字状态")
        
    except Exception as e:
        logger.error(f"迁移过程中发生错误: {str(e)}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    main() 