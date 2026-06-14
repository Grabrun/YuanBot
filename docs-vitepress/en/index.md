---
layout: home

hero:
  name: "🌸 YuanBot"
  text: "Not a tool, but a companion"
  tagline: An open-source AI virtual companion with memory, emotions, and proactive care
  actions:
    - theme: brand
      text: Get Started
      link: /en/guide/getting-started
    - theme: alt
      text: GitHub
      link: https://github.com/Grabrun/YuanBot

features:
  - icon: 🧠
    title: Four-Layer Memory Model
    details: Working memory · Fact memory · Episodic memory · Semantic memory — remembers everything you say
  - icon: 💖
    title: Emotion-Aware Engine
    details: Real-time emotion analysis for the most appropriate responses
  - icon: 🌅
    title: Proactive Companionship
    details: Doesn't wait for you to speak first — cares proactively
  - icon: 🔄
    title: Multiple Personas
    details: Customizable personas for different scenarios
  - icon: 🔌
    title: Cross-Platform
    details: WeChat, QQ, Telegram, Discord, DingTalk, Feishu, Web Chat
  - icon: 🤖
    title: 8 AI Providers
    details: OpenAI, DeepSeek, Claude, GLM, Qwen, and more
---

> 🚧 **English documentation is a work in progress.**  
> Full English translation is coming soon. For now, please refer to the [Chinese documentation](/).

## Quick Install

### pip

```bash
pip install "yuanbot[all]"
yuanbot start
```

### Docker

```bash
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot
cp .env.example .env
docker-compose up -d
```

---

> **© 2026 YuanBot** · Made with 🌸 by [Grabrun](https://github.com/Grabrun)
