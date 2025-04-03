-- 添加节点资源使用率相关字段
ALTER TABLE nodes
ADD COLUMN cpu_usage FLOAT NOT NULL DEFAULT 0 COMMENT 'CPU占用率',
ADD COLUMN gpu_usage FLOAT NOT NULL DEFAULT 0 COMMENT 'GPU占用率';

-- 确认字段添加成功
SELECT column_name, data_type, column_comment
FROM information_schema.columns
WHERE table_schema = DATABASE() AND table_name = 'nodes'
  AND column_name IN ('cpu_usage', 'gpu_usage', 'memory_usage', 'gpu_memory_usage'); 