#!/bin/bash

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 日志目录
LOG_DIR="$PROJECT_ROOT/logs"

# 记录日志
log() {
    local level=$1
    local message=$2
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "$timestamp [$level] $message" >> "$LOG_DIR/shutdown.log"
    case $level in
        "INFO")  echo -e "${GREEN}$message${NC}" ;;
        "WARN")  echo -e "${YELLOW}$message${NC}" ;;
        "ERROR") echo -e "${RED}$message${NC}" ;;
        *)       echo -e "$message" ;;
    esac
}

# 停止服务函数
stop_services() {
    log "INFO" "Stopping all services..."
    
    # 查找所有uvicorn进程
    local pids=$(ps aux | grep 'uvicorn' | grep -v grep | awk '{print $2}')
    
    if [ -n "$pids" ]; then
        log "INFO" "Found running services:"
        ps aux | grep 'uvicorn' | grep -v grep
        
        log "INFO" "Sending SIGTERM to all services..."
        echo $pids | xargs kill -15
        
        # 等待进程结束
        local wait_time=0
        local max_wait=10
        while [ $wait_time -lt $max_wait ]; do
            if ! ps -p $pids > /dev/null 2>&1; then
                log "INFO" "All services stopped gracefully"
                return 0
            fi
            sleep 1
            ((wait_time++))
        done
        
        # 如果进程还在运行，强制结束
        log "WARN" "Some services did not stop gracefully, forcing shutdown..."
        echo $pids | xargs kill -9 2>/dev/null
    else
        log "INFO" "No running services found"
    fi
}

# 清理缓存函数
clean_cache() {
    log "INFO" "Cleaning Python cache files..."
    find . -type d -name "__pycache__" -exec rm -r {} + 2>/dev/null
    find . -type f -name "*.pyc" -delete
    find . -type f -name "*.pyo" -delete
    find . -type f -name "*.pyd" -delete
    log "INFO" "Cache cleaning completed"
}

# 主程序开始
mkdir -p "$LOG_DIR"

# 停止所有服务
stop_services

# 清理缓存
clean_cache

# 退出虚拟环境（如果在虚拟环境中）
if [ -n "$VIRTUAL_ENV" ]; then
    log "INFO" "Deactivating virtual environment..."
    deactivate 2>/dev/null
fi

log "INFO" "Shutdown completed successfully"