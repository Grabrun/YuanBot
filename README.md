# 🌸 缘·Bot (YuanBot)

> 一个开源的、高度可定制的 AI 虚拟伴侣系统

[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com)

YuanBot 是一个有记忆、有情感、有主动性的长期陪伴型 AI 角色。它不只是一次性的问答机器人——它记得你、理解你、主动关心你。

---

## ✨ 特性亮点

| 特性 | 说明 |
|------|------|
| 🧠 **记忆优先架构** | 四层记忆模型（工作/事实/情景/语义），跨时间跨平台记住用户的一切 |
| 💕 **情感感知** | 实时情感分析，情感驱动的对话策略，交互风格自然一致 |
| 🤖 **主动陪伴** | 定时问候、事件驱动关怀、静默检测，根据用户状态主动发起互动 |
| 🔌 **多平台支持** | Telegram、Discord、企业微信、Web Chat 即插即用 |
| 🎭 **人设系统** | 可定制的 AI 角色人格，意图识别 → 情感分析 → 对话决策流水线 |
| 🔧 **可扩展** | 模块化架构，Skills/Tools 三层渐进式加载，Y.E.S. 扩展规范 |
| 🔒 **隐私优先** | 全部数据自托管，零供应商锁定，GDPR 合规 |
| 📊 **可观测性** | Prometheus 指标、结构化日志、健康检查端点 |

---

## 🚀 快速开始

### Docker 部署（推荐）

```bash
# 克隆项目
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入你的 API Key

# 启动服务
docker-compose up -d
```

服务启动后访问 http://localhost:8000/healthz 检查状态。

### 本地开发

```bash
# 克隆项目
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot

# 安装依赖
pip install -e ".[dev]"

# 初始化配置
yuanbot config init

# 编辑 configs/Providers/openai.yaml，填入 API Key

# 启动服务
yuanbot start

# 或使用热重载开发模式
yuanbot start --reload
```

### 环境要求

- **Python** >= 3.12
- **Redis** （可选，用于工作记忆缓存）
- **AI 提供商 API Key**（OpenAI / DeepSeek / Claude / Ollama 任选其一）

---

## 🏗️ 架构概览

YuanBot 采用八大核心系统协同工作的架构：

```
┌─────────────────────────────────────────────────────────┐
│                    消息通道层                              │
│   Telegram │ Discord │ 企业微信 │ Web Chat │ WebSocket   │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                   接入网关层                              │
│   AdapterManager │ Auth │ Privacy │ PushDispatcher      │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                   编排引擎层                              │
│   IntentEngine │ EmotionEngine │ DialogueDecision       │
│   ContextBuilder │ TokenBudget │ OrchestratorEngine     │
└───────────────────────┬─────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  AI 提供商   │ │  能力系统    │ │  记忆系统    │
│  OpenAI      │ │  Skills      │ │  工作记忆    │
│  DeepSeek    │ │  Tools       │ │  事实记忆    │
│  Claude      │ │  Orchestrator│ │  情景记忆    │
│  Ollama      │ │              │ │  语义记忆    │
└──────────────┘ └──────────────┘ └──────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                   主动陪伴系统                            │
│   ProactiveScheduler │ EventEngine │ ProactiveStrategy  │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                   基础设施层                              │
│   SQLite/MySQL │ Milvus │ Redis │ Kuzu/Neo4j            │
│   ConfigWatcher │ EventQueue │ CacheStore               │
└─────────────────────────────────────────────────────────┘
```

### 八大系统

| 系统 | 模块路径 | 职责 |
|------|----------|------|
| **记忆与情感系统** | `memory/` | 四层记忆模型、情感追踪、遗忘曲线、记忆固化 |
| **人格与决策系统** | `persona/` | 人设配置、意图识别、情感引擎、对话决策 |
| **接入与通信系统** | `gateway/` | 通道适配管理、身份认证、隐私保护、消息推送 |
| **AI 提供商系统** | `providers/` + `adapters/ai/` | 多提供商统一接口、模型路由、流式响应 |
| **能力与工具系统** | `skills/` + `tools/` | Skill/Tool 加载、沙箱执行、能力编排 |
| **主动陪伴系统** | `proactive/` | 定时任务、事件引擎、主动策略 |
| **编排引擎** | `orchestrator/` | 消息处理流水线、上下文构建、Token 预算 |
| **基础设施** | `infrastructure/` | 数据库、缓存、向量存储、图存储、配置热加载 |

---

## 📁 配置说明

所有配置文件位于 `configs/` 目录：

```
configs/
├── bot.yaml                  # 根配置（AI 提供商、通道、主动交互、编排引擎）
├── database.yaml             # 数据库配置（SQLite/MySQL、Milvus、Redis、Kuzu/Neo4j）
├── memory.yaml               # 记忆系统参数（四层记忆、遗忘曲线、固化策略）
├── default.yaml              # 默认配置（向后兼容）
├── extensions.yaml           # 已安装扩展列表
├── serverless.yaml           # Serverless 部署专用配置
├── Providers/                # AI 提供商配置
│   ├── openai.yaml
│   ├── deepseek.yaml
│   ├── claude.yaml
│   └── ollama.yaml
├── Channels/                 # 消息通道配置
│   ├── telegram.yaml
│   ├── discord.yaml
│   ├── webchat.yaml
│   └── wecom.yaml
├── Personas/                 # 人设配置
│   └── default.yaml
└── Plugins/                  # 插件配置
    ├── skills/
    │   ├── daily_chat.yaml
    │   ├── creative_storytelling.yaml
    │   └── emotional_comfort.yaml
    └── tools/
        ├── get_weather.yaml
        └── set_reminder.yaml
```

**配置加载优先级**：环境变量 > 配置文件 > 默认值

---

## 🔧 CLI 命令

```bash
# 服务管理
yuanbot start                    # 启动服务
yuanbot start --port 8080        # 指定端口
yuanbot start --host 127.0.0.1   # 指定监听地址
yuanbot start --reload           # 开发模式热重载

# 系统诊断
yuanbot doctor                   # 检查系统组件连通性

# 配置管理
yuanbot config show              # 显示当前配置
yuanbot config init              # 初始化配置目录

# 记忆管理
yuanbot memory stats             # 显示记忆统计
yuanbot memory clear --user-id <id>  # 清除用户记忆

# 扩展管理
yuanbot create --type skill --name my-skill    # 创建扩展脚手架
yuanbot validate <path>         # 验证扩展是否符合 Y.E.S. 规范
yuanbot test <path>             # 运行扩展测试
yuanbot build <path>            # 打包扩展为 .yuanbot 文件
yuanbot publish <path>          # 发布扩展到社区市场

# 版本信息
yuanbot version                  # 显示版本号
```

---

## 🌐 API 端点

### 健康检查

| 端点 | 方法 | 说明 |
|------|------|------|
| `/healthz` | GET | Liveness probe（Kubernetes 用） |
| `/readyz` | GET | Readiness probe（检查所有依赖） |
| `/health` | GET | 健康检查（向后兼容） |
| `/metrics` | GET | Prometheus 监控指标 |

### 对话接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/chat` | POST | 文本对话（Web Chat 通道） |
| `/ws` | WebSocket | 实时 WebSocket 聊天 |

### 数据接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/memory/{user_id}` | GET | 查看用户记忆 |
| `/api/proactive/tasks` | GET | 查看主动任务列表 |
| `/api/proactive/stats` | GET | 查看主动交互统计 |
| `/api/providers` | GET | 查看 AI 提供商状态 |
| `/api/capabilities` | GET | 查看已加载的 Skills/Tools |

### 扩展管理

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/extensions` | GET | 列出已安装扩展 |
| `/api/extensions/{ext_id}` | GET | 获取扩展详情 |
| `/api/extensions/install` | POST | 安装扩展 |
| `/api/extensions/uninstall` | POST | 卸载扩展 |

### GDPR 合规

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/gdpr/export?user_id=xxx` | GET | 导出用户数据 |
| `/api/gdpr/delete` | POST | 删除用户数据 |

---

## 🐳 部署方式

### Docker Compose

```bash
# 最简部署
docker-compose up -d

# 查看日志
docker-compose logs -f yuanbot

# 停止服务
docker-compose down
```

### Kubernetes

```bash
# 创建命名空间和 Secret
kubectl create namespace yuanbot
kubectl create secret generic yuanbot-secrets \
  --from-literal=OPENAI_API_KEY=sk-xxx \
  -n yuanbot

# 部署
kubectl apply -f k8s/

# 查看状态
kubectl get pods -n yuanbot
```

### Serverless

YuanBot 支持 AWS Lambda 和阿里云函数计算部署，详见 [部署文档](docs/deployment.md)。

---

## 🛠️ 技术栈

| 组件 | 技术选择 | 说明 |
|------|----------|------|
| 核心语言 | Python 3.12+ | 生态丰富，AI/LLM 库支持好 |
| Web 框架 | FastAPI | 原生异步、WebSocket 支持 |
| 配置管理 | Pydantic + YAML | 类型安全 + 文件化配置 |
| 关系数据库 | SQLite (默认) / MySQL (可选) | 本地优先 |
| 向量数据库 | Milvus Lite | 嵌入式向量存储 |
| 图数据库 | Kuzu / Neo4j | 知识图谱 |
| 缓存 | Redis | 工作记忆、会话状态 |
| AI 提供商 | OpenAI / DeepSeek / Ollama / Claude | 统一适配接口 |
| 监控 | Prometheus | 指标采集与暴露 |
| 测试 | pytest + pytest-asyncio | 完整测试覆盖 |
| 代码质量 | ruff | lint + format |

---

## 📖 文档索引

- [总体架构 v1.4](docs/architecture-v1.4.md) — 系统架构设计文档
- [记忆与情感系统](docs/memory-emotion-system.md) — 四层记忆与情感追踪
- [人格与决策系统](docs/persona-decision-system.md) — 人设与对话决策
- [接入与通信系统](docs/gateway-communication-system.md) — 通道适配与消息路由
- [AI 提供商系统](docs/ai-provider-system.md) — 多提供商统一接口
- [能力与工具系统](docs/capability-tool-system.md) — Skills/Tools 管理
- [主动陪伴系统](docs/proactive-companion-system.md) — 定时任务与事件驱动
- [基础架构与部署系统](docs/infrastructure-deployment-system.md) — 数据库与部署
- [AI 适配器规范](docs/adapter-ai-spec.md) — AI 提供商适配器接口规范
- [通道适配器规范](docs/adapter-channel-spec.md) — 消息通道适配器接口规范
- [开发规范](docs/development.md) — 开发环境与编码规范

---

## 🤝 参与贡献

1. Fork 本仓库
2. 创建功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'feat: add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 提交 Pull Request

### 开发环境搭建

```bash
# 克隆并安装开发依赖
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot
pip install -e ".[dev]"

# 运行测试
pytest

# 代码检查
ruff check src/ tests/
ruff format src/ tests/
```

---

## 📄 License

MIT License — 详见 [LICENSE](LICENSE)

---

<p align="center">
  用 ❤️ 构建 — 缘·Bot 让 AI 陪伴更有温度
</p>
