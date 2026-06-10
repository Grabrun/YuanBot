---
title: 部署指南
description: YuanBot Docker、Kubernetes、Serverless 等多种部署方案
---

# 部署指南

本指南介绍 YuanBot 的多种部署方式，从本地开发到生产环境。

---

## 目录

- [Docker 部署](#docker-部署)
- [Docker Compose 部署](#docker-compose-部署)
- [Kubernetes 部署](#kubernetes-部署)
- [Serverless 部署](#serverless-部署)
- [生产环境建议](#生产环境建议)

---

## Docker 部署

### 构建镜像

```bash
# 在项目根目录执行
docker build -t yuanbot:latest .
```

Dockerfile 说明：

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends gcc

# 安装 Python 依赖
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# 复制源代码和配置
COPY src/ src/
COPY configs/ configs/

# 创建数据目录
RUN mkdir -p data logs

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# 启动
CMD ["yuanbot", "start"]
```

### 运行容器

```bash
docker run -d \
  --name yuanbot \
  -p 8000:8000 \
  -e YUAN_AI_API_KEY=sk-your-api-key \
  -v $(pwd)/configs:/app/configs \
  -v $(pwd)/data:/app/data \
  yuanbot:latest
```

### 带 Redis 运行

```bash
# 先启动 Redis
docker run -d --name yuanbot-redis -p 6379:6379 redis:7-alpine

# 再启动 YuanBot
docker run -d \
  --name yuanbot \
  -p 8000:8000 \
  -e YUAN_AI_API_KEY=sk-your-api-key \
  -e YUANBOT_REDIS_URL=redis://host.docker.internal:6379/0 \
  -v $(pwd)/configs:/app/configs \
  -v $(pwd)/data:/app/data \
  --link yuanbot-redis:redis \
  yuanbot:latest
```

---

## Docker Compose 部署

### 默认配置

项目根目录的 `docker-compose.yaml`：

```yaml
version: '3.8'

services:
  yuanbot:
    build: .
    restart: always
    ports:
      - "8000:8000"
    volumes:
      - ./configs:/app/configs
      - ./data:/app/data
      - ./logs:/app/logs
    environment:
      - YUAN_AI_API_KEY=${YUAN_AI_API_KEY}
      - YUAN_AI_PROVIDER=${YUAN_AI_PROVIDER:-openai}
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 3s
      retries: 3
```

### 启动

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API Key

# 2. 启动
docker-compose up -d

# 3. 查看日志
docker-compose logs -f yuanbot

# 4. 停止
docker-compose down
```

### 带 Redis 的完整配置

创建 `docker-compose.prod.yaml`：

```yaml
version: '3.8'

services:
  yuanbot:
    build: .
    restart: always
    ports:
      - "8000:8000"
    volumes:
      - ./configs:/app/configs
      - ./data:/app/data
      - ./logs:/app/logs
    environment:
      - YUAN_AI_API_KEY=${YUAN_AI_API_KEY}
      - YUAN_AI_PROVIDER=${YUAN_AI_PROVIDER:-openai}
      - YUANBOT_REDIS_URL=redis://redis:6379/0
    depends_on:
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 3s
      retries: 3

  redis:
    image: redis:7-alpine
    restart: always
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

volumes:
  redis-data:
```

启动：

```bash
docker-compose -f docker-compose.prod.yaml up -d
```

### 带 MySQL 的完整配置

```yaml
version: '3.8'

services:
  yuanbot:
    build: .
    restart: always
    ports:
      - "8000:8000"
    volumes:
      - ./configs:/app/configs
      - ./data:/app/data
    environment:
      - YUAN_AI_API_KEY=${YUAN_AI_API_KEY}
      - YUANBOT_REDIS_URL=redis://redis:6379/0
      - YUAN_DB_MYSQL_PASSWORD=${MYSQL_PASSWORD}
    depends_on:
      - redis
      - mysql

  redis:
    image: redis:7-alpine
    restart: always
    volumes:
      - redis-data:/data

  mysql:
    image: mysql:8.0
    restart: always
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      MYSQL_DATABASE: yuanbot
      MYSQL_USER: yuanbot
      MYSQL_PASSWORD: ${MYSQL_PASSWORD}
    volumes:
      - mysql-data:/var/lib/mysql
    ports:
      - "3306:3306"

volumes:
  redis-data:
  mysql-data:
```

---

## Kubernetes 部署

### 前置要求

- Kubernetes 集群 (>= 1.24)
- kubectl 已配置
- Nginx Ingress Controller（可选，用于外部访问）

### 部署步骤

```bash
# 1. 创建命名空间
kubectl create namespace yuanbot

# 2. 创建 Secret（存放 API Key）
kubectl create secret generic yuanbot-secrets \
  --from-literal=OPENAI_API_KEY=sk-your-api-key \
  -n yuanbot

# 3. 部署所有资源
kubectl apply -f k8s/

# 4. 查看部署状态
kubectl get pods -n yuanbot
kubectl get services -n yuanbot
```

### 资源清单

`k8s/deployment.yaml` 包含以下资源：

| 资源 | 名称 | 说明 |
|------|------|------|
| Namespace | yuanbot | 命名空间 |
| ConfigMap | yuanbot-config | 配置文件 |
| Deployment | yuanbot | 主应用（2 副本） |
| Service | yuanbot | ClusterIP 服务 |
| PersistentVolumeClaim | yuanbot-data | 数据持久化存储 |
| Deployment | yuanbot-redis | Redis（可选） |
| Service | yuanbot-redis | Redis 服务 |
| Ingress | yuanbot | 外部访问（可选） |

### 应用配置

**ConfigMap** 中的 `bot.yaml`：

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: yuanbot-config
  namespace: yuanbot
data:
  bot.yaml: |
    app_name: "YuanBot"
    version: "1.0.0"
    debug: false
    log_level: "INFO"
    ai:
      default_provider: "openai"
    proactive:
      enabled: true
      frequency: "medium"
      max_per_day: 5
```

**资源限制**：

```yaml
resources:
  requests:
    cpu: 250m
    memory: 256Mi
  limits:
    cpu: 1000m
    memory: 1Gi
```

### 健康检查

```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: http
  initialDelaySeconds: 10
  periodSeconds: 30

readinessProbe:
  httpGet:
    path: /readyz
    port: http
  initialDelaySeconds: 5
  periodSeconds: 10
```

### Ingress 配置

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: yuanbot
  namespace: yuanbot
  annotations:
    nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "3600"
    nginx.ingress.kubernetes.io/websocket-services: "yuanbot"
spec:
  ingressClassName: nginx
  rules:
    - host: yuanbot.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: yuanbot
                port:
                  name: http
          - path: /ws
            pathType: Prefix
            backend:
              service:
                name: yuanbot
                port:
                  name: ws
  tls:
    - hosts:
        - yuanbot.example.com
      secretName: yuanbot-tls
```

### 扩缩容

```bash
# 手动扩缩容
kubectl scale deployment yuanbot --replicas=3 -n yuanbot

# 自动扩缩容（需要 metrics-server）
kubectl autoscale deployment yuanbot \
  --min=2 --max=10 --cpu-percent=70 \
  -n yuanbot
```

---

## Serverless 部署

YuanBot 支持 AWS Lambda 和阿里云函数计算部署。

### AWS Lambda

#### 1. 安装依赖

```bash
pip install "yuanbot[serverless]"
```

#### 2. 配置

使用 `configs/serverless.yaml`：

```yaml
app_name: "YuanBot"
version: "1.0.0"
debug: false
log_level: "INFO"

ai_provider:
  provider_id: "openai"
  default_model: "gpt-4o"

channels:
  - platform: "web"
    enabled: true
    config: {}

# Serverless 环境使用临时存储
memory:
  vector_db: "milvus_lite"
  vector_db_url: "/tmp/yuanbot/milvus"
  db_url: "sqlite:///tmp/yuanbot.db"
  redis_url: "${YUANBOT_REDIS_URL}"
  graph_db: "kuzu"
  graph_db_url: "/tmp/yuanbot/kuzu"
  max_working_memory_turns: 10

# Serverless 模式禁用定时任务
proactive:
  enabled: false
```

#### 3. 创建 Handler

```python
# lambda_handler.py
from yuanbot.deployment.serverless import create_handler

handler = create_handler()
```

或使用内置 handler：

```python
# AWS Lambda handler
handler: yuanbot.deployment.serverless.aws_handler
```

#### 4. 部署

使用 AWS SAM 或 Serverless Framework 部署。

**SAM template.yaml 示例**：

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  YuanBotFunction:
    Type: AWS::Serverless::Function
    Properties:
      Handler: yuanbot.deployment.serverless.aws_handler
      Runtime: python3.12
      MemorySize: 512
      Timeout: 30
      Environment:
        Variables:
          YUAN_AI_API_KEY: !Ref ApiKey
          YUANBOT_CONFIG_PATH: configs/serverless.yaml
      Events:
        Api:
          Type: Api
          Properties:
            Path: /{proxy+}
            Method: ANY
```

### 阿里云函数计算

```python
# 使用 aliyun_handler
handler: yuanbot.deployment.serverless.aliyun_handler
```

### Serverless 注意事项

| 项目 | 说明 |
|------|------|
| **存储** | 使用 `/tmp` 临时存储，数据不持久化 |
| **Redis** | 建议使用云 Redis 服务 |
| **主动交互** | Serverless 模式下禁用定时任务 |
| **冷启动** | 首次请求可能有 2-5 秒延迟 |
| **超时** | 设置合理的函数超时时间（建议 30 秒） |

---

## 生产环境建议

### 安全

1. **API Key 管理**
   - 使用环境变量或 Secret 管理服务（如 AWS Secrets Manager、K8s Secrets）
   - 不要将 API Key 硬编码在配置文件中
   - 定期轮换 API Key

2. **网络隔离**
   - 使用防火墙限制端口访问
   - 生产环境不要暴露 Redis、MySQL 等内部服务
   - 使用 VPC 或网络策略隔离服务

3. **HTTPS**
   - 使用 Nginx 或 Ingress 配置 TLS
   - 强制 HTTPS 重定向
   - 配置 HSTS 头

4. **认证**
   - 为 API 端点配置认证（Basic Auth、JWT 或 API Key）
   - WebSocket 连接验证来源

### 数据库

1. **关系数据库**
   - 开发环境使用 SQLite（零配置）
   - 生产环境建议使用 MySQL 或 PostgreSQL
   - 定期备份数据库

2. **Redis**
   - 配置密码认证
   - 使用独立的 Redis 实例
   - 监控内存使用

3. **向量数据库**
   - Milvus Lite 适合单机部署
   - 大规模使用建议部署 Milvus 集群

### 监控

1. **Prometheus 指标**
   - 配置 Prometheus 抓取 `/metrics` 端点
   - 监控请求延迟、错误率、AI 调用次数
   - 设置告警规则

2. **日志**
   - 生产环境使用 JSON 格式日志
   - 集中收集日志（ELK、Loki 等）
   - 设置日志级别为 INFO 或 WARNING

3. **健康检查**
   - 配置 liveness 和 readiness probe
   - 监控 `/healthz` 和 `/readyz` 端点

### 性能

1. **资源规划**
   - 最低配置：1 CPU / 512MB 内存
   - 推荐配置：2 CPU / 2GB 内存
   - 根据并发量调整副本数

2. **缓存**
   - 启用 Redis 缓存工作记忆
   - 配置合理的 TTL

3. **连接池**
   - MySQL 连接池大小：10-20
   - Redis 最大连接数：20-50

### 备份

```bash
# SQLite 备份
cp data/yuanbot.db data/yuanbot.db.backup.$(date +%Y%m%d)

# MySQL 备份
mysqldump -u yuanbot -p yuanbot > backup_$(date +%Y%m%d).sql

# 配置文件备份
tar czf configs_backup_$(date +%Y%m%d).tar.gz configs/
```

### 更新

```bash
# Docker Compose 更新
docker-compose pull
docker-compose up -d

# Kubernetes 更新
kubectl set image deployment/yuanbot yuanbot=yuanbot:latest -n yuanbot

# 本地更新
git pull
pip install -e ".[dev]"
yuanbot start
```

---

## 部署模式对比

| 模式 | 适用场景 | 优势 | 劣势 |
|------|----------|------|------|
| **本地开发** | 开发调试 | 零配置、热重载 | 不适合生产 |
| **Docker** | 单机部署 | 环境隔离、易迁移 | 单点故障 |
| **Docker Compose** | 小型生产 | 多服务编排 | 扩展性有限 |
| **Kubernetes** | 大型生产 | 高可用、自动扩缩 | 运维复杂 |
| **Serverless** | 低流量 API | 按需计费、免运维 | 冷启动、超时限制 |
