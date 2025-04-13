"""
配置常量
"""

# 任务状态
TASK_STATUS_PENDING = 0  # 未启动
TASK_STATUS_RUNNING = 1  # 运行中
TASK_STATUS_STOPPED = 2  # 已停止

# 超时时间设置（秒）
TASK_STOP_TIMEOUT = 30  # 任务停止超时时间，超过这个时间后强制更新任务状态
CONNECTION_TIMEOUT = 10  # 连接超时时间
READ_TIMEOUT = 15  # 读取超时时间

# MQTT配置相关
MQTT_QOS_DEFAULT = 1  # 默认QoS级别
MQTT_RECONNECT_DELAY = 5  # MQTT重连延迟时间（秒）
MQTT_MAX_RECONNECT_ATTEMPTS = 5  # MQTT最大重连尝试次数

# 日志相关
LOG_ROTATION_SIZE = 10 * 1024 * 1024  # 日志轮转大小（10MB）
LOG_BACKUP_COUNT = 10  # 日志备份数量 