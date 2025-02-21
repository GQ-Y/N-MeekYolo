#!/bin/bash

# 启动服务
echo "正在启动 Gateway 服务..."
exec uvicorn gateway.app:app \
    --host ${HOST:-0.0.0.0} \
    --port ${PORT:-8000} \
    --workers ${WORKERS:-1} \
    --proxy-headers \
    --forwarded-allow-ips='*' 