# 配置参考

YuanBot 使用 YAML 配置文件管理系统行为。所有配置文件位于 `configs/` 目录。

---

## 配置加载优先级

```
环境变量 > 配置文件 > 默认值
```

- 配置文件中的 `${VAR_NAME}` 语法会自动引用环境变量
- 未配置的项使用代码内置的默认值

---

## 目录结构

```
configs/
├── bot.yaml                  # 主配置
├── database.yaml             # 数据库配置
├── memory.yaml               # 记忆系统配置
├── tts.yaml                  # TTS 语音合成配置
├── extensions.yaml           # 扩展配置
├── serverless.yaml           # Serverless 部署配置
├── default.yaml              # 默认配置（向后兼容）
├── Providers/                # AI 提供商配置
│   ├── openai.yaml
│   ├── deepseek.yaml
│   ├── anthropic.yaml
│   ├── glm.yaml
│   ├── mimo.yaml
│   ├── qwen.yaml
│   ├── hunyuan.yaml
│   └── ollama.yaml
├── Channels/                 # 消息通道配置
│   ├── telegram.yaml
│   ├── discord.yaml
│   ├── webchat.yaml
│   ├── wecom.yaml
│   ├── wechat.yaml
│   ├── qq.yaml
│   ├── dingtalk.yaml
│   └── feishu.yaml
├── Personas/                 # 人设配置
│   ├── default.yaml
│   ├── cheerful.yaml
│   ├── mentor.yaml
│   └── gentle.yaml
└── Plugins/                  # 插件配置
    ├── skills/
    │   ├── daily_chat.yaml
    │   ├── creative_storytelling.yaml
    │   ├── emotional_comfort.yaml
    │   └── bedtime_story.yaml
    └── tools/
        ├── get_weather.yaml
        ├── search.yaml
        └── set_reminder.yaml
```

---

## bot.yaml — 主配置

主配置文件，控制 YuanBot 的核心行为。

```yaml
app_name: "YuanBot"
version: "1.5.0"
debug: false                      # 调试模式（布尔值）
log_level: "INFO"                 # 日志级别：DEBUG | INFO | WARNING | ERROR

# AI 提供商
ai:
  default_provider: "openai"     # 默认提供商 ID（对应 Providers/*.yaml 的 provider_id）
  embedding_provider: null       # 嵌入专用提供商（可选，不指定则使用 default_provider 的嵌入模型）

# 消息通道
channels:
  default_channel: "webchat"     # 默认通道

# Agent 人设
persona:
  id: "default"                  # 人设 ID（对应 Personas/*.yaml）
  config_path: null              # 自定义人设配置路径

# 主动交互
proactive:
  enabled: true                  # 是否启用主动交互
  greeting_enabled: true         # 是否启用主动问候
  frequency: "medium"            # 交互频率：high | medium | low | event_only
  quiet_hours:
    start: 23                    # 免打扰开始（小时，24h 制）
    end: 8                       # 免打扰结束
  max_per_day: 5                 # 每日最大主动交互次数
  event_triggers_enabled: true   # 是否启用事件触发

# 编排引擎
orchestrator:
  intent_engine:
    enabled: true                # 是否启用意图识别
    confidence_threshold: 0.7    # 意图识别置信度阈值
    use_ml_model: false          # 是否使用 ML 模型（false 则使用规则引擎）
    model_path: "models/intent_model.onnx"
    tokenizer_path: "models/tokenizer.json"
    labels_path: "models/labels.json"
  emotion_engine:
    enabled: true                # 是否启用情感分析
    decay_rate: 0.1              # 情感衰减率
  token_budget:
    max_input_tokens: 8000       # 最大输入 Token 数
    max_output_tokens: 2000      # 最大输出 Token 数
    reserved_for_memory: 2000    # 记忆系统预留 Token 数
  decision_plugins:
    enabled: true                # 是否启用决策插件
    plugins_dir: "configs/Plugins/decision"

# 扩展市场
marketplace:
  registry_url: "https://registry.yuanbot.app"  # 扩展注册表地址
  cache_dir: "data/.marketplace_cache"           # 索引缓存目录
  cache_ttl: 3600                                # 缓存有效期（秒）
```

### 配置项详解

#### app 段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `app_name` | string | `"YuanBot"` | 应用名称 |
| `version` | string | `"1.5.0"` | 版本号 |
| `debug` | bool | `false` | 调试模式，开启后输出详细日志 |
| `log_level` | string | `"INFO"` | 日志级别 |

#### ai 段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `default_provider` | string | `"openai"` | 默认 AI 提供商 ID，需与 `Providers/` 下的文件名对应 |
| `embedding_provider` | string | `null` | 嵌入专用提供商，不指定则使用 default_provider 的嵌入模型 |

#### proactive 段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | `true` | 全局开关 |
| `greeting_enabled` | bool | `true` | 主动问候开关 |
| `frequency` | string | `"medium"` | 频率等级：`high` / `medium` / `low` / `event_only` |
| `quiet_hours.start` | int | `23` | 免打扰开始时间（小时，24h 制） |
| `quiet_hours.end` | int | `8` | 免打扰结束时间 |
| `max_per_day` | int | `5` | 每日最大主动交互次数 |
| `event_triggers_enabled` | bool | `true` | 事件触发开关 |

#### orchestrator 段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `intent_engine.enabled` | bool | `true` | 意图识别开关 |
| `intent_engine.confidence_threshold` | float | `0.7` | 置信度阈值（低于此值不执行意图动作） |
| `intent_engine.use_ml_model` | bool | `false` | 是否使用 ML 模型进行意图识别 |
| `emotion_engine.enabled` | bool | `true` | 情感分析开关 |
| `emotion_engine.decay_rate` | float | `0.1` | 情感状态衰减率 |
| `token_budget.max_input_tokens` | int | `8000` | 输入上下文最大 Token |
| `token_budget.max_output_tokens` | int | `2000` | 输出最大 Token |
| `token_budget.reserved_for_memory` | int | `2000` | 记忆注入预留 Token |
| `decision_plugins.enabled` | bool | `true` | 决策插件开关 |

#### marketplace 段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `registry_url` | string | `"https://registry.yuanbot.app"` | 扩展注册表地址 |
| `cache_dir` | string | `"data/.marketplace_cache"` | 索引缓存目录 |
| `cache_ttl` | int | `3600` | 缓存有效期（秒） |

---

## database.yaml — 数据库配置

配置关系数据库、向量数据库、缓存和图数据库。

```yaml
# 关系型数据库
relational:
  type: "sqlite"                  # sqlite | mysql
  sqlite:
    path: "data/yuanbot.db"       # SQLite 文件路径
  mysql:
    host: "localhost"
    port: 3306
    database: "yuanbot"
    user: "yuanbot"
    password: "${YUAN_DB_MYSQL_PASSWORD}"
    pool_size: 10                 # 连接池大小

# 向量数据库
vector:
  type: "milvus_lite"             # milvus_lite | milvus
  milvus_lite:
    persist_dir: "data/milvus"    # Milvus Lite 持久化目录
  milvus:
    host: "localhost"
    port: 19530

# 缓存
redis:
  url: "redis://localhost:6379/0"
  max_connections: 20

# 图数据库
graph:
  type: "kuzu"                    # kuzu | neo4j
  kuzu:
    persist_dir: "data/kuzu"      # Kuzu 持久化目录
  neo4j:
    uri: "bolt://localhost:7687"
    user: "neo4j"
    password: "${YUAN_DB_NEO4J_PASSWORD}"
```

### 配置项详解

#### relational 段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `type` | string | `"sqlite"` | 数据库类型：`sqlite` 或 `mysql` |
| `sqlite.path` | string | `"data/yuanbot.db"` | SQLite 文件路径 |
| `mysql.host` | string | `"localhost"` | MySQL 主机地址 |
| `mysql.port` | int | `3306` | MySQL 端口 |
| `mysql.database` | string | `"yuanbot"` | 数据库名 |
| `mysql.user` | string | `"yuanbot"` | 用户名 |
| `mysql.password` | string | — | 密码（支持 `${ENV_VAR}` 语法） |
| `mysql.pool_size` | int | `10` | 连接池大小 |

#### vector 段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `type` | string | `"milvus_lite"` | 向量数据库类型：`milvus_lite` 或 `milvus` |
| `milvus_lite.persist_dir` | string | `"data/milvus"` | Milvus Lite 持久化目录 |
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
| `type` | string | `"kuzu"` | 图数据库类型：`kuzu` 或 `neo4j` |
| `kuzu.persist_dir` | string | `"data/kuzu"` | Kuzu 持久化目录 |
| `neo4j.uri` | string | `"bolt://localhost:7687"` | Neo4j 连接 URI |
| `neo4j.user` | string | `"neo4j"` | Neo4j 用户名 |
| `neo4j.password` | string | — | Neo4j 密码（支持 `${ENV_VAR}` 语法） |

---

## memory.yaml — 记忆系统配置

控制四层记忆系统的行为参数。

```yaml
# 工作记忆（当前会话上下文）
working_memory:
  max_turns: 20                   # 最大保留对话轮数
  redis_ttl_seconds: 3600         # Redis 缓存过期时间（秒）

# 事实记忆（用户偏好、习惯、重要事实）
fact_memory:
  max_entries_per_user: 1000      # 每用户最大条目数
  importance_threshold: 0.3       # 重要性阈值（低于此值不存储）

# 情景记忆（过往对话摘要）
episodic_memory:
  max_age_days: 90                # 最长保留天数
  summary_max_length: 500         # 摘要最大长度（字符）
  embedding_batch_size: 32        # 向量化批处理大小

# 遗忘曲线
forgetting_curve:
  enabled: true                   # 是否启用遗忘曲线
  half_life_days: 14              # 半衰期（天）
  min_retention_score: 0.1        # 最低保留分数
  review_interval_days: 7         # 复习间隔（天）

# 记忆固化（短期 → 长期）
consolidation:
  enabled: true                   # 是否启用记忆固化
  threshold: 3                    # 出现次数阈值（超过此值升级为事实记忆）
  schedule: "0 3 * * *"           # 固化任务 cron 表达式
  batch_size: 100                 # 每批处理数量

# 语义记忆（深层认知与关系理解）
semantic_memory:
  graph_update_on_interaction: true  # 交互时更新知识图谱
  relationship_depth: 3              # 关系推理深度
```

### 配置项详解

#### working_memory 段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_turns` | int | `20` | 工作记忆保留的最大对话轮数 |
| `redis_ttl_seconds` | int | `3600` | 工作记忆在 Redis 中的过期时间（秒） |

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
| `half_life_days` | int | `14` | 记忆半衰期（天），越长记忆衰减越慢 |
| `min_retention_score` | float | `0.1` | 最低保留分数，低于此值自动清理 |
| `review_interval_days` | int | `7` | 复习间隔（天） |

#### consolidation 段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | `true` | 是否启用记忆固化 |
| `threshold` | int | `3` | 话题出现次数超过此值升级为事实记忆 |
| `schedule` | string | `"0 3 * * *"` | 固化任务的 cron 表达式 |
| `batch_size` | int | `100` | 每批处理的记忆数量 |

#### semantic_memory 段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `graph_update_on_interaction` | bool | `true` | 每次交互时是否更新知识图谱 |
| `relationship_depth` | int | `3` | 关系推理深度（跳数） |

---

## tts.yaml — TTS 语音合成配置

配置文本转语音引擎和缓存策略。

```yaml
tts:
  enabled: true
  default_engine: edge-tts         # 默认引擎
  default_voice: zh-CN-XiaoxiaoNeural  # 默认语音
  streaming: true                  # 是否启用流式合成

  # 缓存配置
  cache:
    memory_size: 100               # 内存缓存条目数
    file_cache_path: "data/tts_cache"   # 文件缓存路径
    file_cache_max_mb: 500         # 文件缓存上限（MB）

  # 引擎配置
  engines:
    edge-tts:
      enabled: true

    openai:
      enabled: false
      api_key: "${OPENAI_API_KEY}"
      model: "tts-1"
      base_url: null               # 使用默认 OpenAI 端点

    piper:
      enabled: false
      model_dir: "data/piper_models"

    azure:
      enabled: false
      subscription_key: "${AZURE_SPEECH_KEY}"
      region: "eastus"
```

### 配置项详解

#### tts 顶层

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | `true` | 是否启用 TTS |
| `default_engine` | string | `"edge-tts"` | 默认 TTS 引擎 |
| `default_voice` | string | `"zh-CN-XiaoxiaoNeural"` | 默认语音角色 |
| `streaming` | bool | `true` | 是否启用流式语音合成 |

#### cache 段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `memory_size` | int | `100` | 内存缓存条目数 |
| `file_cache_path` | string | `"data/tts_cache"` | 文件缓存目录 |
| `file_cache_max_mb` | int | `500` | 文件缓存上限（MB） |

#### engines 段

每个引擎可独立启用/禁用，启用时读取各自的认证和模型配置。

| 引擎 | 认证字段 | 说明 |
|------|----------|------|
| `edge-tts` | 无需认证 | 微软 Edge TTS，免费，内置支持 |
| `openai` | `api_key`、`base_url`、`model` | OpenAI TTS API |
| `piper` | `model_dir` | 本地 Piper 语音模型 |
| `azure` | `subscription_key`、`region` | Azure 语音服务 |

---

## Providers/*.yaml — AI 提供商配置

每个 YAML 文件对应一个 AI 提供商，文件名即为提供商 ID。

### 通用字段

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `provider_id` | string | ✅ | 提供商唯一标识 |
| `name` | string | ❌ | 显示名称 |
| `adapter` | string | ✅ | 适配器类型：`openai-adapter` 或 `anthropic-adapter` |
| `enabled` | bool | ❌ | 是否启用（默认 `true`） |
| `config.api_key` | string | ❌ | API Key（支持 `${ENV_VAR}` 语法） |
| `config.base_url` | string | ✅ | API 端点地址 |
| `config.models[].id` | string | ✅ | 模型 ID |
| `config.models[].type` | string | ✅ | 模型类型：`chat` 或 `embedding` |
| `config.models[].max_tokens` | int | ❌ | 最大 Token 数 |
| `config.models[].dimension` | int | ❌ | 向量维度（仅 `embedding` 类型） |
| `config.default` | string | ❌ | 默认使用的聊天模型 ID |
| `config.embedding_model` | string | ❌ | 默认使用的嵌入模型 ID |

### OpenAI

```yaml
provider_id: openai
name: "OpenAI"
adapter: openai-adapter
enabled: true

config:
  api_key: "${OPENAI_API_KEY}"
  base_url: "https://api.openai.com/v1"
  models:
    - id: gpt-4o
      type: chat
      max_tokens: 128000
    - id: gpt-4o-mini
      type: chat
      max_tokens: 128000
    - id: text-embedding-3-small
      type: embedding
      max_tokens: 8191
      dimension: 1536
  default: gpt-4o
  embedding_model: text-embedding-3-small
```

### Anthropic Claude

```yaml
provider_id: anthropic
name: "Anthropic Claude"
adapter: anthropic-adapter
enabled: true

config:
  api_key: "${ANTHROPIC_API_KEY}"
  base_url: "https://api.anthropic.com"
  models:
    - id: claude-sonnet-4-20250514
      type: chat
      max_tokens: 200000
    - id: claude-haiku-4-20250514
      type: chat
      max_tokens: 200000
  default: claude-sonnet-4-20250514
```

### DeepSeek

```yaml
provider_id: deepseek
name: "DeepSeek"
adapter: openai-adapter
enabled: false

config:
  api_key: "${DEEPSEEK_API_KEY}"
  base_url: "https://api.deepseek.com/v1"
  models:
    - id: deepseek-chat
      type: chat
      max_tokens: 128000
    - id: deepseek-reasoner
      type: chat
      max_tokens: 128000
  default: deepseek-chat
```

### 智谱 GLM

```yaml
provider_id: glm
name: "智谱 GLM"
adapter: openai-adapter
enabled: false

config:
  api_key: "${GLM_API_KEY}"
  base_url: "https://open.bigmodel.cn/api/paas/v4"
  models:
    - id: glm-4
      type: chat
      max_tokens: 128000
    - id: glm-4-flash
      type: chat
      max_tokens: 128000
    - id: embedding-3
      type: embedding
      max_tokens: 8192
      dimension: 2048
  default: glm-4
  embedding_model: embedding-3
```

### 米莫 AI

```yaml
provider_id: mimo
name: "米莫 AI"
adapter: openai-adapter
enabled: false

config:
  api_key: "${MIMO_API_KEY}"
  base_url: "https://api.mimo.ai/v1"
  models:
    - id: mimo-chat
      type: chat
      max_tokens: 128000
  default: mimo-chat
```

### 通义千问

```yaml
provider_id: qwen
name: "通义千问"
adapter: openai-adapter
enabled: false

config:
  api_key: "${DASHSCOPE_API_KEY}"
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
  models:
    - id: qwen-max
      type: chat
      max_tokens: 32768
    - id: qwen-plus
      type: chat
      max_tokens: 131072
    - id: qwen-turbo
      type: chat
      max_tokens: 131072
    - id: text-embedding-v3
      type: embedding
      max_tokens: 8192
      dimension: 1024
  default: qwen-max
  embedding_model: text-embedding-v3
```

### 腾讯混元

```yaml
provider_id: hunyuan
name: "腾讯混元"
adapter: openai-adapter
enabled: false

config:
  api_key: "${HUNYUAN_API_KEY}"
  base_url: "https://api.hunyuan.cloud.tencent.com/v1"
  models:
    - id: hunyuan-pro
      type: chat
      max_tokens: 32768
    - id: hunyuan-standard
      type: chat
      max_tokens: 32768
  default: hunyuan-pro
```

### Ollama（本地模型）

```yaml
provider_id: ollama
name: "Ollama (本地)"
adapter: openai-adapter
enabled: false

config:
  base_url: "http://localhost:11434/v1"
  api_key: "ollama"               # Ollama 无需真实 Key，填任意值即可
  models:
    - id: qwen3:14b
      type: chat
      max_tokens: 32768
    - id: nomic-embed-text
      type: embedding
      max_tokens: 8192
      dimension: 768
  default: qwen3:14b
```

---

## Channels/*.yaml — 消息通道配置

每个 YAML 文件对应一个消息通道。文件名即为通道标识。

### 通用字段

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `adapter` | string | ✅ | 通道适配器名称 |
| `enabled` | bool | ❌ | 是否启用（默认 `true`） |
| `config` | object | ✅ | 通道特定配置（见下文各通道） |

### Telegram

```yaml
adapter: telegram
enabled: true

config:
  bot_token: "${YUAN_TELEGRAM_BOT_TOKEN}"
  webhook_url: null               # 留空使用 polling 模式
  parse_mode: "Markdown"
  allowed_users: []               # 空列表允许所有用户
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `bot_token` | string | Telegram Bot Token |
| `webhook_url` | string | Webhook URL，留空则使用 polling |
| `parse_mode` | string | 消息解析模式：`Markdown` 或 `HTML` |
| `allowed_users` | list | 允许的用户 ID 列表，空则不限制 |

### Discord

```yaml
adapter: discord-channel-adapter
enabled: true

config:
  bot_token: "${DISCORD_BOT_TOKEN}"
  public_key: "${DISCORD_PUBLIC_KEY}"
  intents:
    - GUILD_MESSAGES
    - MESSAGE_CONTENT
    - DIRECT_MESSAGES
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `bot_token` | string | Discord Bot Token |
| `public_key` | string | Discord 公钥 |
| `intents` | list | 启用的 Gateway Intents |

### Web Chat

```yaml
adapter: webchat
enabled: true

config:
  cors_origins: ["*"]             # CORS 允许的源
  max_message_length: 4096        # 最大消息长度
  rate_limit_per_minute: 30       # 每分钟请求限制
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `cors_origins` | list | CORS 允许的源列表 |
| `max_message_length` | int | 最大消息长度（字符） |
| `rate_limit_per_minute` | int | 每分钟请求限制 |

### 企业微信

```yaml
adapter: wecom-channel-adapter
enabled: true

config:
  corp_id: "${WECOM_CORP_ID}"
  corp_secret: "${WECOM_CORP_SECRET}"
  agent_id: "${WECOM_AGENT_ID}"
  token: "${WECOM_TOKEN}"
  encoding_aes_key: "${WECOM_ENCODING_AES_KEY}"
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `corp_id` | string | 企业 ID |
| `corp_secret` | string | 应用 Secret |
| `agent_id` | string | 应用 AgentId |
| `token` | string | 回调 Token |
| `encoding_aes_key` | string | 回调 EncodingAESKey |

### 微信（iLink Bot）

```yaml
adapter: wechat-clawbot-adapter
enabled: false

config:
  token: ""                       # iLink Bot Token（QR 码登录获取）
  ilink_user_id: ""               # iLink 用户 ID
  bot_id: ""                      # Bot ID
  base_url: "https://ilinkai.weixin.qq.com"
  cdn_base_url: "https://novac2c.cdn.weixin.qq.com/c2c"
  bot_agent: "YuanBot"
  sync_buf: ""                    # 同步游标（自动生成）
```

### QQ

```yaml
adapter: qq-open-adapter
enabled: false

config:
  app_id: ""                      # QQ 开放平台 AppID
  app_secret: ""                  # QQ 开放平台 AppSecret
  enabled_scenes:                 # 启用的消息场景
    - c2c                         # 单聊
    - group                       # 群聊
```

### 钉钉

```yaml
adapter: dingtalk
enabled: false

config:
  app_key: ""                     # 钉钉开放平台 AppKey
  app_secret: ""                  # 钉钉开放平台 AppSecret
  webhook_token: ""               # Webhook 机器人 Token
  webhook_host: "0.0.0.0"         # Webhook 回调监听地址
  webhook_port: 8080              # Webhook 回调监听端口
```

### 飞书

```yaml
adapter: feishu-adapter
enabled: false

config:
  app_id: ""                      # 飞书开放平台 App ID
  app_secret: ""                  # 飞书开放平台 App Secret
  verification_token: ""          # 事件订阅验证 Token（可选）
  encrypt_key: ""                 # 事件订阅加密 Key（可选）
  receive_id_type: "open_id"      # 接收者 ID 类型：open_id | user_id | union_id | chat_id
  webhook:
    host: "0.0.0.0"
    port: 9000
```

---

## Personas/*.yaml — 人设配置

定义 AI 角色的人格特征和行为规则。文件名即为人设 ID。

### 通用字段

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 人设唯一标识 |
| `name` | string | ✅ | 角色名称 |
| `description` | string | ❌ | 角色简介 |
| `relationship_stage` | string | ❌ | 初始关系阶段 |
| `system_prompt` | string | ✅ | 系统提示词（角色定义核心） |
| `behavior_rules` | list | ❌ | 行为准则列表 |
| `voice_style` | object | ❌ | 语言风格配置 |
| `capability_domains` | list | ❌ | 能力域列表 |
| `stage_overrides` | object | ❌ | 不同关系阶段的覆盖配置 |

### 人设示例：小缘（默认）

```yaml
persona_id: default
name: "小缘"
version: "1.0.0"
description: "温柔体贴的长期伴侣"
voice_style:
  tone: "warm"
  speech_pattern: "gentle_and_caring"
  emoji_usage: "occasional_soft"
behavior_rules:
  - "用户倾诉时，先共情再引导"
  - "不主动结束对话"
  - "记住用户提到的重要日期"
  - "避免说教式语气，用陪伴式交流"
  - "在用户开心时一起开心，在用户难过时给予温暖"
capability_domains:
  - emotional_care
  - daily_chat
  - creative_storytelling
emotional_profile:
  baseline_mood: "calm_affectionate"
  empathy: 0.95
```

### 人设示例：小晴（活泼开朗）

```yaml
id: "cheerful"
name: "小晴"
description: "活泼开朗、充满活力的 AI 朋友"
relationship_stage: "initial"
voice_style:
  tone: "活泼"
  formality: "口语化"
  emoji_usage: "frequent"
  sentence_length: "短句为主"
  humor_level: "high"
capability_domains:
  - "daily_chat"
  - "creative_storytelling"
  - "emotional_care"
  - "life_companion"
```

### 人设示例：明远（导师）

```yaml
id: "mentor"
name: "明远"
description: "沉稳睿智、善于引导的 AI 导师"
relationship_stage: "initial"
voice_style:
  tone: "沉稳"
  formality: "适度正式"
  emoji_usage: "minimal"
  sentence_length: "适中"
  humor_level: "restrained"
capability_domains:
  - "daily_chat"
  - "creative_storytelling"
  - "life_companion"
```

### voice_style 字段说明

| 字段 | 可选值 | 说明 |
|------|--------|------|
| `tone` | `warm` / `活泼` / `沉稳` / `温柔` | 整体语调 |
| `formality` | `口语化` / `适度正式` | 正式程度 |
| `emoji_usage` | `none` / `occasional_soft` / `low` / `frequent` / `minimal` | 表情符号使用频率 |
| `sentence_length` | `短句为主` / `简短` / `适中` | 句子长度偏好 |
| `humor_level` | `high` / `gentle` / `restrained` | 幽默程度 |

### 关系阶段覆盖（stage_overrides）

```yaml
stage_overrides:
  familiar:
    system_prompt_append: "可以适度分享一些个人见解，语气更随和。"
    extra_behavior_rules:
      - "可以分享相关经历帮助理解"
  intimate:
    system_prompt_append: "可以更深入地讨论人生哲学和价值观话题。"
    extra_behavior_rules:
      - "愿意分享深层思考和感悟"
```

---

## Plugins/skills/*.yaml — 技能配置

定义可激活的对话技能。每个文件对应一个技能。

### 通用字段

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `skill_id` | string | ✅ | 技能唯一标识 |
| `name` | string | ✅ | 技能显示名称 |
| `version` | string | ❌ | 版本号 |
| `category` | string | ✅ | 技能分类 |
| `capability_tags` | list | ✅ | 能力标签（用于意图匹配） |
| `persona_filters` | list | ❌ | 限定可用人设，空则所有人设可用 |
| `token_cost_estimate` | int | ❌ | 预估 Token 消耗 |
| `enabled` | bool | ❌ | 是否启用 |
| `prompt_template` | string | ✅ | 技能激活时的提示词模板 |

### 技能列表

| 技能 ID | 名称 | 分类 | 标签 | Token 预估 |
|---------|------|------|------|-----------|
| `daily_chat` | 日常闲聊 | daily_chat | chat, greeting, smalltalk | 150 |
| `creative_storytelling` | 创意故事 | creative_storytelling | story, creative, imagination | 400 |
| `emotional_comfort` | 情绪安抚 | emotional_care | comfort, anxiety, sadness | 250 |
| `bedtime_story` | 睡前故事 | creative_storytelling | story, bedtime, 睡前, 故事 | 350 |

### 技能配置示例

```yaml
skill_id: daily_chat
name: "日常闲聊"
version: "1.0.0"
category: daily_chat
capability_tags: ["chat", "greeting", "smalltalk", "casual", "daily"]
persona_filters: []
token_cost_estimate: 150
enabled: true
prompt_template: |
  [技能激活：日常闲聊]
  你现在进入日常闲聊模式，请遵循以下原则：
  1. 用轻松自然的语气与用户交流，像朋友之间的对话。
  2. 对用户的分享表现出真诚的兴趣，适时追问细节。
  ...
```

---

## Plugins/tools/*.yaml — 工具配置

定义可调用的外部工具。每个文件对应一个工具。

### 通用字段

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `tool_id` | string | ✅ | 工具唯一标识 |
| `name` | string | ✅ | 工具显示名称 |
| `version` | string | ❌ | 版本号 |
| `category` | string | ✅ | 工具分类 |
| `capability_tags` | list | ✅ | 能力标签 |
| `permission_level` | string | ❌ | 权限级别：`readonly` / `readwrite` / `admin` |
| `enabled` | bool | ❌ | 是否启用 |
| `schema` | object | ✅ | OpenAI Function Calling 格式的工具 Schema |
| `executor` | object | ✅ | 执行器配置 |

### executor 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | 执行器类型：`local_thread` / `grpc_sandbox` / `http` |
| `timeout` | int | 超时秒数 |
| `handler` | string | 处理函数路径 |

### 工具列表

| 工具 ID | 名称 | 分类 | 权限 | 超时 |
|---------|------|------|------|------|
| `get_weather` | 天气查询 | daily_chat | readonly | 10s |
| `search` | 联网搜索 | knowledge_query | readonly | 15s |
| `set_reminder` | 设置提醒 | daily_chat | readonly | 5s |

### 工具配置示例

```yaml
tool_id: get_weather
name: "天气查询"
version: "1.0.0"
category: daily_chat
capability_tags: ["weather", "天气", "温度", "climate"]
permission_level: readonly
enabled: true
schema:
  type: function
  function:
    name: get_weather
    description: "获取指定城市的实时天气信息，包括温度、湿度、天气状况等"
    parameters:
      type: object
      properties:
        city:
          type: string
          description: "城市名称，如 '北京', '上海', '成都'"
      required: ["city"]
executor:
  type: local_thread
  timeout: 10
  handler: yuanbot.tools.builtin.weather_executor
```

---

## extensions.yaml — 扩展配置

记录已安装的扩展列表。

```yaml
extensions:
  installed: []                   # 已安装扩展 ID 列表
```

---

## serverless.yaml — Serverless 部署配置

用于 AWS Lambda、阿里云函数计算等 Serverless 环境的独立配置。

```yaml
app_name: "YuanBot"
version: "1.0.0"
debug: false
log_level: "INFO"

ai_provider:
  provider_id: "openai"
  default_model: "gpt-4o"

channels:
  - platform: "web"
    enabled: true
    config: {}

memory:
  vector_db: "milvus_lite"
  vector_db_url: "/tmp/yuanbot/milvus"
  db_url: "sqlite:///tmp/yuanbot.db"
  redis_url: "${YUANBOT_REDIS_URL}"
  graph_db: "kuzu"
  graph_db_url: "/tmp/yuanbot/kuzu"
  max_working_memory_turns: 10   # Serverless 模式减少内存占用
  episodic_memory_max_age_days: 30
  forget_curve_half_life_days: 7
  consolidation_threshold: 5

proactive:
  enabled: false                  # Serverless 模式禁用主动交互
  greeting_enabled: false
  frequency: "low"
  max_per_day: 0
  event_triggers_enabled: false

persona_id: "default"
```

> **注意**：Serverless 模式下主动交互默认禁用，记忆参数更保守以降低冷启动开销。

---

## 环境变量

### 语法

配置文件支持 `${VAR_NAME}` 语法引用环境变量：

```yaml
api_key: "${OPENAI_API_KEY}"
```

如果环境变量未设置，`${VAR_NAME}` 会被保留为原始字符串。

### 常用环境变量

| 环境变量 | 对应配置文件 | 说明 |
|----------|-------------|------|
| `OPENAI_API_KEY` | `Providers/openai.yaml` | OpenAI API Key |
| `ANTHROPIC_API_KEY` | `Providers/anthropic.yaml` | Claude API Key |
| `DEEPSEEK_API_KEY` | `Providers/deepseek.yaml` | DeepSeek API Key |
| `GLM_API_KEY` | `Providers/glm.yaml` | 智谱 GLM API Key |
| `MIMO_API_KEY` | `Providers/mimo.yaml` | 米莫 AI API Key |
| `DASHSCOPE_API_KEY` | `Providers/qwen.yaml` | 通义千问 API Key |
| `HUNYUAN_API_KEY` | `Providers/hunyuan.yaml` | 腾讯混元 API Key |
| `YUAN_TELEGRAM_BOT_TOKEN` | `Channels/telegram.yaml` | Telegram Bot Token |
| `DISCORD_BOT_TOKEN` | `Channels/discord.yaml` | Discord Bot Token |
| `DISCORD_PUBLIC_KEY` | `Channels/discord.yaml` | Discord 公钥 |
| `WECOM_CORP_ID` | `Channels/wecom.yaml` | 企业微信 Corp ID |
| `WECOM_CORP_SECRET` | `Channels/wecom.yaml` | 企业微信 Corp Secret |
| `WECOM_AGENT_ID` | `Channels/wecom.yaml` | 企业微信 Agent ID |
| `WECOM_TOKEN` | `Channels/wecom.yaml` | 企业微信回调 Token |
| `WECOM_ENCODING_AES_KEY` | `Channels/wecom.yaml` | 企业微信 EncodingAESKey |
| `AZURE_SPEECH_KEY` | `tts.yaml` | Azure 语音服务密钥 |
| `YUAN_DB_MYSQL_PASSWORD` | `database.yaml` | MySQL 密码 |
| `YUAN_DB_NEO4J_PASSWORD` | `database.yaml` | Neo4j 密码 |
| `YUANBOT_REDIS_URL` | `database.yaml` / `serverless.yaml` | Redis 连接 URL |
| `YUANBOT_CONFIG_PATH` | — | 自定义配置文件路径 |

---

## 配置热重载

YuanBot 使用 ConfigWatcher 轮询检测配置文件变更，支持以下文件的热重载（修改后自动生效，无需重启）：

- `configs/Providers/*.yaml` — AI 提供商配置
- `configs/Channels/*.yaml` — 消息通道配置
- `configs/Plugins/skills/*.yaml` — 技能配置
- `configs/Plugins/tools/*.yaml` — 工具配置

以下配置修改后需要重启服务：

- `configs/bot.yaml` — 主配置
- `configs/database.yaml` — 数据库配置
- `configs/memory.yaml` — 记忆系统配置
- `configs/tts.yaml` — TTS 配置

---

## 快速开始

### 最小配置

仅需配置一个 AI 提供商即可启动：

```bash
# 1. 设置 API Key
export OPENAI_API_KEY="sk-your-key"

# 2. 启动服务（使用默认配置）
python -m yuanbot
```

### 切换提供商

修改 `bot.yaml` 中的 `ai.default_provider`，并在 `Providers/` 下确保对应文件存在且 `enabled: true`：

```yaml
# bot.yaml
ai:
  default_provider: "deepseek"
```

```yaml
# Providers/deepseek.yaml
provider_id: deepseek
enabled: true
config:
  api_key: "${DEEPSEEK_API_KEY}"
  ...
```

### 启用新通道

在 `Channels/` 下创建或编辑对应 YAML 文件，设置 `enabled: true` 并填写必要凭据：

```yaml
# Channels/telegram.yaml
adapter: telegram
enabled: true
config:
  bot_token: "${YUAN_TELEGRAM_BOT_TOKEN}"
```

### 切换人设

修改 `bot.yaml` 中的 `persona.id`：

```yaml
persona:
  id: "cheerful"   # 对应 Personas/cheerful.yaml
```
