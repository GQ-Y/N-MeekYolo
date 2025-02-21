#!/bin/bash
set -e

# 等待依赖服务就绪
wait_for_service() {
    local host="$1"
    local port="$2"
    local service="$3"
    local max_retries=30
    local retry_count=0
    
    echo "Waiting for $service to be ready..."
    while ! nc -z "$host" "$port"; do
        retry_count=$((retry_count+1))
        if [ $retry_count -ge $max_retries ]; then
            echo "Warning: $service is not available after $max_retries attempts"
            # 改为警告而不是错误退出
            return 1
        fi
        echo "Attempt $retry_count/$max_retries: $service is not ready. Retrying..."
        sleep 1
    done
    echo "$service is ready!"
    return 0
}

# 如果配置了Cloud Service，尝试等待但不阻止启动
if [ ! -z "$CLOUD_SERVICE_HOST" ]; then
    if wait_for_service "$CLOUD_SERVICE_HOST" 8004 "Cloud Service"; then
        echo "Successfully connected to Cloud Service"
    else
        echo "Warning: Could not connect to Cloud Service, continuing anyway..."
    fi
fi

# 初始化数据目录
mkdir -p /app/data/models
mkdir -p /app/data/temp
mkdir -p /app/logs

# 启动服务
echo "Starting Model Service..."
exec uvicorn model_service.app:app --host 0.0.0.0 --port 8003 