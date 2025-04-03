"""
更新任务表结构，适应新的任务创建模式
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
sys.path.append(str(project_root))

import logging
from sqlalchemy import create_engine, text
from shared.config.settings import settings

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_task_tables():
    """更新任务和子任务表结构"""
    engine = None
    try:
        # 创建数据库连接
        engine = create_engine(settings.DATABASE["url"])
        
        logger.info("开始更新任务表结构...")
        
        with engine.begin() as conn:
            # 1. 修改任务表结构 - 简化并调整字段
            logger.info("修改任务表结构...")
            
            # 获取数据库名称
            db_name = settings.DATABASE["database"]
            
            # 首先检查并删除外键约束
            logger.info("检查并删除外键约束...")
            foreign_keys = conn.execute(text(f"""
                SELECT CONSTRAINT_NAME, TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
                FROM information_schema.KEY_COLUMN_USAGE
                WHERE TABLE_SCHEMA = '{db_name}'
                AND REFERENCED_TABLE_NAME IS NOT NULL
                AND TABLE_NAME = 'tasks';
            """)).fetchall()
            
            for fk in foreign_keys:
                logger.info(f"删除外键约束: {fk[0]} 从 {fk[1]}.{fk[2]} 到 {fk[3]}.{fk[4]}")
                conn.execute(text(f"ALTER TABLE {fk[1]} DROP FOREIGN KEY {fk[0]}"))
            
            # 检查当前任务表结构
            current_task_columns = conn.execute(text("""
                SELECT COLUMN_NAME
                FROM information_schema.columns 
                WHERE table_name = 'tasks'
            """)).fetchall()
            current_task_columns = [row[0] for row in current_task_columns]
            
            # 需要移除的字段列表
            remove_columns = [
                'callback_interval', 
                'enable_callback', 
                'config', 
                'node_id', 
                'analysis_task_id'
            ]
            
            # 移除不需要的字段
            for column in remove_columns:
                if column in current_task_columns:
                    logger.info(f"从任务表移除字段: {column}")
                    conn.execute(text(f"ALTER TABLE tasks DROP COLUMN {column}"))
            
            # 调整状态字段定义
            logger.info("调整任务状态字段定义...")
            conn.execute(text("""
                ALTER TABLE tasks 
                MODIFY COLUMN status VARCHAR(50) NOT NULL DEFAULT 'created' 
                COMMENT '任务状态: created(已创建), running(运行中), stopped(已停止), error(错误), no_node(无可用节点)';
            """))
            
            # 添加运行统计字段
            logger.info("添加任务运行统计字段...")
            if 'active_subtasks' not in current_task_columns:
                conn.execute(text("""
                    ALTER TABLE tasks 
                    ADD COLUMN active_subtasks INT NOT NULL DEFAULT 0 
                    COMMENT '运行中的子任务数量';
                """))
            
            if 'total_subtasks' not in current_task_columns:
                conn.execute(text("""
                    ALTER TABLE tasks 
                    ADD COLUMN total_subtasks INT NOT NULL DEFAULT 0 
                    COMMENT '子任务总数量';
                """))
            
            # 2. 检查外键约束并删除
            logger.info("检查子任务表的外键约束...")
            
            subtask_foreign_keys = conn.execute(text(f"""
                SELECT CONSTRAINT_NAME, TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
                FROM information_schema.KEY_COLUMN_USAGE
                WHERE TABLE_SCHEMA = '{db_name}'
                AND REFERENCED_TABLE_NAME IS NOT NULL
                AND TABLE_NAME = 'sub_tasks';
            """)).fetchall()
            
            for fk in subtask_foreign_keys:
                if fk[3] == 'nodes' and fk[4] == 'id':
                    logger.info(f"删除外键约束: {fk[0]} 从 {fk[1]}.{fk[2]} 到 {fk[3]}.{fk[4]}")
                    conn.execute(text(f"ALTER TABLE {fk[1]} DROP FOREIGN KEY {fk[0]}"))
            
            # 3. 修改子任务表结构
            logger.info("修改子任务表结构...")
            
            # 检查当前子任务表结构
            current_subtask_columns = conn.execute(text("""
                SELECT COLUMN_NAME
                FROM information_schema.columns 
                WHERE table_name = 'sub_tasks'
            """)).fetchall()
            current_subtask_columns = [row[0] for row in current_subtask_columns]
            
            # 添加配置字段
            if 'config' not in current_subtask_columns:
                logger.info("添加子任务配置字段...")
                conn.execute(text("""
                    ALTER TABLE sub_tasks 
                    ADD COLUMN config JSON NULL 
                    COMMENT '子任务配置信息(置信度、IOU阈值、ROI设置等)';
                """))
            
            # 添加回调设置字段
            if 'enable_callback' not in current_subtask_columns:
                logger.info("添加子任务回调启用字段...")
                conn.execute(text("""
                    ALTER TABLE sub_tasks 
                    ADD COLUMN enable_callback BOOLEAN NOT NULL DEFAULT FALSE 
                    COMMENT '是否启用回调';
                """))
            
            if 'callback_url' not in current_subtask_columns:
                logger.info("添加子任务回调URL字段...")
                conn.execute(text("""
                    ALTER TABLE sub_tasks 
                    ADD COLUMN callback_url VARCHAR(255) NULL 
                    COMMENT '回调URL';
                """))
            
            # 添加节点字段
            if 'node_id' not in current_subtask_columns:
                logger.info("添加子任务节点ID字段...")
                conn.execute(text("""
                    ALTER TABLE sub_tasks 
                    ADD COLUMN node_id INT NULL 
                    COMMENT '节点ID';
                """))
            
            # 添加ROI类型字段
            if 'roi_type' not in current_subtask_columns:
                logger.info("添加ROI类型字段...")
                conn.execute(text("""
                    ALTER TABLE sub_tasks 
                    ADD COLUMN roi_type SMALLINT NOT NULL DEFAULT 0 
                    COMMENT 'ROI类型: 0-无ROI, 1-矩形, 2-多边形, 3-线段';
                """))
            
            # 添加分析类型字段
            if 'analysis_type' not in current_subtask_columns:
                logger.info("添加分析类型字段...")
                conn.execute(text("""
                    ALTER TABLE sub_tasks 
                    ADD COLUMN analysis_type VARCHAR(50) NOT NULL DEFAULT 'detection' 
                    COMMENT '分析类型: detection, tracking, counting等';
                """))
            
            # 创建索引
            logger.info("创建索引...")
            try:
                conn.execute(text("""
                    CREATE INDEX idx_subtask_node_id ON sub_tasks (node_id);
                """))
            except Exception as e:
                if "Duplicate key name" in str(e):
                    logger.info("索引 idx_subtask_node_id 已存在，跳过创建")
                else:
                    logger.warning(f"创建索引时出错: {str(e)}")
            
            # 4. 添加外键约束
            logger.info("添加新的外键约束...")
            
            # 添加节点外键约束
            try:
                conn.execute(text("""
                    ALTER TABLE sub_tasks 
                    ADD CONSTRAINT fk_subtasks_node 
                    FOREIGN KEY (node_id) REFERENCES nodes(id) 
                    ON DELETE SET NULL;
                """))
                logger.info("成功添加外键约束 fk_subtasks_node")
            except Exception as e:
                if "Duplicate key name" in str(e) or "already exists" in str(e):
                    logger.info("外键约束 fk_subtasks_node 已存在，跳过创建")
                else:
                    logger.warning(f"添加外键约束时出错: {str(e)}")
            
            logger.info("表结构更新完成！")
            
        logger.info("现在确认最终结构...")
        # 确认最终表结构
        with engine.connect() as conn:
            # 查看任务表结构
            logger.info("任务表最终结构：")
            result = conn.execute(text("DESC tasks;"))
            for row in result:
                logger.info(f"字段: {row[0]}, 类型: {row[1]}, 可空: {row[2]}, 键: {row[3]}, 默认值: {row[4]}, 扩展: {row[5]}")
            
            # 查看子任务表结构
            logger.info("子任务表最终结构：")
            result = conn.execute(text("DESC sub_tasks;"))
            for row in result:
                logger.info(f"字段: {row[0]}, 类型: {row[1]}, 可空: {row[2]}, 键: {row[3]}, 默认值: {row[4]}, 扩展: {row[5]}")
        
    except Exception as e:
        logger.error(f"更新失败: {str(e)}")
        raise
    finally:
        if engine:
            engine.dispose()

if __name__ == "__main__":
    update_task_tables() 