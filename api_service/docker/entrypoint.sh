#!/bin/bash

# 等待数据库初始化
echo "正在等待数据库初始化..."
python -c "
from api_service.services.database import init_db
init_db()
"

# 启动 API 服务
echo "正在启动 API 服务..."
exec uvicorn api_service.app:app \
    --host ${HOST:-0.0.0.0} \
    --port ${PORT:-8001} \
    --workers ${WORKERS:-1} \
    --proxy-headers \
    --forwarded-allow-ips='*' 