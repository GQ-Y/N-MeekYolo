FROM python:3.10-slim

WORKDIR /app

# 复制共享模块
COPY shared /app/shared

# 复制本服务代码
COPY gateway /app/gateway

# 复制依赖文件
COPY gateway/requirements.txt .
COPY setup.py .

# 创建静态文件目录
RUN mkdir static

# 安装依赖
RUN pip install -r requirements.txt

# 安装本地包
RUN pip install -e .

# 启动服务
CMD ["uvicorn", "gateway.app:app", "--host", "0.0.0.0", "--port", "8000"] 