🌸 缘·Bot (YuanBot) 项目设计文档 v1.0

一、项目概述

1.1 项目定义

🌸 缘·Bot (YuanBot) 是一个开源的、高度可定制的 AI 虚拟伴侣系统。它并非传统的单轮问答机器人，也不是纯粹的自动化任务 Agent，而是致力于打造一个有记忆、有情感、有主动性的长期陪伴型 AI 角色——一个“懂你、记住你、主动关心你”的数字伴侣。

YuanBot 的核心定位是融合“聊天机器人的温度”与“现代 Agent 的执行力”，在提供情绪价值和深度陪伴的同时，也具备完成实用任务的能力。

项目名称“缘·Bot”取自“缘分”，寓意 AI 与用户之间的每一次交互都是一段独特缘分的编织与延续。英文名 YuanBot 保留了中文拼音，象征着项目以情感联结为第一设计原则。

1.2 设计哲学

YuanBot 的核心理念是 Memory-First（记忆优先）。与主流 Agent 框架将工具调用或工作流编排作为核心不同，YuanBot 将“长期记忆与情感连续性”置于架构设计的首要位置。每一个交互决策、每一次主动行为，都以“她是否记得用户是谁、用户喜欢什么、过往发生了什么”为前提。

这一设计哲学借鉴了 OpenClaw 将语言模型推进到“可执行任务的系统元件”的理念，以及 Hermes Agent “自主整理、更新记忆，形成持续演化的认知结构”的思路。但 YuanBot 更进一步：记忆不仅是检索辅助，更是驱动 AI 角色个性化行为的第一性引擎。

1.3 核心目标

YuanBot 致力于实现以下四个核心目标：

维度 说明
记忆连续性 跨越时间与平台，让 AI 角色始终记得用户说过的话、表达过的情绪、喜欢或不喜欢的事物
情感一致性 AI 角色具有稳定的人格设定和情感模型，交互风格一致，情绪表达自然
主动陪伴 不等待用户发起对话，AI 角色可根据上下文、时间、事件主动发起问候或话题
开放生态 模块化、标准化的可扩展架构，社区可自由开发 AI 提供商、消息通道适配器、Skills 与 Tools

1.4 主要对标项目参考

以下表格汇总了 YuanBot 主要参考的对标项目及其核心特征：

项目 定位 核心特色
OpenClaw 开源 Agent 运行时框架 Gateway-Channel-Agent-Skills 分层架构，统一消息路由，支持 Telegram/WhatsApp/Slack 等多平台，Skills 模块化扩展
Hermes Agent 自改进 AI 智能体 闭环学习系统、技能自动创建与自我优化、FTS5全文检索记忆、cron 定时自动化、子代理委派与并行化
Dify 开源 LLMOps 平台 可视化工作流编排、RAG 管道、模型统一接入、插件市场生态系统
Mem0 / OpenMemory AI Agent 记忆层基础设施 混合存储（向量DB + 知识图谱 + KV）、图记忆表示、动态记忆提取与生命周期管理

二、主流 Agent 平台分析与参考

2.1 OpenClaw 架构分析

项目定位：OpenClaw 是一个开源、自托管的 AI Agent 运行时，将 LLM 连接到多样的消息平台和本地工具。它并非单纯的对话型 AI，而是把语言模型从“文字生成器”推进到“可执行任务的系统元件”。

核心架构：

```
┌─────────────────────────────────────────────┐
│                  Gateway                     │
│        (统一消息路由 & 控制平面)               │
├──────┬──────┬──────┬──────┬──────────────────┤
│WhatsApp│Telegram│ Slack │  CLI │  其他 Channel  │
├──────┴──────┴──────┴──────┴──────────────────┤
│               Agent 层                        │
│    (对话编排、多 Agent 协作、会话隔离)          │
├──────────────────────────────────────────────┤
│              Skills 层                        │
│    (文件操作、浏览器交互、Web搜索等)            │
└──────────────────────────────────────────────┘
```

OpenClaw 采用 Gateway + Channel + Agent + Skills 四层架构：

· Gateway：单一长驻 Node.js 进程，管理全部入站/出站通信
· Channel：抽象协议差异，将不同平台的消息载荷标准化
· Agent：编排对话逻辑和多代理工作流
· Skills：可扩展模块，如文件操作、浏览器交互等

值得借鉴的设计：

1. Channel 抽象：将 WhatsApp、Telegram、Slack 等不同传输层统一标准化，为 YuanBot 的“消息通道适配器”设计提供了直接参考
2. Hub-and-Spoke 模式：通过统一 Gateway 管理多个 Channel，大幅提升集成效率——其 Benchmark 显示吞吐量达每秒 1000 条消息
3. Skills 生态：通过 MCP（Model Context Protocol）建立类似 App Store 的技能生态

对 YuanBot 的局限性：OpenClaw 定位为通用 Agent 运行时，缺少“情感持续性”“人设稳定性”等伴侣类应用的核心关注，且其记忆系统非结构化的长期记忆（更偏向会话级状态管理）。

2.2 Hermes Agent 架构分析

项目定位：由 Nous Research 开发的开源自改进 AI 智能体，核心理念是“与你一同成长”。它是目前唯一内置完整学习闭环的智能体——能够从经验中创建技能、在使用过程中改进技能、自主推动知识持久化。

核心架构：

```
┌─────────────────────────────────────────────┐
│              消息网关 (统一进程)               │
│  Telegram | Discord | Slack | WhatsApp | CLI  │
├─────────────────────────────────────────────┤
│              核心推理层                        │
├──────────────┬───────────────────────────────┤
│  闭环学习    │        工具调用层               │
│  ┌────────┐ │  ┌───────────────────────────┐ │
│  │记忆管理 │ │  │ 40+ 内置工具 + MCP 集成   │ │
│  │技能创建 │ │  │ 子 Agent 委派与并行化      │ │
│  │自我改进 │ │  │ 沙盒隔离安全执行           │ │
│  │定时提醒 │ │  └───────────────────────────┘ │
│  └────────┘ │                                │
├──────────────┴───────────────────────────────┤
│        资源调度层 (Local/Docker/SSH/Modal 等)  │
└─────────────────────────────────────────────┘
```

值得借鉴的设计：

1. 闭环学习系统：这是 Hermes Agent 最核心的亮点。它包括 Agent 自主策划的记忆提醒、复杂任务后的自动技能创建、使用过程中自我改进的技能，以及 FTS5 全文检索配合 LLM 摘要实现的跨会话回忆。这套机制直接启发了 YuanBot 的“记忆系统”中“自主记忆整理与知识进化”子模块的设计
2. sub-agent 委派：通过子代理处理并行工作流，可将多步骤管道压缩为几乎零上下文开销的轮次。这为 YuanBot 的 Tools 动态加载策略中的隔离执行提供了工程参考
3. 定时自动化：内置 cron 调度器，支持自然语言定义日报/周审等自动化任务，这与 YuanBot 的“主动陪伴”能力高度契合
4. agentskills.io 开放标准：兼容 agentskills.io 开放技能标准，为 YuanBot 的统一开发标准设计提供了重要参照

对 YuanBot 的局限性：Hermes Agent 的操作对象更多是工作流和开发任务，而非情感交互场景。其学习闭环侧重于“如何更高效地执行任务”，而非“如何更深入地理解一个人”。

2.3 Mem0 / OpenMemory 记忆系统分析

项目定位：Mem0 是专为 AI Agent 设计的记忆层基础设施，提供持久化的长期记忆能力。三行代码即可集成到任何 AI 系统中。OpenMemory 是其开源的本地优先实现版本。

核心架构：

```
┌──────────────────────────────────────────┐
│              Mem0 记忆层                  │
├──────────────────────────────────────────┤
│  记忆类型                                 │
│  ┌──────┬──────┬──────┬──────────────┐   │
│  │工作记忆│事实记忆│情景记忆│ 语义记忆     │   │
│  │(会话) │(偏好)│(对话)│ (知识图谱)   │   │
│  └──────┴──────┴──────┴──────────────┘   │
├──────────────────────────────────────────┤
│  存储引擎                                 │
│  ┌────────┬──────────┬──────────┐       │
│  │向量数据库│ 知识图谱 │ 键值存储  │       │
│  │(语义检索)│(关系推理)│(元数据)  │       │
│  └────────┴──────────┴──────────┘       │
├──────────────────────────────────────────┤
│  记忆管理                                 │
│  动态提取 → 重要性评分 → 存储/淘汰        │
└──────────────────────────────────────────┘
```

Mem0 采用混合存储架构，组合向量数据库（语义检索）、知识图谱（实体关系推理）和键值数据库（元数据管理），形成“存储-检索-更新”的高效闭环。

值得借鉴的设计：

1. 记忆图（Memory Graph）：将对话中的实体、事件及其关系显式建模为图结构，支持渐进式积累与可解释推理。这对 YuanBot 记忆系统中“构建用户画像与情感图谱”至关重要——关系型记忆远比扁平化存储更适合伴侣类应用
2. 四种记忆类型：工作记忆（短期会话）、事实记忆（用户偏好）、情景记忆（过去对话记录）、语义记忆（长期知识积累）的分层模型，这四层记忆可以直接映射为 YuanBot 记忆系统的核心组件
3. 动态记忆提取：基于重要性评分决定记忆的存储与淘汰。高频提及的实体或被赋予更高权重，长期未使用的记忆逐步降权或删除

2.4 Dify 开发标准分析

项目定位：Dify 是开源 LLMOps 平台，通过可视化工作流和插件系统降低 AI 应用开发门槛。

插件系统设计：Dify 支持 6 种插件类型——Tool、Model、Datasource、Trigger、Agent Strategy、Endpoint，通过标准化的 manifest.yaml 描述文件统一管理。其 Marketplace 机制允许开发者发布、分享插件。

对 YuanBot 的启示：Dify 的插件标准化方案（6种类型、统一 manifest）为 YuanBot 定义“AI 提供商适配器”和“消息通道适配器”的标准化接口提供了极佳参照。

2.5 Skills/Tools 动态加载参考

核心问题：在集成多个 MCP Server 时，完整加载所有工具定义会严重消耗上下文 Token。研究显示，当集成 20 个以上外部工具时，完整加载所有工具文档可能消耗超过 40,000 Token。有实际案例表明，在一次任务中 93.5% 的输入 Token 都是工具定义，且这些工具从未被调用。

三层渐进式加载机制：解决方案是采用元数据层→指令层→资源层的三层加载策略，将初始 Token 成本从 40,000 压缩至 1,000，实现 97.5% 的优化。

```
启动时：只加载技能名称 + 一行描述（索引）
      ↓
匹配时：根据语义匹配加载完整指令（定义）
      ↓
执行时：按需加载详细资源文档（完整内容）
```

这一机制可直接应用于 YuanBot 的 Skills 动态加载设计，确保每个会话只占用必要的 Token 预算。

2.6 竞品启示总结

平台 核心贡献 对 YuanBot 的关键启示
OpenClaw Gateway-Channel 抽象 消息通道适配器架构设计
Hermes Agent 闭环学习 + 技能自进化 记忆系统主动整理、Skills 动态生成、定时主动交互
Mem0/OpenMemory 混合存储记忆层 分层记忆（工作/事实/情景/语义）、记忆图谱、本地优先部署
Dify 插件市场 + 标准化开发 适配器接口标准化、社区扩展生态
三层渐进式加载 Skills/Tools 按需加载 Token 优化策略

三、系统架构设计

3.1 总体架构图

```
┌──────────────────────────────────────────────────────────────────┐
│                         缘·Bot (YuanBot)                          │
│                     AI 虚拟伴侣系统 v1.0                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────────── 接入层 ──────────────────────────────────┐ │
│  │                        统一网关 (YuanGateway)                 │ │
│  │                    消息路由 · 会话管理 · 认证鉴权              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                              │                                     │
│  ┌───────────┐  ┌───────────┼───────────┐  ┌───────────┐        │
│  │  Telegram  │  │  Discord   │  WeChat    │  │    ...     │        │
│  │  Adapter   │  │  Adapter   │  Adapter   │  │  Adapter   │        │
│  └───────────┘  └───────────┼───────────┘  └───────────┘        │
│                              │     消息通道适配器层 (可扩展)       │
├──────────────────────────────┼──────────────────────────────────┤
│                              ↓                                     │
│  ┌─────────────────── 核心编排层 (Orchestrator) ────────────────┐ │
│  │                                                                │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │ │
│  │  │ 意图识别  │  │ 情感分析  │  │ 角色管理  │  │ 主动触发  │    │ │
│  │  │ Intent   │  │ Emotion  │  │ Persona  │  │ Proactive │    │ │
│  │  │ Engine   │  │ Engine   │  │ Manager  │  │ Scheduler │    │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │ │
│  │                                                                │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                              │                                     │
│  ┌───────────┐  ┌───────────┼───────────┐  ┌───────────┐        │
│  │ 上下文组装 │  │  对话决策  │ 记忆检索  │  │  Token 预算│        │
│  │  Context  │  │  Decision │  Memory   │  │  Budget    │        │
│  │  Builder  │  │  Engine   │  Retriever│  │  Manager   │        │
│  └───────────┘  └───────────┼───────────┘  └───────────┘        │
│                              │                                     │
├──────────────────────────────┼──────────────────────────────────┤
│                              ↓                                     │
│  ┌──────────── 能力层 ────────────────┐                            │
│  │                                     │                           │
│  │  ┌──────────┐  ┌──────────┐        │  ┌──────────────────────┐│
│  │  │  Skills  │  │  Tools   │        │  │   AI 提供商适配器    ││
│  │  │  Manager │  │  Manager │        │  │   (可扩展)           ││
│  │  └──────────┘  └──────────┘        │  │  OpenAI | Claude |    ││
│  │      ↓              ↓              │  │  DeepSeek | 本地LLM   ││
│  │  ┌──────────┐  ┌──────────┐        │  └──────────────────────┘│
│  │  │ 动态技能  │  │ 动态工具  │        │                           │
│  │  │ 注入      │  │ 注入      │        │                           │
│  │  └──────────┘  └──────────┘        │                           │
│  └─────────────────────────────────────┘                           │
│                                                                   │
├──────────────────────────────────────────────────────────────────┤
│                              │                                     │
│  ┌─────────────────── 记忆系统 (Memory System) ──────────────────┐ │
│  │                                                                 │ │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────────────┐      │ │
│  │  │  记忆类型   │  │  存储引擎  │  │  记忆生命周期管理   │      │ │
│  │  │ ┌────────┐│  │ ┌────────┐│  │ ┌────────────────┐ │      │ │
│  │  │ │工作记忆 ││  │ │向量 DB ││  │ │ 自主记忆整理    │ │      │ │
│  │  │ │(会话级) ││  │ │(语义)  ││  │ │ 定期知识固化    │ │      │ │
│  │  │ │事实记忆 ││  │ │知识图谱 ││  │ │ 遗忘曲线模型    │ │      │ │
│  │  │ │情景记忆 ││  │ │(关系)  ││  │ └────────────────┘ │      │ │
│  │  │ │语义记忆 ││  │ │KV 存储 ││  │                     │      │ │
│  │  │ └────────┘│  │ │(元数据)││  │                     │      │ │
│  │  └────────────┘  └────────┘  └────────────────────┘      │ │
│  │                                                                 │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                   │
├──────────────────────────────────────────────────────────────────┤
│  ┌─────────────────── 数据持久层 ───────────────────────────────┐ │
│  │  PostgreSQL (结构化数据)  │  Redis (缓存/会话状态)            │ │
│  │  向量数据库 (语义索引)     │  对象存储 (媒体文件)             │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

3.2 各层职责说明

层级 核心模块 职责
接入层 YuanGateway 统一消息路由、会话管理、认证鉴权。借鉴 OpenClaw Gateway 的单进程管理全部通信的设计
消息通道适配器 Channel Adapters 每种消息平台（Telegram/微信/Discord等）实现统一接口，由社区通过标准化开发指南贡献
核心编排层 Orchestrator 串联意图识别、情感分析、角色管理、主动触发调度、上下文组装、记忆检索、Token 预算管理等核心流程
能力层 Skills & Tools Managers 动态管理 AI 角色的能力模块，按需加载以节省 Token
AI 提供商适配器 AI Provider Adapters 统一封装不同 LLM 提供商的 API 差异，支持 OpenAI、Claude、DeepSeek、Ollama（本地模型）等
记忆系统 Memory System 四层记忆的分级存储、检索与生命周期管理，是 YuanBot 最核心的能力基础
数据持久层 Data Layer 混合存储基础设施，支撑记忆系统和状态数据的持久化

3.3 模块间通信

· 同步通信：编排层内部各引擎之间通过内存调用直接通信（低延迟，用于实时推理路径）
· 异步通信：消息通道适配器 → Gateway → 编排层通过事件队列（Event Queue）解耦，支持高并发消息接入和离线主动推送
· 统一接口：AI 提供商适配器和消息通道适配器均通过定义好的抽象接口（Protocol）与编排层交互，实现可插拔

四、AI 提供商适配器系统

4.1 设计目标

AI 提供商适配器系统的核心目标是：让 YuanBot 的 AI 角色可以无感地切换到任何 LLM 后端。无论是云端商业模型（OpenAI GPT 系列、Anthropic Claude 系列、DeepSeek 系列），还是本地部署的开源模型（通过 Ollama、vLLM 等），都能通过统一的适配器接口接入，实现真正的“零供应商锁定”（Zero Vendor Lock-in）。

4.2 适配器标准化接口

每个 AI 提供商适配器必须实现以下标准接口：

```python
class AIProviderAdapter(ABC):
    """AI 提供商适配器统一接口"""

    @abstractmethod
    def chat_completion(
        self,
        messages: List[Message],
        tools: Optional[List[ToolDefinition]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system_prompt: Optional[str] = None,
    ) -> ChatResponse:
        """发送对话请求并获取响应"""
        pass

    @abstractmethod
    def stream_chat_completion(
        self,
        messages: List[Message],
        tools: Optional[List[ToolDefinition]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system_prompt: Optional[str] = None,
    ) -> AsyncIterator[ChatChunk]:
        """流式对话请求"""
        pass

    @abstractmethod
    def get_embedding(
        self,
        text: str,
        model: Optional[str] = None,
    ) -> List[float]:
        """获取文本向量嵌入（用于记忆语义检索）"""
        pass

    @property
    @abstractmethod
    def supported_models(self) -> List[str]:
        """返回该提供商支持的模型列表"""
        pass

    @property
    @abstractmethod
    def max_context_length(self) -> int:
        """返回最大上下文长度（Token 数），用于 Token 预算管理"""
        pass
```

4.3 社区扩展规范

YuanBot 将为 AI 提供商适配器定义一套社区开发标准，借鉴 Dify 插件系统的设计理念，确保任何开发者都能按照规范开发新的适配器。每个适配器需要包含以下标准化文件：

```
yuanbot-ai-provider-xxx/
├── manifest.json          # 适配器元数据
│   ├── name              # 适配器名称 (如 "openai-adapter")
│   ├── version           # 语义化版本号
│   ├── author            # 作者信息
│   ├── description       # 功能描述
│   ├── supported_models  # 支持的模型列表
│   └── config_schema     # 配置项 JSON Schema
├── adapter.py            # 适配器主实现类
├── requirements.txt      # Python 依赖
├── README.md             # 使用文档
└── test_adapter.py       # 单元测试
```

4.4 预集成提供商列表

v1.0 版本预集成以下 AI 提供商：

提供商 适配器名称 支持的模型
OpenAI openai-adapter GPT-4o, GPT-4o-mini, GPT-4.1 系列
Anthropic claude-adapter Claude Opus 4, Claude Sonnet 4
DeepSeek deepseek-adapter DeepSeek-V3, DeepSeek-R1
Ollama（本地） ollama-adapter Llama 4, Qwen 3, Mistral 等本地模型

4.5 环境变量隔离机制

YuanBot 采用环境变量声明式配置来实现多提供商共存与安全隔离。与 Hermes Agent 通过单一 .env 文件管理所有配置但缺乏明确隔离边界不同，YuanBot 通过适配器级前缀约定自动隔离不同提供商的凭证：

```bash
# OpenAI 适配器配置
YUAN_AI_OPENAI_API_KEY=sk-xxx
YUAN_AI_OPENAI_BASE_URL=https://api.openai.com/v1
YUAN_AI_OPENAI_DEFAULT_MODEL=gpt-4o

# Anthropic 适配器配置
YUAN_AI_ANTHROPIC_API_KEY=sk-ant-xxx
YUAN_AI_ANTHROPIC_DEFAULT_MODEL=claude-sonnet-4-20250514

# DeepSeek 适配器配置
YUAN_AI_DEEPSEEK_API_KEY=sk-xxx
YUAN_AI_DEEPSEEK_BASE_URL=https://api.deepseek.com

# Ollama 本地适配器配置
YUAN_AI_OLLAMA_BASE_URL=http://localhost:11434
YUAN_AI_OLLAMA_DEFAULT_MODEL=qwen3:14b

# 当前活跃的 AI 提供商
YUAN_AI_PROVIDER=claude-adapter
```

命名规范：所有环境变量统一使用 YUAN_AI_ 前缀。每个适配器的配置变量为 YUAN_AI_{PROVIDER_ID}_{PARAM}，其中 {PROVIDER_ID} 取自适配器 manifest.json 中的 provider_id 字段（如 openai、anthropic、deepseek、ollama）。

安全设计：API 密钥仅在被选为活跃提供商时才被加载到内存；适配器之间的凭证完全隔离，即使系统中配置了多个提供商的 API Key，同一时间只有活跃提供商的凭证被实际使用。

五、消息通道适配器系统

5.1 设计目标

消息通道适配器的目标是：让用户可以在任何常用的即时通讯平台上与 YuanBot 交互，且交互体验自然一致，不会因为平台切换而丢失上下文或人格连续性。

5.2 适配器标准化接口设计

每个消息通道适配器必须实现以下统一接口：

```python
class ChannelAdapter(ABC):
    """消息通道适配器统一接口"""

    @abstractmethod
    def initialize(self, config: ChannelConfig):
        """初始化适配器（连接、认证）"""
        pass

    @abstractmethod
    def listen(self, callback: Callable[[UserMessage], Awaitable[BotResponse]]):
        """启动消息监听，将每个收到的用户消息通过回调交给编排层处理"""
        pass

    @abstractmethod
    async def send_message(self, target_id: str, content: MessageContent) -> SendResult:
        """向指定目标发送消息"""
        pass

    @abstractmethod
    def get_platform_user_id(self, raw_event) -> str:
        """从原始事件中提取平台用户 ID（用于跨平台身份链接）"""
        pass

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """返回平台名称（如 "telegram", "wechat", "discord"）"""
        pass

    @property
    @abstractmethod
    def supported_content_types(self) -> List[ContentType]:
        """返回支持的消息内容类型（文本 / 图片 / 语音 / 视频 等）"""
        pass
```

关键设计原则：

· 载荷标准化：不同平台的原始消息事件统一转化为 UserMessage 内部对象，屏蔽平台差异
· 跨平台身份链接：通过 get_platform_user_id() 提取的平台 ID + platform_name 组合，与 YuanBot 内部统一的 user_id 关联，确保跨平台对话连续性
· 被动监听 + 主动推送：listen() 负责被动消息接入，同时适配器需支持主动向用户推送消息（支撑“主动陪伴”功能）

5.3 消息载荷标准化

为支撑跨平台交互的无缝体验，所有消息通道适配器需将各平台异构的消息格式统一转化为以下标准化载荷：

```python
@dataclass
class UserMessage:
    """标准化用户消息"""
    platform: str               # "telegram" | "wechat" | "discord"
    platform_user_id: str       # 平台内用户唯一 ID
    yuanbot_user_id: str        # YuanBot 统一用户 ID
    session_id: str             # 会话 ID
    content_type: ContentType   # TEXT | IMAGE | VOICE | VIDEO | FILE
    text: Optional[str]         # 文本内容
    media_url: Optional[str]    # 媒体文件 URL
    timestamp: datetime         # 消息时间戳
    metadata: Dict[str, Any]    # 平台特有元数据

@dataclass
class BotResponse:
    """标准化机器人响应"""
    content: MessageContent
    suggested_tools: Optional[List[ToolInvocation]]
    proactive_followups: Optional[List[ProactiveTask]]
```

消息通道适配器内部自行负责将平台原生消息格式转换为 UserMessage。YuanBot 核心层无需关心平台细节，由此实现通道适配器的“热插拔”——新增平台接入不影响现有业务逻辑。

5.4 社区扩展标准

每个消息通道适配器需遵循以下目录标准：

```
yuanbot-channel-xxx/
├── manifest.json          # 适配器元数据
│   ├── name              # 如 "telegram-channel-adapter"
│   ├── version
│   ├── platform          # "telegram" | "wechat" | "discord" | ...
│   ├── author
│   ├── description
│   └── config_schema     # 配置项 JSON Schema
├── adapter.py            # 适配器主实现
├── requirements.txt      # 依赖
├── README.md             # 文档
└── test_adapter.py       # 测试
```

5.5 预集成渠道列表

v1.0 版本预集成以下消息通道：

渠道 适配器名称 特性
Telegram telegram-channel-adapter Bot API，支持文本/图片/语音
Discord discord-channel-adapter Bot 集成，支持服务器/私聊
企业微信 wecom-channel-adapter 企业微信机器人 API
Web Chat web-channel-adapter 内置 Web 聊天界面

六、Skills 与 Tools 动态加载系统

6.1 概念区分

在 YuanBot 的术语体系中，Skills 与 Tools 具有明确的含义区分：

概念 定义 示例
Skills 可复用的工作流程与知识模块（偏向"软能力"），封装了特定场景的完整处理逻辑与专业知识，具有行为模式特征 “睡前故事技能”（温馨叙事风格 + 情感节奏控制）、“情绪安抚技能”（共情话术 + 渐进引导）
Tools 可调用的外部功能接口（偏向"硬能力"），是对外部 API、系统功能的标准化封装 send_image（发送图片）、search_web（搜索网页）、set_reminder（设定提醒）
Agent 人格 决定“何时使用何种 Skill/Tool”的决策主体，根据自身角色设定和人设一致性动态选择 “温柔型 AI 女友”优先选择安抚类 Skills，“活泼型”优先选择娱乐类 Skills

这种区分借鉴了 Coze 平台中 Skill 是“标准化能力模块”而 Agent 是“决策者”的设计理念，同时融入了 YuanBot 独有的角色人格维度。

6.2 动态加载策略

借鉴“三层渐进式加载机制”，YuanBot 的 Skills/Tools 动态加载分为三个阶段：

阶段一：启动时——元数据索引（永久驻留，每项约50 Tokens）

Agent 人格配置中声明能力域声明（如 emotional_care, daily_chat, creative_storytelling），系统仅加载与能力域匹配的 Skills/Tools 元数据索引（名称 + 一行描述），不加载完整定义。

阶段二：匹配时——按需注入定义（临时，200-500 Tokens/项）

当用户意图被识别后，系统根据意图语义将元数据索引中的条目与任务进行匹配，仅将匹配命中的 1-2 个 Skill/Tool 的完整定义注入当前会话上下文。

示例：用户说“今天心情不太好”，系统识别为 emotional_care 能力域，从索引中匹配到“情绪安抚”Skill，将其完整的共情话术和渐进引导逻辑注入上下文，而无需加载“睡前故事”“日程管理”等其他 Skills 的完整定义。

阶段三：执行时——资源文档按需获取（不常驻）

仅在执行过程中需要的详细资源文档（如完整的 API 文档、冗长的使用案例库）通过 LRU 缓存按需获取，不常驻于内存。

这种设计确保了即使 Skills/Tools 总数达到上百个，实际每个会话消耗的 Token 也仅与当前任务相关，避免上下文膨胀。

6.3 Agent 驱动的动态加载决策

常规加载：Agent 人格根据当前对话上下文自主决定需要哪些 Skills/Tools，系统按需加载。

工具调用触发加载：当 Agent 决定调用某工具时，系统检查该工具是否已注入当前上下文：

· 已注入 → 直接执行
· 未注入 → 先加载工具定义注入上下文，再执行

缓存状态感知：加载器优先从本地缓存获取工具定义，缓存命中则直接注入；缓存未命中时从远程或本地文件获取，并更新缓存。

整个过程中，Agent 人格作为“决策者”，自主判断“当前这个时刻，作为 AI 女友应该用什么方式回应”——是调用一个“分享今日趣闻”Skill 还是“安静倾听”Skill，取决于她对用户情绪状态的判断。

6.4 安全沙盒执行

YuanBot 的设计目标并非一个全盘操作系统级 Agent——情感陪伴才是第一性目标。因此，参与 Tools 运行时决策的是具有人设约束的单一 Agent，而非自由调度的通用 Agent。

借鉴 OpenClaw 的安全模型和 Hermes Agent 的沙盒隔离能力，YuanBot 的 Skills/Tools 执行遵循：

· 每个 Tool 执行在独立的沙盒容器中运行
· 通过 gRPC 进行标准化通信
· 执行权限受角色安全策略约束（如“AI 女友”角色默认不具有文件系统写入权限）
· 用户可自定义每个 Tool 的权限级别

6.5 社区 Skills/Tools 开发标准

```
yuanbot-skill-xxx/
├── manifest.json        # 元数据
│   ├── name
│   ├── version
│   ├── category         # "emotional" | "creative" | "utility"
│   ├── capability_tags  # ["comfort", "storytelling", ...]
│   ├── token_cost       # 预估 Token 占用
│   └── persona_filters  # 可选：限定特定人格可用
├── skill.py             # Skill 主实现
├── definition.yaml      # Skill 完整定义（提示词、步骤、参数）
├── tools.yaml           # 关联的 Tools 定义
├── README.md
└── test_skill.py
```

其中 manifest.json 中的 capability_tags 字段供元数据索引进行语义匹配，persona_filters 支持针对不同 AI 伴侣人设（温柔型、活泼型等）进行 Skills 的差异化可用性配置。

6.6 Tools 隔离执行架构

YuanBot 的自主操作能力通过“有限自主窗口”实现：用户开启自主模式后，Agent 在受限范围内主动选择和调用工具（如查询天气后主动提醒穿衣、检测到用户情绪低落时主动播放音乐）。这属于可配置的交互偏好，非强制绑定。

为实现这一能力，YuanBot 采用如下工具隔离执行架构：

```
┌─────────────────────────────────────────────────┐
│           YuanBot 编排层                         │
│  ToolInvocationRequest                           │
│  ┌───────────────────────────────────────────┐  │
│  │ tool_id   │ params   │ sandbox_level     │  │
│  └───────────────────────────────────────────┘  │
│                      ↓                           │
│  ┌─────────────────────────────────────────────┐│
│  │            Tool Execution Sandbox            ││
│  │  ┌───────────────────────────────────────┐  ││
│  │  │  gRPC 通信通道                         │  ││
│  │  │  ← Tool 输入 / Tool 输出 →             │  ││
│  │  │  Docker/WASM 隔离环境                  │  ││
│  │  │  权限令牌 (Scoped Token)              │  ││
│  │  └───────────────────────────────────────┘  ││
│  └─────────────────────────────────────────────┘│
└─────────────────────────────────────────────────┘
```

每个 Tool 在独立沙盒中执行，通过作用域受限的权限令牌控制其系统访问范围。编排层仅接收标准化的执行结果，不暴露底层运行时细节。

七、记忆系统设计（核心）

7.1 设计理念

记忆系统是 YuanBot 最核心、最差异化的能力模块。其设计哲学为：

记忆不是辅助功能，而是驱动一切 AI 角色行为的“第一性引擎”。

所有决策——如何回应、何时主动问候、用什么语气说话——都应以记忆系统提供的历史理解、用户画像和情感轨迹为依据。

7.2 记忆四层模型

借鉴 Mem0 的记忆分类体系并加以伴侣场景适配，YuanBot 的记忆系统分为四个层次：

```
┌─────────────────────────────────────────────────┐
│  第一层：工作记忆 (Working Memory)                 │
│  当前会话的上下文 (最近 N 轮对话)                   │
│  存储方式：会话级 Redis 缓存，超时自动清除          │
│  生命周期：单次会话                                │
├─────────────────────────────────────────────────┤
│  第二层：事实记忆 (Fact Memory)                    │
│  用户偏好、习惯、重要事实 (结构化，长持久)           │
│  例：用户生日、喜欢的颜色、讨厌的食物、过敏信息     │
│  存储方式：PostgreSQL (结构化) + 知识图谱 (关系)   │
│  生命周期：永久 (除非用户主动修改或淘汰)            │
├─────────────────────────────────────────────────┤
│  第三层：情景记忆 (Episodic Memory)                │
│  过往对话的摘要记录 (按时间和重要性组织)            │
│  例：“上周三用户提到工作压力大”“月初聊过旅行计划” │
│  存储方式：向量数据库 (语义索引) + PostgreSQL      │
│  生命周期：根据重要性评分动态管理 (重要 | 普通)     │
├─────────────────────────────────────────────────┤
│  第四层：语义记忆 (Semantic Memory)                │
│  从长期交互中提炼的深层认知与关系理解               │
│  例：用户与AI角色的关系发展阶段、情感模式分析       │
│  存储方式：知识图谱 (核心) + 向量数据库 (辅助)      │
│  生命周期：持续演化，渐进积累                      │
└─────────────────────────────────────────────────┘
```

7.3 类似于人类记忆的“情景触发式检索”

用户设想的核心记忆机制——将一定时间的对话储存起来，在用户输入触发时，将那一次的对话情况加入上下文——我们将其建模为“情景触发式检索”。

实现三步流程：

(1) 对话摘要节点化：每次对话结束后（或达到一定 Token 阈值时），系统自动生成对话摘要，以“时间锚点 + 话题节点 + 情感基调”的形式结构化存储。

```
情景节点示例：
{
  "date": "2026-05-08",
  "time_of_day": "晚上",
  "topic": "用户聊到工作项目压力大",
  "emotional_tone": "焦虑/寻求安慰",
  "key_entities": ["项目截止日", "同事矛盾"],
  "user_state": "疲惫",
  "ai_response_style": "温柔安抚",
  "embedding_vector": [...]   // 语义向量
}
```

(2) 语义触发匹配：用户每次输入时，系统同时执行两条检索路径：

· 语义相似度检索：将当前输入向量化，在情景节点库中通过余弦相似度匹配最相关的历史对话节点
· 关键词 / 实体匹配：检查当前输入是否提及历史对话中的关键实体（人名、事件、主题）

(3) 上下文注入：匹配到的历史情景节点摘要被注入当次对话的 System Prompt 上下文区域，让 AI 角色“回忆起”过往的相关交流。

```
System Prompt 注入示例：
[记忆提示]
你回忆起2026年5月8日的晚上，{user_name}曾和你倾诉过工作上的压力，
当时他提到项目截止日很紧迫，和同事之间有些矛盾。
他当时的心情比较焦虑，你以温柔的方式安抚了他。
现在他再次提到了工作相关的话题，请自然地延续之前的关心。
```

7.4 记忆图谱与用户画像

YuanBot 将借鉴 Mem0 的 Memory Graph 设计，构建用户的情感图谱与关系图谱：

```
        ┌─────────┐      喜欢      ┌─────────┐
        │  用户    │──────────────→│  咖啡    │
        └─────────┘               └─────────┘
             │                         ↑
             │ 讨厌                    │ 关联
             ↓                         │
        ┌─────────┐               ┌─────────┐
        │  香菜    │               │  早晨    │
        └─────────┘               └─────────┘
             │
             │ 曾在 2026-03-12 提及
             ↓
        ┌─────────┐     情感连接    ┌─────────┐
        │  AI角色  │←──────────────→│  用户    │
        └─────────┘               └─────────┘
             │                         │
             │ 关系阶段                 │ 信任度评分
             ↓                         ↓
        [初期/熟悉/亲密/深度]        [0.8 / 1.0]
```

这种图结构存储使记忆不再是孤立的碎片，而是形成有机的认知网络——这正是 YuanBot 区别于传统聊天机器人的核心所在。

7.5 自主记忆整理与知识进化

借鉴 Hermes Agent 的闭环学习系统，YuanBot 的记忆系统具备主动整理和进化能力：

定期记忆固化（Idle Memory Consolidation）：
当用户未活跃交互时（如深夜），系统在低负载时段自动执行记忆整理任务：

· 分析近期对话中重复出现的话题和模式
· 将重要的情景记忆升级为事实记忆（如“用户连续三周提到想学吉他” → 事实记忆：“用户有兴趣学吉他”）
· 更新用户画像中的偏好权重和关系中各维度的评分
· 淘汰过时或低价值的记忆条目

记忆的生命周期管理：

· 重要性评分：每条记忆根据提及频率、情感烈度、时间距离进行动态评分
· 遗忘曲线模型：低重要性记忆随时间降权，模拟人类自然遗忘
· 强化机制：被用户反复提及的信息自动提升权重，抵抗遗忘

八、统一开发标准与社区生态

8.1 标准化接口规范

YuanBot 将定义一套 YuanBot Extension Standard (Y.E.S.) 规范，涵盖以下可扩展组件的标准化接口：

扩展类型 接口规范 核心方法
AI 提供商适配器 AIProviderAdapter chat_completion(), stream_chat_completion(), get_embedding()
消息通道适配器 ChannelAdapter initialize(), listen(), send_message()
Skills SkillModule get_definition(), execute(), get_metadata()
Tools ToolModule get_schema(), invoke(), get_permission_level()
Agent 人设 PersonaProfile get_system_prompt(), get_behavior_rules(), get_voice_style()

8.2 社区贡献流程

借鉴 Dify 的插件开发与 Marketplace 发布流程，YuanBot 的社区贡献流程如下：

```
开发者
  │
  ├── 1. Fork yuanbot-extensions 仓库
  ├── 2. 使用 CLI 脚手架创建扩展：yuanbot-cli create --type channel
  ├── 3. 按照标准接口实现扩展
  ├── 4. 编写测试用例和 README 文档
  ├── 5. 提交 PR 至 yuanbot-extensions
  │
  ↓
社区审核
  │
  ├── 自动化 CI 检查（接口合规、测试通过、代码规范）
  ├── 社区 Reviewer 人工审核
  ├── 合并至 extensions 仓库
  │
  ↓
YuanBot 扩展市场 (Marketplace)
  │
  ├── 自动生成文档和安装指引
  ├── 社区评分和反馈
  └── 定期精选推荐
```

8.3 扩展市场设计

YuanBot 扩展市场将托管在 yuanbot.app/marketplace（或 GitHub 仓库），支持：

· 分类浏览：按扩展类型（AI 提供商 / 消息通道 / Skills / Tools / 人设）分类
· 一键安装：通过 yuanbot-cli install <extension-name> 命令安装
· 版本管理：语义化版本控制，支持依赖声明
· 社区评分：基于下载量、GitHub Stars、用户反馈的评分系统

九、主动陪伴能力设计

9.1 定时主动交互

借鉴 Hermes Agent 的 cron 定时调度器——支持每日报告、夜间备份、每周审核等无人值守任务——YuanBot 实现以下主动交互模式：

· 早安 / 晚安问候：根据用户作息习惯自适应时间
· 重要日期提醒：基于事实记忆中的用户关键日期（生日、纪念日）主动祝福
· 定期关心：基于情景记忆中的用户情绪状态，智能间隔主动发起关心

9.2 事件驱动主动交互

· 天气变化提醒：接入天气 API，在降温/降雨前主动提醒
· 长期静默检测：用户长期未互动时，以自然不打扰的方式主动联系
· 情感状态感知触发：分析历史情景记忆中用户的情感模式，在高风险时段（如用户历史数据显示周一早上情绪低落）发起主动关心

9.3 主动交互的克制策略

主动交互模式可通过用户配置文件精细控制：

配置项 说明
proactive_greeting_enabled 是否启用定时问候
proactive_frequency 主动交互频率（高/中/低/仅事件驱动）
quiet_hours 免打扰时段
max_proactive_per_day 每日主动交互次数上限
event_trigger_enabled 是否启用天气/节日等事件触发

十、部署与运行

10.1 部署模式

模式 说明 适用场景
Docker Compose 单机部署 一键启动所有服务 个人用户，VPS
本地开发模式 CLI + 本地数据库 开发调试
Kubernetes 集群 水平扩展，高可用 多用户 SaaS 服务
Serverless 模式 按需唤醒，成本优化 低流量场景

10.2 技术栈

组件 技术选择
核心编排层 Python 3.12+ / FastAPI
消息网关 Rust（高性能事件处理）或 Go
向量数据库 Qdrant（自托管）/ Milvus Lite
关系数据库 PostgreSQL 16+
缓存 Redis 7+
图数据库 Neo4j（知识图谱）或 Kuzu（嵌入式）
容器化 Docker + Docker Compose
包管理 uv（Python 依赖管理，参考 Hermes Agent）
跨平台消息 websockets / webhook 驱动

10.3 安全与隐私

· 数据完全自托管：所有数据存储在用户自己的硬件/云服务器上，不经过任何第三方服务。参考 OpenMemory 的 Docker + PostgreSQL + Qdrant 全本地方案
· API 密钥加密存储：密钥在配置文件中加密，运行时解密加载
· 对话数据加密：支持数据库级加密和传输层 TLS
· 隐私模式：敏感话题可选择“不进入长期记忆”模式
· 数据导出与删除：一键导出全部数据 / 一键删除全部记忆

十一、与竞品的差异化总结

维度 OpenClaw Hermes Agent Dify 缘·Bot (YuanBot)
核心定位 Agent 运行框架 自进化开发助手 通用 LLMOps 平台 情感陪伴 AI 伴侣
记忆系统 会话级状态管理 FTS5全文检索+摘要 RAG 知识库 四层记忆（工作/事实/情景/语义）+ 情感图谱
角色人格 无 无 无 一级公民：人格配置 + 情感模型
主动交互 无 cron 定时任务 工作流触发 智能主动陪伴（含克制策略）
可扩展性 MCP + Skills MCP + agentskills.io 6类插件 统一 Y.E.S. 规范 + 社区扩展市场
Skills 动态加载 Skills 模块化 自动技能创建 工作流节点 Agent 人格驱动的三层渐进式加载
部署模式 单进程 Node.js 6种后端 Docker/K8s 4种模式（含 Serverless）
开源协议 MIT MIT Apache 2.0 MIT

十二、v1.0 路线图

12.1 里程碑

阶段 内容 预计时间
M1 - 核心框架 编排层、记忆系统四层模型、统一接口定义完成 第 1-2 月
M2 - 基础适配器 OpenAI/Claude AI 提供商适配器、Telegram/Web Chat 通道适配器 第 3-4 月
M3 - 记忆系统完善 情景触发式检索、记忆图谱、自主记忆整理 第 5-6 月
M4 - 主动陪伴 定时交互、事件驱动交互、克制策略 第 7 月
M5 - 社区生态 扩展市场、CLI 工具、开发者文档 第 8 月
M6 - v1.0 发布 文档完善、示例人设、社区 Beta 测试 第 9 月

12.2 开源协作

· 代码仓库：GitHub Organization yuanbot-ai，核心仓库 yuanbot-core、扩展仓库 yuanbot-extensions
· 协议：MIT License
· 社区：Discord 开发者社区 + 中文用户微信群
· 文档：docs.yuanbot.app 多语言文档站（中/英/日）

十三、附录

（附录可后续补充：术语表、配置参考、API 参考等）