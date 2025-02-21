#!/bin/bash

# 确保目录存在
mkdir -p data logs

# 构建并启动服务
docker-compose up --build -d

# 等待服务启动
echo "等待服务启动..."
sleep 5

# 检查服务状态
docker-compose ps

# 显示日志
docker-compose logs -f 