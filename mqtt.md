# MeekYolo MQTT 通信协议规范

## 1. 概述

本文档定义了MeekYolo系统中API服务与分析服务之间的MQTT通信协议规范。该协议基于MQTT 3.1.1版本设计，旨在提供一个可靠、高效、可扩展的服务间通信方案。

## 2. 协议版本

- MQTT版本: 3.1.1
- 协议版本: 2.0.0
- 最后更新: 2024-04-07

## 3. 主题结构设计

### 3.1 系统级主题

```
/meek/system/nodes                    # 节点列表管理
/meek/system/broadcast               # 系统广播消息
/meek/system/config                  # 系统配置更新
```

### 3.2 节点管理主题

```
/meek/nodes/{node_id}/status         # 节点状态
/meek/nodes/{node_id}/health         # 健康检查
/meek/nodes/{node_id}/resource       # 资源状态
/meek/nodes/{node_id}/config         # 节点配置
```

### 3.3 任务管理主题

```
/meek/tasks/{task_id}/request        # 任务请求
/meek/tasks/{task_id}/status         # 任务状态
/meek/tasks/{task_id}/result         # 任务结果
/meek/tasks/{task_id}/control        # 任务控制
```

### 3.4 分组管理主题

```
/meek/groups/{group_id}/tasks        # 分组任务分发
/meek/groups/{group_id}/nodes        # 分组节点管理
/meek/groups/{group_id}/status       # 分组状态
```

## 4. 消息格式

### 4.1 基础消息格式

所有消息都应遵循以下基础格式：

```json
{
    "version": "2.0.0",          // 协议版本
    "timestamp": 1698765432,     // Unix时间戳(秒)
    "trace_id": "uuid-string",   // 追踪ID
    "message_type": "string",    // 消息类型
    "payload": {}                // 具体消息内容
}
```

### 4.2 节点注册消息

```json
{
    "message_type": "node_register",
    "payload": {
        "node_id": "analysis-001",
        "node_type": "analysis",      // analysis, api
        "group_id": "group-001",      // 节点分组
        "capabilities": {
            "models": ["yolov8"],
            "analysis_types": ["detection", "segmentation", "tracking"],
            "gpu_info": {
                "available": true,
                "name": "NVIDIA A100",
                "memory": "40GB"
            },
            "max_concurrent_tasks": 4
        },
        "metadata": {
            "version": "2.0.0",
            "region": "cn-shanghai",
            "tags": ["gpu", "prod"],
            "ip_address": "192.168.1.100"
        }
    }
}
```

### 4.3 任务请求消息

```json
{
    "message_type": "task_request",
    "payload": {
        "task_id": "task-001",
        "task_type": "image_analysis",
        "priority": 1,                // 1-5, 1最高
        "timeout": 30,                // 超时时间(秒)
        "retry_policy": {
            "max_retries": 3,
            "retry_interval": 5
        },
        "source": {
            "type": "image",          // image, video, stream
            "urls": ["http://..."],
            "is_base64": false,
            "metadata": {}
        },
        "config": {
            "model_code": "yolov8",
            "confidence": 0.5,
            "iou": 0.45,
            "classes": [0, 2],
            "roi": {
                "x1": 0.1,
                "y1": 0.1,
                "x2": 0.9,
                "y2": 0.9
            },
            "imgsz": 640,
            "nested_detection": true
        },
        "result_config": {
            "save_result": false,
            "return_base64": false,
            "callback_urls": ["http://..."]
        }
    }
}
```

### 4.4 任务状态消息

```json
{
    "message_type": "task_status",
    "payload": {
        "task_id": "task-001",
        "status": "running",          // pending, running, completed, failed, stopped
        "progress": 45.5,             // 进度百分比
        "message": "正在处理第45帧...",
        "error": null,                // 错误信息(如果有)
        "resource_usage": {
            "cpu": 35.5,
            "memory": 1.2,            // GB
            "gpu": 65.8
        },
        "stats": {
            "frames_processed": 45,
            "objects_detected": 12,
            "processing_time": 0.045   // 秒
        }
    }
}
```

### 4.5 任务结果消息

```json
{
    "message_type": "task_result",
    "payload": {
        "task_id": "task-001",
        "frame_id": 45,               // 视频/流的帧ID，图片分析为0
        "results": {
            "objects": [
                {
                    "class_id": 0,
                    "class_name": "person",
                    "confidence": 0.95,
                    "bbox": [100, 200, 150, 300],
                    "track_id": "track_001",     // 仅跟踪任务
                    "mask": "base64_mask_data"   // 仅分割任务
                }
            ],
            "frame_info": {
                "width": 1920,
                "height": 1080,
                "processed_time": 0.045
            }
        },
        "image_data": "base64_image_data",  // 可选
        "metadata": {
            "camera_id": "cam_001",
            "location": "entrance"
        }
    }
}
```

## 5. QoS 设置

| 主题类型 | QoS级别 | 说明 |
|---------|---------|------|
| 系统广播 | 1 | 确保系统消息至少送达一次 |
| 节点状态 | 1 | 确保节点状态变更被及时感知 |
| 任务请求 | 2 | 确保任务请求精确到达一次 |
| 任务状态 | 1 | 确保状态更新至少送达一次 |
| 任务结果 | 1 | 确保分析结果至少送达一次 |
| 健康检查 | 0 | 定期心跳，丢失允许 |

## 6. 通信流程

### 6.1 节点注册流程

1. 分析节点启动时：
   - 生成唯一node_id
   - 设置遗嘱消息(LWT)
   - 连接到MQTT Broker
   - 发布注册消息到 `/meek/system/nodes`
   - 订阅相关主题

2. API节点响应：
   - 验证节点信息
   - 更新节点列表
   - 分配分组(可选)
   - 返回确认消息

### 6.2 任务处理流程

1. API节点发起任务：
   - 生成task_id
   - 发布任务请求
   - 订阅任务状态和结果

2. 分析节点处理：
   - 接收任务请求
   - 发送任务确认
   - 定期发布状态更新
   - 发布分析结果
   - 发布任务完成状态

### 6.3 任务控制流程

1. API节点发送控制命令：
   - 发布到任务控制主题
   - 等待确认响应

2. 分析节点响应：
   - 执行控制命令
   - 发布执行结果
   - 更新任务状态

## 7. 错误处理

### 7.1 错误码定义

```json
{
    "error_code": "ERR_001",
    "error_type": "VALIDATION_ERROR",
    "message": "无效的任务参数",
    "details": {
        "field": "confidence",
        "reason": "取值范围应为0-1"
    }
}
```

### 7.2 重试机制

- 任务级重试：按照任务配置的重试策略执行
- 消息级重试：由MQTT QoS机制保证
- 节点级重试：节点离线重连后自动恢复任务

## 8. 安全机制

1. 传输安全
   - 启用TLS 1.3
   - 证书双向验证
   - 消息加密(可选)

2. 访问控制
   - 用户名/密码认证
   - 基于角色的ACL
   - 主题访问权限控制

3. 数据安全
   - 敏感数据加密
   - 消息签名验证
   - 会话状态保护

## 9. 监控与维护

1. 节点监控
   - 在线状态
   - 资源使用
   - 任务队列

2. 性能指标
   - 消息延迟
   - 处理时间
   - 错误率

3. 日志记录
   - 操作日志
   - 错误日志
   - 性能日志

## 10. 版本兼容

1. 版本号规则
   - 主版本号：不兼容的API修改
   - 次版本号：向下兼容的功能性增加
   - 修订号：向下兼容的问题修正

2. 兼容性保证
   - 消息格式向后兼容
   - 主题结构稳定性
   - 渐进式功能迁移

## 11. 最佳实践

1. 主题设计
   - 层次结构清晰
   - 命名规范统一
   - 便于权限控制

2. 消息处理
   - 异步处理为主
   - 超时机制完备
   - 错误处理到位

3. 性能优化
   - 合理设置QoS
   - 控制消息大小
   - 适当的保活间隔

## 12. 示例代码

### Python FastAPI 示例

```python
from fastapi import FastAPI
from paho.mqtt import client as mqtt_client
import json

class MQTTClient:
    def __init__(self):
        self.client = mqtt_client.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
    def connect(self):
        self.client.connect("localhost", 1883)
        self.client.loop_start()
        
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("Connected to MQTT Broker!")
        else:
            print(f"Failed to connect, return code {rc}")
            
    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            # 处理消息
            print(f"Received message on {msg.topic}: {payload}")
        except Exception as e:
            print(f"Error processing message: {e}")
            
    def publish(self, topic, payload):
        result = self.client.publish(topic, json.dumps(payload))
        return result[0]
```

## 13. 变更历史

| 版本 | 日期 | 说明 |
|-----|------|-----|
| 2.0.0 | 2024-04-07 | 初始版本 |
| 1.0.0 | 2024-03-01 | 草稿版本 |
