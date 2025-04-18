# 第一阶段：下载依赖
FROM python:3.10-slim AS downloader

# 避免交互式提示
ENV DEBIAN_FRONTEND=noninteractive

# 配置腾讯源
RUN echo "deb https://mirrors.cloud.tencent.com/debian/ bookworm main contrib non-free non-free-firmware" > /etc/apt/sources.list \
    && echo "deb https://mirrors.cloud.tencent.com/debian/ bookworm-updates main contrib non-free non-free-firmware" >> /etc/apt/sources.list \
    && echo "deb https://mirrors.cloud.tencent.com/debian-security bookworm-security main contrib non-free non-free-firmware" >> /etc/apt/sources.list

# 设置 pip 源为腾讯源
RUN pip config set global.index-url https://mirrors.cloud.tencent.com/pypi/simple \
    && pip config set global.timeout 1000 \
    && pip config set install.trusted-host mirrors.cloud.tencent.com

# 设置工作目录
WORKDIR /wheels

# 复制依赖文件
COPY cloud_service/requirements.txt .

# 下载预编译的 wheel 包和构建依赖
RUN pip download --no-deps \
    setuptools>=43 \
    wheel \
    -d /wheels \
    && pip download -r requirements.txt -d /wheels

# 第二阶段：构建环境
FROM python:3.10-slim AS builder

# 避免交互式提示
ENV DEBIAN_FRONTEND=noninteractive

# 配置腾讯源
RUN echo "deb https://mirrors.cloud.tencent.com/debian/ bookworm main contrib non-free non-free-firmware" > /etc/apt/sources.list \
    && echo "deb https://mirrors.cloud.tencent.com/debian/ bookworm-updates main contrib non-free non-free-firmware" >> /etc/apt/sources.list \
    && echo "deb https://mirrors.cloud.tencent.com/debian-security bookworm-security main contrib non-free non-free-firmware" >> /etc/apt/sources.list

# 设置工作目录
WORKDIR /build

# 安装构建必要的包
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件和 wheel 包
COPY cloud_service/requirements.txt .
COPY --from=downloader /wheels /wheels

# 创建虚拟环境并安装依赖
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 安装构建工具
RUN pip install --no-cache-dir --no-index --find-links=/wheels setuptools wheel

# 安装依赖
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt

# 第三阶段：运行环境
FROM python:3.10-slim AS runner

# 避免交互式提示
ENV DEBIAN_FRONTEND=noninteractive

# 配置腾讯源
RUN echo "deb https://mirrors.cloud.tencent.com/debian/ bookworm main contrib non-free non-free-firmware" > /etc/apt/sources.list \
    && echo "deb https://mirrors.cloud.tencent.com/debian/ bookworm-updates main contrib non-free non-free-firmware" >> /etc/apt/sources.list \
    && echo "deb https://mirrors.cloud.tencent.com/debian-security bookworm-security main contrib non-free non-free-firmware" >> /etc/apt/sources.list

# 安装运行必要的工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    netcat-traditional \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制虚拟环境
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 创建必要的目录
RUN mkdir -p /app/data /app/logs /app/config \
    && chmod -R 755 /app/data \
    && chmod -R 755 /app/logs \
    && chmod -R 755 /app/config \
    && touch /app/data/cloud_market.db \
    && chmod 644 /app/data/cloud_market.db

# 设置环境变量
ENV PYTHONPATH=/app
ENV CLOUD_SERVICE_ENV=production
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV CONFIG_PATH=/app/config/config.yaml

# 复制应用代码
COPY cloud_service /app/cloud_service
COPY shared /app/shared

# 复制启动脚本和健康检查脚本
COPY cloud_service/docker/entrypoint.sh /app/
COPY cloud_service/docker/healthcheck.sh /app/
RUN chmod +x /app/entrypoint.sh /app/healthcheck.sh \
    && sed -i 's/\r//g' /app/*.sh

# 创建非 root 用户并设置权限
RUN groupadd -r cloud && useradd -r -g cloud cloud \
    && chown -R cloud:cloud /app

# 切换到非 root 用户
USER cloud

# 设置健康检查
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD [ "/app/healthcheck.sh" ]

# 暴露端口
EXPOSE 8004

# 启动服务
ENTRYPOINT ["/app/entrypoint.sh"] 