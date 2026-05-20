# 🌸 缘·Bot (YuanBot)

> 一个开源的、高度可定制的 AI 虚拟伴侣系统

YuanBot 是一个有记忆、有情感、有主动性的长期陪伴型 AI 角色。它不只是一次性的问答机器人——它记得你、理解你、主动关心你。

## ✨ 特性

- 🧠 **记忆优先架构** — 四层记忆模型（工作/事实/情景/语义），跨时间跨平台记住用户的一切
- 💕 **情感感知** — 实时情感分析，情感驱动的对话策略，交互风格自然一致
- 🤖 **主动陪伴** — 定时问候、事件驱动关怀、静默检测，根据用户状态主动发起互动
- 🔌 **多平台支持** — Telegram、Discord、企业微信、Web Chat 即插即用
- 🎭 **人设系统** — 可定制的 AI 角色人格，意图识别 → 情感分析 → 对话决策流水线
- 🔧 **可扩展** — 模块化架构，Skills/Tools 三层渐进式加载
- 🔒 **隐私优先** — 全部数据自托管，零供应商锁定

## 🚀 快速开始

### Docker 部署（推荐）

```bash
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入你的 API Key

# 启动服务
docker-compose up -d
```

服务启动后访问 http://localhost:8000/health 检查状态。

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

### CLI 命令

```bash
yuanbot start              # 启动服务
yuanbot start --port 8080  # 指定端口
yuanbot start --reload     # 开发模式热重载
yuanbot doctor             # 检查系统状态
yuanbot config show        # 显示当前配置
yuanbot config init        # 初始化配置目录
yuanbot memory stats       # 显示记忆统计
yuanbot memory clear --user-id xxx  # 清除用户记忆
yuanbot version            # 显示版本号
```

## 📖 文档

- [总体架构 v1.4](docs/architecture-v1.4.md)
- [记忆与情感系统](docs/memory-emotion-system.md)
- [人格与决策系统](docs/persona-decision-system.md)
- [接入与通信系统](docs/gateway-communication-system.md)
- [AI 提供商系统](docs/ai-provider-system.md)
- [能力与工具系统](docs/capability-tool-system.md)
- [主动陪伴系统](docs/proactive-companion-system.md)
- [基础架构与部署系统](docs/infrastructure-deployment-system.md)

## 🏗️ 项目结构

```
yuanbot/
├── src/yuanbot/
│   ├── core/               # 核心类型与抽象接口
│   ├── gateway/            # 接入与通信系统
│   ├── persona/            # 人格与行为决策系统
│   ├── memory/             # 记忆与情感系统
│   ├── providers/          # AI 提供商管理
│   ├── proactive/          # 主动陪伴系统
│   ├── infrastructure/     # 基础架构
│   ├── adapters/
│   │   ├── ai/             # AI 提供商适配器
│   │   └── channel/        # 消息通道适配器
│   ├── skills/             # Skills 管理器
│   ├── tools/              # Tools 管理器
│   ├── orchestrator/       # 编排引擎
│   ├── app.py              # FastAPI 应用
│   ├── cli.py              # CLI 入口
│   └── config.py           # 配置管理
├── configs/                # 配置文件目录
├── tests/                  # 测试套件
├── docs/                   # 设计文档
├── Dockerfile
├── docker-compose.yaml
└── pyproject.toml
```

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
| 测试 | pytest + pytest-asyncio | 完整测试覆盖 |
| 代码质量 | ruff | lint + format |

## 🤝 参与贡献

1. Fork 本仓库
2. 创建功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'feat: add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 提交 Pull Request

## 📄 License

MIT License — 详见 [LICENSE](LICENSE)

---

<p align="center">
  用 ❤️ 构建 — 缘·Bot 让 AI 陪伴更有温度
</p>
