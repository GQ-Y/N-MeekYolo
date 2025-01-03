FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai \
    CONFIG_PATH=/app/config/config.yaml

# 安装基础依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3-pip \
    curl \
    gcc \
    python3-dev \
    libpq-dev \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# 创建必要的目录
RUN mkdir -p /app/models /app/data /app/logs /app/results

# 复制shared目录
COPY shared /app/shared/

# 复制analysis_service服务
COPY analysis_service /app/analysis_service/

# 复制配置文件
COPY config /app/config/

# 安装Python依赖
COPY analysis_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 暴露端口
EXPOSE 8002

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

# 启动服务
CMD ["python", "-m", "uvicorn", "analysis_service.app:app", "--host", "0.0.0.0", "--port", "8002"] 