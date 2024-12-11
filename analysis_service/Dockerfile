FROM python:3.10-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 复制共享模块
COPY shared /app/shared

# 复制本服务代码
COPY analysis_service /app/analysis_service

# 复制依赖文件
COPY analysis_service/requirements.txt .
COPY setup.py .

# 安装依赖
RUN pip install -r requirements.txt

# 安装本地包
RUN pip install -e .

# 创建静态文件目录
RUN mkdir static

# 启动服务
CMD ["uvicorn", "analysis_service.app:app", "--host", "0.0.0.0", "--port", "8002"] 