#!/bin/bash

# 设置环境变量禁止生成 __pycache__
export PYTHONDONTWRITEBYTECODE=1

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 日志目录
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"

# 日志文件
STARTUP_LOG="$LOG_DIR/startup.log"

# 函数: 记录日志
log() {
    local level=$1
    local message=$2
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "$timestamp [$level] $message" >> "$STARTUP_LOG"
    case $level in
        "INFO")  echo -e "${GREEN}$message${NC}" ;;
        "WARN")  echo -e "${YELLOW}$message${NC}" ;;
        "ERROR") echo -e "${RED}$message${NC}" ;;
        *)       echo -e "$message" ;;
    esac
}

# 函数: 检查端口是否被占用
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null ; then
        return 1
    fi
    return 0
}

# 函数: 等待服务启动
wait_for_service() {
    local name=$1
    local port=$2
    local max_retries=30
    local retries=0
    
    log "INFO" "Waiting for $name to be ready..."
    while ! curl -s "http://localhost:$port/health" > /dev/null && [ $retries -lt $max_retries ]; do
        sleep 1
        ((retries++))
        if [ $((retries % 5)) -eq 0 ]; then
            log "WARN" "Still waiting for $name... ($retries/$max_retries)"
        fi
    done
    
    if [ $retries -lt $max_retries ]; then
        log "INFO" "$name is ready"
        return 0
    else
        log "ERROR" "$name failed to start"
        return 1
    fi
}

# 函数: 启动服务
start_service() {
    local name=$1
    local port=$2
    local service_name="$3"
    
    # 检查端口
    if ! check_port $port; then
        log "ERROR" "Port $port is already in use. Cannot start $name service."
        return 1
    fi
    
    # 启动服务
    log "INFO" "Starting $name service on port $port..."
    cd "$PROJECT_ROOT"
    PYTHONPATH="$PROJECT_ROOT" python -m uvicorn "$service_name.app:app" --host 0.0.0.0 --port $port --reload > "$LOG_DIR/${name}.log" 2>&1 &
    
    # 等待服务启动
    wait_for_service "$name" "$port"
    return $?
}

# 清理缓存函数
clean_cache() {
    log "INFO" "Cleaning Python cache files..."
    find . -type d -name "__pycache__" -exec rm -r {} +
    find . -type f -name "*.pyc" -delete
    find . -type f -name "*.pyo" -delete
    find . -type f -name "*.pyd" -delete
    log "INFO" "Cache cleaning completed"
}

# 清理旧的日志
log "INFO" "Cleaning old logs..."
rm -f "$LOG_DIR"/*.log

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    log "ERROR" "Python3 not found. Please install Python3 first."
    exit 1
fi

# 检查虚拟环境
if [ ! -d "venv" ]; then
    log "INFO" "Creating virtual environment..."
    python3 -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
log "INFO" "Installing dependencies..."
pip install -r requirements.txt

# 创建必要的目录
log "INFO" "Creating necessary directories..."
mkdir -p data/models data/temp data/results logs

# 清理缓存
clean_cache

# 定义服务列表（使用普通数组）
services=(
    "model_service:8003:Model"
    "analysis_service:8002:Analysis"
    "cloud_service:8004:Cloud"
    "api_service:8001:API"
    "gateway:8000:Gateway"
)

# 启动所有服务
log "INFO" "Starting all services..."

# 记录启动失败的服务
failed_services=()

# 按顺序启动服务
for service in "${services[@]}"; do
    IFS=':' read -r service_name port display_name <<< "$service"
    if ! start_service "$display_name" "$port" "$service_name"; then
        failed_services+=("$display_name")
        log "ERROR" "$display_name failed to start"
        continue
    fi
    log "INFO" "$display_name started successfully"
    sleep 5  # 给每个服务更多启动时间
done

# 检查服务状态
log "INFO" "Checking services status..."
echo -e "\n${BLUE}Service Status:${NC}"
echo -e "${BLUE}================${NC}"

for service in "${services[@]}"; do
    IFS=':' read -r service_name port display_name <<< "$service"
    if curl -s "http://localhost:$port/health" > /dev/null; then
        echo -e "${GREEN}✓ $display_name service is running on port $port${NC}"
    else
        echo -e "${RED}✗ $display_name service failed on port $port${NC}"
    fi
done

# 如果有服务启动失败，显示警告
if [ ${#failed_services[@]} -gt 0 ]; then
    echo -e "\n${RED}Warning: The following services failed to start:${NC}"
    for service in "${failed_services[@]}"; do
        echo -e "${RED}  - $service${NC}"
    done
    echo -e "${YELLOW}Check the logs in $LOG_DIR for more details${NC}"
    echo -e "${YELLOW}You can view logs with: tail -f $LOG_DIR/<service>.log${NC}"
    exit 1
fi

# 显示服务信息
echo -e "\n${GREEN}All services started successfully!${NC}"
echo -e "${YELLOW}Available Services:${NC}"
echo -e "  Gateway:  ${BLUE}http://localhost:8000${NC}"
echo -e "  API:      ${BLUE}http://localhost:8001${NC}"
echo -e "  Analysis: ${BLUE}http://localhost:8002${NC}"
echo -e "  Model:    ${BLUE}http://localhost:8003${NC}"
echo -e "  Cloud:    ${BLUE}http://localhost:8004${NC}"
echo -e "\n${YELLOW}Documentation:${NC}"
echo -e "  Swagger UI: ${BLUE}http://localhost:8000/api/v1/docs${NC}"
echo -e "  ReDoc:      ${BLUE}http://localhost:8000/api/v1/redoc${NC}"
echo -e "\n${YELLOW}Logs:${NC}"
echo -e "  Location: ${BLUE}$LOG_DIR${NC}"
echo -e "  View logs: ${GREEN}tail -f $LOG_DIR/<service>.log${NC}"

# 捕获Ctrl+C信号
trap 'echo -e "\n${YELLOW}Stopping all services...${NC}"; ./stop.sh; exit 0' INT

# 等待用户中断
wait