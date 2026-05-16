# 🌸 缘·Bot (YuanBot)

AI 虚拟伴侣系统 — 一个有记忆、有情感、有主动性的长期陪伴型 AI 角色。

## 核心特性

- **记忆优先 (Memory-First)** — 四层记忆模型，跨时间跨平台记住用户的一切
- **情感一致** — 稳定的人格设定和情感模型，交互风格一致
- **主动陪伴** — 根据上下文、时间、事件主动发起问候或话题
- **开放生态** — 模块化可扩展架构，社区自由开发适配器和技能

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
│   ├── core/           # 核心类型定义与接口
│   ├── memory/         # 四层记忆系统
│   ├── orchestrator/   # 编排引擎
│   ├── adapters/
│   │   ├── ai/         # AI 提供商适配器 (OpenAI, Claude)
│   │   └── channel/    # 消息通道适配器 (Telegram, Web)
│   ├── skills/         # Skills 管理
│   ├── tools/          # Tools 管理
│   ├── persona/        # Agent 人设
│   ├── app.py          # FastAPI 应用
│   ├── cli.py          # CLI 入口
│   └── config.py       # 配置管理
├── configs/            # 配置文件示例
├── tests/              # 测试
├── docs/               # 设计文档与规范
└── examples/           # 示例
```

## 架构设计

详见 [DESIGN.md](./DESIGN.md)

## 开发路线

- [x] M1: 核心框架 — 编排层、记忆系统、统一接口
- [x] M2: 基础适配器 — OpenAI/Claude + Telegram/Web
- [ ] M3: 记忆系统完善 — 情景触发检索、记忆图谱
- [ ] M4: 主动陪伴 — 定时交互、事件驱动
- [ ] M5: 社区生态 — 扩展市场、CLI 工具
- [ ] M6: v1.0 发布

## 协议

MIT License
