#!/bin/bash

# 设置环境变量禁止生成 __pycache__
export PYTHONDONTWRITEBYTECODE=1

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 停止服务函数
stop_services() {
    echo -e "${YELLOW}正在停止所有服务...${NC}"
    
    # 查找并终止所有uvicorn进程
    pids=$(ps aux | grep 'uvicorn' | grep -v grep | awk '{print $2}')
    if [ -n "$pids" ]; then
        echo -e "${YELLOW}找到以下服务进程:${NC}"
        ps aux | grep 'uvicorn' | grep -v grep
        echo -e "${YELLOW}正在终止进程...${NC}"
        echo $pids | xargs kill -9
        echo -e "${GREEN}所有服务已停止${NC}"
    else
        echo -e "${YELLOW}未发现运行中的服务${NC}"
    fi
}

# 清理缓存函数
clean_cache() {
    echo -e "${YELLOW}正在清理Python缓存文件...${NC}"
    
    # 查找并删除所有 __pycache__ 目录
    find . -type d -name "__pycache__" -exec rm -r {} +
    
    # 查找并删除所有 .pyc 文件
    find . -type f -name "*.pyc" -delete
    
    # 查找并删除所有 .pyo 文件
    find . -type f -name "*.pyo" -delete
    
    # 查找并删除所有 .pyd 文件
    find . -type f -name "*.pyd" -delete
    
    echo -e "${GREEN}缓存清理完成${NC}"
}

# 解析命令行参数
case "$1" in
    "stop")
        stop_services
        exit 0
        ;;
    "start")
        # 继续执行启动逻辑
        ;;
    "clean")
        clean_cache
        exit 0
        ;;
    *)
        echo -e "${YELLOW}用法: $0 {start|stop|clean}${NC}"
        echo -e "  start - 启动所有服务"
        echo -e "  stop  - 停止所有服务"
        echo -e "  clean - 清理Python缓存文件"
        exit 1
        ;;
esac

# 创建日志目录
if [ ! -d "logs" ]; then
    mkdir logs
    echo -e "${GREEN}已创建日志目录${NC}"
fi

# 启动网关服务
echo -e "${GREEN}正在启动网关服务...${NC}"
python -m uvicorn gateway.app:app --host 0.0.0.0 --port 8000 > logs/gateway_service.log 2>&1 &
echo -e "${GREEN}网关服务已启动 - 端口 8000${NC}"

# 启动API服务
echo -e "${GREEN}正在启动API服务...${NC}"
python -m uvicorn api_service.app:app --host 0.0.0.0 --port 8001 > logs/api_service.log 2>&1 &
echo -e "${GREEN}API服务已启动 - 端口 8001${NC}"

# 启动模型服务
echo -e "${GREEN}正在启动模型服务...${NC}"
python -m uvicorn model_service.app:app --host 0.0.0.0 --port 8002 > logs/model_service.log 2>&1 &
echo -e "${GREEN}模型服务已启动 - 端口 8002${NC}"

# 启动分析服务
echo -e "${GREEN}正在启动分析服务...${NC}"
python -m uvicorn analysis_service.app:app --host 0.0.0.0 --port 8003 > logs/analysis_service.log 2>&1 &
echo -e "${GREEN}分析服务已启动 - 端口 8003${NC}"

# 启动云服务
echo -e "${GREEN}正在启动云服务...${NC}"
python -m uvicorn cloud_service.app:app --host 0.0.0.0 --port 8004 > logs/cloud_service.log 2>&1 &
echo -e "${GREEN}云服务已启动 - 端口 8004${NC}"

# 等待所有服务启动
sleep 2

# 检查服务状态
check_service() {
    local port=$1
    local name=$2
    if curl -s http://localhost:$port/health > /dev/null; then
        echo -e "${GREEN}✓ $name 运行正常${NC}"
    else
        echo -e "${RED}✗ $name 启动失败${NC}"
    fi
}

echo -e "\n${YELLOW}正在检查服务状态...${NC}"
check_service 8000 "网关服务"
check_service 8001 "API服务"
check_service 8002 "模型服务"
check_service 8003 "分析服务"
check_service 8004 "云服务"

echo -e "\n${GREEN}所有服务启动完成!${NC}"
echo -e "${YELLOW}提示:${NC}"
echo -e "  - API文档: http://localhost:8000/docs"
echo -e "  - 管理面板: http://localhost:8000/admin"
echo -e "  - 查看日志: tail -f logs/*.log"
echo -e "  - 停止服务: $0 stop\n" 