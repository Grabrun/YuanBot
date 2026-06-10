---
title: 架构详解
description: YuanBot 系统架构、核心模块、数据流与配置体系详解
---

# 架构详解

## 系统总览

YuanBot 采用分层架构设计，从下到上分为：

```text
┌─────────────────────────────────────────────────┐
│                   接入层 (Gateway)                │
│  统一网关 │ 认证鉴权 │ 限流 │ 身份映射 │ 事件队列  │
├─────────────────────────────────────────────────┤
│                  适配器层 (Adapters)              │
│     AI 适配器 (OpenAI/Claude/DeepSeek/Ollama)    │
│  通道适配器 (Telegram/Discord/企业微信/WebChat)    │
├─────────────────────────────────────────────────┤
│                 编排层 (Orchestrator)             │
│   意图识别 │ 对话决策 │ 上下文构建 │ 能力编排       │
├─────────────────────────────────────────────────┤
│                  服务层 (Services)                │
│   AI 服务 │ 记忆管理 │ 人格引擎 │ 主动陪伴         │
├─────────────────────────────────────────────────┤
│                基础设施层 (Infrastructure)         │
│   SQLite │ Redis │ Qdrant │ Neo4j │ 事件队列      │
└─────────────────────────────────────────────────┘
```

## 核心模块

### 1. 网关层 (`gateway/`)

**YuanGateway** 是系统的单一入口，职责：

- **入口收敛**: 所有外部消息通过网关进入
- **会话绑定**: 平台用户 → 统一身份 (`IdentityService`)
- **认证鉴权**: 多平台签名验证 (`ChannelAuthenticator`)
- **限流防滥用**: 双层令牌桶 (`RateLimiter`)
- **异步处理**: 事件队列解耦网关与编排层

消息流: `外部平台 → Gateway.receive_message() → 事件队列 → 编排引擎`

### 2. 适配器层 (`adapters/`)

#### AI 适配器 (`adapters/ai/`)

统一接口 `AIProviderAdapter`，支持：
- `chat_completion()`: 同步对话补全
- `stream_chat_completion()`: 流式对话补全
- `get_embedding()`: 文本向量化

已实现：OpenAI、Claude (Anthropic)、DeepSeek、Ollama

#### 通道适配器 (`adapters/channel/`)

统一接口 `ChannelAdapter`，支持：
- `listen()`: 监听消息
- `send_message()`: 发送消息
- `get_platform_user_id()`: 提取用户 ID

已实现：Telegram、Discord、企业微信、WebChat (含 WebSocket)

### 3. 编排层 (`orchestrator/`)

**OrchestratorEngine** 是消息处理核心，流程：

```text
用户消息
  ↓
意图识别 (IntentEngine)
  ↓
上下文构建 (ContextBuilder)
  ↓
对话决策 (DialogueDecisionEngine)
  ↓
能力编排 (CapabilityOrchestrator)
  ↓
AI 服务调用 (AIService)
  ↓
记忆更新 (MemoryManager)
  ↓
情感更新 (EmotionTracker)
  ↓
回复生成
```

### 4. 记忆系统 (`memory/`)

三层记忆架构：

| 层级 | 存储 | 生命周期 | 用途 |
|------|------|----------|------|
| 工作记忆 | 内存 | 单次会话 | 当前对话上下文 |
| 情景记忆 | Qdrant + SQLite | 永久 | 对话事件向量检索 |
| 事实记忆 | SQLite | 永久 | 用户画像、偏好、关系 |

**MemoryManager** 统一管理所有记忆层，支持：
- 自动重要性评分
- 记忆衰减与巩固
- 语义检索（向量相似度）
- 情感趋势追踪

### 5. 人格系统 (`persona/`)

模块化人格引擎：

- **ContextBuilder**: 构建人格上下文注入 prompt
- **EmotionEngine**: 情感识别与追踪
- **IntentEngine**: 用户意图识别
- **DialogueDecisionEngine**: 对话策略决策
- **TokenBudgetManager**: Token 预算管理

人格定义通过 YAML 配置，支持运行时切换。

### 6. 主动陪伴系统 (`proactive/`)

三个子系统协作：

- **ProactiveScheduler**: 定时任务调度（早安、晚安等）
- **ProactiveStrategy**: 基于上下文的主动消息策略
- **EventEngine**: 事件触发引擎（生日、纪念日等）

### 7. 能力系统 (`skills/` + `tools/`)

- **SkillManager**: 管理对话技能（提示词模板）
- **ToolManager**: 管理外部工具（API 调用、计算等）
- **CapabilityOrchestrator**: 编排技能和工具的调用

### 8. AI 提供商管理 (`providers/`)

- **ProviderRegistry**: 提供商注册表
- **ProviderManager**: 提供商生命周期管理
- 支持配置热加载、故障转移

## 数据流

### 入站消息流

```text
外部请求 → Gateway
  → 认证验证
  → 限流检查
  → 身份解析
  → 事件队列
  → OrchestratorEngine.process_message()
    → 记忆检索
    → 上下文构建
    → AI 调用
    → 记忆更新
  → 响应回传
```

### 出站消息流

```text
主动任务触发 → PushDispatcher
  → 目标平台路由
  → 通道适配器.send_message()
  → 外部平台
```

## 配置体系

```text
configs/
├── default.yaml           # 全局默认
├── bot.yaml               # 机器人基础
├── database.yaml          # 数据库配置
├── memory.yaml            # 记忆系统配置
├── extensions.yaml        # 扩展配置
├── serverless.yaml        # Serverless 配置
├── Providers/             # AI 提供商
│   ├── openai.yaml
│   ├── claude.yaml
│   ├── deepseek.yaml
│   └── ollama.yaml
├── Channels/              # 消息通道
│   ├── telegram.yaml
│   ├── discord.yaml
│   ├── wecom.yaml
│   └── webchat.yaml
├── Personas/              # 人设
│   └── default.yaml
└── Plugins/               # 插件
    ├── skills/
    └── tools/
```

支持 ConfigWatcher 热加载，变更即时生效。

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/healthz` | GET | 存活探针 |
| `/readyz` | GET | 就绪探针 |
| `/metrics` | GET | Prometheus 指标 |
| `/api/chat` | POST | 对话接口 |
| `/ws` | WS | WebSocket 聊天 |
| `/api/memory/{user_id}` | GET | 用户记忆 |
| `/api/providers` | GET | AI 提供商状态 |
| `/api/capabilities` | GET | 已加载能力 |
| `/api/proactive/tasks` | GET | 主动任务列表 |
| `/api/proactive/stats` | GET | 主动交互统计 |
| `/api/gdpr/export` | GET | 数据导出 |
| `/api/gdpr/delete` | POST | 数据删除 |
| `/api/extensions` | GET | 扩展列表 |
| `/api/extensions/{id}` | GET | 扩展详情 |
| `/api/extensions/install` | POST | 安装扩展 |
| `/api/extensions/uninstall` | POST | 卸载扩展 |

## 部署架构

### 单机部署

```
[YuanBot 进程] → [SQLite + 内存]
```

### Docker 部署

```yaml
docker-compose.yaml
services:
  yuanbot:
    build: .
    ports: ["8000:8000"]
    depends_on: [redis, qdrant]
  redis:
    image: redis:7
  qdrant:
    image: qdrant/qdrant
```

### Kubernetes 部署

参见 `k8s/deployment.yaml`，支持：
- HPA 自动扩缩容
- Liveness / Readiness 探针
- ConfigMap 配置管理

## 安全设计

- **认证**: 多平台签名验证（HMAC、Ed25519）
- **限流**: 令牌桶算法，双层（全局 + 用户级）
- **隐私**: 隐私模式（会话不入长期记忆）
- **GDPR**: 数据导出 / 删除 API
- **JWT**: 可选的 JWT 认证（`gateway/jwt_auth.py`）
