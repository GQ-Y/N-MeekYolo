#!/bin/bash

# 数据库检查脚本
# 作用：检查数据库状态、表结构以及数据统计
# 使用：在项目根目录下执行 ./api_service/scripts/check_db.sh

# 获取脚本所在目录路径
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
API_ROOT_DIR=$(cd "$SCRIPT_DIR/../.." && pwd)
LOCK_FILE="$SCRIPT_DIR/.db_initialized.lock"
LOG_FILE="$SCRIPT_DIR/.db_check.log"

# 设置颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # 无颜色

echo -e "${YELLOW}API服务数据库检查工具${NC}"
echo "========================================"
echo "脚本目录: $SCRIPT_DIR"
echo "API根目录: $API_ROOT_DIR"
echo "锁文件状态: $([ -f "$LOCK_FILE" ] && echo -e "${GREEN}存在${NC}" || echo -e "${YELLOW}不存在${NC}")"
if [ -f "$LOCK_FILE" ]; then
    echo "锁文件创建时间: $(cat "$LOCK_FILE")"
fi
echo "========================================"

# 进入项目根目录
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

# 创建临时Python脚本来检查数据库
cat > ./.temp_db_check.py << 'EOF'
"""临时数据库检查脚本"""
from sqlalchemy import create_engine, text, inspect
import sys
from api_service.core.config import settings

try:
    # 创建数据库引擎
    engine = create_engine(settings.DATABASE.url)
    inspector = inspect(engine)
    
    # 检查数据库连接
    with engine.connect() as conn:
        # 获取所有表信息
        tables = inspector.get_table_names()
        
        print(f"\n{'-'*50}")
        print(f"数据库连接成功: {settings.DATABASE.url}")
        print(f"发现 {len(tables)} 个表")
        print(f"{'-'*50}")
        
        # 检查所有表
        for table in sorted(tables):
            columns = inspector.get_columns(table)
            row_count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            print(f"\n表名: {table}")
            print(f"  - 字段数: {len(columns)}")
            print(f"  - 记录数: {row_count}")
            
            # 如果是特定表，输出更具体的信息
            if table == "nodes":
                online = conn.execute(text("SELECT COUNT(*) FROM nodes WHERE service_status = 'online'")).scalar()
                offline = conn.execute(text("SELECT COUNT(*) FROM nodes WHERE service_status = 'offline'")).scalar()
                print(f"  - 在线节点: {online}")
                print(f"  - 离线节点: {offline}")
                
                # 输出节点详情
                print("\n节点详情:")
                result = conn.execute(text("SELECT id, ip, port, service_name, service_status FROM nodes"))
                for row in result:
                    print(f"  - 节点 {row[0]}: {row[1]}:{row[2]} ({row[3]}) - {row[4]}")
                    
            elif table == "tasks":
                running = conn.execute(text("SELECT COUNT(*) FROM tasks WHERE status = 'running'")).scalar()
                pending = conn.execute(text("SELECT COUNT(*) FROM tasks WHERE status = 'pending'")).scalar()
                failed = conn.execute(text("SELECT COUNT(*) FROM tasks WHERE status = 'failed'")).scalar()
                print(f"  - 运行中任务: {running}")
                print(f"  - 待处理任务: {pending}")
                print(f"  - 失败任务: {failed}")
                
                # 输出运行中的任务详情
                if running > 0:
                    print("\n运行中任务详情:")
                    result = conn.execute(text("SELECT id, name, node_id FROM tasks WHERE status = 'running'"))
                    for row in result:
                        print(f"  - 任务 {row[0]}: {row[1]} (节点: {row[2]})")
                
            elif table == "streams":
                online = conn.execute(text("SELECT COUNT(*) FROM streams WHERE status = 1")).scalar()
                offline = conn.execute(text("SELECT COUNT(*) FROM streams WHERE status = 0")).scalar()
                print(f"  - 在线视频流: {online}")
                print(f"  - 离线视频流: {offline}")
        
        print(f"\n{'-'*50}")
        print("数据库检查完成！")
        print(f"{'-'*50}\n")
    
except Exception as e:
    print(f"数据库检查失败: {str(e)}")
    sys.exit(1)
EOF

# 执行临时Python脚本
echo "$(date): 开始检查数据库" > "$LOG_FILE"
python ./.temp_db_check.py 2>&1 | tee -a "$LOG_FILE"
CHECK_RESULT=$?

# 删除临时脚本
rm -f ./.temp_db_check.py

# 检查执行结果
if [ $CHECK_RESULT -eq 0 ]; then
    echo -e "${GREEN}数据库检查完成!${NC}"
else
    echo -e "${YELLOW}数据库检查过程中出现错误，请查看日志: $LOG_FILE${NC}"
    exit 1
fi

# 提供一些建议
echo -e "\n${BLUE}操作建议:${NC}"
echo "1. 如需初始化数据库，请执行: ./api_service/scripts/init_db.sh"
if [ -f "$LOCK_FILE" ]; then
    echo "   (注意: 需要先删除锁文件 $LOCK_FILE)"
fi
echo "2. 查看更多数据库信息，请查看日志: $LOG_FILE"