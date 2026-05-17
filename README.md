# 🌸 缘·Bot (YuanBot) v1.0.0

AI 虚拟伴侣系统 — 一个有记忆、有情感、有主动性的长期陪伴型 AI 角色。

## 核心特性

- **记忆优先 (Memory-First)** — 四层记忆模型（工作/事实/情景/语义），跨时间跨平台记住用户的一切
- **情感一致** — 完整的情感追踪系统，规则引擎 + 模式识别，交互风格和情绪表达自然一致
- **主动陪伴** — 定时触发 + 事件驱动，根据用户状态和上下文主动发起关怀
- **零供应商锁定** — 统一的 AI 提供商适配接口，支持 OpenAI / Anthropic / DeepSeek / Ollama
- **平台无关** — 消息通道适配器架构，Telegram / Discord / 企业微信 / WebSocket 即插即用
- **开放生态** — 模块化可扩展架构，Skills/Tools 三层渐进式动态加载

## 快速开始

### 安装

```bash
# 克隆项目
git clone https://github.com/yuanbot-ai/yuanbot-core.git
cd yuanbot-core

# 安装依赖
pip install -e ".[all-providers]"

# 或仅安装核心依赖
pip install -e .
```

### 初始化配置

```bash
yuanbot init -o yuanbot.yaml
```

编辑 `yuanbot.yaml`，填入你的 API Key 和通道配置。

### 启动服务

```bash
# 使用配置文件启动
yuanbot serve -c yuanbot.yaml

# 或指定端口
yuanbot serve -c yuanbot.yaml -p 8080
```

### 环境变量

```bash
# AI 提供商
export YUAN_AI_PROVIDER=openai
export YUAN_AI_OPENAI_API_KEY=sk-xxx
export YUAN_AI_OPENAI_DEFAULT_MODEL=gpt-4o

# 调试模式
export YUAN_DEBUG=true
```

## 项目结构

```
yuanbot/
├── src/yuanbot/
│   ├── core/               # 核心类型定义与抽象接口
│   │   ├── types.py        #   数据类型（消息、记忆、情感、工具）
│   │   └── interfaces.py   #   抽象基类（AIProvider、Channel、Skill、Tool、Persona）
│   ├── gateway/            # 接入与通信系统
│   │   ├── gateway.py      #   统一网关（YuanGateway）
│   │   ├── adapter_manager.py  # 适配器管理器
│   │   ├── identity_service.py # 身份链接服务
│   │   └── push_dispatcher.py  # 主动推送调度器
│   ├── persona/            # 人格与行为决策系统
│   │   ├── default.py      #   默认人设（小缘）
│   │   └── engines/        #   决策引擎模块
│   │       ├── intent_engine.py      # 意图识别引擎
│   │       ├── emotion_engine.py     # 情感分析引擎
│   │       ├── dialogue_decision.py  # 对话决策引擎
│   │       ├── context_builder.py    # 上下文组装器
│   │       └── token_budget.py       # Token 预算管理器
│   ├── memory/             # 记忆与情感系统
│   │   ├── manager.py      #   四层记忆管理器
│   │   └── emotion_tracker.py  # 情感追踪系统
│   ├── providers/          # AI 提供商适配系统
│   │   ├── registry.py     #   适配器注册表
│   │   └── manager.py      #   提供商管理器（模型列表式配置）
│   ├── proactive/          # 主动陪伴与自动化系统
│   │   ├── scheduler.py    #   定时任务调度器
│   │   ├── event_engine.py #   事件监听引擎
│   │   └── strategy.py     #   克制策略决策器
│   ├── infrastructure/     # 基础架构与部署系统
│   │   ├── config_loader.py    # 统一配置加载器
│   │   └── database.py         # 数据库抽象层
│   ├── adapters/
│   │   ├── ai/             # AI 提供商适配器
│   │   │   ├── base.py         # 基类
│   │   │   ├── openai_adapter.py   # OpenAI
│   │   │   └── anthropic_adapter.py # Anthropic Claude
│   │   └── channel/        # 消息通道适配器
│   │       ├── base.py         # 基类
│   │       ├── telegram_adapter.py  # Telegram
│   │       └── web_adapter.py       # WebSocket
│   ├── skills/             # Skills 管理器（三层渐进式加载）
│   ├── tools/              # Tools 管理器（沙盒隔离执行）
│   ├── orchestrator/       # 编排引擎
│   ├── app.py              # FastAPI 应用
│   ├── cli.py              # CLI 入口
│   └── config.py           # Pydantic 配置模型
├── configs/                # 配置文件目录（v1.4 结构）
│   ├── bot.yaml            # 根配置
│   ├── database.yaml       # 数据库配置
│   ├── memory.yaml         # 记忆系统参数
│   ├── Channels/           # 消息通道配置
│   ├── Providers/          # AI 提供商配置（模型列表 + default）
│   └── Plugins/            # Skills/Tools 配置
├── tests/                  # 测试套件（385+ 测试）
├── docs/                   # 设计文档与规范
└── pyproject.toml          # 项目配置
```

## 系统架构

YuanBot v1.0 由八大核心系统组成：

1. **接入与通信系统** — 统一网关、适配器管理、身份链接、主动推送
2. **人格与行为决策系统** — 意图识别、情感分析、对话决策、上下文组装、Token 预算
3. **记忆与情感系统** — 四层记忆模型、情景触发检索、情感追踪、记忆生命周期
4. **能力与工具扩展系统** — Skills/Tools 注册、三层渐进式加载、沙盒执行
5. **AI 提供商适配系统** — 适配器注册表、提供商管理器、模型列表式配置
6. **主动陪伴与自动化系统** — 定时调度、事件监听、克制策略
7. **统一开发标准** — Y.E.S. 扩展规范、标准化接口
8. **基础架构与部署系统** — 统一配置加载、数据库抽象、多模式部署

## 技术栈

| 组件 | 技术选择 | 说明 |
|------|----------|------|
| 核心语言 | Python 3.12+ | 生态丰富，AI/LLM 库支持好 |
| Web 框架 | FastAPI | 原生异步、WebSocket 支持 |
| 配置管理 | Pydantic + YAML | 类型安全 + 文件化配置 |
| 日志 | structlog | 结构化日志 |
| HTTP 客户端 | httpx | 异步 HTTP |
| 关系数据库 | SQLite (默认) / MySQL (可选) | 本地优先 |
| 向量数据库 | Milvus Lite | 嵌入式向量存储 |
| 图数据库 | Kuzu (嵌入式) / Neo4j | 知识图谱 |
| 缓存 | Redis | 工作记忆、会话状态 |
| 测试 | pytest + pytest-asyncio | 385+ 测试用例 |
| 代码质量 | ruff | lint + format |

## 开发路线

- [x] M1: 核心框架 — 编排层、记忆系统、统一接口
- [x] M2: 基础适配器 — OpenAI/Claude + Telegram/Web
- [x] M3: 记忆情感系统 — 四层记忆模型、情感追踪、情景触发检索
- [x] v1.0.0: 完整系统 — 网关、决策引擎、提供商管理、主动陪伴、基础设施

## 设计文档

详细设计文档位于 `docs/` 目录：

- [总体架构 v1.4](docs/architecture-v1.4.md)
- [接入与通信系统](docs/gateway-communication-system.md)
- [人格与行为决策系统](docs/persona-decision-system.md)
- [记忆与情感系统](docs/memory-emotion-system.md)
- [AI 提供商适配系统](docs/ai-provider-system.md)
- [能力与工具扩展系统](docs/capability-tool-system.md)
- [主动陪伴与自动化系统](docs/proactive-companion-system.md)
- [基础架构与部署系统](docs/infrastructure-deployment-system.md)

## 协议

MIT License
