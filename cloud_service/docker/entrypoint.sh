#!/bin/bash

# 等待数据库初始化
echo "正在等待数据库初始化..."
python -c "
from cloud_service.services.database import init_db
init_db()
"

# 启动服务
echo "正在启动 Cloud 服务..."
exec uvicorn cloud_service.app:app \
    --host ${HOST:-0.0.0.0} \
    --port ${PORT:-8004} \
    --workers ${WORKERS:-1} \
    --proxy-headers \
    --forwarded-allow-ips='*' 