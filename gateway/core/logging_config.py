"""
日志系统配置
"""
import logging
import sys

# 定义日志格式
LOG_FORMAT = "%(asctime)s - %(levelname)s - [%(name)s] - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 基本配置
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False, # 不禁用已存在的 logger (例如 FastAPI 的)
    "formatters": {
        "standard": {
            "format": LOG_FORMAT,
            "datefmt": DATE_FORMAT,
        },
    },
    "handlers": {
        "console": {
            "level": "INFO", # 控制台输出级别
            "formatter": "standard",
            "class": "logging.StreamHandler",
            "stream": sys.stdout, # 输出到标准输出
        },
        # 可以添加 FileHandler 等其他处理器
        # "file": {
        #     "level": "DEBUG",
        #     "formatter": "standard",
        #     "class": "logging.handlers.RotatingFileHandler",
        #     "filename": "app.log", # 日志文件名
        #     "maxBytes": 10485760, # 10MB
        #     "backupCount": 5,
        #     "encoding": "utf8",
        # },
    },
    "loggers": {
        "": { # Root logger
            "handlers": ["console"], # 默认使用控制台处理器 (可以添加 'file')
            "level": "INFO", # Root logger 级别
            "propagate": False, # 防止日志消息传递给上级 logger (root logger 没有上级)
        },
        "uvicorn.error": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
         "uvicorn.access": {
            "level": "WARNING", # 减少访问日志的冗余度
            "handlers": ["console"],
            "propagate": False,
        },
        # 可以为特定模块设置不同的级别
        # "services.billing_service": {
        #     "level": "DEBUG",
        #     "handlers": ["console"],
        #     "propagate": False,
        # },
    }
}

def setup_logging():
    """应用日志配置"""
    logging.config.dictConfig(LOGGING_CONFIG)
    # logger = logging.getLogger(__name__)
    # logger.info("日志系统配置完成") # 可以在这里加一条日志确认 