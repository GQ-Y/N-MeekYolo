FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai

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
RUN mkdir -p /app/data /app/logs /app/models && \
    chown -R appuser:appuser /app

# 配置日志轮转
RUN echo "/app/logs/*.log {\n  daily\n  rotate 7\n  compress\n  missingok\n  notifempty\n}" > /etc/logrotate.d/app

# 复制必要的文件
COPY --chown=appuser:appuser shared /app/shared/
COPY --chown=appuser:appuser cloud_service /app/cloud_service/
COPY --chown=appuser:appuser config /app/config/
COPY --chown=appuser:appuser cloud_service/requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 暴露端口
EXPOSE 8004

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8004/health || exit 1

# 切换到非root用户
USER appuser

# 启动服务
CMD ["python", "-m", "uvicorn", "cloud_service.app:app", "--host", "0.0.0.0", "--port", "8004"]