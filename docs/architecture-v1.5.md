🌸 缘·Bot (YuanBot) 项目设计文档 v1.5

版本历史

版本 日期 修改内容
v1.0 2026-05-17 初始设计
v1.2 2026-05-17 重构版，系统分类
v1.3 2026-05-17 配置目录化，SQLite/Milvus Lite
v1.4 2026-05-17 Provider模型列表+default字段
v1.5 2026-05-22 重大功能扩展：TUI/WebUI双界面、TTS系统、日志系统重构、CLI扩展、内置插件/技能、更多通道(QQ/微信Clawbot/钉钉/飞书)、更多AI提供商(GLM/Mimo/Qwen/混元)、新Provider机制：适配器复用，配置文件定义Provider

---

第一章：项目概述与设计哲学

1.1 项目定义

🌸 缘·Bot (YuanBot) 是一个开源的、高度可定制的 AI 虚拟伴侣系统，致力于打造有记忆、有情感、有主动性的长期陪伴型 AI 角色。

v1.5 在伴侣能力之上大幅强化了交互界面多样性（TUI/WebUI）、语音输出能力（TTS）、开箱即用的插件生态（内置 Search/Weather 等）以及更广泛的中国平台与国产模型支持。

1.2 设计哲学：Memory-First

不变：记忆与情感连续性为第一性引擎。

1.3 核心目标（扩展）

维度 说明
记忆连续性 跨时间与平台，始终记得用户
情感一致性 稳定人格，自然情绪
主动陪伴 定时与事件触发主动互动
开放生态 通过标准化适配器与配置文件复用，极低门槛接入任何 LLM 与聊天平台
多模态交互 支持 TUI、WebUI、TTS 语音输出，满足不同场景
开箱即用 内置常用 Skills/Tools，安装即用；CLI 一键管理扩展

1.4 主要对标项目参考

保持不变，略。

---

第二章：总体架构与系统分类

v1.5 在原有的八大系统基础上，新增 用户界面系统、语音合成系统，并将 日志系统 独立为横切关注点。

v1.5 系统分类：

1. 接入与通信系统（新增 QQ、微信 Clawbot、钉钉、飞书）
2. 用户界面系统（新增：TUI 聊天、WebUI 聊天/管理）
3. 语音合成系统（新增：TTS）
4. 人格与行为决策系统
5. 记忆与情感系统
6. 能力与工具扩展系统（内置 Search/Weather 插件，内置安抚/故事等技能）
7. AI 提供商适配系统（重大重构：适配器复用机制，配置文件定义 Provider）
8. 主动陪伴与自动化系统
9. 统一开发标准与社区生态（含 CLI 扩展、规范文档）
10. 基础架构与部署系统（含日志系统完善）

2.1 系统交互数据流

```
┌───────────┐     ┌───────────┐     标准消息      ┌───────────────┐
│ TUI 界面  │     │ WebUI 界面│ ─────────────────→ │ 接入与通信系统 │
└───────────┘     └───────────┘                   └───────┬───────┘
                                                        │
┌───────────┐     语音数据                              │
│ TTS 系统  │ ← ──────────────────────────── ┐          │
└───────────┘                                 │          │
                                              ↓          ↓
                                    ┌──────────────────────┐
                                    │  人格与行为决策系统    │
                                    └──┬───┬───┬───────────┘
                                       │   │   │
                            记忆查询──┘   │   └── 能力调用
                                  ┌──────┘          ↓
                          ┌───────┴──────┐   ┌──────────────┐
                          │ 记忆与情感系统│   │ 能力与工具系统│
                          └──────────────┘   └──────┬───────┘
                                                    │
                                        ┌───────────┘
                                        ↓
                               ┌──────────────────┐
                               │ AI 提供商适配系统 │
                               └──────────────────┘
```

---

第三章：用户界面系统（新增）

3.1 设计目标

提供原生终端（TUI）和现代化 Web（WebUI）两种交互界面，均可进行聊天和系统管理。

3.2 TUI 聊天界面

· 技术选型：基于 Python Textual 框架构建。
· 功能：
  · 终端内实时流式聊天。
  · 多会话切换（类似 tmux 窗口）。
  · 系统命令入口：/persona, /memory, /plugin list, /provider 等。
  · 配色主题可定制，支持表情与部分 Markdown 渲染。
· 启动方式：yuanbot-cli tui 或直接 yuanbot-tui 命令。

3.3 内置 WebUI

· 技术选型：前端 Vue 3 + Naive UI，后端由 FastAPI 提供 API。
· 聊天界面：
  · 流式对话，支持文本、图片、语音消息（播放 TTS 生成的音频）。
  · 会话历史搜索。
  · 主动问候弹窗。
· 管理界面：
  · 仪表盘：服务状态、Token 消耗、记忆统计。
  · 配置编辑器：在线修改 bot.yaml、Providers、Channels 等，支持热重载。
  · 记忆浏览器：查看/删除/编辑事实记忆、情景记忆图谱可视化。
  · 人格商店：浏览、安装社区人设包。
  · 插件管理：安装、启用/禁用 Skills/Tools。
· 部署：默认集成在核心服务中，访问 http://localhost:8000 即可。

---

第四章：语音合成系统（新增）

4.1 设计目标

将 AI 回复的文本转化为自然语音，支持多种 TTS 引擎和音色，提升陪伴感。

4.2 系统架构

```
文本响应 → TTS Manager → 引擎适配 → 音频文件/流
                               ↓
                        本地引擎 (Edge-TTS, Piper)
                        云端引擎 (OpenAI TTS, Azure TTS)
```

4.3 统一 TTS 适配器接口

```python
class TTSAdapter(ABC):
    @abstractmethod
    async def synthesize(self, text: str, voice: str, **kwargs) -> bytes:
        """返回音频字节 (MP3/WAV)"""
        pass
```

4.4 预集成引擎

· Edge-TTS：免费，中文效果好，无需密钥。
· Piper TTS：本地离线，支持多语言，低资源消耗。
· OpenAI TTS：高质量，需要 API Key。
· 人设可指定默认语音（voice_style.tts_voice）。

4.5 配置

configs/tts.yaml：

```yaml
tts:
  enabled: true
  engine: edge-tts
  default_voice: "zh-CN-XiaoxiaoNeural"
```

---

第五章：接入与通信系统（扩展）

在原有 Telegram、Discord、企业微信、Web Chat 基础上，v1.5 新增以下消息通道适配器，并内置在官方扩展库中：

渠道 适配器名称 说明
QQ 开放平台 qq-open-adapter 支持 QQ 机器人官方 API
微信 Clawbot wechat-clawbot-adapter 通过 Clawbot 协议接入个人微信
钉钉 dingtalk-adapter 钉钉机器人回调
飞书 feishu-adapter 飞书应用机器人

每个适配器配置存放于 configs/Channels/，遵循统一的接口标准。

---

第六章：AI 提供商适配系统（重大重构）

6.1 新的 Provider 机制

核心理念：适配器（Adapter）仅负责认证鉴权和 API 调用实现，Provider 由配置文件定义。同一个适配器可被多个 Provider 配置文件共用。

例如：OpenAI、GLM、DeepSeek、Qwen、混元等多家提供商的 API 均与 OpenAI 接口兼容，它们只需使用同一个 OpenAIAdapter，通过不同的配置文件指定不同的 base_url、api_key 和模型列表即可。

优势：

· 添加新模型提供商的成本极低，通常只需一个 YAML 文件。
· 社区无需重复开发适配器代码。
· 统一管理，配置即 Provider。

6.2 Provider 配置文件规范

文件：configs/Providers/<provider_id>.yaml

完整字段：

```yaml
provider_id: openai            # 唯一标识
name: "OpenAI"                 # 显示名称
adapter: openai-adapter        # 指定使用的适配器
enabled: true
config:
  api_key: "${OPENAI_API_KEY}"
  base_url: "https://api.openai.com/v1"
  models:
    - id: gpt-4o
      type: chat
      max_tokens: 128000
    - id: text-embedding-3-small
      type: embedding
      dimension: 1536
  default: gpt-4o
  embedding_model: text-embedding-3-small  # 可选，若不指定则用第一个type=embedding的模型
```

关键点：

· adapter 字段引用一个已安装的适配器（如 openai-adapter）。
· 所有 OpenAI 兼容接口的 Provider 均可使用 openai-adapter。
· 适配器根据配置文件中的 base_url 和 api_key 进行认证和请求。
· 模型列表完全由配置文件定义，无代码变更。

6.3 内置的适配器类

系统预置两个通用适配器，覆盖绝大多数模型：

1. openai-adapter：兼容 OpenAI Chat Completions API 的服务。
2. anthropic-adapter：兼容 Anthropic Messages API 的服务。

其他所有 Provider 均通过配置文件派生，无需编写新适配器。

6.4 预集成 Provider 列表（v1.5 新增）

Provider ID 适配器 默认模型 说明
openai openai-adapter gpt-4o OpenAI 官方
deepseek openai-adapter deepseek-chat 深度求索
glm openai-adapter glm-4 智谱 GLM 系列
mimo openai-adapter mimo-chat 米莫 AI
qwen openai-adapter qwen-max 通义千问
hunyuan openai-adapter hunyuan-pro 腾讯混元
ollama openai-adapter qwen3:14b 本地 Ollama（OpenAI 兼容）
claude anthropic-adapter claude-sonnet-4 Anthropic 官方

6.5 使用示例

用户只需在 configs/Providers/ 下创建一个 qwen.yaml：

```yaml
provider_id: qwen
name: "通义千问"
adapter: openai-adapter
enabled: true
config:
  api_key: "your-dashscope-key"
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
  models:
    - id: qwen-max
      type: chat
      max_tokens: 32768
  default: qwen-max
```

然后在 bot.yaml 中设置 ai.default_provider: qwen 即可切换。

---

第七章：能力与工具扩展系统（内置插件与技能）

7.1 内置 Plugin 开发

v1.5 将携带两个官方内置插件，展示最佳实践并开箱即用：

① Search（搜索插件）

· 类型：Tool
· 功能：联网搜索，返回摘要和链接。
· 后端可配置：Bing API、SerpAPI、自建 SearXNG。
· 配置：configs/Plugins/tools/search.yaml

② Weather（天气插件）

· 类型：Tool
· 功能：查询指定城市实时天气和预报。
· 后端：OpenWeatherMap API 或和风天气 API。
· 配置：configs/Plugins/tools/weather.yaml

7.2 内置 Skills 开发

提供两个内置技能，强化伴侣情感能力：

① emotional_comfort（情绪安抚）
② bedtime_story（睡前故事）

这些 Skills 随核心发布，默认启用。

---

第八章：CLI 命令扩展

yuanbot-cli 新增以下管理命令：

命令 说明
yuanbot-cli channel install <name> 安装消息通道适配器
yuanbot-cli provider install <name> 安装 AI 提供商配置文件（或适配器）
yuanbot-cli plugin install <name> 安装 Skill/Tool
yuanbot-cli list channels/providers/plugins 列出已安装的扩展
yuanbot-cli tui 启动 TUI 聊天界面
yuanbot-cli webui 启动 WebUI 服务（若未随核心启动）
yuanbot-cli logs 查看实时日志
yuanbot-cli config edit 在默认编辑器中打开配置文件

---

第九章：日志系统完善

9.1 结构化日志

· 所有日志输出为 JSON 格式，包含 timestamp、level、module、trace_id。
· 支持同时输出到 console 和文件，文件自动轮转（30 天保留）。

9.2 日志级别动态调整

· 通过 API /admin/logging/level 动态修改特定模块的日志级别，无需重启。

9.3 日志聚合

· 提供 Loki + Grafana 集成指南，方便 Kubernetes 部署时聚合日志。

---

第十章：统一开发标准与社区生态

10.1 规范文档

编写以下规范文档，并托管于 docs.yuanbot.app：

· Channel 开发规范：如何实现 ChannelAdapter，消息标准化要求。
· Provider 配置文件规范：如何通过 YAML 文件定义新 Provider，适配器选择指南。
· Plugin 开发规范：Skill 与 Tool 的 manifest.json、定义文件格式、测试要求。

10.2 社区贡献

新增“内置示例”作为教学模板，降低贡献门槛。

---

第十一章：基础架构与部署系统（更新）

11.1 配置目录结构（v1.5）

```
configs/
├── bot.yaml
├── database.yaml
├── memory.yaml
├── tts.yaml               # 新增
├── orchestrator.yaml
├── extensions.yaml
├── Channels/              # 新增 qq.yaml, wechat.yaml, dingtalk.yaml, feishu.yaml
├── Providers/             # 新增 glm.yaml, qwen.yaml, hunyuan.yaml, mimo.yaml
├── Plugins/               # 内置 search.yaml, weather.yaml
│   ├── skills/
│   └── tools/
└── Personas/
```

11.2 TUI/WebUI 部署

· TUI：通过 yuanbot-cli tui 直接运行，无需额外服务。
· WebUI：随核心服务默认在 8000 端口提供，静态资源内嵌于 Python 包中，无需 Nginx（生产环境建议反向代理）。

---

第十二章：v1.5 路线图

里程碑 内容 预计时间
M1 TUI 聊天、WebUI 聊天基本可用 第1-2月
M2 管理界面实现，TTS 集成 第3月
M3 新 Provider 机制重构，GLM/Qwen/Hunyuan 等适配 第4月
M4 QQ/钉钉/飞书/微信 Clawbot 通道开发 第5月
M5 内置 Search/Weather 插件、内置 Skills 完善 第6月
M6 CLI 全功能、规范文档、社区 Beta 第7-8月
v1.5 发布 全量测试、文档、示例 第9月

---

本 v1.5 总设计文档为缘·Bot 注入了更强的交互能力、更广的生态覆盖和前所未有的扩展便利性，使其朝着“最懂你、最易得、最开放”的 AI 伴侣目标迈出了关键一步。