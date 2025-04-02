# 数据库管理工具

本目录包含用于API服务数据库管理的工具脚本，主要包括数据库的初始化和检查功能。

## 脚本说明

### 1. 数据库初始化 - `init_db.sh`

用于安全地初始化API服务数据库，并创建锁文件防止重复执行导致数据丢失。

**功能特点：**
- 检查锁文件，防止重复初始化
- 用户确认机制，避免误操作
- 完整日志记录
- 自动激活Python虚拟环境（如果存在）
- 初始化所有数据表和基础数据

**使用方法：**
```bash
# 在项目根目录下执行
./api_service/scripts/init_db.sh
```

**说明：**
- 初始化成功后会在项目根目录创建 `db_initialized.lock` 文件
- 如需重新初始化，需要先删除锁文件
- 初始化日志保存在 `db_init.log` 文件中

### 2. 数据库检查 - `check_db.sh`

用于检查数据库状态、表结构以及数据统计信息。

**功能特点：**
- 检查数据库连接
- 显示所有表的结构和记录数
- 显示节点状态统计
- 显示任务状态统计
- 显示视频流状态统计

**使用方法：**
```bash
# 在项目根目录下执行
./api_service/scripts/check_db.sh
```

**说明：**
- 检查结果会实时显示在终端
- 详细日志保存在 `db_check.log` 文件中

### 3. Python初始化模块 - `init_database.py`

供上述脚本调用的Python模块，也可以直接调用。

**功能特点：**
- 创建所有表结构
- 初始化基础数据
- 设置视频流状态
- 验证表结构完整性

**直接使用方法：**
```bash
# 在项目根目录下执行
python -m api_service.scripts.init_database
```

## 建议使用流程

1. 首次部署时，执行初始化脚本：
   ```bash
   ./api_service/scripts/init_db.sh
   ```

2. 想要查看数据库状态时，执行检查脚本：
   ```bash
   ./api_service/scripts/check_db.sh
   ```

3. 如需重置数据库（**谨慎操作**）：
   ```bash
   rm db_initialized.lock
   ./api_service/scripts/init_db.sh
   ```

## 注意事项

- 初始化操作会清空现有数据，请谨慎操作
- 建议在执行初始化前备份重要数据
- 所有脚本需要在项目根目录下执行，而不是在scripts目录中执行 