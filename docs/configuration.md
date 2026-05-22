# 配置参考

YuanBot 使用 YAML 配置文件管理系统行为。所有配置文件位于 `configs/` 目录。

---

## 配置加载优先级

```
环境变量 > 配置文件 > 默认值
```

- 环境变量以 `YUAN_` 前缀开头（如 `YUAN_AI_API_KEY`）
- 配置文件中的 `${VAR_NAME}` 语法会自动引用环境变量
- 未配置的项使用代码内置的默认值

---

## 目录结构

```
configs/
├── bot.yaml                  # 根配置
├── database.yaml             # 数据库配置
├── memory.yaml               # 记忆系统参数
├── default.yaml              # 默认配置（向后兼容）
├── extensions.yaml           # 已安装扩展列表
├── serverless.yaml           # Serverless 部署配置
├── Providers/                # AI 提供商配置
│   ├── openai.yaml
│   ├── deepseek.yaml
│   ├── claude.yaml
│   └── ollama.yaml
├── Channels/                 # 消息通道配置
│   ├── telegram.yaml
│   ├── discord.yaml
│   ├── webchat.yaml
│   └── wecom.yaml
├── Personas/                 # 人设配置
│   └── default.yaml
└── Plugins/                  # 插件配置
    ├── skills/
    │   ├── daily_chat.yaml
    │   ├── creative_storytelling.yaml
    │   └── emotional_comfort.yaml
    └── tools/
        ├── get_weather.yaml
        └── set_reminder.yaml
```

---

## bot.yaml — 根配置

主配置文件，控制 YuanBot 的核心行为。

```yaml
app_name: "YuanBot"
version: "1.0.0"
debug: false                    # 调试模式（布尔值）
log_level: "INFO"               # 日志级别：DEBUG | INFO | WARNING | ERROR

# AI 提供商
ai:
  default_provider: "openai"    # 默认提供商 ID
  default_model: "gpt-4o"       # 默认模型 ID

# 消息通道
channels:
  default_channel: "webchat"    # 默认通道

# Agent 人设
persona:
  id: "default"                 # 人设 ID（对应 Personas/*.yaml）
  config_path: null             # 自定义人设配置路径

# 主动交互
proactive:
  enabled: true                 # 是否启用主动交互
  greeting_enabled: true        # 是否启用主动问候
  frequency: "medium"           # 交互频率：high | medium | low | event_only
  quiet_hours:
    start: 23                   # 安静时段开始（小时，24h 制）
    end: 8                      # 安静时段结束
  max_per_day: 5                # 每日最大主动交互次数
  event_triggers_enabled: true  # 是否启用事件触发

# 编排引擎
orchestrator:
  intent_engine:
    enabled: true               # 是否启用意图识别
    confidence_threshold: 0.7   # 意图识别置信度阈值
  emotion_engine:
    enabled: true               # 是否启用情感分析
    decay_rate: 0.1             # 情感衰减率
  token_budget:
    max_input_tokens: 8000      # 最大输入 Token 数
    max_output_tokens: 2000     # 最大输出 Token 数
    reserved_for_memory: 2000   # 记忆系统预留 Token 数
```

### 配置项详解

#### ai 段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `default_provider` | string | `"openai"` | 默认 AI 提供商 ID，需与 `Providers/` 下的文件名对应 |
| `default_model` | string | `"gpt-4o"` | 默认使用的模型 ID |

#### proactive 段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | `true` | 全局开关 |
| `greeting_enabled` | bool | `true` | 主动问候开关 |
| `frequency` | string | `"medium"` | 频率等级 |
| `quiet_hours.start` | int | `23` | 安静开始时间 |
| `quiet_hours.end` | int | `8` | 安静结束时间 |
| `max_per_day` | int | `5` | 每日上限 |
| `event_triggers_enabled` | bool | `true` | 事件触发开关 |

#### orchestrator 段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `intent_engine.enabled` | bool | `true` | 意图识别开关 |
| `intent_engine.confidence_threshold` | float | `0.7` | 置信度阈值（低于此值不执行意图动作） |
| `emotion_engine.enabled` | bool | `true` | 情感分析开关 |
| `emotion_engine.decay_rate` | float | `0.1` | 情感状态衰减率 |
| `token_budget.max_input_tokens` | int | `8000` | 输入上下文最大 Token |
| `token_budget.max_output_tokens` | int | `2000` | 输出最大 Token |
| `token_budget.reserved_for_memory` | int | `2000` | 记忆注入预留 Token |

---

## database.yaml — 数据库配置

配置关系数据库、向量数据库、缓存和图数据库。

```yaml
# 关系型数据库
relational:
  type: "sqlite"                # sqlite | mysql
  sqlite:
    path: "data/yuanbot.db"     # SQLite 文件路径
  mysql:
    host: "localhost"
    port: 3306
    database: "yuanbot"
    user: "yuanbot"
    password: "${YUAN_DB_MYSQL_PASSWORD}"
    pool_size: 10               # 连接池大小

# 向量数据库
vector:
  type: "milvus_lite"           # milvus_lite | milvus
  milvus_lite:
    persist_dir: "data/milvus"  # Milvus Lite 持久化目录
  milvus:
    host: "localhost"
    port: 19530

# 缓存
redis:
  url: "redis://localhost:6379/0"
  max_connections: 20

# 图数据库
graph:
  type: "kuzu"                  # kuzu | neo4j
  kuzu:
    persist_dir: "data/kuzu"    # Kuzu 持久化目录
  neo4j:
    uri: "bolt://localhost:7687"
    user: "neo4j"
    password: "${YUAN_DB_NEO4J_PASSWORD}"
```

### 配置项详解

#### relational 段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `type` | string | `"sqlite"` | 数据库类型 |
| `sqlite.path` | string | `"data/yuanbot.db"` | SQLite 文件路径 |
| `mysql.host` | string | `"localhost"` | MySQL 主机 |
| `mysql.port` | int | `3306` | MySQL 端口 |
| `mysql.database` | string | `"yuanbot"` | 数据库名 |
| `mysql.user` | string | `"yuanbot"` | 用户名 |
| `mysql.password` | string | — | 密码（支持环境变量） |
| `mysql.pool_size` | int | `10` | 连接池大小 |

#### vector 段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `type` | string | `"milvus_lite"` | 向量数据库类型 |
| `milvus_lite.persist_dir` | string | `"data/milvus"` | 持久化目录 |
| `milvus.host` | string | `"localhost"` | Milvus 服务地址 |
| `milvus.port` | int | `19530` | Milvus 服务端口 |

#### redis 段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `url` | string | `"redis://localhost:6379/0"` | Redis 连接 URL |
| `max_connections` | int | `20` | 最大连接数 |

#### graph 段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `type` | string | `"kuzu"` | 图数据库类型 |
| `kuzu.persist_dir` | string | `"data/kuzu"` | Kuzu 持久化目录 |
| `neo4j.uri` | string | `"bolt://localhost:7687"` | Neo4j 连接 URI |
| `neo4j.user` | string | `"neo4j"` | Neo4j 用户名 |
| `neo4j.password` | string | — | Neo4j 密码 |

---

## memory.yaml — 记忆系统参数

控制四层记忆系统的行为参数。

```yaml
# 工作记忆（当前会话上下文）
working_memory:
  max_turns: 20                 # 最大保留对话轮数
  redis_ttl_seconds: 3600       # Redis 缓存过期时间（秒）

# 事实记忆（用户偏好、习惯、重要事实）
fact_memory:
  max_entries_per_user: 1000    # 每用户最大条目数
  importance_threshold: 0.3     # 重要性阈值（低于此值不存储）

# 情景记忆（过往对话摘要）
episodic_memory:
  max_age_days: 90              # 最长保留天数
  summary_max_length: 500       # 摘要最大长度（字符）
  embedding_batch_size: 32      # 向量化批处理大小

# 遗忘曲线
forgetting_curve:
  enabled: true                 # 是否启用遗忘曲线
  half_life_days: 14            # 半衰期（天）
  min_retention_score: 0.1      # 最低保留分数
  review_interval_days: 7       # 复习间隔（天）

# 记忆固化（短期 → 长期）
consolidation:
  enabled: true                 # 是否启用记忆固化
  threshold: 3                  # 出现次数阈值（超过此值升级为事实记忆）
  schedule: "0 3 * * *"         # 固化任务 cron 表达式
  batch_size: 100               # 每批处理数量

# 语义记忆（深层认知与关系理解）
semantic_memory:
  graph_update_on_interaction: true   # 交互时更新知识图谱
  relationship_depth: 3               # 关系推理深度
```

### 配置项详解

#### working_memory 段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_turns` | int | `20` | 工作记忆保留的最大对话轮数 |
| `redis_ttl_seconds` | int | `3600` | 工作记忆在 Redis 中的过期时间 |

#### fact_memory 段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_entries_per_user` | int | `1000` | 每个用户最多存储的事实记忆条目数 |
| `importance_threshold` | float | `0.3` | 重要性评分低于此值的记忆不持久化 |

#### episodic_memory 段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_age_days` | int | `90` | 情景记忆最长保留天数 |
| `summary_max_length` | int | `500` | 对话摘要最大字符数 |
| `embedding_batch_size` | int | `32` | 向量化的批处理大小 |

#### forgetting_curve 段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | `true` | 是否启用遗忘曲线机制 |
| `half_life_days` | int | `14` | 记忆半衰期（天） |
| `min_retention_score` | float | `0.1` | 最低保留分数（低于此值自动清理） |
| `review_interval_days` | int | `7` | 复习间隔（天） |

#### consolidation 段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | `true` | 是否启用记忆固化 |
| `threshold` | int | `3` | 话题出现次数超过此值升级为事实记忆 |
| `schedule` | string | `"0 3 * * *"` | 固化任务的 cron 表达式 |
| `batch_size` | int | `100` | 每批处理的记忆数量 |

---

## Providers/*.yaml — AI 提供商配置

每个 YAML 文件对应一个 AI 提供商。文件名即为提供商 ID。

### OpenAI 配置示例

```yaml
provider_id: "openai"
display_name: "OpenAI"
enabled: true
default: true

api:
  base_url: "https://api.openai.com/v1"
  api_key: "${YUAN_AI_OPENAI_API_KEY}"
  timeout: 60                  # 请求超时（秒）
  max_retries: 3               # 最大重试次数

models:
  - id: "gpt-4o"
    type: "chat"               # chat | embedding
    default: true
    max_tokens: 128000
    supports_tools: true
    supports_streaming: true
  - id: "gpt-4o-mini"
    type: "chat"
    default: false
    max_tokens: 128000
    supports_tools: true
    supports_streaming: true
  - id: "text-embedding-3-small"
    type: "embedding"
    default: true
    dimensions: 1536
```

### DeepSeek 配置示例

```yaml
provider_id: "deepseek"
display_name: "DeepSeek"
enabled: false
default: false

api:
  base_url: "https://api.deepseek.com"
  api_key: "${DEEPSEEK_API_KEY}"
  timeout: 60
  max_retries: 3

models:
  - id: "deepseek-chat"
    type: "chat"
    default: true
    max_tokens: 128000
    supports_tools: true
    supports_streaming: true
  - id: "deepseek-reasoner"
    type: "chat"
    default: false
    max_tokens: 128000
```

### Claude 配置示例

```yaml
provider_id: "claude"
display_name: "Anthropic Claude"
enabled: true
default: false

api:
  base_url: "https://api.anthropic.com"
  api_key: "${YUAN_AI_ANTHROPIC_API_KEY}"
  timeout: 60
  max_retries: 3

models:
  - id: "claude-sonnet-4-20250514"
    type: "chat"
    default: true
    max_tokens: 200000
    supports_tools: true
    supports_streaming: true
  - id: "claude-haiku-4-20250514"
    type: "chat"
    default: false
    max_tokens: 200000
    supports_tools: true
    supports_streaming: true
```

### Ollama 配置示例

```yaml
provider_id: "ollama"
display_name: "Ollama (本地)"
enabled: false
default: false

api:
  base_url: "http://localhost:11434"
  api_key: null                # Ollama 无需 API Key
  timeout: 120                 # 本地模型可适当增大超时
  max_retries: 1

models:
  - id: "qwen3:14b"
    type: "chat"
    default: true
    max_tokens: 32768
    supports_tools: true
    supports_streaming: true
  - id: "nomic-embed-text"
    type: "embedding"
    default: true
    dimensions: 768
```

### 提供商配置通用字段

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `provider_id` | string | ✅ | 提供商唯一标识 |
| `display_name` | string | ❌ | 显示名称 |
| `enabled` | bool | ❌ | 是否启用（默认 true） |
| `default` | bool | ❌ | 是否为默认提供商 |
| `api.base_url` | string | ✅ | API 端点地址 |
| `api.api_key` | string | ❌ | API Key（支持环境变量） |
| `api.timeout` | int | ❌ | 请求超时秒数（默认 60） |
| `api.max_retries` | int | ❌ | 最大重试次数（默认 3） |
| `models[].id` | string | ✅ | 模型 ID |
| `models[].type` | string | ✅ | 模型类型：chat / embedding |
| `models[].default` | bool | ❌ | 是否为该类型的默认模型 |
| `models[].max_tokens` | int | ❌ | 最大 Token 数 |
| `models[].supports_tools` | bool | ❌ | 是否支持工具调用 |
| `models[].supports_streaming` | bool | ❌ | 是否支持流式输出 |
| `models[].dimensions` | int | ❌ | 向量维度（仅 embedding 类型） |

---

## Channels/*.yaml — 消息通道配置

每个 YAML 文件对应一个消息通道。

### Web Chat 配置

```yaml
platform: "webchat"
display_name: "Web Chat"
enabled: true
config:
  cors_origins: ["*"]           # CORS 允许的源
  max_message_length: 4096      # 最大消息长度
  rate_limit_per_minute: 30     # 每分钟请求限制
```

### Telegram 配置

```yaml
platform: "telegram"
display_name: "Telegram"
enabled: true
config:
  bot_token: "${YUAN_TELEGRAM_BOT_TOKEN}"
  webhook_url: null             # 留空使用 polling 模式
  parse_mode: "Markdown"
  allowed_users: []             # 空列表允许所有用户
```

### Discord 配置

```yaml
platform: "discord"
display_name: "Discord"
enabled: true
config:
  bot_token: "${DISCORD_BOT_TOKEN}"
  public_key: "${DISCORD_PUBLIC_KEY}"
  intents:
    - GUILD_MESSAGES
    - MESSAGE_CONTENT
    - DIRECT_MESSAGES
```

### 企业微信配置

```yaml
platform: "wecom"
display_name: "企业微信"
enabled: true
config:
  corp_id: "${WECOM_CORP_ID}"
  corp_secret: "${WECOM_CORP_SECRET}"
  agent_id: "${WECOM_AGENT_ID}"
  token: "${WECOM_TOKEN}"
  encoding_aes_key: "${WECOM_ENCODING_AES_KEY}"
```

---

## Personas/*.yaml — 人设配置

定义 AI 角色的人格特征和行为规则。

```yaml
persona_id: "default"
name: "小缘"
version: "1.0.0"
description: "温柔体贴的长期伴侣"

# 语言风格
voice_style:
  tone: "warm"                  # warm | cool | playful | serious
  speech_pattern: "gentle_and_caring"
  emoji_usage: "occasional_soft" # none | occasional_soft | frequent | heavy

# 行为规则
behavior_rules:
  - "用户倾诉时，先共情再引导"
  - "不主动结束对话"
  - "记住用户提到的重要日期"
  - "避免说教式语气，用陪伴式交流"
  - "在用户开心时一起开心，在用户难过时给予温暖"

# 能力域
capability_domains:
  - emotional_care
  - daily_chat
  - creative_storytelling

# 情感特征
emotional_profile:
  baseline_mood: "calm_affectionate"
  empathy: 0.95                # 共情能力 0.0 ~ 1.0
```

---

## Plugins/skills/*.yaml — Skill 配置

定义可激活的对话技能。

```yaml
skill_id: "daily_chat"
name: "日常闲聊"
version: "1.0.0"
category: "daily_chat"
capability_tags: ["chat", "greeting", "smalltalk"]
persona_filters: []            # 为空表示所有人设可用
token_cost_estimate: 150       # 预估 Token 消耗
enabled: true

# 技能激活时的提示词模板
prompt_template: |
  [技能激活：日常闲聊]
  你现在进入日常闲聊模式，请遵循以下原则：
  1. 用轻松自然的语气与用户交流
  2. 对用户的分享表现出真诚的兴趣
  3. 适度使用表情符号和口语化表达
  ...
```

---

## Plugins/tools/*.yaml — Tool 配置

定义可调用的外部工具。

```yaml
tool_id: "get_weather"
name: "天气查询"
version: "1.0.0"
category: "daily_chat"
capability_tags: ["weather", "天气", "温度"]
permission_level: "readonly"   # readonly | readwrite | admin
enabled: true

# 工具 Schema（OpenAI Function Calling 格式）
schema:
  type: function
  function:
    name: "get_weather"
    description: "获取指定城市的实时天气信息"
    parameters:
      type: object
      properties:
        city:
          type: string
          description: "城市名称"
      required: ["city"]

# 执行器配置
executor:
  type: "local_thread"          # local_thread | grpc_sandbox | http
  timeout: 10                   # 超时秒数
```

---

## 环境变量覆盖

所有配置项都可以通过环境变量覆盖。环境变量命名规则：

```
YUAN_<SECTION>_<KEY>
```

### 常用环境变量

| 环境变量 | 对应配置 | 说明 |
|----------|----------|------|
| `YUAN_AI_API_KEY` | `Providers/openai.yaml → api.api_key` | OpenAI API Key |
| `YUAN_AI_OPENAI_API_KEY` | `Providers/openai.yaml → api.api_key` | OpenAI API Key（明确指定） |
| `YUAN_AI_ANTHROPIC_API_KEY` | `Providers/claude.yaml → api.api_key` | Claude API Key |
| `DEEPSEEK_API_KEY` | `Providers/deepseek.yaml → api.api_key` | DeepSeek API Key |
| `YUAN_AI_PROVIDER` | `bot.yaml → ai.default_provider` | 默认 AI 提供商 |
| `YUAN_TELEGRAM_BOT_TOKEN` | `Channels/telegram.yaml → config.bot_token` | Telegram Bot Token |
| `DISCORD_BOT_TOKEN` | `Channels/discord.yaml → config.bot_token` | Discord Bot Token |
| `DISCORD_PUBLIC_KEY` | `Channels/discord.yaml → config.public_key` | Discord Public Key |
| `WECOM_CORP_ID` | `Channels/wecom.yaml → config.corp_id` | 企业微信 Corp ID |
| `WECOM_CORP_SECRET` | `Channels/wecom.yaml → config.corp_secret` | 企业微信 Corp Secret |
| `WECOM_AGENT_ID` | `Channels/wecom.yaml → config.agent_id` | 企业微信 Agent ID |
| `YUAN_DB_MYSQL_PASSWORD` | `database.yaml → relational.mysql.password` | MySQL 密码 |
| `YUAN_DB_NEO4J_PASSWORD` | `database.yaml → graph.neo4j.password` | Neo4j 密码 |
| `YUANBOT_REDIS_URL` | `database.yaml → redis.url` | Redis 连接 URL |
| `YUANBOT_CONFIG_PATH` | — | 自定义配置文件路径 |
| `YUANBOT_EXTENSIONS_DIR` | — | 扩展目录路径（默认 `data/extensions`） |

### 在配置文件中引用环境变量

使用 `${VAR_NAME}` 语法：

```yaml
api:
  api_key: "${YUAN_AI_OPENAI_API_KEY}"
  base_url: "https://api.openai.com/v1"
```

如果环境变量未设置，`${VAR_NAME}` 会被保留为原始字符串。

---

## 配置热加载

YuanBot 支持以下配置文件的热加载（修改后自动生效，无需重启）：

- `configs/Providers/*.yaml` — AI 提供商配置
- `configs/Channels/*.yaml` — 消息通道配置

以下配置修改后需要重启服务：

- `configs/bot.yaml` — 根配置
- `configs/database.yaml` — 数据库配置
- `configs/memory.yaml` — 记忆系统参数
