# MeekYolo 目标检测与跟踪系统

## 项目介绍

MeekYolo是一个基于YOLOv11的目标检测与跟踪系统，支持多种输入源（RTSP流、单张图片、批量图片、视频文件），可以进行实时目标检测、目标跟踪，并提供丰富的可视化配置选项。

## 主要功能

- 多输入源支持：
  - RTSP视频流实时检测
  - 单张图片检测
  - 批量图片检测
  - 视频文件检测
- 目标检测与跟踪：
  - 支持多目标检测
  - 实时目标跟踪
  - 目标ID保持
- 可视化功能：
  - 目标框显示
  - 目标类别显示
  - 跟踪ID显示
  - 置信度显示
  - 位置信息显示
  - 尺寸信息显示
  - FPS显示
- 结果输出：
  - 图片结果保存
  - 视频结果保存
  - 控制台信息输出

## 环境要求

- Python 3.8+
- PyTorch 1.8+
- OpenCV 4.5+
- Ultralytics 8.0+

## 环境安装

1. 创建虚拟环境：

   ```bash
   python -m venv venv
   source venv/bin/activate # Linux/Mac
   venv\Scripts\activate # Windows
   ```
2. 安装依赖：

   ```bash
   pip install -r requirements.txt
   ```

## 快速启动

1. 配置config.yaml文件
2. 运行程序：
   ```bash
   ./scripts/start.sh start
   ```
3. 输入命令控制程序：
   - `start` - 开始分析
   - `stop` - 停止分析

## 使用说明

### 1. RTSP流检测

```yaml
source:
type: "rtsp"
rtsp:
url: "rtsp://your_rtsp_url"
ffmpeg_options:
"?tcp"
```

### 2. 单张图片检测

```yaml
source:
type: "image"
image:
path: "data/test.jpg"
save_path: "results/test_result.jpg"
```

### 3. 批量图片检测

```yaml
source:
type: "images"
images:
input_dir: "data/images"
save_dir: "results/images"
formats: [".jpg", ".jpeg", ".png"]
```

### 4. 视频文件检测

```yaml
source:
type: "video"
video:
path: "data/test.mp4"
save_path: "results/test_result.mp4"
fps: 30
```

## 配置文件说明

### 1. 输入源配置 (source)

```yaml
source:
type: "rtsp"/"image"/"images"/"video" # 输入源类型
```

### 2. 模型配置 (model)

```yaml
model:
path: "model/best.pt" # 模型路径
conf_thres: 0.5 # 置信度阈值
```

### 3. 显示配置 (display)

```yaml
display:
window_name: "MeekYolo" # 窗口名称
show_fps: true # 是否显示FPS
```

### 4. 控制台输出配置 (console)

```yaml
console:
enabled: false # 是否启用控制台输出
show_time: false # 显示时间戳
show_total: false # 显示总目标数
show_details: false # 显示详细信息
show_separator: false # 显示分隔线
```

### 5. 可视化视化配置 (visualization)

```yaml
visualization:
show_box: true # 显示目标框
show_class: true # 显示类别
show_track_id: true # 显示跟踪ID
show_confidence: true # 显示置信度
show_position: true # 显示位置信息
show_size: true # 显示尺寸信息
show_anchor: true # 显示锚点
show_line: true # 显示连接线
style:
font_scale: 0.6 # 字体大小
thickness: 2 # 线条粗细
chinese_text_size: 20 # 中文字体大小
margin: 5 # 边距
colors:
text: [255,255,255] # 文本颜色
background: [0,0,0] # 背景颜色
```

### 6. 跟踪配置 (tracking)

```yaml
tracking:
enabled: true # 是否启用跟踪
persist: true # 是否保持ID
```

### 7. 打印控制 (print)

```yaml
print:
enabled: false # 是否允许任何打印输出
```

## 注意事项

1. 确保模型文件存在于指定路径
2. 检查输入源路径的正确性
3. 确保有足够的磁盘空间保存结果
4. 对于RTSP流，确保网络连接稳定
5. 建议根据实际需求调整置信度阈值

## 常见问题

1. 如果出现中文显示问题，请检查字体文件路径
2. 如果检测效果不理想，可以调整置信度阈值
3. 如果跟踪不稳定，可以调整persist参数
4. 如果FPS过低，可以考虑关闭一些可视化选项

## 更新日志

- 2024.12.6: 初始版本发布
  - 支持多种输入源
  - 添加目标跟踪功能
  - 完善可视化配置
  - 支持中文类别显示
  - 支持读取yolo配置文件描述
- 2024.12.26:优化细节
  - 优化启动环境检测
  - 增强多终端系统适配
  - 修复分析错误

## Docker 部署

### 环境要求

- Docker 20.10+
- Docker Compose 2.0+
- NVIDIA Container Toolkit (GPU版本需要)
- 对于 M1/M2/M3 Mac: macOS 12.0+

### 1. CPU 版本部署 (Intel/AMD)

适用于普通 x86_64 架构 CPU。

```bash
# 启动服务
docker-compose up --build -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f analysis-service

# 停止服务
docker-compose down
```

### 2. Apple Silicon 部署 (M1/M2/M3)

适用于搭载 Apple Silicon 芯片的 Mac 设备。

```bash
# 启动服务
docker-compose -f docker-compose.yml -f docker-compose.m1.yml up --build -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f analysis-service

# 停止服务
docker-compose down
```

注意事项：
- 确保 Docker Desktop for Mac (Apple Silicon) 已安装
- 建议在 Docker Desktop 设置中分配至少 4GB 内存
- 首次构建可能需要较长时间，因为需要构建 ARM 版本的依赖

### 3. GPU 版本部署 (NVIDIA)

适用于配备 NVIDIA GPU 的设备。

```bash
# 检查 NVIDIA 驱动和 CUDA
nvidia-smi

# 检查 nvidia-docker
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi

# 启动服务
docker-compose -f docker-compose.yml -f docker-compose.gpu.yml up --build -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f analysis-service

# 检查 GPU 使用情况
docker exec -it analysis-service nvidia-smi

# 停止服务
docker-compose down
```

前置要求：
1. 安装 NVIDIA 驱动和 CUDA：
```bash
sudo apt install nvidia-driver-535 cuda-toolkit-12-1
```

2. 安装 NVIDIA Container Toolkit：
```bash
distribution=$(. /etc/os-release;echo $ID$VERSION_ID) \
   && curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add - \
   && curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update
sudo apt-get install -y nvidia-docker2
sudo systemctl restart docker
```

### 资源清理

对于所有版本，清理命令都是一样的：

```bash
# 停止并删除容器、网络
docker-compose down

# 同时删除构建的镜像
docker-compose down --rmi all

# 同时删除数据卷
docker-compose down --volumes

# 清理所有未使用的资源（慎用）
docker system prune -a
```

### 常见问题处理

1. 构建失败：
```bash
# 清理构建缓存后重试
docker builder prune
docker-compose build --no-cache
```

2. 容器无法启动：
```bash
# 检查端口占用
lsof -i :8002

# 查看详细日志
docker-compose logs -f
```

3. GPU 版本问题：
```bash
# 检查 GPU 是否可用
docker exec -it analysis-service python3 -c "import torch; print(torch.cuda.is_available())"
```

4. M1/M2/M3 版本问题：
```bash
# 确认使用正确的平台
docker inspect analysis-service | grep Platform
```

### 性能优化建议

1. CPU 版本：
   - 适当调整 `cpus` 和 `memory` 限制
   - 使用 volume 而不是 bind mount
   - 考虑使用 tmpfs 挂载临时目录

2. GPU 版本：
   - 确保 CUDA 版本匹配
   - 监控 GPU 内存使用
   - 适当调整批处理大小

3. Apple Silicon 版本：
   - 在 Docker Desktop 中分配足够资源
   - 使用 buildx 进行多平台构建
   - 注意 ARM 兼容性问题

## 子模块

本项目使用了以下子模块：

- ZLMediaKit: 流媒体服务器框架
  ```bash
  # 克隆项目时包含子模块
  git clone --recursive https://github.com/your/project.git

  # 或者在克隆后初始化子模块
  git submodule update --init --recursive
  ```
