FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY pyproject.toml .
COPY src/ src/
COPY configs/ configs/
COPY README.md .

# 升级 pip 并安装
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir .

# 创建数据目录
RUN mkdir -p data logs

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')"

# 启动命令
CMD ["yuanbot", "start"]
