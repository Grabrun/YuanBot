# 🌸 缘·Bot (YuanBot)

> 不是工具，是陪伴。一个有记忆、有情感、会主动想起你的 AI。

[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-1453%20passed-brightgreen.svg)](https://github.com/Grabrun/YuanBot)
[![Version](https://img.shields.io/badge/Version-1.2.0-purple.svg)](https://github.com/Grabrun/YuanBot/releases)

📖 **文档站**: [grabrun.github.io/YuanBot](https://grabrun.github.io/YuanBot)（中文 · English · 日本語）

---

## ✨ 核心特性

| 特性 | 说明 |
|------|------|
| 🧠 **四层记忆系统** | 工作记忆 → 事实记忆 → 情景记忆 → 语义记忆，自动摘要、遗忘、固化 |
| 🎭 **人格系统** | 内置多人设（小晴/明远/静安），运行时切换，关系阶段动态调整 |
| 💬 **多通道** | Web Chat / 微信 / QQ / Telegram / Discord / 企业微信，一处部署全平台可达 |
| 🎤 **语音输出** | Edge-TTS / OpenAI TTS / Piper TTS，WebSocket 流式播放 |
| 🔧 **扩展生态** | Skills / Tools / AI 提供商全接口标准化，扩展市场一键安装 |
| 📊 **全栈可观测** | Loki + Grafana 日志聚合，Prometheus 指标监控 |
| 🛡️ **安全合规** | JWT 权限令牌、GDPR 数据管理、CSRF 保护、速率限制 |
| 🌐 **多语言文档** | 中文 / English / 日本語 三语言 VitePress 文档站 |

---

## 🚀 快速部署

### Docker Compose（推荐）

```bash
# 1. 克隆项目
git clone https://github.com/Grabrun/YuanBot.git && cd YuanBot

# 2. 配置 API Key
cp .env.example .env
# 编辑 .env，填入你的 AI 提供商 API Key
#   YUAN_AI_API_KEY=sk-xxx
#   YUAN_AI_PROVIDER=openai

# 3. 一键启动
docker-compose up -d

# 4. 打开浏览器访问
#    WebUI:  http://localhost:8000
#    健康检查: http://localhost:8000/healthz
#    Grafana: http://localhost:3000 (admin/admin)
```

### 本地安装（Python 3.12+）

```bash
# 1. 安装
pip install -e ".[dev]"

# 2. 初始化配置
yuanbot config init

# 3. 编辑 API Key
#    编辑 configs/Providers/openai.yaml，填入 api_key

# 4. 启动
yuanbot start
# 浏览器打开 http://localhost:8000

# 5. 终端聊天模式
yuanbot tui
```

---

## 🔑 支持的 AI 提供商

| 提供商 | 配置文件 | 默认模型 | 特点 |
|--------|----------|----------|------|
| OpenAI | `openai.yaml` | gpt-4o | 通用最强 |
| DeepSeek | `deepseek.yaml` | deepseek-chat | 国产高性价比 |
| 智谱 GLM | `glm.yaml` | glm-4 | 中文优秀 |
| 通义千问 | `qwen.yaml` | qwen-max | 阿里云 |
| 混元 | `hunyuan.yaml` | hunyuan-pro | 腾讯 |
| Mimo | `mimo.yaml` | mimo-chat | 小米 |
| Ollama | `ollama.yaml` | 本地模型 | 无需 API Key |
| Anthropic | `anthropic.yaml` | claude-sonnet-4 | 长上下文 |

所有兼容 OpenAI 接口的提供商共用同一个适配器，新增提供商只需一个 YAML 文件。

**切换默认提供商**：编辑 `configs/bot.yaml`：
```yaml
ai:
  default_provider: deepseek  # 改成你想用的提供商 ID
```

---

## 💬 消息通道

| 通道 | 配置文件 | 支持场景 |
|------|----------|----------|
| 🌐 Web Chat | `webchat.yaml` | 浏览器直接聊天（WebSocket 流式） |
| 💚 微信 | `wechat.yaml` | 个人微信（扫码登录） |
| 🐧 QQ | `qq.yaml` | 单聊 / 群聊 / 频道 |
| ✈️ Telegram | `telegram.yaml` | 私聊 / 群组 |
| 🎮 Discord | `discord.yaml` | 私聊 / 服务器 |
| 🏢 企业微信 | `wecom.yaml` | 私聊 / 群聊 |

---

## 🌐 WebUI 管理界面

启动服务后访问 `http://localhost:8000`，使用管理员账号登录。

| 页面 | 路由 | 功能 |
|------|------|------|
| 💬 聊天 | `/` | WebSocket 流式对话，Markdown 渲染，TTS 语音播放 |
| 🧠 记忆 | `/memory` | 事实/情景记忆浏览 + 🕸️ 知识图谱可视化 |
| 🎭 人设 | `/persona` | 人格商店浏览/安装/激活/删除 |
| 🧩 插件 | `/plugins` | 管理 Skills/Tools + 扩展市场浏览安装 |
| 🔌 Provider | `/providers` | 查看/管理 AI 提供商 |
| 📋 日志 | `/logs` | 实时日志流 |
| ⚙️ 配置 | `/config` | 在线编辑配置文件 |
| 📊 管理 | `/admin` | 仪表盘、用户管理 |

---

## 🧪 开发者工具

### yuanbot-testkit

```bash
pip install -e ".[test]"
```

```python
from yuanbot_testkit import MockCore, TestAdapter

async def test_chat():
    core = MockCore()
    core.mock_response("你好，我是小艾！")
    result = await core.chat_completion(...)
    assert result.content == "你好，我是小艾！"
    assert core.get_call_count("chat_completion") == 1
```

### CI/CD 流水线

提交 PR 自动触发：Schema 验证 → 接口完整性检查 → 安全扫描 → 测试运行。合入 main 后自动发布 Release + Docker 镜像。

---

## 📊 测试

```bash
pytest -q     # 1453 passed, 16 warnings
ruff check    # All checks passed
```

---

## 📖 设计文档

| 系统 | 文档 | 符合度 |
|------|------|--------|
| 🏗️ 接入与通信 | [gateway-communication-system.md](docs/gateway-communication-system.md) | 97% |
| 🎨 用户界面 | [user-interface-system.md](docs/user-interface-system.md) | **100%** |
| 🎤 语音合成 (TTS) | [tts-system.md](docs/tts-system.md) | 98% |
| 🎭 人格与决策 | [persona-decision-system.md](docs/persona-decision-system.md) | **100%** |
| 🧠 记忆与情感 | [memory-emotion-system.md](docs/memory-emotion-system.md) | 98% |
| 🔧 能力与工具 | [capability-tool-system.md](docs/capability-tool-system.md) | 98% |
| 🤖 AI 提供商 | [ai-provider-system-v2.md](docs/ai-provider-system-v2.md) | 97% |
| 💞 主动陪伴 | [proactive-companion-system.md](docs/proactive-companion-system.md) | 98% |
| 🌍 社区生态 | [development-standards-ecosystem.md](docs/development-standards-ecosystem.md) | 98% |
| 🏛️ 基础架构 | [deployment.md](docs/deployment.md) | 99% |

---

## 🛠️ 技术栈

| 组件 | 技术 |
|------|------|
| 核心 | Python 3.12+ / FastAPI / Starlette WebSocket |
| 前端 | Vue 3 + Naive UI + Vite / Textual TUI |
| 数据库 | SQLite (默认) / MySQL（无缝切换） |
| 向量存储 | Milvus Lite（自动检测，fallback 内存模式） |
| 图存储 | Kuzu（知识图谱持久化） |
| 缓存 | Redis（自动启用，自动降级） |
| TTS | Edge-TTS / OpenAI TTS / Azure TTS / Piper TTS |
| 可观测 | Loki + Promtail + Grafana / Prometheus |
| 测试 | pytest (1453 passed) |

---

## 📄 License

MIT License — 详见 [LICENSE](LICENSE)

---

<p align="center">
  🌸 缘·Bot v1.2.0 — 让 AI 陪伴更有温度<br>
  <a href="https://grabrun.github.io/YuanBot">📖 文档站</a> · 
  <a href="https://github.com/Grabrun/YuanBot/releases">📦 Release</a>
</p>
