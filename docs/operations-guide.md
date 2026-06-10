---
title: 运维指南 — 日志聚合系统
description: YuanBot 日志聚合系统架构、部署、配置和日常运维操作
---

# YuanBot 运维指南 — 日志聚合系统

> 本文档说明 YuanBot 日志聚合系统的架构、部署、配置和日常运维操作。

---

## 目录

1. [系统架构](#1-系统架构)
2. [组件说明](#2-组件说明)
3. [部署步骤](#3-部署步骤)
4. [配置详解](#4-配置详解)
5. [Grafana 仪表盘](#5-grafana-仪表盘)
6. [日常运维](#6-日常运维)
7. [故障排查](#7-故障排查)
8. [安全加固](#8-安全加固)
9. [性能调优](#9-性能调优)

---

## 1. 系统架构

```text
┌──────────────┐    JSON Logs     ┌──────────────┐    Push (HTTP)    ┌──────────┐
│   YuanBot    │ ──────────────>  │   Promtail   │ ──────────────>  │   Loki   │
│   应用服务    │    logs/*.log    │   日志采集    │   /loki/api/v1   │  日志存储  │
└──────────────┘                  └──────────────┘       push       └────┬─────┘
                                                                        │
                                                                        │ Query (LogQL)
                                                                        │
                                                                   ┌────▼─────┐
                                                                   │ Grafana  │
                                                                   │ 可视化    │
                                                                   └──────────┘
                                                                        :3000
```

**数据流：**
1. YuanBot 应用通过 `logging_config.py` 输出结构化 JSON 日志到 `logs/` 目录
2. Promtail 监控日志文件变化，解析 JSON 字段，添加标签
3. Promtail 将解析后的日志推送到 Loki
4. Grafana 通过 Loki 数据源查询和展示日志

---

## 2. 组件说明

| 组件 | 版本 | 端口 | 用途 |
|------|------|------|------|
| **Loki** | 3.0.0 | 3100 | 日志存储与查询引擎 |
| **Promtail** | 3.0.0 | 9080 | 日志文件采集代理 |
| **Grafana** | 11.0.0 | 3000 | 可视化仪表盘 |

### 关键特性

- **Loki**: 使用 `boltdb-shipper` 存储引擎，数据保留 30 天，自动压缩清理
- **Promtail**: 自动解析 JSON 日志，提取 `level`、`logger`、`message` 字段作为标签
- **Grafana**: 自动配置 Loki 数据源，预置 YuanBot 日志监控仪表盘

---

## 3. 部署步骤

### 3.1 前置要求

- Docker 20.10+
- Docker Compose v2+
- 至少 2GB 可用内存
- 至少 10GB 可用磁盘空间

### 3.2 部署命令

```bash
# 进入项目根目录
cd /path/to/yuanbot

# 设置 Grafana 管理员密码（可选，默认: yuanbot2024）
export GRAFANA_ADMIN_PASSWORD="your-secure-password"

# 启动全部服务（含日志聚合栈）
docker compose up -d

# 验证服务状态
docker compose ps

# 检查 Loki 健康状态
curl http://localhost:3100/ready
```

### 3.3 仅启动日志聚合栈

```bash
# 只启动 Loki + Promtail + Grafana
docker compose up -d loki promtail grafana
```

### 3.4 验证部署

```bash
# 1. 检查 Loki 是否就绪
curl -s http://localhost:3100/ready
# 预期输出: ready

# 2. 检查 Promtail 是否能推送到 Loki
curl -s http://localhost:3100/loki/api/v1/labels
# 预期输出: {"status":"success","data":[]}

# 3. 访问 Grafana
open http://localhost:3000
# 账号: admin / 密码: (环境变量设置的密码)
```

---

## 4. 配置详解

### 4.1 Loki 配置 (`configs/loki/loki-config.yaml`)

| 配置项 | 值 | 说明 |
|--------|-----|------|
| `auth_enabled` | false | 单租户模式，不需要多租户认证 |
| `server.http_listen_port` | 3100 | HTTP API 端口 |
| `schema_config.configs[0].store` | tsdb | 使用 TSDB 索引 (Loki 3.0+) |
| `schema_config.configs[0].schema` | v13 | 存储架构版本 |
| `limits_config.retention_period` | 720h (30天) | 日志保留期限 |
| `compactor.retention_enabled` | true | 启用自动清理过期数据 |

**调整保留期：**

```yaml
# 修改 loki-config.yaml 中的 limits_config
limits_config:
  retention_period: 720h  # 改为你需要的时间，如 720h=30天, 168h=7天
```

### 4.2 Promtail 配置 (`configs/loki/promtail-config.yaml`)

**采集路径：**
- YuanBot 日志: `/var/log/yuanbot/*.log` (挂载自 `./logs`)
- Nginx 日志: `/var/log/nginx/*.log`

**Pipeline 处理流程：**

```text
原始日志行 → JSON 解析 → 标签提取 → 时间戳覆盖 → 消息提取 → DEBUG 丢弃
```

**丢弃 DEBUG 日志：** 默认配置会丢弃 DEBUG 级别日志以减少存储。如需保留，注释掉 `match` 阶段：

```yaml
# 注释掉以下配置即可保留 DEBUG 日志
# - match:
#     selector: '{job="yuanbot", level="DEBUG"}'
#     action: drop
```

### 4.3 Grafana 配置

**数据源** (`configs/grafana/provisioning/datasources/datasources.yaml`)：
- Loki 数据源自动注册，指向 `http://loki:3100`

**仪表盘** (`configs/grafana/provisioning/dashboards/dashboards.yaml`)：
- 自动加载 `configs/grafana/dashboards/` 目录下的 JSON 仪表盘

---

## 5. Grafana 仪表盘

### 预置仪表盘面板

| 面板 | 类型 | 说明 |
|------|------|------|
| **日志吞吐量** | 时序柱状图 | 各级别日志每分钟写入速率，堆叠展示 |
| **错误 & 告警日志** | 日志流 | 实时 ERROR/CRITICAL 级别日志 |
| **模块日志分布** | 饼图 | Top 10 Python Logger 模块的日志产出占比 |
| **错误率趋势** | 时序折线图 | ERROR/CRITICAL 占总日志的百分比 |
| **关键事件追踪** | 日志流 | 包含 `event` 字段的业务事件 |
| **最近日志流** | 日志流 | 全部 YuanBot 日志实时流 |
| **错误关键词搜索** | 日志流 | Exception/Traceback/Timeout 等错误模式 |

### LogQL 查询示例

```logql
# 查看所有 ERROR 日志
{job="yuanbot", level="ERROR"}

# 搜索包含 "timeout" 的日志
{job="yuanbot"} |= "timeout"

# 统计每分钟错误数
sum(rate({job="yuanbot", level="ERROR"} [1m])) by (logger)

# 按模块统计日志量
sum by (logger) (count_over_time({job="yuanbot"} [5m]))

# 正则匹配异常堆栈
{job="yuanbot"} |~ "(?i)(Exception|Traceback)"

# JSON 表达式查询（查找特定事件）
{job="yuanbot"} | json | event = "user_login"
```

### 访问仪表盘

1. 打开 `http://localhost:3000`
2. 使用 admin 账号登录
3. 导航至 **Dashboards → YuanBot → YuanBot 日志监控**

---

## 6. 日常运维

### 6.1 日志存储管理

```bash
# 查看 Loki 数据卷大小
docker exec yuanbot-loki du -sh /loki

# 查看各目录大小
docker exec yuanbot-loki du -sh /loki/*

# 手动触发压缩（通常自动执行）
docker exec yuanbot-loki /usr/bin/loki -config.file=/etc/loki/loki-config.yaml -target=compactor
```

### 6.2 扩展存储

对于生产环境，建议使用外部对象存储（S3/MinIO）替代本地文件系统：

```yaml
# loki-config.yaml 中修改 common.storage
common:
  storage:
    s3:
      endpoint: minio:9000
      insecure: true
      bucketnames: loki-data
      access_key_id: ${MINIO_ACCESS_KEY}
      secret_access_key: ${MINIO_SECRET_KEY}
      s3forcepathstyle: true
```

### 6.3 备份与恢复

```bash
# 备份 Loki 数据
docker run --rm -v yuanbot_loki-data:/data -v $(pwd):/backup \
  alpine tar czf /backup/loki-backup-$(date +%Y%m%d).tar.gz -C /data .

# 恢复 Loki 数据
docker run --rm -v yuanbot_loki-data:/data -v $(pwd):/backup \
  alpine tar xzf /backup/loki-backup-YYYYMMDD.tar.gz -C /data
```

### 6.4 更新镜像

```bash
# 拉取最新镜像
docker compose pull

# 滚动更新（不停止日志采集）
docker compose up -d --force-recreate loki
docker compose up -d --force-recreate promtail
docker compose up -d --force-recreate grafana
```

---

## 7. 故障排查

### 7.1 常见问题

| 症状 | 可能原因 | 解决方案 |
|------|---------|---------|
| Grafana 无数据 | Loki 未就绪 | `docker compose logs loki` 检查启动日志 |
| Promtail 报错 | 日志文件权限不足 | 确保 `logs/` 目录可读: `chmod -R 755 logs/` |
| 查询超时 | 日志量过大 | 缩小查询时间范围，添加标签过滤 |
| 磁盘空间不足 | 保留期过长 | 减小 `retention_period` 或清理旧数据 |
| 仪表盘未加载 | Provisioning 路径错误 | 检查 Grafana 日志: `docker compose logs grafana` |

### 7.2 诊断命令

```bash
# 查看各服务日志
docker compose logs -f loki
docker compose logs -f promtail
docker compose logs -f grafana

# 检查 Loki 健康状态
curl -s http://localhost:3100/ready
curl -s http://localhost:3100/metrics | head -50

# 检查 Loki 标签
curl -s http://localhost:3100/loki/api/v1/labels

# 检查 Promtail 位置文件
docker exec yuanbot-promtail cat /tmp/positions.yaml

# 测试 LogQL 查询
curl -s 'http://localhost:3100/loki/api/v1/query' \
  --data-urlencode 'query={job="yuanbot"}' \
  --data-urlencode 'limit=10'
```

### 7.3 重置 Promtail 采集进度

如果需要重新采集所有日志（例如修复了 pipeline 配置后）：

```bash
docker compose stop promtail
docker volume rm yuanbot_promtail-positions
docker compose up -d promtail
```

---

## 8. 安全加固

### 8.1 生产环境建议

1. **修改默认密码**：设置强密码的 `GRAFANA_ADMIN_PASSWORD`
2. **限制端口暴露**：Loki 和 Promtail 端口仅内部访问
3. **启用 HTTPS**：在 Nginx 反向代理后配置 TLS
4. **启用认证**：Loki 启用 `auth_enabled: true` + 多租户

### 8.2 Nginx 反向代理示例

```nginx
# Grafana 代理
server {
    listen 443 ssl;
    server_name grafana.yourdomain.com;

    ssl_certificate     /etc/ssl/certs/grafana.crt;
    ssl_certificate_key /etc/ssl/private/grafana.key;

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 9. 性能调优

### 9.1 日志量预估

| 日志级别 | 预估速率 | 日存储量 |
|---------|---------|---------|
| DEBUG | 50-200 lines/s | 5-20 GB |
| INFO | 10-50 lines/s | 1-5 GB |
| WARNING | 1-5 lines/s | 50-500 MB |
| ERROR | 0.1-1 lines/s | 5-50 MB |

### 9.2 资源限制配置

```yaml
# docker-compose.yaml 中添加资源限制
services:
  loki:
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '1.0'
        reservations:
          memory: 256M

  promtail:
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: '0.5'
```

### 9.3 大规模部署建议

- 日志量 > 100GB/天：使用 S3/MinIO 作为存储后端
- 多实例部署：启用 Loki 的 memberlist 做 ring gossip
- 查询性能：为高频查询配置 `query_range.results_cache`
- 采集性能：使用 Docker service discovery 替代 static_configs

---

## 附录：文件清单

```text
yuanbot/
├── configs/
│   └── loki/
│       ├── loki-config.yaml          # Loki 服务端配置
│       └── promtail-config.yaml      # Promtail 采集配置
│   └── grafana/
│       ├── provisioning/
│       │   ├── datasources/
│       │   │   └── datasources.yaml  # 数据源自动配置
│       │   └── dashboards/
│       │       └── dashboards.yaml   # 仪表盘自动加载配置
│       └── dashboards/
│           └── yuanbot-logs.json     # 预置仪表盘定义
├── docker-compose.yaml               # 包含日志聚合栈的完整编排
└── docs/
    └── operations-guide.md           # 本文档
```
