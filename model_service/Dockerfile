# 第一阶段：依赖安装
FROM ubuntu:22.04 AS builder

# 避免交互式提示
ENV DEBIAN_FRONTEND=noninteractive

# 设置工作目录
WORKDIR /build

# 安装 Python 和基础工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3.10-venv \
    python3-pip \
    build-essential \
    curl \
    netcat-traditional \
    && rm -rf /var/lib/apt/lists/*

# 设置pip镜像源和超时
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    && pip config set global.timeout 1000

# 复制依赖文件
COPY model_service/requirements.txt .

# 创建虚拟环境并安装依赖
RUN python3.10 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt

# 第二阶段：运行环境
FROM ubuntu:22.04 AS runner

# 避免交互式提示
ENV DEBIAN_FRONTEND=noninteractive

# 安装 Python 运行时
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3-venv \
    netcat-traditional \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制虚拟环境
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 创建必要的目录
RUN mkdir -p /app/data /app/logs \
    && mkdir -p /app/config \
    && chmod -R 755 /app/data \
    && chmod -R 755 /app/logs \
    && chmod -R 755 /app/config

# 设置环境变量
ENV PYTHONPATH=/app
ENV MODEL_SERVICE_ENV=production
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV CONFIG_PATH=/app/config/config.yaml

# 复制应用代码
COPY model_service /app/model_service
COPY shared /app/shared

# 复制启动脚本和健康检查脚本
COPY model_service/docker/entrypoint.sh /app/entrypoint.sh
COPY model_service/docker/healthcheck.sh /app/healthcheck.sh
RUN chmod +x /app/entrypoint.sh /app/healthcheck.sh

# 设置健康检查
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD [ "/app/healthcheck.sh" ]

# 暴露端口
EXPOSE 8003

# 启动服务
ENTRYPOINT ["/app/entrypoint.sh"] 