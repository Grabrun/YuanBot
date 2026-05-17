好的，这是根据你的最新要求修改后的 《🌸 缘·Bot (YuanBot) 项目设计文档 v1.4》。本次升级将 AI 提供商的配置改为显式的模型列表模式，并通过 default 字段指定默认模型，配置结构更清晰、可扩展性更强。

---

🌸 缘·Bot (YuanBot) 项目设计文档 v1.4

版本历史

版本 日期 修改内容
v1.0 2026-05-17 初始设计，包含项目概述、竞品分析、系统架构及各项设计
v1.2 2026-05-17 重构版。基于系统分类重新组织，强化系统间接口与通信
v1.3 2026-05-17 配置架构升级。统一文件型配置目录；记忆系统默认 SQLite，支持 MySQL；向量数据库确定为 Milvus Lite
v1.4 2026-05-17 Provider 配置模型化。Providers 配置改为显式模型列表 + default 字段指定默认模型

---

第一章：项目概述与设计哲学

1.1 项目定义

🌸 缘·Bot (YuanBot) 是一个开源的、高度可定制的 AI 虚拟伴侣系统。它并非传统的单轮问答机器人，也不是纯粹的自动化任务 Agent，而是致力于打造一个有记忆、有情感、有主动性的长期陪伴型 AI 角色——一个“懂你、记住你、主动关心你”的数字伴侣。

YuanBot 的核心定位是融合“聊天机器人的温度”与“现代 Agent 的执行力”，在提供情绪价值和深度陪伴的同时，也具备完成实用任务的能力。

项目名称“缘·Bot”取自“缘分”，寓意 AI 与用户之间的每一次交互都是一段独特缘分的编织与延续。

1.2 设计哲学：Memory-First

YuanBot 的核心理念是 Memory-First (记忆优先)。与传统 Agent 框架将工具调用或工作流编排作为核心不同，YuanBot 将“长期记忆与情感连续性”置于架构设计的首要位置。每一个交互决策、每一次主动行为，都以“她是否记得用户是谁、用户喜欢什么、过往发生了什么”为前提。

1.3 核心目标

维度 说明
记忆连续性 跨越时间与平台，让 AI 角色始终记得用户说过的话、情绪和好恶。
情感一致性 AI 角色具备稳定的人格设定和情感模型，交互风格和情绪表达自然一致。
主动陪伴 不等待用户发起对话，AI 角色可根据上下文、时间、事件主动发起问候。
开放生态 模块化、标准化的可扩展架构，社区可自由开发各类扩展组件。

1.4 主要对标项目参考

项目 核心贡献 对 YuanBot 的关键启示
OpenClaw Gateway-Channel 抽象 消息通道适配器架构设计
Hermes Agent 闭环学习 + 技能自进化 记忆系统主动整理、Skills 动态生成、定时主动交互
Mem0/OpenMemory 混合存储记忆层 分层记忆模型、记忆图谱、本地优先部署
Dify 插件市场 + 标准化开发 适配器接口标准化、社区扩展生态

---

第二章：总体架构与数据流

2.1 系统分类总览

YuanBot v1.4 被划分为八大核心系统：

1. 接入与通信系统
2. 人格与行为决策系统
3. 记忆与情感系统
4. 能力与工具扩展系统
5. AI 提供商适配系统
6. 主动陪伴与自动化系统
7. 统一开发标准与社区生态
8. 基础架构与部署系统（含配置管理）

2.2 系统交互与数据流

```
┌───────────────┐     标准消息      ┌───────────────┐
│ 接入与通信系统 │ ──────────────→ │ 人格与行为     │
│ (消息标准化)  │                 │ 决策系统       │
└───────────────┘                 └───┬───┬───┬───┘
                                      │   │   │
                        ┌─── 记忆查询与注入──┘   │   └── 能力调用与结果处理
                        ↓                       ↓
              ┌───────────────┐     ┌───────────────┐
              │ 记忆与情感系统 │     │ 能力与工具扩展系统 │
              └───────────────┘     └───────┬───────┘
                                            │
                              ┌─── 工具调用时获取模型能力───┘
                              ↓
                    ┌───────────────┐
                    │ AI 提供商适配  │
                    │ 系统           │
                    └───────────────┘

        ┌───────────────┐
        │ 主动陪伴与     │ ──── 主动触发信号 ───→ 人格与行为决策系统
        │ 自动化系统     │
        └───────────────┘
```

---

第三章：记忆与情感系统

核心理念：记忆不是辅助功能，而是驱动一切 AI 角色行为的“第一性引擎”。

3.1 记忆四层模型

记忆层 定义与示例 存储方式 生命周期
1. 工作记忆 当前会话的上下文 (最近N轮对话) 会话级 Redis 缓存 单次会话，超时清除
2. 事实记忆 用户偏好、习惯、重要事实 (如生日、讨厌的食物) SQLite (默认) / MySQL (可选) + 知识图谱 永久 (除非主动修改或淘汰)
3. 情景记忆 过往对话的摘要记录 (如“上周三聊过工作压力”) Milvus Lite (语义索引) + SQLite/MySQL (元数据) 动态管理 (根据重要性评分)
4. 语义记忆 深层认知与关系理解 (如“与用户关系处于亲密阶段”) 知识图谱 (核心) + Milvus Lite (辅助) 持续演化，渐进积累

存储方案说明：

· 关系型数据库默认采用 SQLite，无需额外部署，开箱即用。对于生产环境或高并发场景，可通过 configs/database.yaml 无缝切换至 MySQL。
· 向量数据库统一使用 Milvus Lite，它是 Milvus 的轻量级嵌入式版本，支持本地持久化，可与 SQLite 一起实现完全本地化的记忆存储。

3.2 情景触发式检索

1. 对话摘要节点化：每次对话结束后，系统自动生成包含“时间锚点、话题、情感基调、关键实体”的情景节点，并通过嵌入模型向量化后存入 Milvus Lite。
2. 双路径触发匹配：
   · 语义相似度检索：在 Milvus Lite 中检索相似向量。
   · 关键词/实体匹配：在 SQLite/MySQL 中查询元数据。
3. 上下文注入：匹配到的历史情景摘要，作为 [记忆提示] 注入到当前对话的 System Prompt 中。

3.3 记忆图谱与用户画像

构建实体（用户、AI、喜好）和关系（喜欢、讨厌、关联）的图结构，默认使用内嵌的图引擎（如 Kuzu），亦可对接 Neo4j，实现关系推理。

3.4 自主记忆整理与知识进化

系统在空闲时自动对记忆进行整理：将高价值情景记忆固化为事实记忆，并根据遗忘曲线淘汰低价值记忆。

---

第四章：人格与行为决策系统

核心理念：AI 伴侣的“灵魂”，是所有交互的决策中枢。

4.1 角色人设配置

Agent 人格是系统的一级公民，其配置也遵循目录化原则，存放在 configs/ 特定位置。人设配置包含：

· 性格与语音风格
· 行为规则
· 能力域声明（如 emotional_care, daily_chat）
· 关系阶段感知策略

4.2 核心引擎模块

· 意图识别引擎
· 情感分析引擎
· 对话决策引擎：中枢，综合上述信息做出行为决策。
· 上下文组装器
· Token 预算管理器

---

第五章：接入与通信系统

核心理念：实现消息平台的完全抽象与标准化，配置统一管理。

5.1 统一网关

依然作为系统的单一入口点，负责消息路由、会话管理和认证鉴权。

5.2 消息通道适配器配置

每个消息通道（Telegram、Discord 等）的配置统一存放在 configs/Channels/ 目录下。每个通道一个配置文件，例如 telegram.yaml。

示例：configs/Channels/telegram.yaml

```yaml
adapter: telegram-channel-adapter
enabled: true
config:
  bot_token: "YOUR_BOT_TOKEN"
  webhook_path: "/webhook/telegram"
```

5.3 载荷标准化

保持不变，所有平台消息统一转换为 UserMessage 和 BotResponse 内部格式。

预集成渠道： Telegram, Discord, 企业微信, Web Chat。

---

第六章：能力与工具扩展系统

核心理念：按需赋予 AI 角色“软能力”和“硬工具”，并安全执行。

6.1 Skills 与 Tools 概念区分

· Skills：封装特定场景逻辑的“软能力”。
· Tools：外部 API 或系统功能的标准化封装“硬能力”。

6.2 三层渐进式动态加载

1. 启动时 - 元数据索引
2. 匹配时 - 定义注入
3. 执行时 - 资源获取

6.3 安全沙盒执行

Tool 在独立的 Docker/WASM 沙盒中通过 gRPC 执行，受权限令牌严格控制。

---

第七章：AI 提供商适配系统

核心理念：配置文件驱动的 LLM 无感切换，模型列表显式管理，实现“零供应商锁定”。

7.1 标准化适配器接口

所有 AI 提供商适配器实现统一的 AIProviderAdapter 抽象接口，核心方法包括 chat_completion(), stream_chat_completion(), get_embedding()。

7.2 模型列表式提供商配置

v1.4 中，Provider 被定义为向不同供应商访问的基础，所有 AI 提供商的配置集中存放在 configs/Providers/ 目录下。每个提供商一个配置文件，例如 openai.yaml。

每个提供商配置必须显式声明其所支持的模型列表，并通过 default 字段从该列表中指定一个模型作为该提供商的默认模型。这样做的好处是：支持同一供应商的多个模型共存，并允许系统根据任务类型（对话、嵌入等）灵活选用不同模型。

示例：configs/Providers/openai.yaml

```yaml
provider_id: openai
adapter: openai-adapter
enabled: true
config:
  api_key: "sk-xxx"
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
  default: gpt-4o  # 该提供商的默认模型，必须存在于 models 列表中
```

示例：configs/Providers/claude.yaml

```yaml
provider_id: anthropic
adapter: claude-adapter
enabled: false
config:
  api_key: "sk-ant-xxx"
  models:
    - id: claude-sonnet-4-20250514
      type: chat
      max_tokens: 200000
    - id: claude-opus-4-20250514
      type: chat
      max_tokens: 200000
  default: claude-sonnet-4-20250514
```

活跃提供商的选择通过在根配置 configs/bot.yaml 中指定提供商 ID（而非具体模型）：

```yaml
ai:
  default_provider: openai  # 使用 openai 提供商的 default 模型
```

若需要临时覆盖提供商的默认模型，可在对话请求中动态指定 model 参数，但必须属于该提供商的 models 列表中。

7.3 嵌入模型的选定

嵌入模型同样从提供商配置的 models 列表中选取，系统默认会选择第一个 type: embedding 的模型。也可以在 bot.yaml 中显式指定嵌入模型所属的提供商和模型 ID。

预集成提供商： OpenAI, Anthropic, DeepSeek, Ollama。

---

第八章：主动陪伴与自动化系统

核心理念：让 AI 从被动响应者，转变为主动的陪伴者。

8.1 主动触发调度器

独立后台调度器，管理所有主动行为的触发。

8.2 触发模式

· 定时触发：基于 Cron，实现问候、提醒。
· 事件驱动：天气变化、用户静默检测、基于历史记忆的情绪风险触发。

8.3 克制策略

通过 configs/bot.yaml 中的配置项精细控制频率、免打扰时段等。

---

第九章：统一开发标准与社区生态

9.1 YuanBot Extension Standard (Y.E.S.)

为 AI 提供商、消息通道、Skills、Tools、Agent 人设五种扩展类型定义统一抽象接口。

9.2 社区扩展市场与贡献流程

提供扩展市场与标准化的 PR → CI → 审核 → 上架流水线。

---

第十章：基础架构与部署系统

核心理念：提供稳定、安全、易于配置的运行基础。

10.1 统一配置目录结构

所有配置文件集中于项目根目录下的 configs/ 文件夹。 结构如下：

```
configs/
├── bot.yaml                # 根配置：默认AI提供商、主动陪伴策略、数据目录等
├── database.yaml           # 数据库配置：切换 SQLite / MySQL，Milvus Lite 持久化路径
├── memory.yaml             # 记忆系统参数：遗忘曲线、固化周期等
├── Channels/               # 消息通道适配器配置
│   ├── telegram.yaml
│   ├── discord.yaml
│   └── wecom.yaml
├── Providers/              # AI 提供商适配器配置（含模型列表及默认模型）
│   ├── openai.yaml
│   ├── claude.yaml
│   └── deepseek.yaml
└── Plugins/                # Skills/Tools 按需注册配置
    ├── skills/
    │   └── emotional_comfort.yaml
    └── tools/
        └── weather.yaml
```

配置文件加载优先级： 环境变量 > 配置文件。敏感信息（如 API Key）既可写在 Providers/*.yaml 中，也可通过环境变量覆盖，保证灵活性。

10.2 技术栈选型

组件 技术选择 说明
核心编排层 Python 3.12+ / FastAPI 业务逻辑的核心
消息网关 Rust / Go 高性能事件处理
关系数据库 SQLite (默认) / MySQL (可选) 事实记忆、情景元数据等持久化
向量数据库 Milvus Lite 嵌入式向量存储，本地持久化
图数据库 Kuzu (嵌入式) / Neo4j 知识图谱与关系推理
缓存 Redis 7+ 工作记忆与高速缓存
容器化 Docker + Compose 标准化部署

完全本地化部署能力： 使用 SQLite + Milvus Lite + Kuzu，用户无需安装任何外部数据库即可运行完整记忆系统。

10.3 部署模式

· Docker Compose：个人用户一键部署，MySQL、Redis 等可选依赖通过容器化提供。
· Kubernetes：多用户 SaaS 服务，支持切换至 MySQL、Milvus 集群版。
· Serverless：按需唤醒，成本优化。

10.4 安全与隐私设计

· 数据全自托管：所有数据（含对话、记忆、向量）存储在用户指定的本地目录。
· 凭证加密：Providers/ 下的 API Key 支持通过系统密钥环或环境变量加密注入。
· 隐私模式：支持“不进入长期记忆”会话、一键数据导出与删除。

---

附录
(详细 API 参考、配置项完整模板等将在后续补充)