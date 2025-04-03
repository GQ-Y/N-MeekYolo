#!/bin/bash

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m'

# 项目信息
VERSION="2.0.0"
AUTHOR="PandaKing"
GITHUB="https://github.com/PandaKing/MeekYolo"

# 项目根目录
PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 服务列表 (使用普通数组)
SERVICES=(
    "gateway:8000"
    "api_service:8001"
    "analysis_service:8002"
    "model_service:8003"
    "cloud_service:8004"
)

# 获取服务端口
get_service_port() {
    local service_info=$1
    echo "${service_info#*:}"
}

# 获取服务名称
get_service_name() {
    local service_info=$1
    echo "${service_info%:*}"
}

# 显示服务启动标识
show_service_banner() {
    local service_name=$1
    echo -e "${BLUE}"
    echo -e "███╗   ███╗███████╗███████╗██╗  ██╗██╗   ██╗ ██████╗ ██╗      ██████╗     ${WHITE}@${service_name}${BLUE}"
    echo '████╗ ████║██╔════╝██╔════╝██║ ██╔╝╚██╗ ██╔╝██╔═══██╗██║     ██╔═══██╗'
    echo '██╔████╔██║█████╗  █████╗  █████╔╝  ╚████╔╝ ██║   ██║██║     ██║   ██║'
    echo '██║╚██╔╝██║██╔══╝  ██╔══╝  ██╔═██╗   ╚██╔╝  ██║   ██║██║     ██║   ██║'
    echo '██║ ╚═╝ ██║███████╗███████╗██║  ██╗   ██║   ╚██████╔╝███████╗╚██████╔╝'
    echo '╚═╝     ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝   ╚═╝    ╚═════╝ ╚══════╝ ╚═════╝ '
    echo -e "${NC}"
}

# 显示 Logo
show_logo() {
    show_service_banner "MeekYolo"
    echo -e "${WHITE}版本: ${VERSION}${NC}"
    echo -e "${WHITE}作者: ${AUTHOR}${NC}"
    echo -e "${WHITE}Github: ${GITHUB}${NC}"
    echo
}

# 检查服务状态
check_service_status() {
    local service_info=$1
    local name=$(get_service_name "$service_info")
    local port=$(get_service_port "$service_info")
    if curl -s "http://localhost:$port/health" > /dev/null; then
        echo -e "${GREEN}✓ $name 正在运行，端口: $port${NC}"
        return 0
    else
        echo -e "${RED}✗ $name 未运行，端口: $port${NC}"
        return 1
    fi
}

# 初始化环境
init_environment() {
    local force=$1
    echo -e "${YELLOW}正在初始化环境...${NC}"
    
    for service_info in "${SERVICES[@]}"; do
        local name=$(get_service_name "$service_info")
        echo -e "\n${CYAN}正在初始化 $name...${NC}"
        cd "$PROJECT_ROOT/$name"
        
        # 检查是否强制重新初始化
        if [ "$force" = "force" ]; then
            rm -f requirements.lock
        fi
        
        # 如果存在锁文件且不是强制重新初始化，则跳过
        if [ -f "requirements.lock" ] && [ "$force" != "force" ]; then
            echo -e "${GREEN}$name 已经初始化过了 (发现 requirements.lock)${NC}"
            continue
        fi
        
        # 安装依赖
        if [ -f "requirements.txt" ]; then
            pip install -r requirements.txt && touch requirements.lock
            if [ $? -eq 0 ]; then
                echo -e "${GREEN}$name 初始化成功${NC}"
            else
                echo -e "${RED}$name 初始化失败${NC}"
            fi
        else
            echo -e "${RED}未找到 $name 的 requirements.txt 文件${NC}"
        fi
    done
}

# 显示服务选择菜单
show_service_menu() {
    echo -e "\n${YELLOW}请选择要启动的服务:${NC}"
    local i=1
    for service_info in "${SERVICES[@]}"; do
        local name=$(get_service_name "$service_info")
        local port=$(get_service_port "$service_info")
        echo -e "${WHITE}$i. $name (端口: $port)${NC}"
        ((i++))
    done
    echo -e "${WHITE}0. 返回主菜单${NC}"
    echo -n "请输入选项 (0-$((${#SERVICES[@]})): "
}

# 启动服务
start_services() {
    local mode=$1
    
    if [ "$mode" = "foreground" ]; then
        while true; do
            show_service_menu
            read service_choice
            
            # 检查输入是否为数字
            if ! [[ "$service_choice" =~ ^[0-9]+$ ]]; then
                echo -e "${RED}无效的选项${NC}"
                sleep 2
                continue
            fi
            
            # 返回主菜单
            if [ "$service_choice" = "0" ]; then
                return
            fi
            
            # 检查选项范围
            if [ "$service_choice" -gt "${#SERVICES[@]}" ] || [ "$service_choice" -lt 0 ]; then
                echo -e "${RED}无效的选项${NC}"
                sleep 2
                continue
            fi
            
            # 获取选择的服务信息
            local service_info="${SERVICES[$((service_choice-1))]}"
            local selected_service=$(get_service_name "$service_info")
            local port=$(get_service_port "$service_info")
            
            # 显示启动标识
            clear
            show_service_banner "$selected_service"
            echo -e "${CYAN}正在启动服务...${NC}"
            echo -e "${WHITE}服务名称: $selected_service${NC}"
            echo -e "${WHITE}监听端口: $port${NC}"
            echo
            
            cd "$PROJECT_ROOT/$selected_service"
            mkdir -p logs
            
            PYTHONPATH="$PROJECT_ROOT/$selected_service" uvicorn app:app --host 0.0.0.0 --port $port
            
            # 服务停止后返回菜单
            echo -e "\n${YELLOW}服务已停止，按回车键继续...${NC}"
            read
            return
        done
    else
        echo -e "${YELLOW}正在启动所有服务...${NC}"
        for service_info in "${SERVICES[@]}"; do
            local name=$(get_service_name "$service_info")
            local port=$(get_service_port "$service_info")
            
            # 显示启动标识
            clear
            show_service_banner "$name"
            echo -e "${CYAN}正在启动服务...${NC}"
            echo -e "${WHITE}服务名称: $name${NC}"
            echo -e "${WHITE}监听端口: $port${NC}"
            echo
            
            cd "$PROJECT_ROOT/$name"
            mkdir -p logs
            
            PYTHONPATH="$PROJECT_ROOT/$name" nohup uvicorn app:app --host 0.0.0.0 --port $port > logs/service.log 2>&1 &
            echo $! > logs/service.pid
            echo -e "${GREEN}$name 已在后台启动${NC}"
            sleep 1
        done
    fi
}

# 停止服务
stop_services() {
    echo -e "${YELLOW}正在停止服务...${NC}"
    
    for service_info in "${SERVICES[@]}"; do
        local name=$(get_service_name "$service_info")
        echo -e "\n${CYAN}正在停止 $name...${NC}"
        local pid_file="$PROJECT_ROOT/$name/logs/service.pid"
        
        if [ -f "$pid_file" ]; then
            local pid=$(cat "$pid_file")
            if kill -0 $pid 2>/dev/null; then
                kill $pid
                rm "$pid_file"
                echo -e "${GREEN}$name 已停止${NC}"
            else
                echo -e "${RED}$name 未在运行${NC}"
                rm "$pid_file"
            fi
        else
            echo -e "${RED}未找到 $name 的 PID 文件${NC}"
        fi
    done
}

# 显示菜单
show_menu() {
    echo -e "\n${YELLOW}请选择操作:${NC}"
    echo -e "${WHITE}1. 初始化环境${NC}"
    echo -e "${WHITE}2. 重新初始化环境${NC}"
    echo -e "${WHITE}3. 启动服务 (前台运行)${NC}"
    echo -e "${WHITE}4. 启动服务 (后台运行)${NC}"
    echo -e "${WHITE}5. 停止服务${NC}"
    echo -e "${WHITE}0. 退出${NC}"
    echo -n "请输入选项 (0-5): "
}

# 主循环
while true; do
    clear
    show_logo
    show_menu
    
    read choice
    case $choice in
        1)
            init_environment
            echo -e "\n${YELLOW}按回车键继续...${NC}"
            read
            ;;
        2)
            init_environment force
            echo -e "\n${YELLOW}按回车键继续...${NC}"
            read
            ;;
        3)
            start_services foreground
            ;;
        4)
            start_services background
            echo -e "\n${YELLOW}按回车键继续...${NC}"
            read
            ;;
        5)
            stop_services
            echo -e "\n${YELLOW}按回车键继续...${NC}"
            read
            ;;
        0)
            echo -e "${GREEN}再见!${NC}"
            exit 0
            ;;
        *)
            echo -e "${RED}无效的选项${NC}"
            sleep 2
            ;;
    esac
done 