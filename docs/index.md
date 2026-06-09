# 🌸 缘·Bot (YuanBot)

> 不是工具，是陪伴。一个有记忆、有情感、会主动想起你的 AI。

---

## ✨ 特性

<div class="grid cards" markdown>

- :material-brain:{ .lg .middle } **四层记忆系统**

    ---

    工作记忆、事实记忆、情景记忆、语义记忆，像人一样记住你的一切。

    [:octicons-arrow-right-24: 记忆系统](memory-emotion-system.md)

- :material-heart:{ .lg .middle } **情感感知**

    ---

    实时感知你的情绪变化，难过时安慰你，开心时与你分享喜悦。

    [:octicons-arrow-right-24: 情感系统](memory-emotion-system.md)

- :material-robot-happy:{ .lg .middle } **主动陪伴**

    ---

    不只是被动回答，会主动关心你、提醒你、想起你。

    [:octicons-arrow-right-24: 主动陪伴](proactive-companion-system.md)

- :material-puzzle:{ .lg .middle } **多平台接入**

    ---

    微信、QQ、Telegram、Discord、企业微信、钉钉、飞书，一处部署，处处陪伴。

    [:octicons-arrow-right-24: 接入通道](gateway-communication-system.md)

</div>

## 🚀 快速开始

=== "Docker Compose（推荐）"

    ```bash
    # 1. 克隆项目
    git clone https://github.com/Grabrun/YuanBot.git && cd YuanBot

    # 2. 配置 API Key
    cp .env.example .env
    # 编辑 .env，填入你的 AI 提供商 API Key

    # 3. 一键启动
    docker-compose up -d

    # 4. 打开浏览器访问
    #    WebUI: http://localhost:8000
    ```

=== "Python 安装"

    ```bash
    # 1. 安装（需要 Python 3.12+）
    pip install -e ".[dev]"

    # 2. 初始化配置
    yuanbot config init

    # 3. 编辑 API Key
    # 编辑 configs/Providers/openai.yaml

    # 4. 启动
    yuanbot start
    ```

## 🤖 支持的 AI 提供商

| 提供商 | 默认模型 | 说明 |
|--------|----------|------|
| OpenAI | gpt-4o | 需要 API Key |
| DeepSeek | deepseek-chat | 国产高性价比 |
| 智谱 GLM | glm-4 | 国产，中文优秀 |
| 通义千问 | qwen-max | 阿里云 |
| 混元 | hunyuan-pro | 腾讯 |
| Mimo | mimo-chat | 小米 |
| Ollama | 本地模型 | 无需 API Key |
| Anthropic | claude-sonnet-4 | Claude 系列 |

## 📱 支持的通道

| 通道 | 场景 | 状态 |
|------|------|------|
| Web Chat | 浏览器直接聊天 | ✅ |
| 微信 | 私聊 | ✅ |
| QQ | 单聊 / 群聊 / 频道 | ✅ |
| Telegram | 私聊 / 群组 | ✅ |
| Discord | 私聊 / 服务器 | ✅ |
| 企业微信 | 私聊 / 群聊 | ✅ |
| 钉钉 | Webhook | ✅ |
| 飞书 | Webhook | ✅ |

## 📊 项目状态

- **总体符合度**: ~100%
- **测试**: 1405+ 个测试用例全部通过
- **代码质量**: Ruff lint 全部通过
- **许可证**: MIT

---

<div class="admonition tip">
<p class="admonition-title">💬 加入社区</p>

GitHub: [Grabrun/YuanBot](https://github.com/Grabrun/YuanBot)

</div>
