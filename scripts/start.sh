#!/bin/bash

# 设置环境变量禁止生成 __pycache__
export PYTHONDONTWRITEBYTECODE=1

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查并设置Python虚拟环境
setup_virtual_env() {
    # 检查是否已在虚拟环境中
    if [ -n "$VIRTUAL_ENV" ]; then
        echo -e "${GREEN}已在Python虚拟环境中: $VIRTUAL_ENV${NC}"
        return 0
    fi

    # 检查项目根目录下是否存在venv
    if [ -d "venv" ]; then
        echo -e "${YELLOW}发现已存在的虚拟环境，正在激活...${NC}"
        source venv/bin/activate
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}虚拟环境激活成功${NC}"
            return 0
        else
            echo -e "${RED}虚拟环境激活失败${NC}"
            return 1
        fi
    fi

    # 创建新的虚拟环境
    echo -e "${YELLOW}正在创建新的Python虚拟环境...${NC}"
    python -m venv venv
    if [ $? -ne 0 ]; then
        echo -e "${RED}虚拟环境创建失败${NC}"
        return 1
    fi

    echo -e "${YELLOW}正在激活虚拟环境...${NC}"
    source venv/bin/activate
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}虚拟环境创建并激活成功${NC}"
        # 升级pip
        pip install --upgrade pip > /dev/null 2>&1
        return 0
    else
        echo -e "${RED}虚拟环境激活失败${NC}"
        return 1
    fi
}

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

# 检查并安装依赖函数
check_dependencies() {
    local service=$1
    echo -e "${YELLOW}正在检查 ${service} 的依赖...${NC}"
    
    # 检查requirements.txt是否存在
    if [ ! -f "${service}/requirements.txt" ]; then
        echo -e "${RED}错误: ${service}/requirements.txt 不存在${NC}"
        return 1
    fi
    
    # 检查requirements.lock是否存在
    if [ -f "${service}/requirements.lock" ]; then
        echo -e "${GREEN}${service} 依赖已安装 (发现requirements.lock)${NC}"
        return 0
    fi
    
    echo -e "${YELLOW}正在安装 ${service} 的依赖...${NC}"
    
    # 创建虚拟环境并安装依赖
    python -m venv "${service}/.venv" 2>/dev/null || true
    source "${service}/.venv/bin/activate"
    
    if pip install -r "${service}/requirements.txt"; then
        # 安装成功后生成lock文件
        pip freeze > "${service}/requirements.lock"
        deactivate
        echo -e "${GREEN}${service} 依赖安装完成${NC}"
        return 0
    else
        deactivate
        echo -e "${RED}${service} 依赖安装失败${NC}"
        return 1
    fi
}

# 主程序开始

# 首先设置虚拟环境
if ! setup_virtual_env; then
    echo -e "${RED}无法设置Python虚拟环境，退出启动${NC}"
    exit 1
fi

# 解析命令行参数
case "$1" in
    "stop")
        stop_services
        deactivate 2>/dev/null  # 退出虚拟环境
        exit 0
        ;;
    "start")
        # 继续执行启动逻辑
        ;;
    "clean")
        clean_cache
        deactivate 2>/dev/null  # 退出虚拟环境
        exit 0
        ;;
    *)
        echo -e "${YELLOW}用法: $0 {start|stop|clean}${NC}"
        echo -e "  start - 启动所有服务"
        echo -e "  stop  - 停止所有服务"
        echo -e "  clean - 清理Python缓存文件"
        deactivate 2>/dev/null  # 退出虚拟环境
        exit 1
        ;;
esac

# 创建日志目录
if [ ! -d "logs" ]; then
    mkdir logs
    echo -e "${GREEN}已创建日志目录${NC}"
fi

# 检查所有服务的依赖
echo -e "${YELLOW}正在检查所有服务依赖...${NC}"
services=("gateway" "api_service" "model_service" "analysis_service" "cloud_service")
for service in "${services[@]}"; do
    if ! check_dependencies "$service"; then
        echo -e "${RED}依赖检查失败，退出启动${NC}"
        exit 1
    fi
done
echo -e "${GREEN}所有依赖检查完成${NC}"

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

# 等待其他服务启动
echo -e "${YELLOW}等待其他服务初始化...${NC}"
for i in {10..1}; do
    echo -ne "\r${YELLOW}等待服务初始化中，还需 ${i} 秒...${NC}"
    sleep 1
done
echo -e "\n${GREEN}初始化等待完成${NC}"

# 检查服务状态
check_service() {
    local port=$1
    local name=$2
    if curl -s http://localhost:$port/health > /dev/null; then
        echo -e "${GREEN}✓ $name 运行正常${NC}"
        return 0
    else
        echo -e "${RED}✗ $name 启动失败${NC}"
        return 1
    fi
}

# 检查所有服务状态
check_all_services() {
    local attempt=$1
    local success=true
    
    echo -e "\n${YELLOW}正在进行第 $attempt 次服务状态检查...${NC}"
    
    check_service 8001 "API服务" || success=false
    check_service 8002 "模型服务" || success=false
    check_service 8003 "分析服务" || success=false
    check_service 8004 "云服务" || success=false
    
    $success
}

# 循环检查服务状态4次
max_attempts=4
attempt=1
success=false

while [ $attempt -le $max_attempts ]; do
    if check_all_services $attempt; then
        success=true
        break
    fi
    
    if [ $attempt -lt $max_attempts ]; then
        echo -e "${YELLOW}等待5秒后进行下一次检查...${NC}"
        sleep 5
    fi
    
    attempt=$((attempt + 1))
done

if ! $success; then
    echo -e "${RED}服务启动检查失败，请检查日志文件了解详细信息${NC}"
    echo -e "${YELLOW}日志文件位置: logs/*.log${NC}"
    exit 1
fi

# 等待1分钟后启动网关
echo -e "${YELLOW}等待60秒后启动网关服务...${NC}"
for i in {60..1}; do
    echo -ne "\r${YELLOW}还需等待 ${i} 秒...${NC}"
    sleep 1
done
echo -e "\n${GREEN}正在启动网关服务...${NC}"
python -m uvicorn gateway.app:app --host 0.0.0.0 --port 8000 > logs/gateway_service.log 2>&1 &
echo -e "${GREEN}网关服务已启动 - 端口 8000${NC}"

# 最后检查网关状态
sleep 2
check_service 8000 "网关服务"

echo -e "\n${GREEN}所有服务启动完成!${NC}"
echo -e "${YELLOW}提示:${NC}"
echo -e "  - API文档: http://localhost:8000/docs"
echo -e "  - 管理面板: http://localhost:8000/admin"
echo -e "  - 查看日志: tail -f logs/*.log"
echo -e "  - 停止服务: $0 stop\n"

# 在脚本结束时添加
trap 'deactivate 2>/dev/null' EXIT  # 确保脚本退出时关闭虚拟环境