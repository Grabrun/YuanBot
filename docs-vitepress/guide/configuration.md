# 配置说明

YuanBot 使用 YAML 配置文件管理系统行为。所有配置文件位于 `configs/` 目录。

## 配置加载优先级

```
环境变量 > 配置文件 > 默认值
```

- 配置文件中的 `${VAR_NAME}` 语法会自动引用环境变量
- 未配置的项使用代码内置的默认值

## 目录结构

```
configs/
├── bot.yaml                  # 主配置
├── database.yaml             # 数据库配置
├── memory.yaml               # 记忆系统配置
├── tts.yaml                  # TTS 语音合成配置
├── serverless.yaml           # Serverless 部署配置
├── Providers/                # AI 提供商配置（9 个）
│   ├── openai.yaml           # GPT-5.4 / GPT-5.5
│   ├── deepseek.yaml         # DeepSeek-V4-Pro / V4-Flash (1M ctx)
│   ├── anthropic.yaml        # Claude Sonnet 4.6 / Opus 4.8
│   ├── glm.yaml              # GLM-5 (744B)
│   ├── qwen.yaml             # Qwen3-Max / Qwen3.5-Plus (1M ctx)
│   ├── hunyuan.yaml          # Hunyuan-TurboS / 2.0-Thinking
│   ├── mimo.yaml             # MiMo-V2.5-Pro
│   ├── kimi.yaml             # Kimi K2.6 🆕
│   └── ollama.yaml           # 本地模型
├── Channels/                 # 消息通道配置
│   ├── telegram.yaml         # Telegram Bot
│   ├── discord.yaml          # Discord Bot
│   ├── webchat.yaml          # Web Chat (WebSocket)
│   ├── wechat.yaml           # 微信个人号（iLink Bot 长轮询）
│   ├── qq.yaml               # QQ 开放平台 Bot
│   ├── napcat.yaml           # QQ (NapCat / OneBot v11) 🆕
│   ├── dingtalk.yaml         # 钉钉
│   ├── feishu.yaml           # 飞书
│   ├── wecom.yaml            # 企业微信
│   └── ...
├── Personas/                 # 人设配置
│   ├── default.yaml
│   ├── cheerful.yaml
│   ├── mentor.yaml
│   └── gentle.yaml
└── Plugins/                  # 插件配置
    ├── skills/
    └── tools/
```

## 主配置 (bot.yaml)

```yaml
app_name: "YuanBot"
version: "1.5.0"
debug: false
log_level: "INFO"

ai:
  default_provider: "openai"
  embedding_provider: null

channels:
  default_channel: "webchat"

persona:
  id: "default"

proactive:
  enabled: true
  frequency: "medium"
  quiet_hours:
    start: 23
    end: 8
  max_per_day: 5
```

## 数据库配置 (database.yaml)

```yaml
relational:
  type: "sqlite"                # sqlite | mysql
  sqlite:
    path: "data/yuanbot.db"

vector:
  type: "milvus_lite"
  milvus_lite:
    persist_dir: "data/milvus"

redis:
  url: "redis://localhost:6379/0"

graph:
  type: "kuzu"
  kuzu:
    persist_dir: "data/kuzu"
```

## 环境变量

常用环境变量：

| 变量名 | 用途 |
|--------|------|
| `OPENAI_API_KEY` | OpenAI API Key（GPT-5.4 / GPT-5.5） |
| `ANTHROPIC_API_KEY` | Claude API Key（Sonnet 4.6 / Opus 4.8） |
| `DEEPSEEK_API_KEY` | DeepSeek API Key（V4-Flash / V4-Pro，1M 上下文） |
| `YUANBOT_ADMIN_PASSWORD` | 管理员密码 |
| `YUAN_TELEGRAM_BOT_TOKEN` | Telegram Bot Token |
| `YUAN_DB_MYSQL_PASSWORD` | MySQL 密码 |

## 配置热重载

以下文件的修改支持热加载，无需重启：

- `configs/Providers/*.yaml`
- `configs/Channels/*.yaml`
- `configs/Plugins/skills/*.yaml`
- `configs/Plugins/tools/*.yaml`

以下配置修改后需要重启服务：

- `configs/bot.yaml`
- `configs/database.yaml`
- `configs/memory.yaml`
- `configs/tts.yaml`

## 快速配置

仅需配置一个 AI 提供商即可启动：

```bash
export OPENAI_API_KEY="***"
python -m yuanbot
```

更多配置详情请参考 [GitHub 文档](https://github.com/Grabrun/YuanBot)。
