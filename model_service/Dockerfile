FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai \
    MODEL_PATH=/app/models

# 安装基础依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    python3-dev \
    libpq-dev \
    logrotate \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 创建非root用户
RUN useradd -m -s /bin/bash appuser

# 创建必要的目录
RUN mkdir -p /app/models /app/data /app/logs && \
    chown -R appuser:appuser /app

# 配置日志轮转
RUN echo "/app/logs/*.log {\n  daily\n  rotate 7\n  compress\n  missingok\n  notifempty\n}" > /etc/logrotate.d/app

# 复制shared目录
COPY --chown=appuser:appuser shared /app/shared/

# 复制model_service服务
COPY --chown=appuser:appuser model_service /app/model_service/

# 复制配置文件
COPY --chown=appuser:appuser config /app/config/

# 安装Python依赖
COPY --chown=appuser:appuser model_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 暴露端口
EXPOSE 8003

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8003/health || exit 1

# 切换到非root用户
USER appuser

# 启动服务
CMD ["python", "-m", "uvicorn", "model_service.app:app", "--host", "0.0.0.0", "--port", "8003"]