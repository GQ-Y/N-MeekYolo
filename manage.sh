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

# 数据库服务列表 (需要进行数据库迁移的服务)
DB_SERVICES=(
    "gateway"
    "api_service"
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
    
    # 检查是否安装了 python3-venv
    if ! command -v python3 -m venv &> /dev/null; then
        echo -e "${RED}错误: python3-venv 未安装${NC}"
        echo -e "${YELLOW}请先安装 python3-venv:${NC}"
        echo -e "Ubuntu/Debian: sudo apt-get install python3-venv"
        echo -e "CentOS/RHEL: sudo yum install python3-venv"
        echo -e "macOS: brew install python3"
        return 1
    fi
    
    for service_info in "${SERVICES[@]}"; do
        local name=$(get_service_name "$service_info")
        echo -e "\n${CYAN}正在初始化 $name...${NC}"
        cd "$PROJECT_ROOT/$name"
        
        # 虚拟环境目录
        local venv_dir="venv"
        
        # 检查是否强制重新初始化
        if [ "$force" = "force" ]; then
            echo -e "${YELLOW}强制重新初始化，删除旧的虚拟环境...${NC}"
            rm -rf "$venv_dir"
            rm -f requirements.lock
        fi
        
        # 如果存在锁文件且不是强制重新初始化，则跳过
        if [ -f "requirements.lock" ] && [ "$force" != "force" ]; then
            echo -e "${GREEN}$name 已经初始化过了 (发现 requirements.lock)${NC}"
            continue
        fi
        
        # 创建虚拟环境
        echo -e "${WHITE}创建虚拟环境...${NC}"
        python3 -m venv "$venv_dir"
        
        if [ ! -d "$venv_dir" ]; then
            echo -e "${RED}创建虚拟环境失败${NC}"
            continue
        fi
        
        # 激活虚拟环境并安装依赖
        echo -e "${WHITE}激活虚拟环境并安装依赖...${NC}"
        source "$venv_dir/bin/activate"
        
        # 升级 pip
        python -m pip install --upgrade pip
        
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
        
        # 退出虚拟环境
        deactivate
    done
}

# 数据库迁移
migrate_database() {
    local action=$1  # upgrade 或 downgrade
    local service=$2 # 服务名称，如果为空则处理所有服务
    
    echo -e "${YELLOW}正在执行数据库迁移...${NC}"
    
    # 如果指定了服务名称，只处理该服务
    if [ -n "$service" ]; then
        if [[ " ${DB_SERVICES[@]} " =~ " ${service} " ]]; then
            _migrate_single_service "$service" "$action"
        else
            echo -e "${RED}错误: $service 不是有效的数据库服务${NC}"
            return 1
        fi
    else
        # 处理所有数据库服务
        for db_service in "${DB_SERVICES[@]}"; do
            _migrate_single_service "$db_service" "$action"
        done
    fi
}

# 迁移单个服务的数据库
_migrate_single_service() {
    local service=$1
    local action=$2
    
    echo -e "\n${CYAN}正在处理 $service 的数据库迁移...${NC}"
    cd "$PROJECT_ROOT/$service"
    
    # 检查 alembic 配置是否存在
    if [ ! -f "alembic.ini" ]; then
        echo -e "${RED}错误: $service 中未找到 alembic.ini${NC}"
        return 1
    fi
    
    # 执行迁移
    case "$action" in
        "upgrade")
            echo -e "${WHITE}正在升级数据库...${NC}"
            alembic upgrade head
            ;;
        "downgrade")
            echo -e "${WHITE}正在回滚数据库...${NC}"
            alembic downgrade base
            ;;
        *)
            echo -e "${RED}错误: 无效的迁移操作 $action${NC}"
            return 1
            ;;
    esac
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}$service 数据库迁移成功${NC}"
    else
        echo -e "${RED}$service 数据库迁移失败${NC}"
        return 1
    fi
}

# 显示数据库状态
show_database_status() {
    echo -e "${YELLOW}数据库状态:${NC}"
    
    for service in "${DB_SERVICES[@]}"; do
        echo -e "\n${CYAN}检查 $service 数据库状态...${NC}"
        cd "$PROJECT_ROOT/$service"
        
        if [ -f "alembic.ini" ]; then
            echo -e "${WHITE}当前版本:${NC}"
            alembic current
            echo -e "${WHITE}历史记录:${NC}"
            alembic history
        else
            echo -e "${RED}错误: 未找到 alembic.ini${NC}"
        fi
    done
}

# 显示系统安装菜单
show_install_menu() {
    echo -e "\n${YELLOW}┌────────────────────────────────────────────┐${NC}"
    echo -e "${YELLOW}│${NC}            系统安装与环境配置            ${YELLOW}│${NC}"
    echo -e "${YELLOW}└────────────────────────────────────────────┘${NC}"
    echo -e "\n${CYAN}可用操作:${NC}"
    echo -e "${WHITE}1. 🔧 初始化环境${NC}"
    echo -e "   └─ 首次安装时使用，配置基础环境和依赖"
    echo -e "${WHITE}2. 🔄 重新初始化环境${NC}"
    echo -e "   └─ 环境出现问题时使用，完全重置并重新安装"
    echo -e "${WHITE}0. ↩️  返回主菜单${NC}"
    echo -e "   └─ 返回到主操作界面"
    echo -e "\n${YELLOW}提示: 初次使用请选择选项 1${NC}"
    echo -n "请输入选项 (0-2): "
}

# 处理系统安装菜单
handle_install_menu() {
    while true; do
        clear
        show_logo
        show_install_menu
        read install_choice
        
        case $install_choice in
            1)
                init_environment
                ;;
            2)
                init_environment force
                ;;
            0)
                return
                ;;
            *)
                echo -e "${RED}无效的选项${NC}"
                sleep 2
                ;;
        esac
        
        if [ "$install_choice" != "0" ]; then
            echo -e "\n${YELLOW}按回车键继续...${NC}"
            read
        fi
    done
}

# 显示数据库管理菜单
show_database_menu() {
    echo -e "\n${YELLOW}┌────────────────────────────────────────────┐${NC}"
    echo -e "${YELLOW}│${NC}            数据库管理控制台              ${YELLOW}│${NC}"
    echo -e "${YELLOW}└────────────────────────────────────────────┘${NC}"
    echo -e "\n${CYAN}可用操作:${NC}"
    echo -e "${WHITE}1. ⬆️  升级所有数据库${NC}"
    echo -e "   └─ 将所有服务的数据库升级到最新版本"
    echo -e "${WHITE}2. ⬇️  回滚所有数据库${NC}"
    echo -e "   └─ 将所有服务的数据库回滚到初始状态"
    echo -e "${WHITE}3. 📦 升级指定服务数据库${NC}"
    echo -e "   └─ 选择特定服务进行数据库升级"
    echo -e "${WHITE}4. 🔄 回滚指定服务数据库${NC}"
    echo -e "   └─ 选择特定服务进行数据库回滚"
    echo -e "${WHITE}5. 📊 查看数据库状态${NC}"
    echo -e "   └─ 显示所有数据库的当前版本和迁移历史"
    echo -e "${WHITE}0. ↩️  返回主菜单${NC}"
    echo -e "   └─ 返回到主操作界面"
    echo -e "\n${YELLOW}提示: 首次使用请先执行选项 1${NC}"
    echo -n "请输入选项 (0-5): "
}

# 显示服务选择菜单
show_service_menu() {
    echo -e "\n${YELLOW}┌────────────────────────────────────────────┐${NC}"
    echo -e "${YELLOW}│${NC}            可用服务列表                  ${YELLOW}│${NC}"
    echo -e "${YELLOW}└────────────────────────────────────────────┘${NC}"
    echo -e "\n${CYAN}请选择要操作的服务:${NC}"
    local i=1
    for service_info in "${SERVICES[@]}"; do
        local name=$(get_service_name "$service_info")
        local port=$(get_service_port "$service_info")
        echo -e "${WHITE}$i. 🚀 $name${NC}"
        echo -e "   └─ 端口: $port | 状态: $(check_service_status_quiet "$service_info")"
        ((i++))
    done
    echo -e "${WHITE}0. ↩️  返回主菜单${NC}"
    echo -e "   └─ 返回到主操作界面"
    echo -n "请输入选项 (0-$((${#SERVICES[@]})): "
}

# 显示数据库服务选择菜单
show_db_service_menu() {
    echo -e "\n${YELLOW}┌────────────────────────────────────────────┐${NC}"
    echo -e "${YELLOW}│${NC}            数据库服务列表                ${YELLOW}│${NC}"
    echo -e "${YELLOW}└────────────────────────────────────────────┘${NC}"
    echo -e "\n${CYAN}请选择要操作的数据库:${NC}"
    local i=1
    for service in "${DB_SERVICES[@]}"; do
        echo -e "${WHITE}$i. 💾 $service${NC}"
        echo -e "   └─ $(get_db_service_status "$service")"
        ((i++))
    done
    echo -e "${WHITE}0. ↩️  返回上级菜单${NC}"
    echo -e "   └─ 返回到数据库管理菜单"
    echo -n "请输入选项 (0-$((${#DB_SERVICES[@]})): "
}

# 获取服务状态的简短描述
check_service_status_quiet() {
    local service_info=$1
    local name=$(get_service_name "$service_info")
    local port=$(get_service_port "$service_info")
    if curl -s "http://localhost:$port/health" > /dev/null; then
        echo -e "${GREEN}运行中${NC}"
    else
        echo -e "${RED}未运行${NC}"
    fi
}

# 获取数据库服务状态
get_db_service_status() {
    local service=$1
    if [ -f "$PROJECT_ROOT/$service/alembic.ini" ]; then
        cd "$PROJECT_ROOT/$service"
        local current_version=$(alembic current 2>/dev/null | grep "^[a-f0-9]" | cut -d' ' -f1)
        if [ -n "$current_version" ]; then
            echo "当前版本: ${CYAN}$current_version${NC}"
        else
            echo "${YELLOW}未初始化${NC}"
        fi
    else
        echo "${RED}配置缺失${NC}"
    fi
}

# 显示主菜单
show_menu() {
    echo -e "\n${YELLOW}┌────────────────────────────────────────────┐${NC}"
    echo -e "${YELLOW}│${NC}            MeekYOLO 控制面板            ${YELLOW}│${NC}"
    echo -e "${YELLOW}└────────────────────────────────────────────┘${NC}"
    
    echo -e "\n${CYAN}服务管理:${NC}"
    echo -e "${WHITE}1. 🖥️  启动服务 (前台运行)${NC}"
    echo -e "   └─ 在终端前台启动服务，可实时查看日志"
    echo -e "${WHITE}2. 🚀 启动服务 (后台运行)${NC}"
    echo -e "   └─ 在后台启动所有服务，适合生产环境"
    echo -e "${WHITE}3. 🛑 停止服务${NC}"
    echo -e "   └─ 停止所有正在运行的服务"
    
    echo -e "\n${CYAN}系统管理:${NC}"
    echo -e "${WHITE}4. ⚙️  系统安装${NC}"
    echo -e "   └─ 环境初始化和系统配置"
    echo -e "${WHITE}5. 🗄️  数据库管理${NC}"
    echo -e "   └─ 数据库迁移、升级和状态管理"
    
    echo -e "\n${RED}其他任意键退出程序${NC}"
    
    # 显示系统状态
    echo -e "\n${PURPLE}系统状态:${NC}"
    echo -e "├─ 运行环境: $(python3 --version 2>/dev/null || echo "Python未安装")"
    echo -e "├─ 数据库: $(check_mysql_status)"
    echo -e "└─ 活动服务: $(count_active_services)/${#SERVICES[@]}"
    
    echo -n "请输入选项: "
}

# 检查MySQL状态
check_mysql_status() {
    if docker exec mysql8 mysqladmin ping -h localhost -u root -p123456 >/dev/null 2>&1; then
        echo -e "${GREEN}已连接${NC}"
    else
        echo -e "${RED}未连接${NC}"
    fi
}

# 统计活动服务数量
count_active_services() {
    local count=0
    for service_info in "${SERVICES[@]}"; do
        local name=$(get_service_name "$service_info")
        local port=$(get_service_port "$service_info")
        if curl -s "http://localhost:$port/health" > /dev/null; then
            ((count++))
        fi
    done
    echo "$count"
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
            
            # 检查虚拟环境
            if [ ! -d "venv" ]; then
                echo -e "${RED}错误: 虚拟环境不存在，请先初始化环境${NC}"
                echo -e "\n${YELLOW}按回车键继续...${NC}"
                read
                return
            fi
            
            # 激活虚拟环境
            source "venv/bin/activate"
            PYTHONPATH="$PROJECT_ROOT/$selected_service" uvicorn app:app --host 0.0.0.0 --port $port
            deactivate
            
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
            
            # 检查虚拟环境
            if [ ! -d "venv" ]; then
                echo -e "${RED}错误: $name 的虚拟环境不存在，请先初始化环境${NC}"
                continue
            fi
            
            # 使用虚拟环境中的 Python
            PYTHONPATH="$PROJECT_ROOT/$name" nohup venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port $port > logs/service.log 2>&1 &
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
        local port=$(get_service_port "$service_info")
        echo -e "\n${CYAN}正在停止 $name...${NC}"
        
        # 查找对应端口的Python进程
        local pids=$(pgrep -f "python.*uvicorn.*--port $port")
        
        if [ -n "$pids" ]; then
            echo -e "${YELLOW}找到服务进程: $pids${NC}"
            # 终止进程
            echo "$pids" | while read pid; do
                if kill -0 $pid 2>/dev/null; then
                    kill $pid
                    echo -e "${GREEN}已停止进程: $pid${NC}"
                fi
            done
            
            # 等待进程完全终止
            sleep 1
            
            # 检查是否还有残留进程
            pids=$(pgrep -f "python.*uvicorn.*--port $port")
            if [ -n "$pids" ]; then
                echo -e "${RED}进程未能正常终止，强制终止...${NC}"
                echo "$pids" | while read pid; do
                    pkill -9 -P $pid 2>/dev/null  # 终止子进程
                    kill -9 $pid 2>/dev/null      # 强制终止主进程
                done
            fi
            
            # 清理PID文件
            local pid_file="$PROJECT_ROOT/$name/logs/service.pid"
            if [ -f "$pid_file" ]; then
                rm "$pid_file"
            fi
            
            echo -e "${GREEN}$name 已停止${NC}"
        else
            echo -e "${YELLOW}未发现 $name 的运行进程${NC}"
            # 清理可能存在的过期PID文件
            local pid_file="$PROJECT_ROOT/$name/logs/service.pid"
            if [ -f "$pid_file" ]; then
                rm "$pid_file"
            fi
        fi
    done
}

# 处理数据库管理菜单
handle_database_menu() {
    while true; do
        clear
        show_logo
        show_database_menu
        read db_choice
        
        case $db_choice in
            1)
                migrate_database "upgrade"
                ;;
            2)
                migrate_database "downgrade"
                ;;
            3)
                show_db_service_menu
                read service_choice
                if [ "$service_choice" != "0" ] && [ "$service_choice" -le "${#DB_SERVICES[@]}" ]; then
                    migrate_database "upgrade" "${DB_SERVICES[$((service_choice-1))]}"
                fi
                ;;
            4)
                show_db_service_menu
                read service_choice
                if [ "$service_choice" != "0" ] && [ "$service_choice" -le "${#DB_SERVICES[@]}" ]; then
                    migrate_database "downgrade" "${DB_SERVICES[$((service_choice-1))]}"
                fi
                ;;
            5)
                show_database_status
                ;;
            0)
                return
                ;;
            *)
                echo -e "${RED}无效的选项${NC}"
                sleep 2
                ;;
        esac
        
        if [ "$db_choice" != "0" ]; then
            echo -e "\n${YELLOW}按回车键继续...${NC}"
            read
        fi
    done
}

# 主循环
while true; do
    clear
    show_logo
    show_menu
    
    read choice
    case $choice in
        1)
            start_services foreground
            ;;
        2)
            start_services background
            echo -e "\n${YELLOW}按回车键继续...${NC}"
            read
            ;;
        3)
            stop_services
            echo -e "\n${YELLOW}按回车键继续...${NC}"
            read
            ;;
        4)
            handle_install_menu
            ;;
        5)
            handle_database_menu
            ;;
        *)
            echo -e "${GREEN}再见!${NC}"
            exit 0
            ;;
    esac
done 