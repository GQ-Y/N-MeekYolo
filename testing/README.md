# MQTT测试工具

这个测试工具用于模拟分析节点与API服务之间的MQTT通信，可以帮助验证节点管理功能和MQTT通信是否正常。

## 功能特点

1. **自动连接MQTT** - 自动连接到MQTT服务器并设置遗嘱消息
2. **发布节点状态** - 连接后自动发布上线状态
3. **监控资源使用** - 每分钟自动发送资源使用情况（CPU、内存、GPU）
4. **响应任务请求** - 自动响应任务请求并模拟任务执行过程

## 使用方法

### 安装依赖

```bash
pip install paho-mqtt
```

### 运行测试客户端

基本用法：

```bash
python mqtt_test_client.py
```

自定义参数：

```bash
# 指定节点ID
python mqtt_test_client.py --node-id your_node_id

# 指定服务类型
python mqtt_test_client.py --service-type model

# 指定MQTT服务器地址
python mqtt_test_client.py --broker localhost --port 1883
```

### 交互命令

测试客户端运行后支持以下交互命令：

- `status [状态]` - 发布节点状态，可选值: online, busy, offline
- `resource` - 立即发送资源使用报告
- `info` - 显示节点信息
- `quit/exit` - 退出程序

## 消息格式

### 节点状态消息

主题: `yolo/nodes/{node_id}/status`

```json
{
  "timestamp": 1633123456,
  "payload": {
    "node_id": "test_node_12345678",
    "service_type": "analysis",
    "status": "online",
    "metadata": {
      "ip": "192.168.1.100",
      "port": 8002,
      "hostname": "test-machine",
      "version": "1.0.0",
      "os": "Darwin-21.6.0",
      "resource": {
        "cpu_usage": 45.6,
        "memory_usage": 32.1,
        "gpu_usage": 28.5,
        "task_count": 3
      }
    }
  }
}
```

### 任务状态消息

主题: `yolo/tasks/{task_id}/status`

```json
{
  "timestamp": 1633123456,
  "payload": {
    "task_id": "abc123",
    "node_id": "test_node_12345678",
    "status": "completed"
  }
}
```

## 测试流程

1. 先确保API服务已启动并配置为MQTT模式
2. 运行测试客户端，它会自动连接MQTT并发布上线状态
3. 观察API服务日志，确认节点状态更新是否正常接收和处理
4. 检查API服务的MQTT节点管理接口，验证节点是否被添加到数据库

## 故障排除

- **无法连接MQTT服务器**：检查broker地址、端口以及用户名密码是否正确
- **未收到节点状态更新**：检查API服务是否正确订阅了相应的主题
- **节点未出现在管理界面**：检查数据库连接和MQTT消息处理逻辑 