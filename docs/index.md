---
title: 首页
description: YuanBot - 有记忆、有情感、会主动想起你的开源 AI 虚拟伴侣
---

# 🌸 缘·Bot

**不是工具，是陪伴**

一个开源的、高度可定制的 AI 虚拟伴侣系统

![GitHub Stars](https://img.shields.io/github/stars/Grabrun/YuanBot?style=for-the-badge&logo=github&color=4d6bfe)
![Tests](https://img.shields.io/badge/tests-1412%20passed-10b981?style=for-the-badge)
![Python](https://img.shields.io/badge/python-3.12+-3776ab?style=for-the-badge&logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-4d6bfe?style=for-the-badge)

[:octicons-mark-github-16: GitHub](https://github.com/Grabrun/YuanBot){ .md-button .md-button--primary }
[:fontawesome-solid-rocket: 快速开始](getting-started.md){ .md-button }

---

## ✨ 核心特性

<div class="grid cards" markdown>

- :material-brain:{ .lg .middle } **四层记忆模型**

    ---

    工作记忆 · 事实记忆 · 情景记忆 · 语义记忆

    像人一样，记住你说过的每一件事

- :material-heart-pulse:{ .lg .middle } **情感感知引擎**

    ---

    实时分析情绪变化，用最合适的方式回应

    难过时温柔安慰，开心时一起庆祝

- :material-weather-sunset:{ .lg .middle } **主动陪伴**

    ---

    不只等你开口

    天气变化提醒带伞，心情低落主动关心

- :material-account-switch:{ .lg .middle } **多人设切换**

    ---

    自定义人设，不同场景不同性格

    温柔朋友 / 专业助手 / 可爱伙伴

</div>

---

## 📊 项目数据

<div class="grid cards" markdown>

- **10 大核心系统**
    
    覆盖记忆、情感、通信、AI、TUI、WebUI 等全链路

- **107 个源代码文件**
    
    高内聚、低耦合的模块化架构

- **1412 个测试全部通过**
    
    :material-check-all: 99% 设计文档符合度

- **CI/CD 自动化**
    
    GitHub Actions 持续集成与部署

</div>

---

## 🔌 全平台接入

8 大消息通道，一处部署，处处陪伴：

| 通道 | 说明 |
|------|------|
| :material-wechat: **微信** | 个人微信接入 |
| :material-penguin: **QQ** | QQ 机器人接入 |
| :material-telegram: **Telegram** | Telegram Bot |
| :material-discord: **Discord** | Discord Bot |
| :material-domain: **企业微信** | 企业微信应用 |
| :material-nail: **钉钉** | 钉钉机器人 |
| :material-feather: **飞书** | 飞书机器人 |
| :material-web: **Web Chat** | 浏览器内嵌聊天 |

---

## 🤖 AI 提供商

支持 8 大 AI 提供商，自由切换：

| 提供商 | 特点 |
|--------|------|
| **OpenAI** | GPT-4o / GPT-4 系列 |
| **DeepSeek** | 高性价比中文模型 |
| **GLM** | 智谱清言系列 |
| **MiMo** | 小米自研模型 |
| **Qwen** | 通义千问系列 |
| **Hunyuan** | 腾讯混元系列 |
| **Ollama** | 本地模型运行 |
| **Claude** | Anthropic Claude 系列 |

---

## 🗣️ TTS 语音引擎

4 种文本转语音方案，让伴侣「开口说话」：

- **Edge-TTS** — 微软免费语音，开箱即用
- **Piper** — 本地离线 TTS，隐私优先
- **OpenAI TTS** — 高质量 AI 语音合成
- **Azure TTS** — 企业级语音服务

---

## 🧠 存储架构

4 层存储引擎，支撑完整的记忆与知识系统：

| 引擎 | 用途 |
|------|------|
| **SQLite + FTS5** | 结构化数据 + 全文检索 |
| **MySQL** | 生产级关系型存储 |
| **Milvus Lite** | 向量数据库，语义检索 |
| **Kuzu** | 图数据库，关系推理 |

---

## 🖥️ 双界面

=== "TUI 终端"

    ```bash
    yuanbot tui
    ```
    
    基于 **Textual** 的终端 UI，轻量快捷，适合开发者和终端爱好者。

=== "WebUI"

    ```bash
    yuanbot webui
    ```
    
    基于 **Vue 3 + Naive UI** 的现代化 Web 界面，美观直观，适合所有用户。

---

## ⚡ 快速安装

### Python 安装

```bash
pip install "yuanbot[all]"
yuanbot start
```

### Docker 安装

```bash
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot
cp .env.example .env
# 编辑 .env，填入你的 API Key
docker-compose up -d
```

!!! tip "环境要求"
    - Python 3.12+
    - Docker (可选，推荐)

!!! info "首次使用"
    首次启动后访问 `http://localhost:8000` 进入 WebUI，或运行 `yuanbot tui` 进入终端界面。

---

## 🏗️ 技术栈

<div class="grid" markdown>

**后端** {.text-center}

- Python 3.12+
- FastAPI + WebSocket
- structlog 结构化日志
- Prometheus 监控

**前端** {.text-center}

- Vue 3 + Naive UI
- Textual (TUI)

**数据** {.text-center}

- SQLite + MySQL
- Milvus Lite 向量数据库
- Kuzu 图数据库
- Redis 缓存

**基础设施** {.text-center}

- WASM / Docker / gRPC 三沙盒
- GitHub Actions CI/CD

</div>

---

## 🚀 下一步

<div class="grid cards" markdown>

- [:fontawesome-solid-book: **快速开始**](getting-started.md)
    
    5 分钟完成部署

- [:fontawesome-solid-puzzle-piece: **架构概览**](architecture.md)
    
    了解系统设计

- [:fontawesome-solid-code: **API 参考**](api-reference.md)
    
    开发者接口文档

- [:fontawesome-solid-gear: **配置指南**](configuration.md)
    
    个性化定制

</div>

---

---

**© 2026 YuanBot** · Made with 🌸 by [Grabrun](https://github.com/Grabrun)

[:octicons-mark-github-16: GitHub](https://github.com/Grabrun/YuanBot){ .md-button }
[:fontawesome-solid-book-open: 文档](https://grabrun.github.io/YuanBot){ .md-button }
