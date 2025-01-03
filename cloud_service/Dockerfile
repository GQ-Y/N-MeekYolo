FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai \
    CONFIG_PATH=/app/config/config.yaml

# 安装基础依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    python3-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 创建必要的目录
RUN mkdir -p /app/data /app/logs

# 复制shared目录
COPY shared /app/shared/

# 复制cloud_service服务
COPY cloud_service /app/cloud_service/

# 复制配置文件
COPY config /app/config/

# 安装Python依赖
COPY cloud_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 暴露端口
EXPOSE 8004

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://cloud_service:8004/health || exit 1

# 启动服务
CMD ["python", "-m", "uvicorn", "cloud_service.app:app", "--host", "0.0.0.0", "--port", "8004"] 