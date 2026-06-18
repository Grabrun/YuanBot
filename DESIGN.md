# YuanBot 系统设计文档

> **项目**: 缘·Bot (YuanBot) — AI 虚拟伴侣系统
> **版本**: 1.2.2 | **语言**: Python 3.12+ | **框架**: FastAPI + asyncio
> **许可证**: MIT | **代码行数**: ~13,000 行 (src) + ~3,500 行 (tests)

---

## 一、概述

YuanBot 是一个全功能的 AI 虚拟伴侣系统，提供多平台消息通道接入、多 LLM 提供商支持、人格驱动的行为决策、记忆系统、主动陪伴、TTS 语音合成、工具调用等能力。设计上遵循**适配器模式**和**依赖注入**原则，具备良好的可扩展性。

---

## 二、架构总览

```
┌──────────────────────────────────────────────────────────┐
│                      FastAPI 应用层                        │
│                    (app.py + TUI)                          │
├──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┤
│  Web  │微信   │NapCat  │其他通道│ TTS  │ Gate- │ 认证  │ 管理  │
│Adapter│Adapter│Adapter │ Adapter│     │ way   │ Auth │ Admin │
├──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┤
│                    编排引擎 (Orchestrator)                 │
│   ┌──────────┐ ┌──────────┐ ┌──────────────┐            │
│   │对话决策引擎│ │上下文构建器│ │能力编排器     │            │
│   │Dialogue  │ │Context   │ │Capability    │            │
│   │Decision  │ │Builder   │ │Orchestrator  │            │
│   └─────┬────┘ └────┬─────┘ └──────┬───────┘            │
│         │           │              │                     │
│   ┌─────▼───────────▼──────────────▼───────┐             │
│   │            AI 服务 (AIService)          │              │
│   │    ┌──────┐ ┌────────┐ ┌──────────┐    │              │
│   │    │OpenAI│ │Claude  │ │DeepSeek  │ ...│              │
│   │    └──────┘ └────────┘ └──────────┘    │              │
│   └────────────────────────────────────────┘              │
│                                                           │
│  ┌─────────────┐  ┌───────────┐  ┌────────────────────┐ │
│  │ 记忆管理器    │  │ 人设管理器  │  │ 主动陪伴调度器      │ │
│  │ MemoryMgr   │  │PersonaMgr│  │ ProactiveScheduler │ │
│  └──────┬──────┘  └───────────┘  └────────┬───────────┘ │
│         │                                  │             │
│  ┌──────▼──────────────────────────────────▼───────────┐│
│  │            基础设施层                                ││
│  │  SQLite / MySQL / Redis / Qdrant / Neo4j / Milvus   ││
│  └────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────┘
```

---

## 三、核心模块

### 3.1 应用入口 (`app.py`, ~2,500 行)

FastAPI 应用，使用 `asynccontextmanager` 管理生命周期：

1. **初始化阶段** (lifespan startup):
   - 初始化 MemoryManager、ProviderManager、AIService
   - 初始化 SkillManager、ToolManager、CapabilityOrchestrator
   - 初始化 PersonaManager、对话决策引擎、情感引擎
   - 初始化 ProactiveScheduler、EventEngine、TriggerManager
   - 初始化 Gateway (YuanGateway)
   - 初始化 Auth 系统、ConversationStore
   - **启动各消息通道适配器**: Web → 微信 → NapCat（串行，每个 listen 必须非阻塞）
   - 启动主动陪伴系统、事件引擎、配置热加载

2. **运行时** (FastAPI routes):
   - REST API: 认证、会话管理、管理后台
   - WebSocket: 聊天、TTS 流式输出、日志流
   - SPA 静态资源服务

3. **清理阶段** (lifespan shutdown):
   - 关闭 Gateway → 停止各适配器 (wechat/napcat shutdown)
   - 关闭 MemoryManager、ProviderManager
   - 关闭 ProactiveScheduler、EventEngine

### 3.2 核心类型 (`core/types.py`, 371 行)

使用 Pydantic v2 定义所有数据模型：

| 模型 | 用途 |
|------|------|
| `ContentType` | 消息内容类型枚举 (TEXT/IMAGE/VOICE/VIDEO/FILE) |
| `Message` | LLM 对话消息 (role/content/tool_calls) |
| `MessageContent` | 通道适配器消息内容 |
| `UserMessage` | 标准化用户消息（通道适配器输出） |
| `BotResponse` | 标准化机器人响应 |
| `SendResult` | 消息发送结果 |
| `ChannelConfig` | 消息通道配置 |
| `ToolCall` / `ToolDefinition` / `ToolResult` | 工具调用相关 |
| `ProactiveTask` | 主动交互任务 |
| `EmotionState` / `EmotionRecord` / `EmotionTrend` | 情感追踪 |
| `MemoryNode` / `UserProfile` / `MemorySearchResult` | 记忆系统 |
| `ValidationResult` | 配置验证结果 |

### 3.3 核心接口 (`core/interfaces.py`, 296 行)

抽象基类定义系统边界：

- **`AIProviderAdapter`**: LLM 提供商接口（chat_completion, stream_chat_completion, get_embedding）
- **`ChannelAdapter`**: 消息通道接口（initialize, listen, send_message, get_platform_user_id）
- **`SkillModule` / `ToolModule`**: 能力扩展接口
- **`PersonaProfile`**: 人设配置接口

### 3.4 配置系统 (`config.py`, 770 行)

双层配置架构：

```
bot.yaml（主配置）
├── ai: AI 子系统（默认提供商、模型）
├── persona: 人设配置
├── proactive: 主动交互配置
├── memory: 记忆持久化配置
├── tts: 语音合成配置
├── gateway: 网关配置
└── channels: 启用的消息通道列表

configs/Providers/*.yaml（AI 提供商配置）
└── per-provider config (API key, model list, endpoint)

configs/Channels/*.yaml（消息通道配置）
└── per-channel config (token, host, port, etc.)
```

配置加载优先级: **环境变量 > 配置文件 > 默认值**

### 3.5 AI 提供商管理 (`providers/manager.py`, ~200 行)

- `ProviderRegistry`: 注册所有 AI 适配器实现
- `ProviderManager`: 从 `configs/Providers/*.yaml` 加载配置
  - 支持 `${ENV_VAR}` 环境变量占位符替换
  - 支持多模型条目定义
  - 支持自动故障切换（主/备提供商）

已实现的适配器:
| 适配器 | 提供商 |
|--------|--------|
| `openai_adapter.py` | OpenAI / Azure OpenAI |
| `anthropic_adapter.py` | Anthropic Claude |
| `deepseek_adapter.py` | DeepSeek |
| `ollama_adapter.py` | Ollama (本地模型) |

---

## 四、消息处理流水线

当用户消息通过任一通道进入系统，由 `OrchestratorEngine` 处理：

```
UserMessage
    │
    ├── 1. 获取/创建用户画像 (MemoryManager)
    ├── 2. 添加用户消息到工作记忆
    ├── 3. 并行: 记忆检索 + 对话决策
    │       ├── 检索相关记忆 (事实/情景/语义)
    │       └── DialogueDecisionEngine:
    │           ├── IntentEngine → 意图识别
    │           ├── EmotionEngine → 情感分析
    │           ├── TokenBudget → Token 预算管理
    │           └── 决策输出 (策略/情感/技能/工具)
    ├── 4. 能力加载 (CapabilityOrchestrator)
    │       ├── SkillManager → 注入技能提示词
    │       └── ToolManager → 加载工具定义
    ├── 5. 上下文组装 (ContextBuilder)
    │       └── 系统提示词 = 人设 + 记忆 + 情感 + 技能
    ├── 6. LLM 推理 (AIService → ProviderAdapter)
    │       └── 支持工具执行循环 (最多5轮)
    ├── 7. 响应生成 & 记忆更新
    └── 8. BotResponse → 通道适配器 → 用户
```

### DialogueDecisionEngine 内部流程

```
用户输入
    │
    ├── IntentEngine:
    │   ├── 规则匹配 (规则基础)
    │   └── [可选] ONNX 模型分类 (ML 增强)
    │   └── 输出: PrimaryIntent + SecondaryIntents
    │
    ├── EmotionEngine:
    │   ├── 规则 + 关键词情感分析
    │   ├── [可选] 模型增强情感分析
    │   └── 输出: EmotionState (类别/强度/效价)
    │
    ├── TokenBudget:
    │   ├── 评估历史对话 Token 占用
    │   └── 决定是否需要摘要/压缩
    │   └── 输出: BudgetDecision
    │
    └── 综合决策:
        ├── ResponseStrategy (闲聊/关怀/引导/等)
        ├── Skills/Tools 选择
        ├── 情感应对策略
        └── 主动交互触发条件检查
```

---

## 五、消息通道适配器

所有适配器实现 `ChannelAdapter` 接口，统一生命周期：

```python
await adapter.initialize(config)  # 配置读取、HTTP 客户端初始化
await adapter.listen(on_message)  # 启动监听（必须非阻塞，创建 task 返回）
await adapter.shutdown()          # 清理资源
```

### 已实现的适配器

| 适配器 | 文件 | 通讯方式 | 集成状态 |
|--------|------|---------|----------|
| Web | `web_adapter.py` | WebSocket | ✅ 已接入 app.py |
| 微信 iLink | `wechat_adapter.py` | HTTP 长轮询 | ✅ 已接入 app.py |
| NapCat QQ | `napcat_adapter.py` | 反向 WebSocket | ✅ 已接入 app.py |
| QQ 官方 | `qq_adapter.py` | WebSocket | ❌ 未启动 |
| Telegram | `telegram_adapter.py` | HTTP 长轮询 | ❌ 未启动 |
| Discord | `discord_adapter.py` | WebSocket Gateway | ❌ 未启动 |
| 钉钉 | `dingtalk_adapter.py` | HTTP Webhook | ❌ 未启动 |
| 飞书 | `feishu_adapter.py` | HTTP Webhook | ❌ 未启动 |
| 企业微信 | `wecom_adapter.py` | HTTP Webhook | ❌ 未启动 |

### NapCat 适配器细节 (`napcat_adapter.py`, 2,109 行)

**通讯架构**（最新）:
```
NapCat ──反向 WS──→ YuanBot
  (WS 客户端)     (WS 服务端)
  
  - 事件上报: NapCat → YuanBot (同一 WS 连接)
  - API 调用: YuanBot → NapCat (echo 匹配)
  - 降级: HTTP API (WS 不可用时)
```

**关键配置** (`configs/Channels/napcat.yaml`):
```yaml
reverse_ws_host: "0.0.0.0"
reverse_ws_port: 8080
reverse_ws_path: "/onebot/v11/ws"
http_host: "127.0.0.1"
http_port: 3000
```

**WS 服务端处理流程**:
1. `listen()` → `asyncio.start_server()` → 非阻塞返回
2. `_on_ws_connect()` → WS 握手 (HTTP Upgrade → 101)
3. `_ws_read_loop()` → 帧读取 → Ping/Pong → 文本消息 → 事件处理
4. `_ws_call_api()` → 通过 WS 发送 API 请求 (带 echo)
5. `_http_api_call()` → HTTP 降级

---

## 六、记忆系统 (`memory/manager.py`, ~600 行)

四层记忆架构：

| 层级 | 类型 | 存储 | 特点 |
|------|------|------|------|
| 工作记忆 | `MemoryType.WORKING` | Redis / 内存 | 当前会话上下文 |
| 事实记忆 | `MemoryType.FACT` | SQLite | 用户偏好、习惯、重要事实 |
| 情景记忆 | `MemoryType.EPISODIC` | SQLite + 向量库 | 过往对话摘要嵌入 |
| 语义记忆 | `MemoryType.SEMANTIC` | SQLite | 深层认知与关系理解 |

**检索策略**:
- 情景触发检索 (情景相似度)
- 语义向量检索 (Embedding 相似度)
- 重要性评分 + 时序衰减
- 支持异步持久化工作记忆

**情感追踪** (`emotion_tracker.py`):
- 8 类情感分类 (Joy/Sadness/Anger/Fear/Surprise/Disgust/Trust/Anticipation)
- 多维度情感状态 (强度/效价/唤醒度/优势度)
- 情感趋势分析 (日/周/月)
- 模式识别 (时间/场景/话题关联)

---

## 七、主动陪伴系统 (`proactive/`)

| 模块 | 职责 |
|------|------|
| `scheduler.py` | 定时任务调度 (cron/间隔/事件) |
| `strategy.py` | 触发后决策是否行动 (克制策略) |
| `trigger.py` | 事件触发器管理 (定时/情感/系统) |
| `event_engine.py` | 事件引擎 (消息路由) |
| `retry_queue.py` | 消息发送失败重试 |

**克制策略** (`strategy.py`):
- 安静时段限制 (23:00 - 08:00)
- 日最大交互次数限制
- 防重复发送锁
- 情感状态感知 (高负能量时触发关怀)
- 用户级个性化配置

---

## 八、基础设施 (`infrastructure/`)

| 模块 | 功能 |
|------|------|
| `database.py` | 数据库连接管理 (SQLite/MySQL) |
| `sqlite_store.py` | SQLite 存储实现 |
| `mysql_store.py` | MySQL 存储实现 |
| `cache_store.py` | 缓存存储 (Redis/内存) |
| `vector_store.py` | 向量存储 (Qdrant/Milvus Lite) |
| `graph_store.py` | 图数据库 (Neo4j) |
| `event_queue.py` | 事件队列 (内存/Redis) |
| `config_loader.py` | 配置加载器 (YAML) |
| `config_watcher.py` | 配置热加载监听 |
| `migration.py` | 数据库迁移管理 |
| `alerting.py` | 告警系统 |
| `backup.py` | 备份管理 |
| `logging_config.py` | 日志配置 (文件轮转 + 结构化) |

---

## 九、TTS 语音合成 (`tts/`)

| 适配器 | 引擎 |
|--------|------|
| `edge_tts_adapter.py` | Microsoft Edge TTS (免费) |
| `openai_tts_adapter.py` | OpenAI TTS API |
| `azure_tts_adapter.py` | Azure Speech |
| `piper_tts_adapter.py` | Piper (本地离线) |

**特性**:
- 两级缓存 (L1 内存 + L2 文件)
- 流式音频输出 (WebSocket)
- 自动引擎故障切换
- 语音偏好管理

---

## 十、网关系统 (`gateway/`)

| 模块 | 职责 |
|------|------|
| `gateway.py` | 统一入口 (YuanGateway) |
| `adapter_manager.py` | 适配器生命周期管理 |
| `auth.py` | 通道认证 + 速率限制 (令牌桶) |
| `identity_service.py` | 跨平台身份关联 |
| `push_dispatcher.py` | 消息推送分发 |
| `jwt_auth.py` | JWT 认证管理 |
| `privacy.py` | 隐私管理 |

---

## 十一、配置示例

### `configs/Channels/napcat.yaml`
```yaml
platform: napcat
display_name: "NapCat QQ"
enabled: false
config:
  reverse_ws_host: "0.0.0.0"
  reverse_ws_port: 8080
  reverse_ws_path: "/onebot/v11/ws"
  http_host: "127.0.0.1"
  http_port: 3000
  bot_qq: ""
```

### `configs/Providers/deepseek.yaml`
```yaml
provider_id: deepseek
name: "DeepSeek"
adapter: deepseek
enabled: true
config:
  api_key: "${DEEPSEEK_API_KEY}"
  base_url: "https://api.deepseek.com"
  models:
    - id: deepseek-v4-flash
      type: chat
      max_tokens: 128000
  default_model: deepseek-v4-flash
```

---

## 十二、部署与发布

### CI/CD 流水线 (GitHub Actions)

| Workflow | 触发条件 | 阶段 |
|----------|---------|------|
| `ci.yml` | push/PR to master | Lint → Test (3.12+3.13) → Build → Docker → Extension Validate |
| `publish.yml` | push to master (非 docs/.md/.github) | Test → Build → Release → PyPI → Docker → Docs |
| `docs-vitepress-deploy.yml` | push docs-vitepress/** | Build → Deploy to GitHub Pages |
| `pr-review.yml` | PR opened/synchronized | 自动分析 PR 变更 + 评论 |

### 构建工具
- **包管理器**: uv (Python >=3.12)
- **构建系统**: Hatchling
- **格式化**: Ruff (lint + format)
- **测试**: Pytest (1,453 测试用例)
- **发布**: GitHub Release + PyPI (yuanbot-cli)

---

## 十三、依赖关系图

```
app.py
├── core/types.py (Pydantic models)
├── core/interfaces.py (ABCs)
├── config.py (configuration)
│
├── adapters/channel/
│   ├── base.py ← ChannelAdapter(ABC)
│   ├── web_adapter.py → WebSocket
│   ├── wechat_adapter.py → iLink HTTP long-poll
│   └── napcat_adapter.py → NapCat QQ reverse WS
│
├── providers/
│   ├── registry.py ← AIProviderAdapter(ABC)
│   └── manager.py → loads from configs/Providers/*.yaml
│
├── orchestrator/engine.py → 编排流水线
│   ├── services/ai_service.py → LLM 调用门面
│   ├── services/capability_orchestrator.py
│   │   ├── skills/manager.py → configs/Plugins/skills/
│   │   └── tools/manager.py → configs/Plugins/tools/
│   ├── persona/engines/
│   │   ├── dialogue_decision.py → 综合决策
│   │   ├── intent_engine.py → 意图识别
│   │   ├── emotion_engine.py → 情感分析
│   │   ├── context_builder.py → 上下文组装
│   │   └── token_budget.py → Token 预算
│   └── memory/manager.py → 四层记忆
│
├── proactive/ → 主动陪伴
│   ├── scheduler.py
│   ├── strategy.py
│   ├── trigger.py
│   └── event_engine.py
│
├── tts/ → 语音合成
├── gateway/ → 统一网关
├── auth/ → 认证鉴权
└── infrastructure/ → 基础设施
```

---

## 十四、注意事项与已知限制

1. **适配器非阻塞**: 所有 `listen()` 方法必须非阻塞返回（创建 task）。已修正 NapCat，但 Discord/Telegram listen 使用 `while True` 阻塞，目前未接入 app.py 所以无影响。
2. **配置热加载**: 通过 `ConfigWatcher` 监听 `configs/` 目录变化，支持运行时更新通道和 AI 提供商配置。
3. **无持久化队列**: 当前事件队列支持内存/Redis 模式，但无持久化保证。若 Redis 不可用，消息可能丢失。
4. **单实例**: 当前设计为单实例运行，未支持水平扩展。
5. **通道适配器加载**: app.py 中通道适配器串行启动，若某个适配器初始化失败不会影响其他适配器。
6. **测试覆盖**: 1,453 个测试用例覆盖核心模块和所有适配器。
