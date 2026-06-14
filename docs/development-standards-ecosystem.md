---
title: 统一开发标准与社区生态
description: YuanBot 统一开发标准与社区生态 v1.4 详细设计
---

🌸 缘·Bot 统一开发标准与社区生态详细设计文档 (v1.4)

版本历史

| 版本 | 日期 | 修改内容 |
|------|------|----------|
| v1.0 | 2026-05-17 | 初始详细设计，基于总体架构 v1.4 |
---

1. 系统定位与目标

统一开发标准与社区生态是 缘·Bot 的“可持续引擎”，它并非一个运行时可执行模块，而是一套贯穿整个项目的规范体系、工具链和治理机制。本系统确保：

· 任何开发者都能遵循清晰的标准，快速开发出与缘·Bot 核心无缝集成的扩展组件。
· 所有扩展（AI 提供商、消息通道、Skills、Tools、人设、触发器）共享统一的接口契约、配置格式和目录结构。
· 社区贡献有明确的审核、上架、分发和反馈流程，形成良性循环的开放生态。
· 用户能在一个可信的市场中浏览、安装、评价扩展，个性化自己的 AI 伴侣。

核心目标：

· 标准化 (Standardization)：定义 Y.E.S. (YuanBot Extension Standard) 规范，覆盖所有可扩展点。
· 低门槛 (Low Barrier)：提供 CLI 脚手架、项目模板和丰富的文档，降低开发上手难度。
· 可信赖 (Trustworthy)：通过自动化检查、人工审核和社区评分，保证扩展质量和安全。
· 可发现 (Discoverable)：构建扩展市场，支持分类、搜索、推荐，让好扩展触达用户。
· 国际化 (International)：支持多语言文档和扩展描述，服务全球社区。

---

2. 系统架构概览

```
┌──────────────────────────────────────────────────────────────┐
│              统一开发标准与社区生态                             │
├──────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │              Y.E.S. 规范体系 (Specification)              │ │
│  │  · 接口定义  · Schema 标准  · 目录结构  · 版本规范       │ │
│  └────────────────────────┬─────────────────────────────────┘ │
│                           │                                    │
│  ┌────────────────────────▼─────────────────────────────────┐ │
│  │              开发者工具链 (Toolchain)                     │ │
│  │  · yuanbot-cli  · 项目模板  · 本地测试环境  · CI 检查    │ │
│  └────────────────────────┬─────────────────────────────────┘ │
│                           │                                    │
│  ┌────────────────────────▼─────────────────────────────────┐ │
│  │              扩展市场平台 (Marketplace)                    │ │
│  │  · 扩展仓库  · 分类/搜索  · 一键安装  · 评分/评论        │ │
│  └────────────────────────┬─────────────────────────────────┘ │
│                           │                                    │
│  ┌────────────────────────▼─────────────────────────────────┐ │
│  │              社区治理 (Governance)                        │ │
│  │  · 贡献流程  · 审核机制  · 版本策略  · 社区公约          │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
└──────────────────────────────────────────────────────────────┘
```

设计原则：

· 约定优于配置：提供合理的默认值，减少开发者决策负担。
· 渐进式披露：简单的扩展只需寥寥几行，复杂扩展可逐步深入高级功能。
· 安全第一：所有扩展在进入市场前必须通过安全扫描和人工审核。

---

3. Y.E.S. 规范体系

Y.E.S. (YuanBot Extension Standard) 是本项目的基石规范，定义了所有扩展类型的接口契约、配置 Schema 和包结构。

3.1 扩展类型总览

扩展类型 目录前缀 说明 核心接口
AI 提供商适配器 yuanbot-ai-provider- 接入新的 LLM 后端 AIProviderAdapter
消息通道适配器 yuanbot-channel- 接入新的即时通讯平台 ChannelAdapter
Skill yuanbot-skill- 可复用的对话技能模块 SkillModule
Tool yuanbot-tool- 可调用的外部功能接口 ToolModule
Agent 人设 yuanbot-persona- AI 角色人格配置包 PersonaProfile
主动触发器 yuanbot-trigger- 自定义主动交互触发条件 ProactiveTrigger

3.2 通用包结构

所有类型的扩展必须遵循统一的顶级目录结构：

```
yuanbot-<type>-<name>/
├── manifest.json          # 必须：扩展元数据
├── README.md              # 必须：使用文档
├── LICENSE                # 必须：开源协议
├── changelog.md           # 推荐：更新日志
├── icon.png               # 推荐：扩展图标 (512x512)
└── src/                   # 必须：源代码目录
```

manifest.json 通用字段：

```json
{
  "$schema": "https://yuanbot.app/schemas/manifest-v1.json",
  "type": "ai_provider | channel | skill | tool | persona | trigger",
  "id": "唯一标识符，如 openai-adapter",
  "name": "显示名称",
  "version": "1.0.0",
  "author": {
    "name": "作者名称",
    "email": "author@example.com",
    "url": "https://github.com/author"
  },
  "description": "简短描述（支持多语言）",
  "license": "MIT",
  "homepage": "https://github.com/xxx/xxx",
  "repository": "https://github.com/xxx/xxx.git",
  "keywords": ["标签1", "标签2"],
  "yuanbot": {
    "min_core_version": "1.4.0",
    "max_core_version": "2.0.0"
  },
  "dependencies": {
    "other-extension-id": ">=1.0.0"
  }
}
```

多语言描述：description 字段支持国际化：

```json
{
  "description": {
    "zh": "OpenAI GPT 系列模型适配器",
    "en": "Adapter for OpenAI GPT series models"
  }
}
```

3.3 各类型扩展规范

3.3.1 AI 提供商适配器

完整目录结构：

```
yuanbot-ai-provider-openai/
├── manifest.json
├── README.md
├── src/
│   ├── adapter.py          # 主类，实现 AIProviderAdapter
│   ├── schemas.py          # 请求/响应数据模型
│   └── errors.py           # 自定义异常
├── tests/
│   └── test_adapter.py
└── requirements.txt
```

manifest.json 追加字段：

```json
{
  "type": "ai_provider",
  "yuanbot": {
    "provider_id": "openai",
    "supported_models": [
      {"id": "gpt-4o", "type": "chat", "max_tokens": 128000},
      {"id": "text-embedding-3-small", "type": "embedding", "dimension": 1536}
    ],
    "config_schema": {
      "type": "object",
      "properties": {
        "api_key": {"type": "string", "secret": true},
        "base_url": {"type": "string", "default": "https://api.openai.com/v1"}
      },
      "required": ["api_key"]
    }
  }
}
```

3.3.2 消息通道适配器

完整目录结构：

```
yuanbot-channel-telegram/
├── manifest.json
├── README.md
├── src/
│   ├── adapter.py          # 主类，实现 ChannelAdapter
│   ├── webhook.py          # Webhook 处理逻辑
│   ├── message_parser.py   # 消息解析
│   └── media_handler.py    # 媒体文件处理
├── tests/
└── requirements.txt
```

manifest.json 追加字段：

```json
{
  "type": "channel",
  "yuanbot": {
    "platform": "telegram",
    "supported_content_types": ["text", "image", "voice", "video", "file"],
    "config_schema": {
      "type": "object",
      "properties": {
        "bot_token": {"type": "string", "secret": true},
        "webhook": {
          "type": "object",
          "properties": {
            "enabled": {"type": "boolean", "default": true},
            "secret_token": {"type": "string", "secret": true}
          }
        }
      },
      "required": ["bot_token"]
    }
  }
}
```

3.3.3 Skill

完整目录结构：

```
yuanbot-skill-emotional-comfort/
├── manifest.json
├── README.md
├── src/
│   ├── definition.yaml     # 技能定义（提示词模板、步骤）
│   └── resources/          # 可选资源文件
│       ├── prompts_zh.txt
│       └── prompts_en.txt
└── tests/
    └── test_skill.py
```

definition.yaml 规范：

```yaml
skill_id: emotional_comfort
name: "情绪安抚"
version: "1.0.0"
category: emotional_care
capability_tags: ["comfort", "anxiety", "sadness"]
persona_filters: []  # 或 ["gentle_companion"] 限制特定人设
token_cost_estimate: 250
prompt_template: |
  [技能激活：情绪安抚]
  你现在启用了情绪安抚模式...
steps:
  - acknowledge: true
  - empathize: true
  - guide_gently: optional
```

manifest.json 追加字段：

```json
{
  "type": "skill",
  "yuanbot": {
    "category": "emotional_care",
    "capability_tags": ["comfort", "anxiety"],
    "persona_filters": [],
    "token_cost_estimate": 250
  }
}
```

3.3.4 Tool

完整目录结构：

```
yuanbot-tool-get-weather/
├── manifest.json
├── README.md
├── src/
│   ├── schema.json         # Function Calling Schema
│   ├── executor.py         # 执行逻辑
│   └── sandbox/
│       └── Dockerfile      # 若为 docker 类型
├── tests/
└── requirements.txt
```

schema.json 规范（兼容 OpenAI Function Calling）：

```json
{
  "type": "function",
  "function": {
    "name": "get_weather",
    "description": "获取指定城市的实时天气信息",
    "parameters": {
      "type": "object",
      "properties": {
        "city": {
          "type": "string",
          "description": "城市名称"
        }
      },
      "required": ["city"]
    }
  }
}
```

manifest.json 追加字段：

```json
{
  "type": "tool",
  "yuanbot": {
    "category": "daily_chat",
    "permission_level": "readonly",
    "executor_type": "docker",
    "timeout_seconds": 10,
    "config_schema": {
      "type": "object",
      "properties": {
        "api_key": {"type": "string", "secret": true}
      }
    }
  }
}
```

3.3.5 Agent 人设

完整目录结构：

```
yuanbot-persona-gentle-companion/
├── manifest.json
├── README.md
├── src/
│   ├── persona.yaml        # 人设定义
│   ├── avatar.png          # 可选：头像
│   └── voice_samples/      # 可选：语音样本
└── tests/
```

persona.yaml 规范：

```yaml
persona_id: gentle_companion
name: "小缘"
version: "1.0.0"
description:
  zh: "温柔体贴的长期伴侣"
  en: "A gentle and caring long-term companion"
voice_style:
  tone: "warm"
  speech_pattern: "gentle_and_caring"
  emoji_usage: "occasional_soft"
behavior_rules:
  - "用户倾诉时，先共情再引导"
  - "不主动结束对话"
capability_domains:
  - emotional_care
  - daily_chat
  - creative_storytelling
emotional_profile:
  baseline_mood: "calm_affectionate"
  empathy: 0.95
```

3.3.6 主动触发器

完整目录结构：

```
yuanbot-trigger-weather/
├── manifest.json
├── README.md
├── src/
│   ├── trigger.py          # 实现 ProactiveTrigger
│   └── config.yaml         # 触发器配置
└── tests/
```

manifest.json 追加字段：

```json
{
  "type": "trigger",
  "yuanbot": {
    "event_type": "weather_change",
    "priority": 5,
    "config_schema": {
      "type": "object",
      "properties": {
        "temp_change_threshold": {"type": "number", "default": 5},
        "rain_probability_threshold": {"type": "number", "default": 0.7}
      }
    }
  }
}
```

---

4. 开发者工具链

4.1 yuanbot-cli 命令行工具

提供全流程的命令行工具，降低开发门槛。

安装：

```bash
# 通过源码安装（yuanbot-cli 随 yuanbot 一起安装）
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[cli]"
```

核心命令：

命令 说明
yuanbot-cli create --type <type> 创建扩展项目，从模板生成脚手架
yuanbot-cli validate 验证 manifest.json 和代码是否符合 Y.E.S.
yuanbot-cli test 在本地模拟环境中运行测试
yuanbot-cli build 打包扩展为 .yuanbot 文件
yuanbot-cli publish 发布到社区市场
yuanbot-cli install <ext-id> 从市场安装扩展
yuanbot-cli list 列出已安装的扩展
yuanbot-cli update <ext-id> 更新指定扩展

创建项目交互流程：

```
$ yuanbot-cli create --type skill

? Skill 名称: emotional_comfort
? Skill ID: emotional_comfort
? 能力域: emotional_care
? 能力标签 (逗号分隔): comfort, anxiety, sadness
? 作者名称: YourName
? 许可证: MIT

✅ 项目已创建: yuanbot-skill-emotional_comfort/
   下一步: cd yuanbot-skill-emotional_comfort && yuanbot-cli test
```

4.2 本地开发与测试

开发环境配置：

开发者可通过 Docker Compose 快速启动一个本地缘·Bot 实例进行集成测试：

```bash
yuanbot-cli dev start
```

此命令启动一个包含核心编排层、SQLite、Milvus Lite、Redis 的最小化本地环境，自动加载当前开发的扩展。

测试框架：

缘·Bot 提供 yuanbot-testkit 包，用于编写扩展的单元和集成测试：

```python
from yuanbot_testkit import MockCore, TestAdapter

async def test_chat_completion():
    core = MockCore()
    adapter = MyAdapter(config)
    result = await adapter.chat_completion(
        messages=[Message(role="user", content="你好")],
        model="gpt-4o"
    )
    assert result.content is not None
```

4.3 CI/CD 集成

在 GitHub Actions 中自动验证扩展：

```yaml
name: YuanBot Extension CI
on: [push, pull_request]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: yuanbot-ai/validate-action@v1
        with:
          type: skill
```

CI 检查项包括：

1. manifest.json Schema 验证。
2. 接口实现完整性检查（反射检查是否实现所有抽象方法）。
3. 配置文件格式校验。
4. 安全扫描（检测硬编码密钥、依赖漏洞）。
5. 单元测试通过。

---

5. 扩展市场平台

5.1 平台架构

扩展市场是一个 Web 应用，托管于 yuanbot.app/marketplace，后端 API 与 GitHub 仓库同步。

功能模块：

模块 说明
扩展仓库 所有已上架扩展的索引，数据来自 yuanbot-extensions 仓库
分类浏览 按类型、能力域、标签筛选
搜索 全文搜索，支持中英文
详情页 扩展描述、版本历史、依赖、安装量、评分
一键安装 生成 yuanbot-cli install 命令
评分与评论 社区用户打分（1-5 星）和文字评价
开发者面板 管理自己发布的扩展，查看下载统计

5.2 扩展上架流程

```
开发者
  │
  ├── 1. 在 yuanbot-extensions 仓库 Fork 并创建扩展目录
  ├── 2. 按照 Y.E.S. 规范编写 manifest.json 和代码
  ├── 3. 本地通过 yuanbot-cli validate 和 yuanbot-cli test
  ├── 4. 提交 Pull Request 到 yuanbot-extensions
  │
  ↓
自动化 CI 检查
  │
  ├── manifest Schema 验证
  ├── 接口实现检查
  ├── 安全扫描（密钥检测、依赖审计）
  └── 单元测试运行
  │
  ↓ (全部通过)
社区审核 (Reviewer)
  │
  ├── 代码质量审查
  ├── 功能完整性验证
  ├── 文档可读性检查
  └── 安全合规确认
  │
  ↓ (审核通过)
合并并上架
  │
  ├── 合并 PR 到主分支
  ├── 自动生成扩展页面
  ├── 更新市场索引
  └── 通知开发者
```

5.3 版本管理

语义化版本 (SemVer)：主版本.次版本.修订号

· 主版本 (Major)：不兼容的 API 变更。
· 次版本 (Minor)：向下兼容的功能新增。
· 修订号 (Patch)：向下兼容的问题修复。

版本约束：manifest.json 中可声明依赖版本范围：

```json
{
  "dependencies": {
    "yuanbot-core": ">=1.4.0 <2.0.0"
  }
}
```

5.4 信任与安全

· 验证徽章：通过官方审核的扩展获得“已验证”徽章。
· 安全分级：
  · safe：无需网络、无文件写入。
  · cautious：需网络访问但非敏感。
  · restricted：需用户数据访问，首次使用时系统会提示用户确认。
· 举报机制：用户可举报有问题的扩展，触发重新审核。

---

6. 社区治理

6.1 社区结构

角色 职责
核心维护者 管理核心仓库，制定规范方向，最终审核权
审核者 (Reviewer) 审核社区 PR，确保质量和安全
贡献者 (Contributor) 提交代码、文档、翻译
用户 使用、评价、反馈

6.2 贡献指南

行为准则：遵循 Contributor Covenant 行为准则，建立友好、包容的社区。

贡献类型：

· 提交 Bug 报告和功能请求（通过 GitHub Issues）。
· 贡献代码（通过 Pull Request）。
· 改进文档（中/英/日多语言）。
· 翻译扩展描述。
· 帮助回答社区问题。

首次贡献：仓库中标记 good first issue 标签，引导新贡献者上手。

6.3 社区渠道

渠道 说明
GitHub Discussions 技术讨论、提案
Discord 实时交流、开发者答疑
中文微信群 中国社区即时沟通
文档站 docs.yuanbot.app 多语言文档

6.4 激励计划

· 贡献者榜单：月度活跃贡献者展示在官网。
· 认证开发者：持续高质量贡献者获得认证徽章。
· 社区精选：每月精选推荐优秀扩展。

---

7. 配置管理

7.1 扩展安装配置

已安装的扩展记录在 configs/extensions.yaml：

```yaml
extensions:
  installed:
    - id: openai-adapter
      version: 1.2.0
      source: marketplace
    - id: telegram-channel-adapter
      version: 1.1.0
      source: marketplace
    - id: emotional_comfort
      version: 1.0.0
      source: local
```

7.2 市场配置

configs/bot.yaml 中：

```yaml
marketplace:
  registry_url: "https://yuanbot.app/api/v1/marketplace"
  auto_update_check: true
  allow_prerelease: false
```

---

8. 国际化与文档

8.1 多语言文档站

docs.yuanbot.app 使用 VitePress 构建，支持：

· 中文 / English / 日本語 三语切换。
· 快速入门教程。
· API 参考。
· 扩展开发指南。
· 视频教程（未来）。

8.2 多语言扩展

扩展的 manifest.json 中 description、name 均支持多语言字段，市场前端自动根据用户语言展示。

---

9. 与核心系统的交互

统一开发标准与社区生态本身不直接参与运行时，但它定义了所有可扩展系统（AI 提供商、消息通道、Skills/Tools、人设、触发器）与核心之间的接口契约。

核心系统在启动时，通过以下方式加载扩展：

1. 扫描 configs/ 目录：加载用户配置的扩展设置。
2. 读取 extensions.yaml：获取已安装扩展列表。
3. 动态导入：根据 manifest.json 中的入口文件，加载扩展类。
4. 接口验证：运行时检查扩展是否实现了完整的抽象接口，若不符合则拒绝加载并提示。

---

本详细设计为缘·Bot 铺设了一条从个人项目走向全球开源社区的开放大道，确保每一个有想法的开发者都能轻松参与，共同丰富 AI 伴侣的能力边界。