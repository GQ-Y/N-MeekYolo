#!/bin/bash

# 设置颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 服务端口列表
PORTS=(8000 8001 8002 8003 8004)
SERVICE_NAMES=("Gateway" "API" "Analysis" "Model" "Cloud")

# 函数：杀掉指定端口的进程
kill_port_process() {
    local port=$1
    local service_name=$2
    
    # 查找使用该端口的进程
    local pid=$(lsof -ti :$port)
    
    if [ ! -z "$pid" ]; then
        echo -e "${YELLOW}发现 $service_name 服务进程 (PID: $pid) 在端口 $port${NC}"
        echo -e "${YELLOW}正在终止进程...${NC}"
        kill -9 $pid 2>/dev/null
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}成功终止 $service_name 服务进程${NC}"
        else
            echo -e "${RED}终止 $service_name 服务进程失败${NC}"
        fi
    else
        echo -e "${GREEN}端口 $port ($service_name) 没有运行中的进程${NC}"
    fi
}

# 函数：杀掉 Python 相关进程
kill_python_processes() {
    echo -e "${YELLOW}正在查找 Python 相关进程...${NC}"
    
    # 查找包含特定服务名的 Python 进程
    local pids=$(ps aux | grep -E "uvicorn.*:(8000|8001|8002|8003|8004)" | grep -v grep | awk '{print $2}')
    
    if [ ! -z "$pids" ]; then
        echo -e "${YELLOW}发现以下 Python 进程:${NC}"
        ps aux | grep -E "uvicorn.*:(8000|8001|8002|8003|8004)" | grep -v grep
        
        echo -e "${YELLOW}正在终止这些进程...${NC}"
        for pid in $pids; do
            kill -9 $pid 2>/dev/null
            if [ $? -eq 0 ]; then
                echo -e "${GREEN}成功终止进程 $pid${NC}"
            else
                echo -e "${RED}终止进程 $pid 失败${NC}"
            fi
        done
    else
        echo -e "${GREEN}没有发现相关的 Python 进程${NC}"
    fi
}

echo -e "${YELLOW}开始清理服务进程...${NC}"

# 先杀掉所有端口上的进程
for i in "${!PORTS[@]}"; do
    kill_port_process "${PORTS[$i]}" "${SERVICE_NAMES[$i]}"
done

# 再清理可能残留的 Python 进程
kill_python_processes

echo -e "${GREEN}服务进程清理完成${NC}"
echo -e "${GREEN}现在可以重新启动服务了${NC}" 