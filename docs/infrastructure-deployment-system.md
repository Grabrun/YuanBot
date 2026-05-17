🌸 缘·Bot 基础架构与部署系统详细设计文档 (v1.4)

版本历史

版本 日期 修改内容
v1.0 2026-05-17 初始详细设计，基于总体架构 v1.4

---

1. 系统定位与目标

基础架构与部署系统是 缘·Bot 的“骨架与环境”，为上层的记忆、决策、通信等系统提供稳定、安全、可伸缩的运行基础。它涵盖了配置管理、存储选型、部署方案、安全策略、监控运维和系统生命周期，确保项目从个人开发者的树莓派到企业级 Kubernetes 集群都能顺畅运行。

核心目标：

· 配置集中化：所有配置统一在 configs/ 目录下，文件化、可版本控制、可备份。
· 本地优先：默认使用 SQLite + Milvus Lite + Kuzu 等嵌入式数据库，实现零依赖快速启动；同时保留 MySQL、Milvus 集群版等生产级替代方案。
· 部署灵活：提供 Docker Compose（个人/小团队）、Kubernetes（SaaS）、Serverless（低成本）等多种部署模式。
· 安全默认可信：数据全自托管，密钥与业务逻辑分离，支持加密存储与传输。
· 可观测性：提供日志、指标、健康检查接口，方便运维监控。

---

2. 总体架构分层

```
┌──────────────────────────────────────────────────────────┐
│                应用层 (Application Layer)                 │
│  人格决策 · 记忆系统 · 接入网关 · 能力系统 · 主动系统    │
├──────────────────────────────────────────────────────────┤
│                服务层 (Service Layer)                     │
│  FastAPI (REST/WS) · gRPC (内部通信) · 事件总线          │
├──────────────────────────────────────────────────────────┤
│                数据层 (Data Layer)                        │
│  SQLite/MySQL · Milvus Lite · Redis · Kuzu/Neo4j         │
├──────────────────────────────────────────────────────────┤
│              基础设施层 (Infrastructure)                  │
│  Docker · Kubernetes · Systemd · Serverless              │
├──────────────────────────────────────────────────────────┤
│              安全与运维 (Cross-cutting)                   │
│  配置管理 · 密钥保护 · 日志监控 · 备份恢复 · 健康检查    │
└──────────────────────────────────────────────────────────┘
```

· 应用层：业务逻辑，依赖下层提供的抽象接口。
· 服务层：HTTP/WebSocket 由 FastAPI 提供，内部高性能模块（如工具执行沙盒）通过 gRPC 通信，异步消息通过 Redis Streams 或 RabbitMQ 传递。
· 数据层：混合存储，默认使用嵌入式数据库，可通过配置文件切换为生产级数据库。
· 基础设施层：编排容器、管理进程、提供运行环境。

---

3. 技术栈选型

组件 默认选择 生产可选 选型理由
应用语言 Python 3.12+ - 生态丰富，开发效率高，AI/LLM 库支持好
Web 框架 FastAPI - 原生异步、自动 OpenAPI、WebSocket 支持
内部 RPC gRPC (protobuf) - 强类型契约，高性能，支持流式，适合工具沙盒通信
网关 Nginx (反向代理) / Traefik Envoy 处理 TLS 终止、限流、负载均衡
事件队列 Redis Streams RabbitMQ / NATS 轻量，同时可兼做缓存和会话存储
关系数据库 SQLite (WAL 模式) MySQL 8.0+ SQLite 零配置本地优先；MySQL 支持高并发和集群
向量数据库 Milvus Lite Milvus (分布式) 嵌入式向量存储，无额外服务；可无缝迁移至集群版
图数据库 Kuzu (嵌入式) Neo4j 嵌入式图引擎，无需独立进程；Neo4j 用于复杂图分析
缓存 Redis 7+ - 会话状态、工作记忆、主动交互锁、速率限制
对象存储 本地文件系统 MinIO / S3 媒体文件等二进制大对象
容器运行时 Docker + Compose containerd, Kubernetes 标准化封装与隔离
包管理 uv (Python) pip 快速，兼容 pip，借鉴 Hermes Agent 实践

完全本地化能力：SQLite + Milvus Lite + Kuzu + Redis 的组合，用户无需安装任何外部数据库即可运行完整功能。Redis 虽是独立进程，但也可通过 Docker 一键启动。

---

4. 配置管理详细设计

4.1 配置目录结构

所有配置文件集中在项目根目录下的 configs/ 文件夹，遵循类型分目录和文件即配置的原则。

```
configs/
├── bot.yaml                    # 根配置：默认AI提供商、主动系统、扩展管理等
├── database.yaml               # 数据库配置：SQLite/MySQL/Milvus路径/Redis等
├── memory.yaml                 # 记忆系统参数：遗忘曲线、固化周期、检索TopK等
├── orchestrator.yaml           # 决策引擎参数：意图/情感模型、Token预算等
├── persona.yaml                # 默认活跃人格（可被扩展覆盖）
├── extensions.yaml             # 已安装的扩展列表
├── Channels/                   # 消息通道适配器配置
│   ├── telegram.yaml
│   ├── discord.yaml
│   └── webchat.yaml
├── Providers/                  # AI 提供商适配器配置（含模型列表及默认模型）
│   ├── openai.yaml
│   ├── claude.yaml
│   └── deepseek.yaml
├── Plugins/                    # Skills/Tools/触发器 按需注册配置
│   ├── skills/
│   │   ├── emotional_comfort.yaml
│   │   └── bedtime_story.yaml
│   └── tools/
│       ├── get_weather.yaml
│       └── set_reminder.yaml
└── Personas/                   # 自定义人设文件夹
    ├── gentle_companion.yaml
    └── lively_friend.yaml
```

4.2 核心配置文件详解

bot.yaml — 根配置，定义全局行为：

```yaml
yuanbot:
  version: "1.4.0"
  name: "缘·Bot"
  timezone: "Asia/Shanghai"

ai:
  default_provider: openai        # 活跃AI提供商ID
  embedding_provider: openai      # 嵌入提供商，默认同default_provider
  fallback_provider: deepseek     # 主提供商故障时切换（可选）

orchestrator:
  intent:
    local_model_enabled: true
    local_model_name: "yuanbot-intent-v1"
  emotion:
    deep_analysis_threshold: 0.7
  token_budget:
    total_limit: 8000
    memory_ratio: 0.3
    conversation_ratio: 0.5

proactive:
  enabled: true
  scheduler:
    check_interval_seconds: 30
  greeting:
    morning:
      enabled: true
      default_time: "08:00"
    evening:
      enabled: true
      default_time: "22:30"
  event_triggers:
    weather_change: true
    user_silence: true
    silence_timeout_hours: 48
    emotion_alert: true
  rate_limit:
    max_per_user_per_day: 5
  message_generation:
    max_tokens: 150
    temperature: 0.8

extensions:
  marketplace:
    registry_url: "https://yuanbot.app/api/v1/marketplace"
    auto_update_check: false
    allow_prerelease: false

logging:
  level: "INFO"
  format: "json"
  file: "logs/yuanbot.log"
```

database.yaml — 数据库连接与存储路径：

```yaml
databases:
  relational:
    engine: "sqlite"              # 'sqlite' 或 'mysql'
    sqlite:
      path: "data/yuanbot.db"
    mysql:
      host: "localhost"
      port: 3306
      user: "yuanbot"
      password: "${MYSQL_PASSWORD}"  # 支持环境变量引用
      database: "yuanbot"
      pool_size: 10

  vector:
    engine: "milvus_lite"         # 'milvus_lite' 或 'milvus'
    milvus_lite:
      path: "data/milvus_lite.db"
    milvus:
      host: "localhost"
      port: 19530
      collection_prefix: "yuanbot"

  graph:
    engine: "kuzu"                # 'kuzu' 或 'neo4j'
    kuzu:
      path: "data/kuzu"
    neo4j:
      uri: "bolt://localhost:7687"
      user: "neo4j"
      password: "${NEO4J_PASSWORD}"

  cache:
    engine: "redis"
    redis:
      host: "localhost"
      port: 6379
      db: 0
      password: null

  file_store:
    engine: "local"
    local:
      path: "data/files"
```

memory.yaml — 记忆系统参数（详见记忆系统文档）：

```yaml
memory:
  working:
    max_turns: 20
    redis_ttl_after_session: 86400

  fact:
    min_confidence_for_decision: 0.5
    auto_extraction_enabled: true

  episodic:
    embedding_model_provider: "openai"   # 或其它提供商ID
    embedding_model: "text-embedding-3-small"
    vector_dim: 1536
    retrieval_top_k: 5
    merge_similarity_threshold: 0.9

  semantic:
    trust_score_update_interval: 86400

  lifecycle:
    importance:
      weights: [0.3, 0.25, 0.2, 0.15, 0.1]
    forgetting:
      fact_lambda: 0.001
      episodic_lambda_base: 0.01
    consolidation:
      schedule: "0 3 * * *"
      min_occurrences_for_fact: 3
    eviction:
      threshold: 0.1
      schedule: "0 4 * * 0"
```

Providers/openai.yaml（示例）：

```yaml
provider_id: openai
adapter: openai-adapter
enabled: true
config:
  api_key: "${OPENAI_API_KEY}"      # 支持环境变量
  base_url: "https://api.openai.com/v1"
  models:
    - id: gpt-4o
      type: chat
      max_tokens: 128000
    - id: gpt-4o-mini
      type: chat
      max_tokens: 128000
    - id: text-embedding-3-small
      type: embedding
      dimension: 1536
  default: gpt-4o
```

Channels/telegram.yaml（示例）：

```yaml
adapter: telegram-channel-adapter
enabled: true
config:
  bot_token: "${TELEGRAM_BOT_TOKEN}"
  webhook:
    enabled: true
    url: "https://yourdomain.com/gateway/inbound/telegram"
    secret_token: "${TELEGRAM_SECRET}"
```

4.3 配置加载策略

加载顺序（后者覆盖前者）：

1. 代码内默认值（最低优先级）
2. configs/ 目录下 YAML 文件
3. 环境变量（最高优先级，可覆盖任何配置项）

环境变量映射规则：

· 全局根配置：YUAN_BOT__AI__DEFAULT_PROVIDER → bot.yaml 中的 ai.default_provider
· 提供商密钥：YUAN_PROVIDER_OPENAI_API_KEY → 自动注入到 Providers/openai.yaml 的 config.api_key

敏感信息处理：

· YAML 文件中支持 ${ENV_VAR} 占位符，系统在加载时自动替换为环境变量值。
· 若直接硬编码了密钥，系统会在日志中自动脱敏。

热加载：

· Channels/ 和 Providers/ 下的配置变更可被监听，适配器自动重载。
· 记忆和数据库配置需重启生效（防止运行时连接池异常）。

---

5. 部署模式

5.1 Docker Compose（个人/小团队）

适用场景：个人自托管、家庭服务器、VPS 单机部署。

docker-compose.yaml：

```yaml
version: '3.8'
services:
  yuanbot-core:
    image: yuanbot/yuanbot-core:1.4.0
    restart: always
    ports:
      - "8000:8000"
    volumes:
      - ./configs:/app/configs
      - ./data:/app/data
      - ./logs:/app/logs
    environment:
      - YUAN_BOT__TIMEZONE=Asia/Shanghai
    depends_on:
      redis:
        condition: service_healthy

  redis:
    image: redis:7-alpine
    restart: always
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

volumes:
  redis_data:
```

特点：

· SQLite 和 Milvus Lite 内嵌于核心镜像，无需独立容器。
· 持久化数据映射到宿主机目录。
· 可通过 docker-compose up -d 一键启动。

5.2 Kubernetes（SaaS/多用户）

适用场景：面向多用户的云端服务，需要水平扩展和高可用。

核心组件：

· yuanbot-core：Deployment，副本数 3+，HPA 基于 CPU/内存。
· redis：使用 Redis Sentinel 或 Redis Cluster。
· MySQL：使用云数据库或 MySQL Operator。
· Milvus：分布式模式，使用 Milvus Operator。
· Neo4j：可选，使用 Neo4j Aura 或自建集群。
· Ingress：Nginx Ingress Controller 处理 TLS 终止和 WebSocket 路由。

关键配置：

· 数据库连接通过 Kubernetes Secrets 注入。
· 配置文件通过 ConfigMap 挂载。
· 主动定时任务使用 Kubernetes CronJob（替代内部 Cron 引擎，避免多副本重复触发）。

5.3 Serverless（低成本/低频）

适用场景：个人用户、低频使用、希望按需付费。

方案：

· 使用 Google Cloud Run 或 AWS App Runner 部署核心服务，请求到来时唤醒。
· 持久化数据使用 Cloud SQL 或兼容 S3 的存储 + 外部 Redis。
· 主动系统由外部的 cron 触发器（Cloud Scheduler）调用核心服务的特定端点来触发问候逻辑，而不是内部常驻进程。
· 启动时间优化：使用轻量镜像，SQLite + Milvus Lite 数据存储在对象存储中，实例启动时拉取到临时存储。

优点：无请求时缩容至零，成本极低。

---

6. 系统启动流程

1. 加载全局配置：读取 configs/bot.yaml，初始化日志系统。
2. 初始化数据层：根据 database.yaml 建立数据库连接池、缓存连接、向量数据库连接。
3. 注册适配器：
   · 扫描 configs/Providers/，加载已启用的 AI 适配器，实例化活跃提供商的客户端。
   · 扫描 configs/Channels/，加载消息通道适配器，注册 Webhook 或建立长连接。
4. 加载扩展：根据 configs/extensions.yaml 导入已安装的 Skills、Tools、触发器。
5. 启动能力索引：构建 Skills/Tools 元数据索引。
6. 启动调度器：
   · 激活主动陪伴系统内部的 Cron 引擎（或注册 Kubernetes CronJob）。
   · 启动事件监听器。
7. 启动 FastAPI 应用：监听 HTTP/WebSocket，注册 /gateway/* 路由和健康检查。
8. 就绪检查：/healthz 返回所有组件的健康状态，网关启动。

---

7. 安全与隐私设计

7.1 数据自托管

· 所有数据（对话、记忆、向量、文件）存储在用户指定的 data/ 目录或自建数据库中。
· 系统不向任何第三方服务器发送用户数据（除非用户主动配置的 AI 提供商 API 调用，但提供商密钥由用户完全控制）。

7.2 凭证安全

· API 密钥、数据库密码等敏感信息绝不硬编码，通过环境变量或 ${ENV} 占位符注入。
· 运行时密钥对象在内存中仅于必要作用域存在，适配器销毁时主动清除。
· 日志系统自动过滤 api_key、password 等字段，脱敏显示为 ***。

7.3 通信加密

· 外部 Webhook 端点强制使用 HTTPS（TLS 1.2+）。
· WebSocket 连接使用 wss://。
· 内部微服务间通信可启用 mTLS。

7.4 隐私模式与会话控制

· 用户可通过对话指令开启“隐私会话”，该模式下对话不进入长期记忆，仅在工作记忆中短暂存在。
· 支持“忘记我”、“删除我的所有数据”等指令，系统执行硬删除。
· 提供 GDPR/个人信息保护法合规的数据导出与删除 API。

---

8. 监控与可观测性

8.1 健康检查

· /healthz：返回 200 当核心进程正常。
· /readyz：检查数据库、缓存、至少一个 AI 提供商可用。
· 网关健康检查面板可展示各通道适配器连接状态。

8.2 日志

· 结构化的 JSON 日志，输出到 stdout 和文件。
· 日志级别：DEBUG, INFO, WARNING, ERROR。
· 可通过环境变量动态调整日志级别。

8.3 指标

· 使用 prometheus-client 暴露 /metrics 端点。
· 关键指标：
  · 请求量、延迟、错误率（HTTP/gRPC）。
  · 消息处理吞吐量。
  · AI 提供商调用次数、Token 消耗。
  · 主动消息发送数。
  · 数据库连接池状态、缓存命中率。

8.4 告警

· 当连续多次 AI 提供商调用失败、磁盘空间不足、数据库连接丢失时，通过日志和 webhook 发出告警。

---

9. 备份与恢复

9.1 备份策略

数据 备份方式 频率
SQLite 数据库 文件拷贝（cp data/yuanbot.db data/backups/） 每日凌晨
Milvus Lite 数据 复制整个 data/milvus_lite.db 文件 每日凌晨
配置文件 Git 版本控制 实时
用户文件 同步到远程对象存储 每日

9.2 恢复流程

1. 停止核心服务。
2. 将备份的数据库文件覆盖到 data/ 目录。
3. 重启服务，系统自动执行完整性检查。

9.3 迁移工具

· 提供 yuanbot-cli migrate 命令，支持从 SQLite 迁移到 MySQL、从本地文件迁移到 S3。

---

10. 运维工具

· yuanbot-cli：除扩展管理外，还支持：
  · yuanbot-cli doctor：检查所有组件连通性。
  · yuanbot-cli backup：执行一次性备份。
  · yuanbot-cli restore <path>：从备份恢复。
  · yuanbot-cli shell：进入交互式 Python REPL，加载核心组件。

---

本详细设计为缘·Bot 提供了从硬件到运维的完整基础设施蓝图，确保其不仅能在开发者的笔记本上完美运行，也能稳健地支撑起成千上万用户的长期陪伴服务。