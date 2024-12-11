#!/bin/bash

# 设置环境变量
export PYTHONPATH=$PYTHONPATH:$(pwd)

# 创建日志目录
mkdir -p logs

# 启动服务
uvicorn cloud_service.app:app \
    --host ${CLOUD_HOST:-0.0.0.0} \
    --port ${CLOUD_PORT:-8004} \
    --reload \
    --log-config config/logging.yaml 