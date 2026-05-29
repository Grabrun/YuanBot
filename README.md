# 🌸 缘·Bot (YuanBot)

> 一个开源的、有记忆、有情感、会主动关心你的 AI 虚拟伴侣系统。支持微信、QQ、Telegram 等多平台接入，8 家 AI 提供商一键切换，自托管、零锁定、数据完全属于你。

[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

它不只是问答机器人——它会记住你、理解你、主动关心你。跨平台、跨时间的长期陪伴，让 AI 真正融入你的生活。

---

## 🚀 5 分钟快速部署

### 方式一：Docker Compose（推荐）

```bash
# 1. 克隆项目
git clone https://github.com/Grabrun/YuanBot.git && cd YuanBot

# 2. 配置 API Key
cp .env.example .env
# 编辑 .env，填入你的 AI 提供商 API Key（任选其一即可）
#   YUAN_AI_API_KEY=sk-xxx
#   YUAN_AI_PROVIDER=openai

# 3. 一键启动
docker-compose up -d

# 4. 打开浏览器访问
#    WebUI:  http://localhost:8000
#    健康检查: http://localhost:8000/healthz
```

### 方式二：本地安装

```bash
# 1. 安装（需要 Python 3.12+）
pip install -e ".[dev]"

# 2. 初始化配置
yuanbot config init

# 3. 编辑 API Key
#    编辑 configs/Providers/openai.yaml，填入 api_key

# 4. 启动
yuanbot start
# 浏览器打开 http://localhost:8000
```

### 方式三：TUI 终端聊天

```bash
# 启动后，用终端界面直接聊天
yuanbot tui
```

---

## 🔑 AI 提供商配置

YuanBot 支持多家 AI 提供商，通过配置文件切换，**零代码改动**。

| 提供商 | 配置文件 | 默认模型 | 说明 |
|--------|----------|----------|------|
| OpenAI | `configs/Providers/openai.yaml` | gpt-4o | 需要 API Key |
| DeepSeek | `configs/Providers/deepseek.yaml` | deepseek-chat | 国产高性价比 |
| 智谱 GLM | `configs/Providers/glm.yaml` | glm-4 | 国产，中文优秀 |
| 通义千问 | `configs/Providers/qwen.yaml` | qwen-max | 阿里云 |
| 混元 | `configs/Providers/hunyuan.yaml` | hunyuan-pro | 腾讯 |
| Mimo | `configs/Providers/mimo.yaml` | mimo-chat | 小米 |
| Ollama | `configs/Providers/ollama.yaml` | 本地模型 | 无需 API Key |
| Anthropic | `configs/Providers/anthropic.yaml` | claude-sonnet-4 | Claude 系列 |

**切换提供商**：编辑 `configs/bot.yaml`：

```yaml
ai:
  default_provider: deepseek  # 改成你想用的提供商 ID
```

所有兼容 OpenAI 接口的提供商共用同一个适配器，添加新提供商只需一个 YAML 文件。

---

## 💬 消息通道

| 通道 | 配置文件 | 支持场景 |
|------|----------|----------|
| Web Chat | `configs/Channels/webchat.yaml` | 浏览器直接聊天 |
| 微信 | `configs/Channels/wechat.yaml` | 私聊 |
| QQ | `configs/Channels/qq.yaml` | 单聊 / 群聊 / 频道 |
| Telegram | `configs/Channels/telegram.yaml` | 私聊 / 群组 |
| Discord | `configs/Channels/discord.yaml` | 私聊 / 服务器 |
| 企业微信 | `configs/Channels/wecom.yaml` | 私聊 / 群聊 |

### 微信接入

1. 编辑 `configs/Channels/wechat.yaml`，设置 `enabled: true`
2. 启动服务，扫描终端中的二维码完成登录
3. 开始聊天

### QQ 接入

1. 在 [QQ 开放平台](https://q.qq.com) 注册机器人，获取 `app_id` 和 `app_secret`
2. 编辑 `configs/Channels/qq.yaml`，填入凭据
3. 启动服务即可

---

## 🌐 WebUI 管理界面

启动服务后访问 `http://localhost:8000`，使用管理员账号登录。

### 默认管理员

首次使用需要创建管理员：

```bash
# 通过 CLI 创建
yuanbot config init   # 如果还没有初始化配置
# 然后通过 API 或 WebUI 注册
```

### WebUI 功能

| 页面 | 路由 | 功能 |
|------|------|------|
| 💬 聊天 | `/` | WebSocket 流式对话，Markdown 渲染 |
| 🔌 Provider | `/providers` | 查看/管理 AI 提供商 |
| 🧠 记忆 | `/memory` | 浏览事实记忆、情景记忆、用户画像 |
| 🧩 插件 | `/plugins` | 管理 Skills 和 Tools |
| 📋 日志 | `/logs` | 实时日志流 |
| ⚙️ 配置 | `/config` | 在线编辑配置文件 |
| 📊 管理 | `/admin` | 仪表盘、用户管理 |

支持暗色主题、移动端响应式适配。

---

## 🧠 记忆系统

YuanBot 的核心是 **记忆优先** 架构：

| 记忆层 | 说明 | 存储 |
|--------|------|------|
| 工作记忆 | 当前会话上下文 | Redis / 内存 |
| 事实记忆 | 用户偏好、习惯、重要事实 | SQLite / MySQL |
| 情景记忆 | 过往对话摘要（语义检索） | Milvus Lite |
| 语义记忆 | 深层认知与关系理解 | Kuzu / Neo4j |

记忆系统自动运行：对话摘要生成、遗忘曲线淘汰、记忆固化，无需手动管理。

---

## 🔧 常用命令

```bash
# 服务
yuanbot start                      # 启动服务
yuanbot start --reload             # 开发模式（热重载）
yuanbot doctor                     # 系统诊断

# WebUI & TUI
yuanbot webui                      # 启动 WebUI 开发服务器
yuanbot tui                        # 启动终端聊天界面

# 配置
yuanbot config show                # 查看当前配置
yuanbot config init                # 初始化配置目录
yuanbot config edit bot.yaml       # 编辑配置文件

# 提供商
yuanbot provider list              # 列出所有提供商
yuanbot provider info openai       # 查看提供商详情
yuanbot provider set default deepseek  # 切换默认提供商
yuanbot provider create            # 创建新提供商

# 插件
yuanbot list channels              # 列出通道
yuanbot list providers             # 列出提供商
yuanbot list plugins               # 列出 Skills/Tools

# 记忆
yuanbot memory stats               # 记忆统计
yuanbot memory clear --user-id xxx # 清除用户记忆

# 扩展开发
yuanbot create --type skill --name my-skill  # 创建扩展
yuanbot validate <path>            # 验证扩展规范
yuanbot build <path>               # 打包扩展

# 日志
yuanbot logs                       # 查看最近日志
yuanbot logs -f                    # 实时跟踪日志
yuanbot logs -n 100 --level error  # 查看最近 100 条错误日志
```

---

## 📖 设计文档

| 文档 | 说明 |
|------|------|
| [总体架构 v1.5](docs/architecture-v1.5.md) | 系统架构设计（最新） |
| [AI 提供商适配系统](docs/ai-provider-system-v2.md) | 适配器复用，配置即 Provider |
| [记忆与情感系统](docs/memory-emotion-system.md) | 四层记忆与情感追踪 |
| [人格与决策系统](docs/persona-decision-system.md) | 人设与对话决策流水线 |
| [用户界面系统](docs/user-interface-system.md) | TUI/WebUI 双界面 |
| [TTS 语音合成](docs/tts-system.md) | 语音输出系统 |
| [接入与通信系统](docs/gateway-communication-system.md) | 通道适配与消息路由 |
| [能力与工具系统](docs/capability-tool-system.md) | Skills/Tools 管理 |
| [主动陪伴系统](docs/proactive-companion-system.md) | 定时任务与事件驱动 |
| [部署指南](docs/deployment.md) | Docker / K8s / Serverless |

---

## 🛠️ 技术栈

| 组件 | 技术 |
|------|------|
| 核心 | Python 3.12+ / FastAPI |
| 前端 | Vue 3 + Naive UI + Vite |
| 数据库 | SQLite (默认) / MySQL |
| 向量存储 | Milvus Lite |
| 图存储 | Kuzu / Neo4j |
| 缓存 | Redis |
| TTS | Edge-TTS / OpenAI TTS |
| 监控 | Prometheus |
| 测试 | pytest (941 用例全通过) |

---

## 📄 License

MIT License — 详见 [LICENSE](LICENSE)

---

<p align="center">
  🌸 缘·Bot — 让 AI 陪伴更有温度
</p>
