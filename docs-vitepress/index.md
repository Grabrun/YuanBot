---
# https://vitepress.dev/reference/default-theme-home-page
layout: home

hero:
  name: "🌸 YuanBot"
  text: "不是工具，是陪伴"
  tagline: 有记忆、有情感、会主动想起你的开源 AI 虚拟伴侣
  actions:
    - theme: brand
      text: 快速开始
      link: /guide/getting-started
    - theme: alt
      text: GitHub
      link: https://github.com/Grabrun/YuanBot

features:
  - icon: 🧠
    title: 四层记忆模型
    details: 工作记忆 · 事实记忆 · 情景记忆 · 语义记忆，像人一样，记住你说过的每一件事
  - icon: 💖
    title: 情感感知引擎
    details: 实时分析情绪变化，用最合适的方式回应。难过时温柔安慰，开心时一起庆祝
  - icon: 🌅
    title: 主动陪伴
    details: 不只等你开口。天气变化提醒带伞，心情低落主动关心
  - icon: 🔄
    title: 多人设切换
    details: 自定义人设，不同场景不同性格。温柔朋友 / 专业助手 / 可爱伙伴
  - icon: 🔌
    title: 全平台接入
    details: 微信（iLink Bot 个人号）、QQ（开放平台 + NapCat OneBot v11）、Telegram、Discord、企业微信、钉钉、飞书、Web Chat，一处部署，处处陪伴
  - icon: 🤖
    title: 多 AI 提供商
    details: 支持 OpenAI (GPT-5.5)、DeepSeek (V4, 1M ctx)、Claude (Sonnet 4.6)、GLM-5、Qwen3-Max 等 9 大 AI 提供商
  - icon: 🗣️
    title: TTS 语音引擎
    details: Edge-TTS、Piper、OpenAI TTS、Azure TTS 四种方案，WebSocket 流式播放
  - icon: 🖥️
    title: 双界面
    details: TUI 终端界面（Textual）+ WebUI（Vue 3 + Naive UI），满足不同使用习惯
---

## 🚀 快速安装

### 源码安装

::: code-group

```bash [Linux / macOS]
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot
python3 -m venv .venv
source .venv/bin/activate
pip install -e "."
pip install -e ".[cli,openai]"  # 可选扩展
yuanbot start
```

```powershell [Windows]
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot
python -m venv .venv
.venv\Scripts\activate
pip install -e "."
pip install -e ".[cli,openai]"  # 可选扩展
yuanbot start
```

:::

### Docker 安装

```bash
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot
cp .env.example .env
# 编辑 .env，填入你的 API Key
docker-compose up -d
```

首次启动后访问 **http://localhost:8000** 进入 WebUI，或运行 `yuanbot tui` 进入终端界面。

---

## 📊 项目数据

- **10 大核心系统** — 覆盖记忆、情感、通信、AI、TUI、WebUI 等全链路
- **100+ 个源代码文件** — 高内聚、低耦合的模块化架构
- **1453 个测试全部通过** — 99% 设计文档符合度
- **10 种消息通道** — 涵盖主流 IM 平台，频道适配器 API 文档开源参考
- **CI/CD 自动化** — GitHub Actions 持续集成与部署

---

## 🏗️ 技术栈

| 领域 | 技术 |
|------|------|
| **后端** | Python 3.12+ · FastAPI + WebSocket · structlog · Prometheus |
| **前端** | Vue 3 + Naive UI · Textual (TUI) |
| **数据** | SQLite + MySQL · Milvus Lite 向量数据库 · Kuzu 图数据库 · Redis 缓存 |
| **基础设施** | WASM / Docker / gRPC 三沙盒 · GitHub Actions CI/CD |

---

## 🧠 存储架构

| 引擎 | 用途 |
|------|------|
| **SQLite + FTS5** | 结构化数据 + 全文检索 |
| **MySQL** | 生产级关系型存储 |
| **Milvus Lite** | 向量数据库，语义检索 |
| **Kuzu** | 图数据库，关系推理 |

---

> **© 2026 YuanBot** · Made with 🌸 by [Grabrun](https://github.com/Grabrun)
