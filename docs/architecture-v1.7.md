# 🌸 YuanBot 架构设计文档 v1.7

> 基于项目代码 v1.2.1 生成 | 2026-06-15

---

## 目录

1. [概述](#1-概述)
2. [总体架构](#2-总体架构)
3. [核心数据类型与接口](#3-核心数据类型与接口)
4. [配置系统](#4-配置系统)
5. [AI 提供商系统](#5-ai-提供商系统)
6. [消息通道适配器系统](#6-消息通道适配器系统)
7. [统一网关](#7-统一网关)
8. [编排引擎](#8-编排引擎)
9. [决策系统](#9-决策系统)
10. [记忆系统](#10-记忆系统)
11. [情感追踪系统](#11-情感追踪系统)
12. [主动陪伴系统](#12-主动陪伴系统)
13. [能力与工具系统](#13-能力与工具系统)
14. [AI 服务门面](#14-ai-服务门面)
15. [人格系统](#15-人格系统)
16. [TTS 语音合成系统](#16-tts-语音合成系统)
17. [认证与会话系统](#17-认证与会话系统)
18. [基础设施](#18-基础设施)
19. [用户界面](#19-用户界面)
20. [CLI 命令行工具](#20-cli-命令行工具)
21. [测试体系](#21-测试体系)
22. [部署与运维](#22-部署与运维)
23. [数据流全景](#23-数据流全景)

---

## 1. 概述

### 1.1 项目定位

**YuanBot（缘·Bot）** 是一个开源、可自托管的 AI 虚拟伴侣系统，提供类似 Replika/Character.AI 的个性化 AI 陪伴体验。核心设计理念是 **零供应商锁定、可私有化部署、架构可扩展**。

### 1.2 技术栈

| 层 | 技术选择 |
|------|----------|
| 运行时 | Python 3.12+ |
| Web 框架 | FastAPI + Starlette |
| AI 提供商 | OpenAI / Anthropic / DeepSeek / Ollama（统一接口） |
| 消息通道 | Telegram / 微信 / Discord / 钉钉 / 飞书 / QQ / 企微 / WebSocket |
| 前端 | Vue 3 + TypeScript + Vite + Naive UI |
| 终端 UI | Textual |
| 数据库 | SQLite (默认) / MySQL / PostgreSQL / Milvus Lite |
| 缓存 | Redis（可选）|
| 图数据库 | Kuzu（可选）|
| 文档 | VitePress（多语言：中/英/日）|
| 测试 | pytest + pytest-asyncio, 1453 测试用例 |
| Lint | Ruff (100% clean) |
| 容器化 | Docker + Kubernetes |
| 监控 | Prometheus + Grafana |

### 1.3 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0 | 2026-05 | M1 核心框架（编排层、记忆系统、统一接口）|
| v1.1 | 2026-05 | M2 基础适配器层（OpenAI/Claude + Telegram/Web）|
| v1.2 | 2026-05 | M3 记忆与情感系统完善、文档规范化 |
| v1.2.1 | 2026-06 | 性能优化、V6/V7 符合度检查（100%）|

---

## 2. 总体架构

### 2.1 分层架构图

```
┌─────────────────────────────────────────────────────────────┐
│                     用户界面层                               │
│   WebUI (Vue3)    TUI (Textual)    CLI     WebSocket API    │
├─────────────────────────────────────────────────────────────┤
│                       网关层                                 │
│    YuanGateway：消息路由 · 会话绑定 · 认证鉴权 · 限流防滥用  │
├─────────────────────────────────────────────────────────────┤
│                     编排引擎（大脑）                          │
│  OrchestratorEngine：意图/情感 → 记忆检索 → 决策 → LLM → 响应 │
├──────────┬──────────┬──────────┬──────────┬──────────────────┤
│ AI提供商  │ 通道适配器│ 能力系统  │ 人格系统  │    记忆系统      │
│ 系统      │ 系统      │ Skills  │ Persona  │ 四层记忆+情感    │
│ OpenAI   │ Telegram │ Tools   │ 决策引擎 │ 追踪+遗忘曲线    │
│ Claude   │ 微信     │ 沙盒    │ 意图识别 │ 向量检索         │
│ DeepSeek │ Discord  │ 扩展    │ 情感分析 │ 用户画像         │
│ Ollama   │ 钉钉等   │         │ Token预算│                  │
├──────────┴──────────┴──────────┴──────────┴──────────────────┤
│                       基础设施层                              │
│    SQLite/MySQL · Redis · Kuzu · 日志 · 告警 · 备份 · 迁移   │
├─────────────────────────────────────────────────────────────┤
│                  主动陪伴系统（后台守护）                      │
│    EventEngine · Scheduler · Strategy · RetryQueue · Trigger │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 模块依赖关系

```
app.py (FastAPI 应用入口)
  ├─ config.py (配置加载)
  ├─ providers/manager.py (AI 提供商管理)
  ├─ adapters/ai/ (AI 适配器)
  ├─ adapters/channel/ (通道适配器)
  ├─ gateway/ (网关集成)
  ├─ orchestrator/engine.py (编排引擎)
  ├─ memory/manager.py (记忆管理)
  ├─ memory/emotion_tracker.py (情感追踪)
  ├─ persona/ (人设与决策)
  ├─ proactive/ (主动陪伴)
  ├─ services/ (AI服务、能力编排)
  ├─ skills/ (Skill 管理)
  ├─ tools/ (工具与沙盒)
  ├─ tts/ (语音合成)
  ├─ auth/ (认证)
  ├─ infrastructure/ (基础设施)
  └─ cli.py (CLI 入口)
```

### 2.3 源码统计

| 模块 | 文件数 | 说明 |
|------|--------|------|
| 核心类型/接口 | 2 | types.py, interfaces.py |
| 配置系统 | 1 | config.py (770行) |
| AI 提供商管理 | 3 | manager.py, registry.py, __init__.py |
| AI 适配器 | 6 | openai, anthropic, deepseek, ollama, base, __init__ |
| 通道适配器 | 11 | telegram, wechat, discord, dingtalk, feishu, qq, wecom, web, base 等 |
| 网关 | 6 | gateway, auth, adapter_manager, identity_service, push_dispatcher, jwt_auth, privacy |
| 编排引擎 | 1 | engine.py |
| 记忆系统 | 2 | manager.py, emotion_tracker.py |
| 决策系统 | 7 | dialogue_decision, intent_engine, emotion_engine, context_builder, decision_plugin, token_budget |
| 人设管理 | 3 | manager.py, default.py, __init__.py |
| 主动陪伴 | 5 | strategy, scheduler, event_engine, trigger, retry_queue |
| TTS | 6 | base, manager, edge-tts, openai-tts, azure-tts, piper-tts |
| 工具系统 | 5 | manager, sandbox, grpc_sandbox, builtin, proto |
| Skills | 1 | manager.py |
| 服务层 | 7 | ai_service, capability_orchestrator, marketplace, skill_chain, domain_matcher 等 |
| 认证系统 | 6 | models, store, routes, middleware, admin_routes, conversation_routes |
| 基础设施 | 12 | logging, database, cache, config_watcher, graph_store, migration, sqlite_store 等 |
| 主应用 | 1 | app.py (2438行) |
| CLI | 1 | cli.py (2517行) |
| TUI | 3 | app.py, client.py, __main__.py |
| 测试 | ~60+ | 1453 测试用例 |
| **总计** | **~107 源文件** | **~40+ 配置文件** |

---

## 3. 核心数据类型与接口

### 3.1 数据模型 (`core/types.py`)

| 类型 | 说明 |
|------|------|
| `Message` | LLM 对话消息（role/content/tool_calls） |
| `ToolCall` / `FunctionCall` | 工具调用请求结构 |
| `ChatResponse` / `ChatChunk` | LLM 响应/流式块 |
| `TokenUsage` | Token 用量统计 |
| `ToolDefinition` | 工具定义（JSON Schema） |
| `ToolResult` | 工具执行结果 |
| `UserMessage` / `BotResponse` | 标准化通道消息 |
| `ContentType` | 消息内容类型枚举 |
| `MemoryType` | 记忆类型枚举（working/fact/episodic/semantic） |
| `MemoryNode` | 记忆节点（含向量嵌入、情感标签、重要性评分） |
| `UserProfile` | 用户画像（偏好、关系阶段、信任分、情感模式） |
| `EmotionState` / `EmotionRecord` / `EmotionTrend` | 情感追踪数据结构 |
| `SendResult` / `ValidationResult` | 通用结果类型 |

### 3.2 抽象接口 (`core/interfaces.py`)

| 接口 | 说明 |
|------|------|
| `AIProviderAdapter` | AI 提供商适配器（chat/stream/embedding） |
| `ChannelAdapter` | 消息通道适配器（listen/send/initialize） |
| `SkillModule` / `SkillMetadata` | 技能模块接口 |
| `ToolModule` | 工具模块接口（get_schema/invoke） |
| `PersonaProfile` | 人设配置接口（system_prompt/behavior/capability） |

---

## 4. 配置系统

### 4.1 双层配置架构

YuanBot 采用 **双层配置架构**，保持向后兼容：

#### 新架构：`configs/` 目录结构（推荐）

```
configs/
├── bot.yaml                 # 根配置（AI、Persona、Proactive 等）
├── database.yaml            # 数据库配置（SQLite/MySQL/Redis/Kuzu）
├── memory.yaml              # 记忆系统配置
├── Providers/
│   ├── openai.yaml          # OpenAI 提供商配置
│   ├── anthropic.yaml        # Anthropic 提供商配置
│   └── deepseek.yaml         # DeepSeek 提供商配置
├── Channels/
│   ├── telegram.yaml         # Telegram 通道配置
│   ├── wechat.yaml           # 微信通道配置
│   └── discord.yaml          # Discord 通道配置
├── Personas/                # 人设文件目录
├── Plugins/
│   ├── decision/             # 决策插件
│   ├── skills/               # Skills
│   └── tools/                # 工具配置
└── grafana/                 # Grafana 仪表盘配置
```

#### 旧架构：`YuanBotConfig`（向后兼容）

通过 `ConfigLoader` 自动适配两种模式，对外保持同一 `load_config()` 接口。

### 4.2 环境变量覆盖

支持通过 `YUAN_BOT__` 前缀的双下划线分隔环境变量覆盖配置：
```
YUAN_BOT__AI__DEFAULT_PROVIDER=anthropic
YUAN_BOT__DEBUG=true
```

### 4.3 配置热加载

`ConfigWatcher` 监控 `configs/` 目录变化：
- `Providers/*.yaml` → 热重载 AI 提供商配置
- `Channels/*.yaml` → 热重载通道配置
- 通过 `watchdog` 库实现文件系统事件监听

---

## 5. AI 提供商系统

### 5.1 架构

```
ProviderRegistry (全局注册表)
     ↓ 注册适配器类
ProviderManager (提供商管理器)
     ├─ load_providers()     # 从 configs/Providers/*.yaml 加载
     ├─ set_default_provider()
     ├─ resolve_model()      # 解析 model_ref 为具体提供商+模型
     └─ reload_provider()    # 热重载
        ↓ 实例化
  ┌────┴────┐  ┌────┴────┐  ┌────┴────┐
  │OpenAI   │  │Anthropic│  │Ollama   │
  │Adapter  │  │Adapter  │  │Adapter  │
  └─────────┘  └─────────┘  └─────────┘
```

### 5.2 适配器实现

| 适配器 | 文件 | 特点 |
|--------|------|------|
| `OpenAIAdapter` | `openai_adapter.py` | 兼容任意 OpenAI API 格式提供商（含 DeepSeek/GLM/Qwen 等） |
| `AnthropicAdapter` | `anthropic_adapter.py` | Claude 模型专用适配器 |
| `DeepSeekAdapter` | `deepseek_adapter.py` | **已废弃**，内部委托给 OpenAIAdapter |
| `OllamaAdapter` | `ollama_adapter.py` | 本地 Ollama 部署支持 |
| `BaseAIProvider` | `base.py` | 公共基类（配置加载、日志脱敏、环境变量替换）|

### 5.3 v2.0 Provider 配置格式

```yaml
# configs/Providers/openai.yaml
provider_id: openai
name: "OpenAI"
adapter: "openai-adapter"
enabled: true
config:
  api_key: "${OPENAI_API_KEY}"
  base_url: "https://api.openai.com/v1"
  models:
    - id: "gpt-4o"
      type: chat
      max_tokens: 128000
    - id: "text-embedding-3-small"
      type: embedding
      dimension: 512
```

### 5.4 日志脱敏

所有 AI 提供商自动脱敏敏感字段（api_key、token、password），用 `****` 替换。

---

## 6. 消息通道适配器系统

### 6.1 架构

```
ChannelAdapter (抽象接口)
  ├─ initialize(config)       # 初始化连接
  ├─ listen(callback)         # 启动监听，回调处理
  ├─ send_message(target, content) # 发送消息
  └─ get_platform_user_id(event) # 提取用户 ID
```

### 6.2 已实现的适配器

| 适配器 | 文件 | 协议 | 说明 |
|--------|------|------|------|
| `TelegramAdapter` | `telegram_adapter.py` | HTTP Polling | Telegram Bot API |
| `WeixinAdapter` | `wechat_adapter.py` | HTTP Server | 微信公众平台（支持 CDN） |
| `DiscordAdapter` | `discord_adapter.py` | WebSocket | Discord Bot |
| `DingTalkAdapter` | `dingtalk_adapter.py` | HTTP Server | 钉钉机器人 |
| `FeishuAdapter` | `feishu_adapter.py` | HTTP Server | 飞书机器人 |
| `QQAdapter` | `qq_adapter.py` | WebSocket | QQ 机器人 |
| `WeComAdapter` | `wecom_adapter.py` | HTTP Server | 企业微信 |
| `WebAdapter` | `web_adapter.py` | WebSocket | WebUI 内部通道 |

### 6.3 消息标准化

所有通道的输入统一转换为 `UserMessage`，输出统一使用 `BotResponse`：
```
UserMessage { platform, platform_user_id, yuanbot_user_id, session_id, content_type, text, media_url }
BotResponse  { content, suggested_tools, proactive_followups }
```

---

## 7. 统一网关

### 7.1 YuanGateway 职责

| 功能 | 实现 | 说明 |
|------|------|------|
| 入口收敛 | `YuanGateway` | 所有外部消息通过网关进入 |
| 会话绑定 | `IdentityService` | 平台用户 → 统一身份映射 |
| 通道管理 | `AdapterManager` | 多通道适配器生命周期管理 |
| 认证鉴权 | `ChannelAuthenticator` | 各平台请求合法性验证 |
| 限流防滥用 | `RateLimiter` | 双层令牌桶限流 |
| 异步处理 | `EventQueue` | 事件队列解耦（支持 Redis/Memory） |
| 健康检查 | `gateway.health()` | 各通道适配器连通性状态 |
| 推送调度 | `PushDispatcher` | 主动消息推送 |

### 7.2 隐私管理

`PrivacyManager` 提供隐私保护功能：
- 敏感信息自动检测与脱敏
- 数据保留策略管理（GDPR 合规）
- 用户数据导出/删除 API

---

## 8. 编排引擎

### 8.1 完整处理流水线

```
UserMessage
  │
  ▼
┌─ 1. 意图识别 ──────────────────────────────────────┐
│   IntentEngine: 规则匹配 + 可选 ML 模型分类器        │
│   输出: IntentResult { intent, confidence, entities }  │
└──────────────────────────────────────────────────────┘
  │
  ▼
┌─ 2. 情感分析 ──────────────────────────────────────┐
│   EmotionEngine: 规则词典 + 强度修饰 + 否定词检测    │
│   输出: EmotionState { emotion, intensity, valence }  │
└──────────────────────────────────────────────────────┘
  │
  ▼
┌─ 3. 决策 ──────────────────────────────────────────┐
│   DialogueDecisionEngine: 综合意图+情感+人设做出决策 │
│   输出: DecisionResult { strategy, should_use_skills } │
└──────────────────────────────────────────────────────┘
  │
  ▼
┌─ 4. 记忆检索 ──────────────────────────────────────┐
│   四层记忆并行检索 + 情感优先排序                     │
│   输出: 相关记忆列表 + 用户画像                        │
└──────────────────────────────────────────────────────┘
  │
  ▼
┌─ 5. 能力加载 ───────────────────────────────────────┐
│   CapabilityOrchestrator: 加载 Skills/Tools          │
│   输出: skill_prompts + tool_definitions              │
└──────────────────────────────────────────────────────┘
  │
  ▼
┌─ 6. 上下文组装 ─────────────────────────────────────┐
│   ContextBuilder: 人设提示 + 记忆 + 能力 → LLM messages│
└──────────────────────────────────────────────────────┘
  │
  ▼
┌─ 7. LLM 推理 + 工具循环 ────────────────────────────┐
│   AIService.chat_completion()                         │
│   → tool_calls? CapabilityOrchestrator.execute_tools()│
│   → 结果回填 → 重新推理 (最多5轮)                     │
└──────────────────────────────────────────────────────┘
  │
  ▼
┌─ 8. 响应生成 ───────────────────────────────────────┐
│   组装 BotResponse                                   │
└──────────────────────────────────────────────────────┘
  │
  ▼
┌─ 9. 记忆更新 ───────────────────────────────────────┐
│   更新工作记忆 + 提取事实 + 归档情景 + 更新情感       │
└──────────────────────────────────────────────────────┘
  │
  ▼
┌─ 10. 主动交互触发 ──────────────────────────────────┐
│   根据对话内容触发 EventEngine 事件                    │
└──────────────────────────────────────────────────────┘
  │
  ▼
BotResponse
```

---

## 9. 决策系统

### 9.1 意图识别 (`persona/engines/intent_engine.py`)

| 组件 | 说明 |
|------|------|
| `IntentEngine` | 规则引擎核心，关键词匹配 + 正则 |
| `MLIntentClassifier` | ONNX 模型推理（可选） |
| `SklearnIntentClassifier` | scikit-learn 模型（可选） |
| `create_intent_classifier()` | 工厂函数，自动选择可用引擎 |

支持的意图类型：greeting, farewell, emotion_expression, question, request, complaint, small_talk, chitchat, compliment, self_introduction, gratitude, agreement, disagreement, reflection, suggestion, flirt, tease, challenge, reminiscence, planning, special_date, instruction, empty, emergency, privacy, roleplay_narrative, roleplay_dialogue, roleplay_action, repost, system。

### 9.2 情感分析 (`persona/engines/emotion_engine.py`)

基于规则的中文情感分析引擎：

| 功能 | 实现方式 |
|------|----------|
| 八类情感词典 | joy, sadness, anger, fear, surprise, disgust, trust, anticipation |
| 否定词检测 | 不/没/没有/别/不要 等 |
| 强度修饰 | 非常/特别/很/有点 等 |
| 复合情感 | 多维度独立评分 |
| 情感衰减 | 随时间衰减的遗忘曲线 |

### 9.3 对话决策 (`persona/engines/dialogue_decision.py`)

`DialogueDecisionEngine` 综合以下因子做出决策：

```
DecisionResult {
  response_strategy: "comfort" | "celebrate" | "calm" | "engage" | "neutral"
  intent: IntentResult
  should_use_skills: list[str]
  should_use_tools: list[str]
  context_priority: "high" | "normal" | "low"
  token_budget_ratio: float (0.0 ~ 1.0)
}
```

### 9.4 上下文构建 (`persona/engines/context_builder.py`)

`ContextBuilder` 组装 LLM 输入消息数组：
```
[System Prompt] + [Persona Rules] + [Memory Context] + [Conversation History] + [Current Query]
```

### 9.5 Token 预算管理 (`persona/engines/token_budget.py`)

动态计算可用 Token 预算在各组件间分配。

### 9.6 决策插件 (`persona/engines/decision_plugin.py`)

可插拔的决策插件系统，通过 `configs/Plugins/decision/` 加载自定义决策逻辑。

---

## 10. 记忆系统

### 10.1 四层记忆模型

```
┌─────────────────────────────────────────────────────────┐
│                    工作记忆 (Working)                     │
│  当前会话上下文 · 最后 N 轮对话 · TTL 过期自动归档        │
│  存储: 内存/Redis                                       │
├─────────────────────────────────────────────────────────┤
│                    事实记忆 (Fact)                        │
│  用户偏好 · 习惯 · 重要事实 · 结构化存储                  │
│  特点: 置信度机制 · 相似事实去重                          │
│  存储: SQLite                                            │
├─────────────────────────────────────────────────────────┤
│                    情景记忆 (Episodic)                    │
│  过往对话摘要 · 情感感知检索                              │
│  特点: 向量嵌入 · 情感标签 · 自动归档                      │
│  存储: SQLite + 向量存储                                  │
├─────────────────────────────────────────────────────────┤
│                    语义记忆 (Semantic)                    │
│  知识图谱 · 用户画像深度集成                              │
│  特点: 关系推理 · 用户行为模式                            │
│  存储: Kuzu/Neo4j                                        │
└─────────────────────────────────────────────────────────┘
```

### 10.2 记忆管理器 (`memory/manager.py`)

`MemoryManager` 提供统一 API：

| 方法 | 说明 |
|------|------|
| `get_or_create_user_profile(user_id)` | 获取/创建用户画像 |
| `add_working_memory(user_id, session_id, message)` | 更新工作记忆 |
| `save_fact_memory(user_id, key, value, confidence)` | 保存事实记忆 |
| `save_episodic_memory(user_id, summary, emotional_tone)` | 保存情景记忆 |
| `search_memories(user_id, query, limit)` | 语义检索记忆 |
| `get_emotion_trend(user_id, period)` | 获取情感趋势 |
| `get_consolidation_candidates()` | 获取需固化的记忆 |
| `consolidate()` | 执行记忆固化 |

### 10.3 记忆生命周期

```
创建 → 工作记忆 (hot) → 重要性评估 → 归档到情景/事实 (warm)
→ 遗忘曲线衰减 → 可能被固化到语义 (cold) → GC 清理
```

- **遗忘曲线**: 14 天半衰期，最低保留分数 0.1
- **记忆固化**: 每天 3:00 AM 自动执行，访问≥3次的记忆提升重要性
- **向量检索**: Milvus Lite / Qdrant，用于语义相似度匹配

---

## 11. 情感追踪系统

### 11.1 EmotionTracker (`memory/emotion_tracker.py`)

| 功能 | 说明 |
|------|------|
| 情感分析 | 基于规则的中文八类情感词典 |
| 否定词检测 | 识别否定结构反转情感极性 |
| 强度修饰 | 程度副词调节情感强度 |
| 情感记录 | 每次分析结果持久化到 SQLite |
| 趋势分析 | 日/周/月维度的情感分布统计 |
| 模式识别 | 时间/场景/主题相关性分析 |
| 安慰机制 | 高风险情感自动推荐安慰策略 |

### 11.2 数据流

```
用户消息 → EmotionTracker.analyze(text)
  → EmotionRecord { emotion, intensity, confidence }
  → 更新 EmotionTrend { dominant_emotion, valence_ratio, mood_stability }
  → 检测 EmotionPattern { temporal/situational/topic_based }
  → 主动陪伴系统触发 EMOTION_RISK 事件（若 negative_ratio ≥ 0.6）
```

---

## 12. 主动陪伴系统

### 12.1 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    EventEngine                           │
│  事件监听: idle_too_long, emotion_alert, special_date  │
│  评估: 该不该触发主动交互                                 │
└──────────────────┬──────────────────────────────────────┘
                   │ 触发事件
                   ▼
┌─────────────────────────────────────────────────────────┐
│                   ProactiveStrategy                      │
│  决策: 是否发送 · 什么时候发 · 发什么                      │
│  策略: 克制策略 · 用户画像适配 · 免打扰时段                 │
└──────────────────┬──────────────────────────────────────┘
                   │ 决定发送
                   ▼
┌─────────────────────────────────────────────────────────┐
│                   ProactiveScheduler                     │
│  调度: 定时任务 · 延迟发送 · Cron 表达式 · 重试管理         │
└──────────────────┬──────────────────────────────────────┘
                   │ 提交发送
                   ▼
┌─────────────────────────────────────────────────────────┐
│                   PushDispatcher                         │
│  推送: 调用对应通道适配器发送 · 回调管理                    │
└─────────────────────────────────────────────────────────┘
```

### 12.2 策略控制

`ProactiveStrategy` 实现多重约束：

| 约束 | 说明 |
|------|------|
| 安静时段 | 默认 23:00-07:00 免打扰 |
| 每日上限 | 默认每天最多 5 次 |
| 频率控制 | high/medium/low/event_only |
| 冷却期 | 同一用户分钟内不重复发送 |
| 用户画像 | 根据用户偏好调整频率和内容 |
| 兜底消息 | AI 不可用时使用模板回复 |

### 12.3 任务类型

| 类型 | 说明 |
|------|------|
| `greeting` | 问候（早/午/晚） |
| `care` | 久未联系时的关心 |
| `reminder` | 用户设定的提醒 |
| `special_date` | 节日/生日祝福 |
| `emotion_alert` | 检测到负面情绪后安慰 |
| `weather` | 天气关怀 |
| `fun` | 趣味互动 |

### 12.4 重试队列 (`proactive/retry_queue.py`)

SQLite 持久化的任务重试队列：
- 指数退避重试
- 最大重试次数限制
- 任务状态追踪

---

## 13. 能力与工具系统

### 13.1 Skills vs Tools

| 维度 | Skills | Tools |
|------|--------|-------|
| 本质 | 软能力（工作流程/知识） | 硬能力（外部接口）|
| 使用方式 | 注入为系统提示词 | LLM tool_calls 调用 |
| 执行 | execute(context, params) | invoke(params, context) |
| 权限 | 无 | safe/restricted/dangerous |
| 接口 | SkillModule/SkillMetadata | ToolModule/ToolDefinition |

### 13.2 CapabilityOrchestrator

```
技能加载：根据决策结果 → 匹配 Skill → 获取 prompt → 注入上下文
工具循环：LLM 推理 → tool_calls → 安全策略检查 → 执行 → 结果回填 → 再推理
权限管控：JWT scope 校验 + permission_level 检查
```

### 13.3 工具沙盒

| 沙盒类型 | 文件 | 说明 |
|----------|------|------|
| `WasmSandboxExecutor` | `sandbox.py` | WebAssembly 轻量沙盒 |
| `GrpcSandboxExecutor` | `grpc_sandbox.py` | gRPC 远程沙盒 |
| `BuiltinToolExecutor` | `builtin.py` | 内置工具（无需沙盒）|

WASM 沙盒特性：LRU 编译缓存、fuel 时间限制、内存限制、WASI 文件系统隔离。

### 13.4 Skills 管理 (`skills/manager.py`)

`SkillManager` 从 `configs/Plugins/skills/` 加载技能模块。

---

## 14. AI 服务门面

### 14.1 AIService

`AIService` 是对编排层暴露的统一 AI 接口：

| 方法 | 说明 |
|------|------|
| `chat(messages, tools, **kwargs)` | 对话（带熔断+重试） |
| `stream_chat(messages, tools, **kwargs)` | 流式对话 |
| `get_embedding(text)` | 嵌入向量 |
| `resolve_model(model_ref)` | 委托 ProviderManager |

### 14.2 熔断器

内置熔断机制防止连锁故障：
```
连续 5 次失败 → 熔断器打开（30 秒冷却）→ 成功后重置
```

### 14.3 重试逻辑

| 条件 | 重试策略 |
|------|----------|
| 429 Rate Limit | 最多重试 3 次 |
| 5xx Server Error | 最多重试 3 次 |
| Network Timeout | 最多重试 3 次 |
| 4xx Client Error | 不重试 |

---

## 15. 人格系统

### 15.1 架构

```
PersonaProfile (抽象接口)
  ├─ persona_id / name
  ├─ get_system_prompt()         # 系统提示词
  ├─ get_behavior_rules()        # 行为规则
  ├─ get_voice_style()           # 语言风格
  ├─ get_capability_domains()    # 能力域声明
  └─ should_use_skill()          # Skill 使用决策

PersonaManager
  ├─ 从 configs/Personas/ 加载人设
  ├─ 多 People 管理
  └─ 动态切换人设
```

### 15.2 默认人设

`DefaultPersona` 提供基础 AI 伴侣角色设定，支持关系阶段演进：
`initial → familiar → intimate → deep`

---

## 16. TTS 语音合成系统

### 16.1 架构

```
TTSAdapter (抽象基类)
  ├─ synthesize(text, voice, ...) → bytes (完整合成)
  └─ synthesize_stream(text, voice, ...) → AsyncIterator[bytes] (流式合成)

TTSManager
  ├─ 多引擎注册
  ├─ 引擎选择（按 persona 配置）
  ├─ 缓存管理（哈希键值 + LRU）
  ├─ 流式合成（SSML 分流 + 缓冲）
  └─ 缓存预热（空闲时预加载）
```

### 16.2 已实现的引擎

| 引擎 | 文件 | 类型 | 特点 |
|------|------|------|------|
| EdgeTTS | `edge_tts_adapter.py` | 在线 | 微软 Edge 免费 TTS |
| OpenAITTS | `openai_tts_adapter.py` | 在线 | OpenAI TTS API |
| AzureTTS | `azure_tts_adapter.py` | 在线 | Azure 认知服务 |
| PiperTTS | `piper_tts_adapter.py` | 本地离线 | Piper 本地 TTS |

### 16.3 流式合成流程

```
文本输入 → SSML 分句 → 异步流式合成 → 音频块缓冲 →
→ WebSocket 推送 (base64 AudioChunk) → 客户端解码播放
```

---

## 17. 认证与会话系统

### 17.1 认证系统

| 组件 | 说明 |
|------|------|
| `User` / `UserRole` | 用户模型（admin/user） |
| `UserStore` | JSON 文件持久化 + bcrypt 密码哈希 |
| `AuthManager` | JWT token 管理（Cookie/Header 双认证）|
| `API Key` | 长期令牌支持 |
| `get_current_user` | FastAPI 依赖注入 |
| `require_admin` | 管理员权限守卫 |

### 17.2 会话管理

| API | 说明 |
|-----|------|
| `POST /api/auth/login` | 密码登录 |
| `POST /api/auth/api-key` | API Key 认证 |
| `GET/POST /api/conversations` | 会话列表/创建 |
| `POST /api/chat` | 发送消息 |
| `GET /api/admin/users` | 用户管理 |
| `POST /api/admin/backup` | 数据备份 |

### 17.3 WebSocket 认证

```
/ws/chat?token=<jwt>
/ws/tts?token=<jwt>
/ws/logs?token=<jwt>
```

---

## 18. 基础设施

### 18.1 存储层

| 存储类型 | 默认实现 | 可选实现 |
|----------|----------|----------|
| 关系型数据库 | SQLite | MySQL |
| 向量数据库 | Milvus Lite | Qdrant |
| 缓存 | 内存字典 | Redis |
| 图数据库 | Kuzu | Neo4j |
| 消息队列 | 内存队列 | Redis |

### 18.2 SQLite 增强

`sqlite_store.py` 提供：
- **FTS5 全文搜索**：消息内容实时索引
- **复合索引**：查询性能优化
- **JSON 字段回退**：FTS5 不可用时自动降级

### 18.3 日志系统

| 功能 | 实现 |
|------|------|
| 结构化日志 | structlog + JSON 格式 |
| 文件轮转 | TimedRotatingFileHandler（按天）|
| 动态级别 | API 动态调整日志级别 |
| 日志流 | WebSocket 实时日志（管理员）|

### 18.4 监控

- Prometheus 指标：请求计数、延迟、活跃连接
- Grafana 仪表盘
- 告警系统：阈值告警 + 通知

### 18.5 备份与迁移

- 自动备份 API
- 数据库迁移框架（UP/DOWN 脚本）
- 数据恢复 API

---

## 19. 用户界面

### 19.1 WebUI

- **框架**: Vue 3 + TypeScript + Vite + Naive UI
- **状态管理**: Pinia（auth, chat store）
- **路由**: Vue Router + 路由守卫
- **页面**:
  - 登录页（密码 + API Key）
  - 聊天页（会话侧边栏 + 消息气泡 + 流式输出）
  - 管理页（系统指标、用户管理、备份管理）
- **SSR**: VitePress 文档站（支持中/英/日）

### 19.2 TUI（终端界面）

- **框架**: Textual
- **功能**:
  - 登录界面（用户名密码 + API Key）
  - 聊天界面（消息气泡、RichLog）
  - 会话列表管理
  - 斜杠命令系统
  - 快捷键（Ctrl+N/Q/L, F1, Ctrl+Tab）
  - 信息面板（状态/记忆/帮助）
  - 输入历史（Up/Down）
- **启动**: `yuanbot tui [--host] [--token] [--api-key]`

---

## 20. CLI 命令行工具

`cli.py`（2517 行）提供完整的命令行界面：

| 命令组 | 命令 | 说明 |
|--------|------|------|
| 内置 | `yuanbot serve` | 启动 Web 服务 |
| | `yuanbot tui` | 启动终端 UI |
| AI 提供商 | `yuanbot provider list` | 列出所有提供商 |
| | `yuanbot provider info <id>` | 查看提供商详情 |
| | `yuanbot provider set default/embedding <id>` | 切换提供商 |
| | `yuanbot provider create` | 交互式创建提供商 |
| 配置 | `yuanbot config show` | 显示当前配置 |
| | `yuanbot config init` | 初始化配置目录 |
| | `yuanbot config validate` | 验证配置文件 |
| 记忆 | `yuanbot memory search <query>` | 搜索记忆 |
| | `yuanbot memory stats` | 记忆统计 |
| 工具 | `yuanbot tool list` | 列出可用工具 |
| 更新 | `yuanbot update [--check]` | 检查/执行更新 |
| 数据 | `yuanbot export` | 导出用户数据 |
| | `yuanbot gdpr delete <user_id>` | GDPR 删除用户数据 |
| 系统 | `yuanbot doctor` | 运行系统诊断 |

---

## 21. 测试体系

### 21.1 概况

| 指标 | 数值 |
|------|------|
| 测试总数 | **1453** |
| 通过 | **1453** (100%) |
| 失败 | **0** |
| 跳过 | **3** |
| Ruff 错误 | **0** (100% clean) |
| 覆盖率 | 持续追踪 |

### 21.2 测试覆盖模块

```
tests/
├── test_adapters/       # AI + 通道适配器测试
├── test_auth/           # 认证系统测试
├── test_core/           # 核心类型测试
├── test_gateway/        # 网关测试
├── test_infrastructure/ # 基础设施测试
├── test_memory/         # 记忆系统测试（含情感追踪）
├── test_orchestrator/   # 编排引擎测试
├── test_persona/        # 决策系统测试
├── test_proactive/      # 主动陪伴测试
├── test_providers/      # 提供商管理测试
├── test_services/       # 服务层测试
├── test_skills/         # Skill 系统测试
├── test_tts/            # TTS 测试
└── test_tools/          # 工具沙盒测试
```

---

## 22. 部署与运维

### 22.1 部署方式

| 方式 | 说明 |
|------|------|
| Docker 容器 | 单容器部署，包含所有服务 |
| Docker Compose | 多服务编排（含 Redis/MySQL）|
| Kubernetes | k8s/ 目录提供部署配置 |
| 裸机/VM | Python 3.12+ 直接运行 |

### 22.2 配置目录结构

```
configs/
├── bot.yaml            # 主配置
├── database.yaml       # 数据库
├── memory.yaml         # 记忆系统
├── Providers/          # AI 提供商
├── Channels/           # 消息通道
├── Personas/           # 人设
├── Plugins/            # 插件
├── grafana/            # 监控
└── loki/               # 日志聚合
```

### 22.3 环境变量

| 变量 | 说明 |
|------|------|
| `OPENAI_API_KEY` | OpenAI API 密钥 |
| `ANTHROPIC_API_KEY` | Anthropic API 密钥 |
| `YUANBOT_ADMIN_PASSWORD` | 管理员初始密码 |
| `YUANBOT_API_KEY` | TUI/CLI 自动登录密钥 |
| `YUAN_BOT__*` | 配置覆盖（双下划线分隔） |

---

## 23. 数据流全景

### 23.1 用户消息处理流

```
外部平台 (Telegram/微信/Discord/WebSocket)
  → ChannelAdapter.listen()
  → UserMessage 标准化
  → YuanGateway 路由 + 认证 + 限流
  → OrchestratorEngine.process_message()
    → DialogueDecisionEngine 决策
      → IntentEngine.analyze() + EmotionEngine.analyze()
    → MemoryManager.search_memories() + get_user_profile()
    → CapabilityOrchestrator.load_capabilities() 加载 Skills/Tools
    → ContextBuilder.build_context() 组装 LLM 消息
    → AIService.chat() 调用 LLM
      → [循环] tool_calls → CapabilityOrchestrator.execute_tools()
    → MemoryManager 更新记忆
    → EventEngine 检查是否需要主动交互
  → BotResponse 返回
  → ChannelAdapter.send_message() 发送给用户
```

### 23.2 主动交互流

```
定时器/事件触发
  → EventEngine 评估
  → ProactiveStrategy 决策（免打扰/冷却/上限检查）
  → ProactiveScheduler 调度（Cron/延迟）
  → PushDispatcher.dispatch()
  → ChannelAdapter.send_message()
```

### 23.3 配置热加载流

```
文件系统变更（watchdog）
  → ConfigWatcher.on_change() 回调
  → ProviderManager.reload_provider() / ChannelAdapter 重连
  → 运行时生效，无需重启
```

---

## 附录

### A. 设计文档索引

| 文档 | 说明 |
|------|------|
| `architecture-v1.7.md` | 本文件 |
| `architecture-v1.4.md` | 原始架构设计 |
| `ai-provider-system.md` | AI 提供商系统设计 |
| `persona-decision-system.md` | 人格决策系统设计 |
| `gateway-communication-system.md` | 网关通信系统设计 |
| `capability-tool-system.md` | 能力工具系统设计 |
| `memory-emotion-system.md` | 记忆情感系统设计 |
| `proactive-companion-system.md` | 主动陪伴系统设计 |
| `tts-system.md` | TTS 系统设计 |
| `user-interface-system.md` | 用户界面系统设计 |
| `deployment.md` | 部署运维指南 |
| `development-standards-ecosystem.md` | 开发标准与生态 |
| `conformance-report-v7.md` | 第七轮符合度报告 |
| `infrastructure-deployment-system.md` | 基础设施部署设计 |

### B. 版本合规性

| 标准 | 状态 | 说明 |
|------|------|------|
| Ruff Lint | ✅ 0 errors | 100% clean |
| 测试通过率 | ✅ 100% | 1453/1453 passed |
| 设计符合度 | ✅ 100% | v1.5/v1.6 功能全覆盖 |
| 类型注解 | ⚠️ 106 mypy errors | 主要为 structlog 兼容性误报 |
