#!/bin/bash

# 检查服务是否响应
response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health)

if [ "$response" = "200" ]; then
    exit 0
else
    exit 1
fi 