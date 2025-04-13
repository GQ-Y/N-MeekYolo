# MeekYolo MQTT 通信协议规范

## 1. 概述

本文档定义了MeekYolo系统中API服务与分析服务之间的MQTT通信协议规范。该协议基于MQTT 3.1.1版本设计，旨在提供一个可靠、高效、可扩展的服务间通信方案。通过指令式通信模式，实现了更精确的任务分配与节点管理。

## 2. 协议版本

- MQTT版本: 3.1.1
- 协议版本: 3.0.0
- 最后更新: 2024-04-07

## 3. 主题结构设计

### 3.1 系统级主题

```
/meek/connection                      # 节点连接状态主题(上线、下线通知)
/meek/system/broadcast                # 系统广播消息
```

### 3.2 节点通信主题

```
/meek/{mac_address}/request_setting    # 节点配置、任务分配和指令发送主题
/meek/device_config_reply              # 节点配置和指令回复主题
/meek/{mac_address}/status             # 节点状态更新主题
/meek/{mac_address}/result             # 任务结果上报主题
```

## 4. 消息格式

### 4.1 基础消息格式

所有消息都应遵循以下基础格式：

```json
{
    "confirmation_topic": "/meek/device_config_reply",  // 回复平台消息的发布主题
    "message_id": 12345678,                             // 消息ID，回复时带上用于确认
    "message_uuid": "c626714ee6e14620",                 // 消息UUID，回复时带上用于确认
    "request_type": "string",                           // 请求类型
    "data": {}                                          // 具体消息内容
}
```

### 4.2 节点连接消息 (发布到 /meek/connection)

```json
{
    "message_type": "connection",
    "status": "online",                 // online, offline
    "mac_address": "00:11:22:33:44:55", // 节点MAC地址
    "node_type": "analysis",            // analysis, api
    "timestamp": 1698765432,            // 时间戳(秒)
    "metadata": {
        "version": "3.0.0",
        "ip": "192.168.1.100",
        "port": 8000,
        "hostname": "analysis-node-1",
        "capabilities": {
            "models": ["yolov8"],
            "gpu_available": true,
            "max_tasks": 4,
            "cpu_cores": 8,
            "memory": 16
        }
    }
}
```

### 4.3 节点配置指令 (发布到 /meek/"mac_address"/request_setting)

```json
{
    "confirmation_topic": "/meek/device_config_reply",
    "message_id": 12345678,
    "message_uuid": "c626714ee6e14620",
    "request_type": "node_cmd",
    "data": {
        "cmd_type": "update_config",
        "config": {
            "max_tasks": 6,
            "log_level": "info",
            "models": ["yolov8n", "yolov8s"]
        }
    }
}
```

### 4.4 时间同步指令 (发布到 /meek/ "mac_address" /request_setting)

```json
{
    "confirmation_topic": "/meek/device_config_reply",
    "message_id": 12345678,
    "message_uuid": "c626714ee6e14620",
    "request_type": "node_cmd",
    "data": {
        "cmd_type": "sync_time",
        "ntp_time": 1594282090000.0    // 毫秒级时间戳，UTC时间
    }
}
```

### 4.5 任务分配指令 (发布到 /meek/"mac_address"/request_setting)

```json
{
    "confirmation_topic": "/meek/device_config_reply",
    "message_id": 12345678,
    "message_uuid": "c626714ee6e14620",
    "request_type": "task_cmd",
    "data": {
        "cmd_type": "start_task",
        "task_id": "task-001",
        "subtask_id": "subtask-001-01",
        "source": {
            "type": "image",             // image, video, stream
            "urls": ["http://..."],
            "is_base64": false
        },
        "config": {
            "model_code": "yolov8",
            "confidence": 0.5,
            "iou": 0.45,
            "classes": [0, 2],
            "imgsz": 640
        },
        "result_config": {
            "save_result": false,
            "return_base64": false,
            "callback_topic": "/meek/{mac_address}/result"
        }
    }
}
```

### 4.6 节点指令回复 (发布到 /meek/node_config_reply)

```json
{
    "message_id": 12345678,
    "message_uuid": "c626714ee6e14620",
    "response_type": "cmd_reply",
    "status": "success",                    // success, error
    "data": {
        "cmd_type": "start_task",           // 对应请求的指令类型
        "task_id": "task-001",
        "subtask_id": "subtask-001-01",
        "message": "任务已成功启动",
        "timestamp": 1698765432
    }
}
```

### 4.7 任务结果消息 (发布到 /meek/ {mac_address}/result)

```json
{
    "message_id": 12345678,
    "message_uuid": "c626714ee6e14620",
    "task_id": "task-001",
    "subtask_id": "subtask-001-01",
    "status": "completed",                 // running, completed, failed
    "progress": 100,                       // 进度百分比
    "timestamp": 1698765432,
    "result": {
        "frame_id": 0,                     // 视频/流的帧ID，图片分析为0
        "objects": [
            {
                "class_id": 0,
                "class_name": "person",
                "confidence": 0.95,
                "bbox": [100, 200, 150, 300]
            }
        ],
        "frame_info": {
            "width": 1920,
            "height": 1080,
            "processed_time": 0.045
        }
    }
}
```

### 4.8 节点状态更新 (发布到 /meek/ {mac_address}/status)

```json
{
    "mac_address": "00:11:22:33:44:55",
    "timestamp": 1698765432,
    "status": "running",                   // running, idle, error
    "load": {
        "cpu": 45.5,                       // CPU使用率(%)
        "memory": 2.5,                     // 内存使用(GB)
        "gpu": 65.8,                       // GPU使用率(%)
        "running_tasks": 2,                // 当前运行任务数
        "queue_length": 0                  // 队列中等待任务数
    }
}
```

## 5. QoS 设置


| 主题类型 | QoS级别 | 说明                           |
| -------- | ------- | ------------------------------ |
| 连接状态 | 1       | 确保节点连接状态变更被及时感知 |
| 配置指令 | 2       | 确保配置和指令精确到达一次     |
| 指令回复 | 1       | 确保回复至少送达一次           |
| 任务结果 | 1       | 确保分析结果至少送达一次       |
| 节点状态 | 0       | 定期状态更新，允许少量丢失     |

## 6. 通信流程

### 6.1 节点连接流程

1. 分析节点启动时：

   - 确定唯一标识(MAC地址)
   - 设置遗嘱消息(LWT, Last Will and Testament)
   - 连接到MQTT Broker
   - 发布上线消息到 `/meek/connection`
   - 订阅自身配置主题 `/meek/{mac_address}/request_setting`
2. API服务响应：

   - 接收连接消息
   - 更新节点列表和状态
   - 根据需要发送初始配置

### 6.2 任务处理流程

1. API服务分配任务：

   - 计算节点负载，选择合适的节点
   - 生成message_id和message_uuid
   - 发布任务指令到选定节点的 `/meek/{mac_address}/request_setting` 主题
   - 等待节点回复
2. 分析节点处理：

   - 接收任务指令
   - 发送指令确认到 `/meek/node_config_reply` 主题
   - 执行任务
   - 发布任务结果到 `/meek/{mac_address}/result` 主题
3. API服务重分配机制：

   - 若节点回复失败或超时未回复，选择其他节点重新分配任务
   - 若所有可用节点都无法处理，任务进入等待队列

### 6.3 节点配置流程

1. API服务发送配置：

   - 生成message_id和message_uuid
   - 发布配置指令到 `/meek/{mac_address}/request_setting` 主题
   - 等待节点回复
2. 分析节点响应：

   - 接收配置指令
   - 应用新配置
   - 发送确认回复到 `/meek/node_config_reply` 主题

## 7. 错误处理

### 7.1 错误响应格式

```json
{
    "message_id": 12345678,
    "message_uuid": "c626714ee6e14620",
    "response_type": "cmd_reply",
    "status": "error",
    "data": {
        "cmd_type": "start_task",
        "error_code": "ERR_001",
        "error_type": "RESOURCE_ERROR",
        "message": "资源不足，无法执行任务"
    }
}
```

### 7.2 重试与故障转移机制

1. 指令级重试：

   - 若节点未回复或回复错误，API服务重新选择节点发送指令
   - 重试次数和间隔可配置
2. 节点离线处理：

   - 通过遗嘱消息检测节点离线
   - 自动将离线节点的任务重新分配给其他在线节点
3. 任务状态恢复：

   - 节点重新上线后，API服务可向节点发送查询命令获取任务状态
   - 对于中断的任务，可选择继续执行或重新分配

## 8. 安全机制

1. 传输安全

   - 启用TLS 1.3
   - 证书双向验证
2. 访问控制

   - 用户名/密码认证
   - 基于主题的访问控制列表(ACL)
3. 消息验证

   - 使用message_uuid确保消息一致性
   - 可选择对敏感数据进行加密

## 9. 负载均衡

1. 负载计算

   - 基于节点当前CPU、内存、GPU使用率
   - 考虑节点当前运行任务数
   - 综合评分决定最优节点
2. 动态调整

   - 定期重新评估节点负载
   - 支持热任务迁移

## 10. 版本兼容

1. 版本号规则

   - 主版本号：不兼容的协议修改
   - 次版本号：向下兼容的功能性增加
   - 修订号：向下兼容的问题修正
2. 兼容性保证

   - 保留必要字段
   - 新增字段默认可选
   - 在版本升级时提供转换层

## 11. 最佳实践

1. 主题使用

   - 使用MAC地址确保节点唯一性
   - 遵循主题层次结构
   - 避免过深的主题层级
2. 消息处理

   - 实现异步处理
   - 设置合理的消息超时机制
   - 保持消息简洁，减少网络负载
3. 性能优化

   - 适当设置QoS级别
   - 批量处理分析结果
   - 合理使用保活机制

## 12. 示例代码

### Python示例 - 发送任务给指定节点

```python
import json
import uuid
import time
from paho.mqtt import client as mqtt_client

class MQTTController:
    def __init__(self, broker, port, username, password):
        self.client = mqtt_client.Client()
        self.client.username_pw_set(username, password)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.connect(broker, port)
        self.client.loop_start()
      
        # 订阅回复主题
        self.client.subscribe("/meek/device_config_reply", qos=1)
      
        # 响应缓存
        self.responses = {}
      
    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("已连接到MQTT Broker!")
        else:
            print(f"连接失败，返回码: {rc}")
          
    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            if "message_uuid" in payload:
                self.responses[payload["message_uuid"]] = payload
                print(f"收到回复: {payload}")
        except Exception as e:
            print(f"处理消息错误: {e}")
          
    def send_task(self, mac_address, task_id, subtask_id, source, config):
        """发送任务到指定节点"""
        message_id = int(time.time())
        message_uuid = str(uuid.uuid4()).replace("-", "")[:16]
      
        payload = {
            "confirmation_topic": "/meek/device_config_reply",
            "message_id": message_id,
            "message_uuid": message_uuid,
            "request_type": "task_cmd",
            "data": {
                "cmd_type": "start_task",
                "task_id": task_id,
                "subtask_id": subtask_id,
                "source": source,
                "config": config,
                "result_config": {
                    "save_result": True,
                    "callback_topic": f"/meek/{mac_address}/result"
                }
            }
        }
      
        # 发布任务指令
        topic = f"/meek/{mac_address}/request_setting"
        result = self.client.publish(topic, json.dumps(payload), qos=2)
      
        # 等待响应
        timeout = time.time() + 10  # 10秒超时
        while time.time() < timeout:
            if message_uuid in self.responses:
                return True, self.responses[message_uuid]
            time.sleep(0.1)
          
        return False, {"error": "节点响应超时"}
```

## 13. 变更历史


| 版本  | 日期       | 说明                                             |
| ----- | ---------- | ------------------------------------------------ |
| 3.0.0 | 2024-04-07 | 重新设计为指令式通信，简化主题结构，增加回复机制 |
| 2.0.0 | 2024-04-07 | 初始版本                                         |
| 1.0.0 | 2024-03-01 | 草稿版本                                         |
