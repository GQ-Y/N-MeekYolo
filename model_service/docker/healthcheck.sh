#!/bin/bash
set -e

# 检查服务健康状态
if curl -f http://localhost:8003/health; then
    exit 0
fi

exit 1 