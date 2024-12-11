#!/bin/bash

# 获取脚本所在目录的上级目录（项目根目录）
PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"

# 设置环境变量
export CONFIG_PATH="${PROJECT_ROOT}/config/config.yaml"
export PYTHONPATH=$PYTHONPATH:${PROJECT_ROOT}

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 检查目录是否存在
check_directory() {
    if [ ! -d "$1" ]; then
        echo -e "${RED}Error: Directory $1 does not exist${NC}"
        exit 1
    fi
}

# 检查服务是否正在运行
check_service() {
    local port=$1
    local service_name=$2
    local max_retries=30
    local retry_count=0
    
    echo -e "${YELLOW}Waiting for $service_name to start...${NC}"
    while ! nc -z localhost $port && [ $retry_count -lt $max_retries ]; do
        sleep 1
        ((retry_count++))
        echo -n "."
    done
    echo ""
    
    if nc -z localhost $port; then
        echo -e "${GREEN}$service_name is running on port $port${NC}"
        return 0
    else
        echo -e "${RED}$service_name failed to start on port $port${NC}"
        return 1
    fi
}

# 启动网关服务
start_gateway() {
    echo -e "${GREEN}Starting Gateway Service...${NC}"
    check_directory "${PROJECT_ROOT}/gateway"
    cd "${PROJECT_ROOT}/gateway" && \
    uvicorn app:app --host 0.0.0.0 --port 8000 --log-level info \
    > "${PROJECT_ROOT}/logs/gateway_service.log" 2>&1 &
    cd "${PROJECT_ROOT}"
    check_service 8000 "Gateway Service"
}

# 启动API服务
start_api() {
    echo -e "${GREEN}Starting API Service...${NC}"
    check_directory "${PROJECT_ROOT}/api_service"
    cd "${PROJECT_ROOT}/api_service" && \
    uvicorn app:app --host 0.0.0.0 --port 8001 --log-level info \
    > "${PROJECT_ROOT}/logs/api_service.log" 2>&1 &
    cd "${PROJECT_ROOT}"
    check_service 8001 "API Service"
}

# 启动分析服务
start_analysis() {
    echo -e "${GREEN}Starting Analysis Service...${NC}"
    check_directory "${PROJECT_ROOT}/analysis_service"
    cd "${PROJECT_ROOT}/analysis_service" && \
    uvicorn app:app --host 0.0.0.0 --port 8002 --log-level info \
    > "${PROJECT_ROOT}/logs/analysis_service.log" 2>&1 &
    cd "${PROJECT_ROOT}"
    check_service 8002 "Analysis Service"
}

# 启动模型服务
start_model() {
    echo -e "${GREEN}Starting Model Service...${NC}"
    check_directory "${PROJECT_ROOT}/model_service"
    cd "${PROJECT_ROOT}/model_service"
    
    # 检查 Python 环境
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}Error: Python3 is not installed${NC}"
        return 1
    fi
    
    # 检查依赖
    if ! pip list | grep -q "fastapi"; then
        echo -e "${RED}Error: Dependencies not installed. Run: pip install -r requirements.txt${NC}"
        return 1
    fi
    
    # 启动服务并捕获错误
    uvicorn model_service.app:app --host 0.0.0.0 --port 8003 --log-level debug \
    > "${PROJECT_ROOT}/logs/model_service.log" 2>&1 &
    
    local pid=$!
    cd "${PROJECT_ROOT}"
    
    # 检查服务是否启动成功
    if ! check_service 8003 "Model Service"; then
        echo -e "${RED}Error: Model Service failed to start. Check logs for details:${NC}"
        tail -n 20 "${PROJECT_ROOT}/logs/model_service.log"
        return 1
    fi
    
    return 0
}

# 启动云模型市场服务
start_cloud() {
    echo -e "${GREEN}Starting Cloud Model Market Service...${NC}"
    check_directory "${PROJECT_ROOT}/cloud_service"
    cd "${PROJECT_ROOT}/cloud_service"
    
    # 检查 Python 环境
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}Error: Python3 is not installed${NC}"
        return 1
    fi
    
    # 检查依赖
    if ! pip list | grep -q "fastapi"; then
        echo -e "${RED}Error: Dependencies not installed. Run: pip install -r requirements.txt${NC}"
        return 1
    fi
    
    # 启动服务并捕获错误
    uvicorn app:app --host 0.0.0.0 --port 8004 --log-level debug \
    > "${PROJECT_ROOT}/logs/cloud_service.log" 2>&1 &
    
    local pid=$!
    cd "${PROJECT_ROOT}"
    
    # 检查服务是否启动成功
    if ! check_service 8004 "Cloud Model Market Service"; then
        echo -e "${RED}Error: Cloud Model Market Service failed to start. Check logs for details:${NC}"
        tail -n 20 "${PROJECT_ROOT}/logs/cloud_service.log"
        return 1
    fi
    
    return 0
}

# ��示帮助信息
show_help() {
    echo "Usage: ./scripts/start.sh [options]"
    echo "Options:"
    echo "  all        - Start all services"
    echo "  gateway    - Start gateway service"
    echo "  api        - Start API service"
    echo "  analysis   - Start analysis service"
    echo "  model      - Start model service"
    echo "  cloud      - Start cloud model market service"
    echo "  stop       - Stop all services"
    echo "  logs       - View service logs"
    echo "  status     - Check services status"
    echo "  help       - Show this help message"
}

# 停止所有服务
stop_all() {
    echo -e "${BLUE}Stopping all services...${NC}"
    pkill -f "uvicorn app:app"
}

# 检查所有服务状态
check_all_services() {
    echo -e "${BLUE}Checking services status...${NC}"
    check_service 8000 "Gateway Service"
    check_service 8001 "API Service"
    check_service 8002 "Analysis Service"
    check_service 8003 "Model Service"
    check_service 8004 "Cloud Model Market Service"
}

# 添加查看日志的功能
show_logs() {
    service=$1
    if [ -z "$service" ]; then
        tail -f "${PROJECT_ROOT}"/logs/*.log
    else
        tail -f "${PROJECT_ROOT}/logs/${service}_service.log"
    fi
}

# 创建必要的目录
mkdir -p "${PROJECT_ROOT}/logs"
mkdir -p "${PROJECT_ROOT}/models"
mkdir -p "${PROJECT_ROOT}/results"
mkdir -p "${PROJECT_ROOT}/data"

# 检查配置文件
if [ ! -f "${CONFIG_PATH}" ]; then
    echo -e "${RED}Warning: Config file not found at ${CONFIG_PATH}${NC}"
    echo -e "${BLUE}Creating default config file...${NC}"
    mkdir -p "${PROJECT_ROOT}/config"
    cat > "${CONFIG_PATH}" << EOL
# 基础配置
PROJECT_NAME: "MeekYolo Service"
VERSION: "1.0.0"

# 服务配置
SERVICES:
  model:
    host: "localhost"
    port: 8003
  analysis:
    host: "localhost"
    port: 8002
  api:
    host: "localhost"
    port: 8001

# 存储配置
STORAGE:
  base_dir: "models"
  temp_dir: "temp"
  max_size: 1073741824  # 1GB
  allowed_formats: [".pt", ".pth", ".onnx", ".yaml"]

# 分析配置
ANALYSIS:
  confidence: 0.5
  iou: 0.45
  max_det: 300
  device: "auto"

# 输出配置
OUTPUT:
  save_dir: "results"
  save_img: true
  save_txt: false
EOL
fi

# 检查模型文件
MODEL_PATH="${PROJECT_ROOT}/models/yolo/yolov11.pt"
if [ ! -f "${MODEL_PATH}" ]; then
    echo -e "${RED}Error: Model file not found at ${MODEL_PATH}${NC}"
    echo -e "${YELLOW}Please ensure the model file exists before starting services${NC}"
    exit 1
fi

# 根据参数启动服务
case "$1" in
    "all")
        start_model || exit 1
        sleep 2
        start_analysis || exit 1
        sleep 2
        start_api || exit 1
        sleep 2
        start_gateway || exit 1
        sleep 2
        start_cloud || exit 1
        ;;
    "gateway")
        start_gateway
        ;;
    "api")
        start_api
        ;;
    "analysis")
        start_analysis
        ;;
    "model")
        start_model
        ;;
    "cloud")
        start_cloud
        ;;
    "stop")
        stop_all
        ;;
    "logs")
        shift
        show_logs $1
        ;;
    "status")
        check_all_services
        ;;
    "help"|"")
        show_help
        ;;
    *)
        echo "Unknown option: $1"
        show_help
        exit 1
        ;;
esac

# 如果没有stop参数，等待所有后台进程
if [ "$1" != "stop" ] && [ "$1" != "status" ] && [ "$1" != "logs" ]; then
    echo -e "${GREEN}Services are running. Press Ctrl+C to stop.${NC}"
    wait
fi 