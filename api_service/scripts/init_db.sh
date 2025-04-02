#!/bin/bash

# 数据库初始化脚本
# 作用：安全地初始化API服务数据库，防止重复执行导致数据丢失
# 使用：在项目根目录下执行 ./api_service/scripts/init_db.sh

# 获取脚本所在目录路径
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
API_ROOT_DIR=$(cd "$SCRIPT_DIR/../.." && pwd)
LOCK_FILE="$SCRIPT_DIR/.db_initialized.lock"
LOG_FILE="$SCRIPT_DIR/.db_init.log"

# 设置颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # 无颜色

echo -e "${YELLOW}API服务数据库初始化工具${NC}"
echo "========================================"
echo "脚本目录: $SCRIPT_DIR"
echo "API根目录: $API_ROOT_DIR"
echo "锁文件位置: $LOCK_FILE"
echo "日志文件: $LOG_FILE"
echo "========================================"

# 检查锁文件是否存在
if [ -f "$LOCK_FILE" ]; then
    echo -e "${YELLOW}检测到锁文件，数据库已经初始化过。${NC}"
    echo "如需强制重新初始化数据库（警告：这将清空所有数据！），请执行以下操作："
    echo "1. 删除锁文件: rm $LOCK_FILE"
    echo "2. 重新运行此脚本"
    exit 1
fi

# 确认用户真的想初始化数据库
echo -e "${RED}警告: 此操作将初始化数据库并可能清空已有数据！${NC}"
read -p "是否确认继续? (y/n): " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "操作已取消"
    exit 0
fi

echo -e "${YELLOW}开始初始化数据库...${NC}"

# 执行Python初始化脚本
cd "$API_ROOT_DIR" || { echo "无法进入API根目录"; exit 1; }

# 确保激活了Python虚拟环境（如果存在的话）
if [ -d "venv" ] || [ -d ".venv" ]; then
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
    elif [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
    fi
    echo "已激活Python虚拟环境"
fi

# 执行数据库初始化脚本并记录日志
echo "$(date): 开始执行数据库初始化" > "$LOG_FILE"
python -m api_service.scripts.init_database 2>&1 | tee -a "$LOG_FILE"
INIT_RESULT=$?

# 检查初始化结果
if [ $INIT_RESULT -eq 0 ]; then
    # 创建锁文件
    echo "$(date): 数据库初始化成功完成" > "$LOCK_FILE"
    echo -e "${GREEN}数据库初始化成功!${NC}"
    echo "已创建锁文件: $LOCK_FILE"
    echo "如需重新初始化，请先删除此文件"
else
    echo -e "${RED}数据库初始化失败，请查看日志: $LOG_FILE${NC}"
    exit 1
fi

# 显示一些基本信息
echo -e "${YELLOW}数据库初始化摘要:${NC}"
echo "========================================"
grep -E "表|创建|完成" "$LOG_FILE" | tail -n 20
echo "========================================"
echo -e "${GREEN}完成!${NC}" 