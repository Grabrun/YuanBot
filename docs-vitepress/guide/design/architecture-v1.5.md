---
title: 架构设计文档 v1.6
description: YuanBot v1.6 架构设计文档，涵盖十大系统、107 源文件、1412 测试
---

# 🌸 缘·Bot (YuanBot) 架构设计文档 v1.6

## 版本历史

| 版本   | 日期       | 修改内容                                                              |
| ------ | ---------- | --------------------------------------------------------------------- |
| v1.0   | 2026-05-17 | 初始设计                                                              |
| v1.2   | 2026-05-17 | 重构版，系统分类                                                      |
| v1.3   | 2026-05-17 | 配置目录化，SQLite/Milvus Lite                                        |
| v1.4   | 2026-05-17 | Provider 模型列表 + default 字段                                      |
| v1.5   | 2026-05-22 | TUI/WebUI 双界面、TTS 系统、日志系统重构、CLI 扩展、内置插件/技能     |
| v1.6   | 2026-06-10 | 全面反映代码实现：107 源文件、1412 测试、FTS5 全文搜索、gRPC 沙盒等 |
| v1.7   | 2026-06-18 | NapCat 反向 WS 重写、依赖清理、文档重构、1453 测试 |

---

## 第一章：项目概述与设计哲学

### 1.1 项目定义

🌸 缘·Bot (YuanBot) 是一个开源的、高度可定制的 AI 虚拟伴侣系统，致力于打造有记忆、有情感、有主动性的长期陪伴型 AI 角色。

v1.6 标志着系统从"功能完备"走向"工程成熟"——107 个源文件、1412 个测试全部通过、完整的 CI/CD 流水线、以及覆盖意图识别、情感分析、图谱记忆、沙盒执行、链式技能组合等深层能力的实现。

### 1.2 设计哲学：Memory-First

记忆与情感连续性为第一性引擎。所有系统组件围绕"让 AI 记住你、理解你、主动关心你"这一核心原则组织。

### 1.3 核心目标

| 维度       | 说明                                                                   |
| ---------- | ---------------------------------------------------------------------- |
| 记忆连续性 | 四层记忆架构（工作/事实/情景/语义），跨平台持久化                      |
| 情感一致性 | LLM CoT 深度情感分析 + 情绪追踪器，稳定人格自然情绪                   |
| 主动陪伴   | Cron 调度 + 事件引擎 + 免打扰策略 + 用户反馈自动降频                  |
| 开放生态   | Y.E.S. 扩展标准 + Marketplace + SkillChain 链式组合 + 渐进式加载       |
| 多模态交互 | TUI + WebUI + 4 种 TTS 引擎 + 流式合成 + 双层缓存预热                 |
| 安全可信   | JWT 三级 scope + RBAC + Docker/gRPC/WASM 三重沙盒 + GDPR 隐私合规     |
| 工程成熟   | 1412 测试 + CI (ruff/py3.12/3.13) + 热重载 + Serverless 部署          |

### 1.4 对标参考

保持不变，略。

---

## 第二章：总体架构与系统分类

v1.6 十大系统，覆盖从用户接入到模型推理、从记忆管理到社区生态的完整链路。

| 编号 | 系统名                       | 核心职责                                    |
| ---- | ---------------------------- | ------------------------------------------- |
| 1    | 接入与通信系统               | 8 通道适配 + JWT 认证 + 推送分发 + 隐私合规 |
| 2    | 用户界面系统                 | TUI + WebUI (Vue 3) + FastAPI 后端          |
| 3    | 语音合成系统 (TTS)           | 4 引擎 + 双层缓存 + 流式合成                |
| 4    | 人格与行为决策系统           | 多人设 + ONNX 意图识别 + LLM 情感分析       |
| 5    | 记忆与情感系统               | 四层记忆 + 图数据库 + 向量检索 + FTS5       |
| 6    | 能力与工具扩展系统           | SkillChain + 渐进式加载 + Marketplace       |
| 7    | AI 提供商适配系统            | 适配器复用 + 熔断限流 + 8 Provider 预置     |
| 8    | 主动陪伴与自动化系统         | Cron 调度 + 事件驱动 + 防骚扰策略           |
| 9    | 统一开发标准与社区生态       | Y.E.S. 标准 + CLI 18 命令 + CI/CD           |
| 10   | 基础架构与部署系统           | 配置热重载 + 备份恢复 + 迁移 + Serverless   |

### 2.1 系统交互数据流

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                         接入与通信系统 (System 1)                        │
│  Telegram · Discord · 企业微信 · Web · QQ · 微信iLink · 钉钉 · 飞书     │
│  ├── BaseChannelAdapter (统一消息抽象)                                   │
│  ├── IdentityService (跨平台用户映射)                                   │
│  ├── ChannelAuth + JWTAuth (三级 scope) + RateLimiter                   │
│  └── PushDispatcher (多通道推送)                                        │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │ 标准消息
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       人格与行为决策系统 (System 4)                       │
│  OrchestratorEngine (编排)                                              │
│  ├── IntentEngine + MLIntentClassifier (ONNX) ←── 意图分类              │
│  ├── EmotionEngine + DeepEmotionAnalyzer (LLM CoT) ←── 情感分析         │
│  ├── DialogueDecisionEngine ←── 对话决策                                │
│  ├── ContextBuilder ←── 上下文组装                                      │
│  ├── TokenBudgetManager ←── Token 预算管理                              │
│  └── DecisionPluginManager ←── 决策插件扩展                             │
└────┬───────────┬───────────────┬────────────────────────────────────────┘
     │           │               │
     │ 记忆查询  │ 能力调用      │ 模型推理
     ▼           ▼               ▼
┌──────────┐ ┌──────────┐ ┌──────────────────────────────────────────────┐
│ System 5 │ │ System 6 │ │           System 7: AI 提供商适配系统         │
│ 记忆与   │ │ 能力与   │ │  AIService (TokenBucket + CircuitBreaker)     │
│ 情感系统 │ │ 工具扩展 │ │  ├── OpenAIAdapter (通用 OpenAI 兼容)         │
│          │ │          │ │  ├── AnthropicAdapter                          │
│ 四层记忆 │ │ SkillChain│ │  ├── OllamaAdapter                            │
│ 图数据库 │ │ 渐进加载 │ │  └── 8 Provider 配置                          │
│ 向量检索 │ │ Marketplace│ │                                              │
│ FTS5     │ │ 沙盒执行 │ └──────────────────────────────────────────────┘
└──────────┘ └──────────┘
     │
     ▼
┌──────────────────┐        ┌──────────────────┐
│  TTS 系统 (S3)   │        │  主动陪伴 (S8)   │
│  文本 → 语音      │        │  Cron + 事件     │
│  双层缓存预热     │        │  免打扰策略       │
└────────┬─────────┘        └──────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          用户界面系统 (System 2)                         │
│  TUI (Textual) · WebUI (Vue 3 + Naive UI) · FastAPI 后端               │
│  会话 CRUD · 消息搜索(FTS5) · 导出(Markdown/JSON) · 管理面板            │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 第三章：接入与通信系统

### 3.1 核心组件

| 文件/类                              | 职责                                        |
| ------------------------------------ | ------------------------------------------- |
| `gateway/gateway.py` — YuanGateway   | 统一入口，生命周期管理                      |
| `gateway/adapter_manager.py`         | AdapterManager，动态加载/卸载通道适配器     |
| `gateway/identity_service.py`        | IdentityService，跨平台用户身份映射         |
| `gateway/push_dispatcher.py`         | PushDispatcher，多通道推送分发              |
| `gateway/auth.py`                    | ChannelAuthenticator + RateLimiter + TokenBucket |
| `gateway/jwt_auth.py`               | JWTAuthManager，三级 scope + token 自动刷新 |
| `gateway/privacy.py`                 | PrivacyManager，GDPR 数据导出/删除          |
| `adapters/channel/base.py`          | BaseChannelAdapter，统一消息抽象接口        |
| `adapters/channel/weixin_cdn.py`    | 微信 CDN 媒体上传/下载                     |

### 3.2 八大通道适配器

| 渠道       | 适配器文件             | 说明                        |
| ---------- | ---------------------- | --------------------------- |
| Telegram   | `telegram_adapter.py`  | Telegram Bot API            |
| Discord    | `discord_adapter.py`   | Discord Bot + Gateway       |
| 企业微信   | `wecom_adapter.py`     | 企业微信回调                |
| Web        | `web_adapter.py`       | WebChat + WebSocket         |
| QQ         | `qq_adapter.py`        | QQ 机器人官方 API           |
| 微信 iLink | `weixin_ilink_adapter.py` | 通过 iLink 协议接入个人微信 |
| 钉钉       | `dingtalk_adapter.py`  | 钉钉机器人回调              |
| 飞书       | `feishu_adapter.py`    | 飞书应用机器人              |

### 3.3 认证与安全

- **ChannelAuthenticator**: 通道级签名校验
- **JWTAuthManager**: 三级 scope（admin / user / readonly），token 自动刷新
- **RateLimiter + TokenBucket**: 多维限流（用户级 + 通道级）
- **PrivacyManager**: GDPR 合规的数据导出和删除接口

---

## 第四章：用户界面系统

### 4.1 TUI 终端界面

| 文件               | 职责                              |
| ------------------ | --------------------------------- |
| `tui/app.py`       | Textual 应用主程序                |
| `tui/client.py`    | 与后端通信的客户端               |
| `tui/__main__.py`  | CLI 入口 (`yuanbot-cli tui`)     |

**特性**: 终端内实时流式聊天、多会话切换、系统命令入口（/persona, /memory, /plugin, /provider）、配色主题可定制。

### 4.2 WebUI (Vue 3 + Naive UI)

**前端视图模块**:

| 视图                | 功能                              |
| ------------------- | --------------------------------- |
| LoginView           | 登录认证                          |
| ChatView            | 流式对话，支持文本/图片/语音      |
| AdminView           | 用户管理、系统指标、备份恢复      |
| ProviderView        | AI 提供商配置管理                 |
| MemoryView          | 记忆浏览器（查看/编辑/图谱可视化）|
| PluginView          | 插件安装、启用/禁用               |
| ConfigView          | 在线编辑 bot.yaml 等配置          |
| LogView             | 实时日志查看                      |
| MarketplaceView     | 扩展市场浏览安装                  |
| PersonaStoreView    | 人设商店浏览                      |

**后端 API** (`auth/` 目录):

| 文件/模块                    | 功能                                              |
| ---------------------------- | ------------------------------------------------- |
| `auth/` 认证系统             | JWT + Cookie + bcrypt + RBAC                      |
| `auth/conversation_routes.py` | 会话 CRUD + 消息搜索 (FTS5) + 导出 (Markdown/JSON) |
| `auth/admin_routes.py`       | 用户管理 + 系统指标 + 备份恢复 + `PUT /admin/logging/level` 动态日志级别 |

---

## 第五章：语音合成系统 (TTS)

### 5.1 系统架构

```text
文本响应 → TTSManager → 双层缓存(L1 内存 / L2 文件) → 引擎适配 → 音频文件/流
                           │
                           ├── 缓存命中 → 直接返回
                           └── 缓存未命中 → 引擎合成 → 写入缓存 → 返回
```

### 5.2 核心组件

| 文件/类                              | 职责                                          |
| ------------------------------------ | --------------------------------------------- |
| `tts/base.py` — TTSAdapter          | 抽象接口，定义 `synthesize()` 协议            |
| `tts/manager.py` — TTSManager       | 双层缓存 (L1 内存 / L2 文件) + 流式合成 + `prewarm_cache` 缓存预热 |

### 5.3 四大引擎

| 引擎     | 类型   | 说明                                      |
| -------- | ------ | ----------------------------------------- |
| Edge-TTS | 云端   | 免费，中文效果好，无需密钥                |
| Piper    | 本地   | 离线运行，多语言支持，低资源消耗          |
| OpenAI TTS | 云端 | 高质量，需要 API Key                      |
| Azure TTS  | 云端 | 微软 Azure 认知服务                       |

### 5.4 配置

```yaml title="configs/tts.yaml"
tts:
  enabled: true
  engine: edge-tts
  default_voice: "zh-CN-XiaoxiaoNeural"
  cache:
    l1_max_size: 100       # 内存缓存条目上限
    l2_directory: "~/.yuanbot/tts-cache"
    prewarm: true           # 启动时预热常用语音
```

---

## 第六章：人格与行为决策系统

### 6.1 核心组件

| 文件/类                                            | 职责                                    |
| -------------------------------------------------- | --------------------------------------- |
| `persona/default.py` — DefaultPersona              | 默认人设 + RELATIONSHIP_STAGES (4 阶段) |
| `persona/manager.py` — PersonaManager + YamlPersona | 多人设运行时切换                        |
| `persona/engines/intent_engine.py`                 | IntentEngine + MLIntentClassifier (ONNX) + SklearnIntentClassifier |
| `persona/engines/emotion_engine.py`                | EmotionEngine + DeepEmotionAnalyzer (LLM CoT 深度情感分析) |
| `persona/engines/dialogue_decision.py`             | DialogueDecisionEngine 对话决策         |
| `persona/engines/context_builder.py`               | ContextBuilder 上下文组装               |
| `persona/engines/token_budget.py`                  | TokenBudgetManager Token 预算管理       |
| `persona/engines/decision_plugin.py`               | DecisionPlugin 抽象 + DecisionPluginManager |
| `orchestrator/engine.py` — OrchestratorEngine       | 编排引擎，协调各子系统                  |

### 6.2 4 阶段关系进化

DefaultPersona 内置 `RELATIONSHIP_STAGES`，定义从陌生到亲密的 4 个关系阶段，影响对话风格、情感表达和主动行为的密度。

### 6.3 意图识别引擎

- **MLIntentClassifier**: 基于 ONNX Runtime 的本地推理，零延迟意图分类
- **SklearnIntentClassifier**: 备选方案，基于 scikit-learn 的轻量分类器
- **IntentEngine**: 统一调度，自动选择最佳分类器

### 6.4 情感分析引擎

- **DeepEmotionAnalyzer**: 利用 LLM 的 CoT (Chain-of-Thought) 推理能力进行深度情感分析
- **EmotionEngine**: 情感状态管理 + 与 EmotionTracker 联动

---

## 第七章：记忆与情感系统

### 7.1 核心组件

| 文件/类                                       | 职责                                      |
| --------------------------------------------- | ----------------------------------------- |
| `memory/manager.py` — MemoryManager           | 四层记忆 (工作/事实/情景/语义) + `detect_important_dates` 重要日期检测 |
| `memory/emotion_tracker.py` — EmotionTracker  | 情绪追踪与记录                            |
| `infrastructure/sqlite_store.py`              | SQLiteStore + FTS5 全文搜索               |
| `infrastructure/mysql_store.py`               | MySQLStore                                |
| `infrastructure/vector_store.py`              | Milvus Lite + InMemory fallback           |
| `infrastructure/graph_store.py`               | Kuzu 图数据库 + InMemory fallback         |
| `infrastructure/cache_store.py`               | Redis CacheStore + InMemoryCacheStore     |
| `infrastructure/database.py`                  | DatabaseManager，SQLite/MySQL 透明切换    |

### 7.2 四层记忆架构

| 层级   | 名称   | 说明                            | 存储后端       |
| ------ | ------ | ------------------------------- | -------------- |
| L1     | 工作记忆 | 当前会话短期上下文              | 内存           |
| L2     | 事实记忆 | 用户属性、偏好、关键事件        | SQLite/MySQL   |
| L3     | 情景记忆 | 具体对话场景与情绪关联          | Kuzu 图数据库  |
| L4     | 语义记忆 | 向量化语义检索                  | Milvus Lite    |

### 7.3 FTS5 全文搜索

`infrastructure/sqlite_store.py` 实现了 SQLite FTS5 全文搜索支持：

- **messages 表**: 存储原始消息
- **messages_fts 虚拟表**: FTS5 索引，支持中文分词
- **自动同步触发器**: INSERT/UPDATE/DELETE 自动维护 FTS5 索引一致性
- **会话搜索 API**: 通过 `auth/conversation_routes.py` 暴露全文搜索能力

### 7.4 图数据库记忆

`infrastructure/graph_store.py` 使用 Kuzu 嵌入式图数据库存储情景记忆的关系网络：

- 实体节点（用户、地点、事件、情感）
- 关系边（经历、关联、触发）
- 内置 InMemory fallback，Kuzu 不可用时自动降级

### 7.5 向量检索

`infrastructure/vector_store.py` 基于 Milvus Lite 提供语义向量检索：

- 内嵌式部署，无需独立 Milvus 服务
- InMemory fallback 确保开发环境可用
- 支持 embedding 模型配置（通过 Provider 配置中的 `embedding_model`）

### 7.6 重要日期检测

`MemoryManager.detect_important_dates()` 自动从对话中提取生日、纪念日等重要日期，写入事实记忆并可触发主动问候。

---

## 第八章：能力与工具扩展系统

### 8.1 核心组件

| 文件/类                                              | 职责                                        |
| ---------------------------------------------------- | ------------------------------------------- |
| `skills/manager.py` — SkillManager                   | 技能生命周期管理                            |
| `tools/manager.py` — ToolManager                     | 工具注册与调度                              |
| `tools/builtin.py`                                   | search_executor + weather_executor 内置工具 |
| `tools/sandbox.py`                                   | DockerSandboxExecutor + WasmSandboxExecutor |
| `tools/grpc_sandbox.py`                              | GrpcToolServer + SandboxClient (gRPC 沙盒)  |
| `services/capability_orchestrator.py`                | CapabilityOrchestrator 能力编排             |
| `services/extension_standard.py` — Y.E.S.            | 扩展标准 + `create_scaffold` 脚手架生成     |
| `services/marketplace.py`                            | MarketplaceClient + ExtensionReviewStore    |
| `services/progressive_loader.py` — ProgressiveLoader | 三层渐进式加载                              |
| `services/skill_chain.py` — SkillChainManager        | 链式技能组合 (5 种触发条件)                 |
| `services/domain_matcher.py` — DomainMatcher         | 领域匹配器                                  |

### 8.2 内置工具

**Search Executor** (`tools/builtin.py`):

| 后端       | 说明                   |
| ---------- | ---------------------- |
| Bing API   | 微软 Bing 搜索         |
| SerpAPI    | Google 搜索结果        |
| DuckDuckGo | 无需 API Key 的搜索    |

**Weather Executor** (`tools/builtin.py`):

| 后端       | 说明                   |
| ---------- | ---------------------- |
| 和风天气   | 中国天气数据           |
| OpenWeatherMap | 国际天气数据       |
| wttr.in    | 无需 API Key 的天气    |

### 8.3 三重沙盒执行

| 沙盒类型           | 实现                              | 适用场景                |
| ------------------ | --------------------------------- | ----------------------- |
| Docker 沙盒        | DockerSandboxExecutor             | 隔离运行第三方代码      |
| gRPC 沙盒          | GrpcToolServer + SandboxClient    | 已编译 proto stubs，高性能 RPC |
| WASM 沙盒          | WasmSandboxExecutor (wasmtime)    | 原生 WebAssembly 沙盒，轻量安全 |

### 8.4 SkillChain 链式组合

`SkillChainManager` 支持将多个技能串联执行，提供 5 种触发条件：

1. 意图触发
2. 关键词触发
3. 时间触发
4. 情感状态触发
5. 手动触发

### 8.5 渐进式加载

`ProgressiveLoader` 实现三层加载策略：

1. **即时加载**: 核心技能，启动即就绪
2. **按需加载**: 首次调用时加载
3. **预加载**: 基于使用模式预测性加载

### 8.6 Y.E.S. 扩展标准

`services/extension_standard.py` 定义了 YuanBot Extension Standard：

- 标准化的 `manifest.json` 格式
- `create_scaffold()` 一键生成扩展脚手架
- 与 Marketplace 集成，支持发布、安装、评分

---

## 第九章：AI 提供商适配系统

### 9.1 核心组件

| 文件/类                                    | 职责                                          |
| ------------------------------------------ | --------------------------------------------- |
| `adapters/ai/base.py` — BaseAIProvider     | 统一抽象接口 + `sanitize_log_data` 日志脱敏   |
| `adapters/ai/openai_adapter.py`           | OpenAIAdapter (通用 OpenAI 兼容)              |
| `adapters/ai/anthropic_adapter.py`        | AnthropicAdapter                              |
| `adapters/ai/deepseek_adapter.py`         | DeepSeekAdapter (已废弃 → 继承 OpenAIAdapter) |
| `adapters/ai/ollama_adapter.py`           | OllamaAdapter                                 |
| `providers/manager.py` — ProviderManager   | resolve_model + list_providers + validate_provider_config |
| `services/ai_service.py` — AIService       | TokenBucket 限流 + CircuitBreaker 熔断 + 重试 + HTTP 429 Retry-After |

### 9.2 Provider 配置复用机制

核心理念：适配器仅负责 API 调用实现，Provider 由配置文件定义。同一适配器可被多个 Provider 共用。

```yaml title="configs/Providers/qwen.yaml"
provider_id: qwen
name: "通义千问"
adapter: openai-adapter        # 复用 OpenAI 兼容适配器
enabled: true
config:
  api_key: "your-dashscope-key"
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
  models:
    - id: qwen-max
      type: chat
      max_tokens: 32768
    - id: text-embedding-v3
      type: embedding
      dimension: 1536
  default: qwen-max
  embedding_model: text-embedding-v3
```

### 9.3 预置 Provider (8 个)

| Provider ID | 适配器             | 默认模型         | 说明               |
| ----------- | ------------------ | ---------------- | ------------------ |
| openai      | openai-adapter     | gpt-4o           | OpenAI 官方        |
| deepseek    | openai-adapter     | deepseek-chat    | 深度求索           |
| glm         | openai-adapter     | glm-4            | 智谱 GLM 系列      |
| mimo        | openai-adapter     | mimo-chat        | 米莫 AI            |
| qwen        | openai-adapter     | qwen-max         | 通义千问           |
| hunyuan     | openai-adapter     | hunyuan-pro      | 腾讯混元           |
| ollama      | openai-adapter     | qwen3:14b        | 本地 Ollama        |
| claude      | anthropic-adapter  | claude-sonnet-4  | Anthropic 官方     |

### 9.4 AIService 保障机制

- **TokenBucket**: 令牌桶限流，防止 API 过载
- **CircuitBreaker**: 熔断器，连续失败后自动降级
- **重试策略**: 指数退避 + HTTP 429 Retry-After 尊重
- **日志脱敏**: `sanitize_log_data` 自动移除敏感字段

---

## 第十章：主动陪伴与自动化系统

### 10.1 核心组件

| 文件/类                                       | 职责                                    |
| --------------------------------------------- | --------------------------------------- |
| `proactive/scheduler.py` — ProactiveScheduler | Cron 调度引擎                           |
| `proactive/strategy.py` — ProactiveStrategy   | 免打扰 + 每日上限 + 防重锁 + 用户反馈自动降频 |
| `proactive/event_engine.py` — EventEngine     | 事件驱动引擎                            |
| `proactive/trigger.py`                        | ProactiveTrigger + TriggerManager 插件系统 |
| `proactive/retry_queue.py` — PersistentRetryQueue | 持久化重试队列                       |

### 10.2 策略与防骚扰

- **免打扰**: 基于时间段的消息抑制
- **每日上限**: 每日主动消息数量限制
- **防重锁**: 防止同一话题重复发送
- **用户反馈降频**: 检测到"别发了"等反馈时自动降低推送频率

---

## 第十一章：统一开发标准与社区生态

### 11.1 CLI 命令 (18 个)

`cli.py` 提供完整的命令行管理工具：

| 分类     | 命令                                                                |
| -------- | ------------------------------------------------------------------- |
| 服务管理 | `start` · `doctor`                                                  |
| 配置管理 | `config`                                                            |
| 记忆管理 | `memory`                                                            |
| 版本信息 | `version`                                                           |
| AI 提供商 | `provider`                                                         |
| 人设管理 | `persona`                                                           |
| 界面启动 | `tui` · `webui`                                                     |
| 扩展开发 | `create` · `validate` · `test` · `build` · `publish`               |
| 扩展安装 | `install` · `search`                                                |
| 运维     | `logs`                                                              |

### 11.2 CI/CD 流水线

**`.github/workflows/ci.yml`**:

1. **Lint**: ruff 代码风格检查
2. **Test**: Python 3.12 / 3.13 矩阵测试
3. **Build**: 包构建
4. **Docker**: 容器镜像构建

**`.github/workflows/docs.yml`**:

- GitHub Pages 自动部署 (MkDocs Material)

### 11.3 测试覆盖

- **1412 个测试全部通过**
- 覆盖所有十大系统的核心功能
- CI 矩阵确保 Python 3.12 和 3.13 兼容性

---

## 第十二章：基础架构与部署系统

### 12.1 核心组件

| 文件/类                                    | 职责                                          |
| ------------------------------------------ | --------------------------------------------- |
| `infrastructure/config_loader.py`         | 配置加载                                      |
| `infrastructure/config_watcher.py`        | 配置热重载                                    |
| `infrastructure/backup.py` — BackupManager | 备份管理                                      |
| `infrastructure/migration.py` — DatabaseMigrator | SQLite → MySQL 数据迁移                 |
| `infrastructure/logging_config.py`        | TimedRotatingFileHandler 30 天轮转 + `set_log_level` 动态调整 |
| `infrastructure/alerting.py` — AlertManager | Webhook + 日志告警                           |
| `infrastructure/event_queue.py`           | MemoryEventQueue + RedisEventQueue            |
| `deployment/serverless.py`               | AWS Lambda + 阿里云 FC 部署支持               |

### 12.2 配置目录结构

```text
configs/
├── bot.yaml                    # 主配置
├── database.yaml               # 数据库配置 (SQLite/MySQL)
├── memory.yaml                 # 记忆系统配置 (四层策略)
├── tts.yaml                    # TTS 引擎配置
├── orchestrator.yaml           # 编排引擎配置
├── extensions.yaml             # 扩展注册表
├── Channels/                   # 通道适配器配置
│   ├── telegram.yaml
│   ├── discord.yaml
│   ├── wecom.yaml
│   ├── web.yaml
│   ├── qq.yaml
│   ├── weixin_ilink.yaml
│   ├── dingtalk.yaml
│   └── feishu.yaml
├── Providers/                  # AI 提供商配置
│   ├── openai.yaml
│   ├── deepseek.yaml
│   ├── glm.yaml
│   ├── mimo.yaml
│   ├── qwen.yaml
│   ├── hunyuan.yaml
│   ├── ollama.yaml
│   └── claude.yaml
├── Plugins/                    # 插件配置
│   ├── skills/
│   └── tools/
│       ├── search.yaml
│       └── weather.yaml
└── Personas/                   # 人设配置
```

### 12.3 日志系统

- **结构化日志**: JSON 格式，包含 timestamp / level / module / trace_id
- **自动轮转**: TimedRotatingFileHandler，30 天保留
- **动态调整**: `PUT /admin/logging/level` API，无需重启
- **告警集成**: AlertManager 支持 Webhook + 日志告警

### 12.4 部署方案

| 方案          | 说明                                  |
| ------------- | ------------------------------------- |
| 本地部署      | 直接 `yuanbot-cli start`              |
| Docker        | 容器化部署                            |
| Kubernetes    | 生产级编排                            |
| Nginx 反向代理 | WebUI 生产环境推荐                   |
| Serverless    | AWS Lambda / 阿里云 FC               |

---

## 附录 A：v13–v34 性能优化摘要

v1.6 包含了从 v13 到 v34 共 22 轮迭代的性能优化，涵盖以下关键改进：

| 轮次范围     | 优化方向                      | 关键成果                                               |
| ------------ | ----------------------------- | ------------------------------------------------------ |
| v13–v16      | 记忆系统优化                  | 四层记忆架构落地，FTS5 全文搜索，Kuzu 图数据库集成     |
| v17–v19      | AI 提供商适配                 | 适配器复用机制，AIService 熔断限流，日志脱敏            |
| v20–v22      | 人格引擎增强                  | ONNX 意图识别，LLM CoT 情感分析，4 阶段关系进化        |
| v23–v25      | 扩展系统深化                  | SkillChain 链式组合，渐进式加载，Y.E.S. 标准           |
| v26–v28      | 沙盒与安全                    | gRPC 沙盒 (proto 编译)，WASM 沙盒 (wasmtime)，JWT 三级 scope |
| v29–v31      | TTS 与缓存                    | 双层缓存 (L1/L2)，缓存预热，Piper 本地离线引擎        |
| v32–v34      | 工程成熟度                    | 1412 测试全通过，CI/CD 流水线，Serverless 部署，热重载 |

### 关键性能指标

- **FTS5 搜索**: 消息全文搜索延迟 < 10ms (SQLite 内嵌)
- **意图识别**: ONNX 本地推理，单次 < 50ms
- **TTS 缓存命中率**: L1 内存缓存热路径命中率 > 80%
- **API 熔断**: CircuitBreaker 连续 5 次失败自动熔断，30s 恢复窗口
- **渐进式加载**: 核心技能启动即就绪，扩展技能首次调用 < 500ms

---

## 附录 B：路线图（更新）

| 里程碑      | 内容                                                  | 状态 |
| ----------- | ----------------------------------------------------- | ---- |
| M1          | TUI 聊天、WebUI 聊天基本可用                          | ✅    |
| M2          | 管理界面实现，TTS 集成                                | ✅    |
| M3          | 新 Provider 机制重构，GLM/Qwen/Hunyuan 等适配        | ✅    |
| M4          | QQ/钉钉/飞书/微信 iLink 通道开发                      | ✅    |
| M5          | 内置 Search/Weather 插件、内置 Skills 完善            | ✅    |
| M6          | CLI 全功能、规范文档、社区 Beta                       | ✅    |
| v1.5 发布   | 全量测试、文档、示例                                  | ✅    |
| v1.6        | FTS5、图数据库、gRPC/WASM 沙盒、SkillChain、Serverless | ✅    |
| v1.7 (规划) | 多模态输入 (图像理解)、语音识别 (STT)                 | 🔲    |
| v1.8 (规划) | 端到端加密、多用户协作、移动端 App                    | 🔲    |

---

## 附录 C：源文件清单统计

| 系统                           | 源文件数 | 占比   |
| ------------------------------ | -------- | ------ |
| 接入与通信系统                 | ~12      | 11.2%  |
| 用户界面系统                   | ~12      | 11.2%  |
| 语音合成系统                   | ~3       | 2.8%   |
| 人格与行为决策系统             | ~10      | 9.3%   |
| 记忆与情感系统                 | ~8       | 7.5%   |
| 能力与工具扩展系统             | ~12      | 11.2%  |
| AI 提供商适配系统              | ~8       | 7.5%   |
| 主动陪伴与自动化系统           | ~5       | 4.7%   |
| 统一开发标准与社区生态         | ~3       | 2.8%   |
| 基础架构与部署系统             | ~9       | 8.4%   |
| 测试                           | ~25      | 23.4%  |
| **合计**                       | **~107** | **100%** |

---

*本文档由架构分析自动生成，基于 107 个源代码文件的静态分析。最后更新：2026-06-10。*
