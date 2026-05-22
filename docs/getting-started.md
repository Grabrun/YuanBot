# 快速开始指南

本指南将帮助你从零开始安装、配置并运行 YuanBot。

---

## 环境要求

### 必需

| 依赖 | 版本要求 | 说明 |
|------|----------|------|
| Python | >= 3.12 | 核心运行环境 |
| pip | 最新版 | 包管理器 |
| AI 提供商 API Key | — | OpenAI / DeepSeek / Claude 任选其一 |

### 可选

| 依赖 | 说明 |
|------|------|
| Redis | 工作记忆缓存、会话状态（不安装时使用内存缓存） |
| Docker | 容器化部署 |
| MySQL | 生产环境关系数据库（默认使用 SQLite） |

---

## 安装步骤

### 方式一：pip 安装（推荐开发）

```bash
# 1. 克隆项目
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot

# 2. 创建虚拟环境（推荐）
python3.12 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# 3. 安装（包含开发工具）
pip install -e ".[dev]"

# 4. 验证安装
yuanbot version
```

### 方式二：Docker 安装（推荐生产）

```bash
# 1. 克隆项目
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot

# 2. 配置环境变量
cp .env.example .env

# 3. 编辑 .env 填入 API Key
# YUAN_AI_API_KEY=sk-your-api-key-here

# 4. 构建并启动
docker-compose up -d

# 5. 验证
curl http://localhost:8000/healthz
```

### 方式三：仅安装核心包

```bash
pip install yuanbot

# 如需特定提供商支持
pip install "yuanbot[openai]"
pip install "yuanbot[anthropic]"
pip install "yuanbot[all-providers]"

# 安装所有可选依赖
pip install "yuanbot[all]"
```

---

## 配置文件

### 初始化配置目录

```bash
yuanbot config init
```

这会在当前目录创建完整的 `configs/` 目录结构：

```
configs/
├── bot.yaml              # 主配置
├── database.yaml         # 数据库配置
├── memory.yaml           # 记忆系统参数
├── Providers/
│   ├── openai.yaml       # OpenAI 配置
│   ├── deepseek.yaml     # DeepSeek 配置
│   ├── claude.yaml       # Claude 配置
│   └── ollama.yaml       # Ollama 本地模型配置
└── Channels/
    ├── webchat.yaml      # Web Chat 配置
    ├── telegram.yaml     # Telegram 配置
    ├── discord.yaml      # Discord 配置
    └── wecom.yaml        # 企业微信配置
```

### 配置 AI 提供商

编辑 `configs/Providers/openai.yaml`，填入你的 API Key：

```yaml
provider_id: "openai"
display_name: "OpenAI"
enabled: true
default: true

api:
  base_url: "https://api.openai.com/v1"
  api_key: "sk-your-api-key-here"  # ← 填入你的 Key
  timeout: 60
  max_retries: 3

models:
  - id: "gpt-4o"
    type: "chat"
    default: true
    max_tokens: 128000
    supports_tools: true
    supports_streaming: true
```

或者使用环境变量（推荐）：

```bash
# .env 文件
YUAN_AI_OPENAI_API_KEY=sk-your-api-key-here
```

```yaml
# openai.yaml 中使用环境变量引用
api:
  api_key: "${YUAN_AI_OPENAI_API_KEY}"
```

### 配置消息通道

默认启用 Web Chat 通道，无需额外配置。如需 Telegram：

编辑 `configs/Channels/telegram.yaml`：

```yaml
platform: "telegram"
display_name: "Telegram"
enabled: true  # ← 改为 true

config:
  bot_token: "${YUAN_TELEGRAM_BOT_TOKEN}"  # 从 @BotFather 获取
```

---

## 第一次运行

### 启动服务

```bash
# 直接启动
yuanbot start

# 指定端口
yuanbot start --port 8080

# 开发模式（代码变更自动重载）
yuanbot start --reload
```

启动成功后你会看到：

```
🌸 缘·Bot (YuanBot) — 启动中...

  版本:     v1.0.0
  地址:     0.0.0.0:8000
  AI 提供商: openai
  调试模式:  关
  热重载:    关

🌸 YuanBot 启动完成（含主动陪伴系统 + 配置热加载）
```

### 验证服务

```bash
# 健康检查
curl http://localhost:8000/healthz
# {"status":"ok"}

# 详细健康状态
curl http://localhost:8000/health
# {"status":"ok","version":"1.0.0","ai_service":{...}}
```

### 发送第一条消息

使用 curl 测试对话接口：

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user",
    "message": "你好，我是小明"
  }'
```

响应示例：

```json
{
  "content": "你好小明！很高兴认识你～有什么我可以帮你的吗？",
  "proactive_followups": []
}
```

### WebSocket 连接

```javascript
const ws = new WebSocket("ws://localhost:8000/ws");

ws.onopen = () => {
  ws.send(JSON.stringify({
    type: "message",
    text: "你好"
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data);
};
```

---

## 系统诊断

运行 `yuanbot doctor` 检查系统状态：

```bash
yuanbot doctor
```

输出示例：

```
🌸 缘·Bot (YuanBot) — 系统诊断

  ✅ Python 3.12.0
  ✅ AI 提供商 [openai] API Key 已配置
  ✅ openai 库已安装
  ✅ Redis 连接正常 (redis://localhost:6379/0)
  ✅ SQLite 数据库 (sqlite:///data/yuanbot.db)
  ✅ 配置目录 configs/ (12 个 YAML 文件)
  ✅ 依赖 pyyaml ✓
  ✅ 依赖 python-dotenv ✓

  🎉 系统状态良好！
```

---

## 常见问题 FAQ

### Q: 启动时报 `ModuleNotFoundError: No module named 'yuanbot'`

**A:** 确保已正确安装项目：

```bash
pip install -e ".[dev]"
```

如果使用虚拟环境，确认已激活：

```bash
source .venv/bin/activate
```

### Q: 连接 AI 提供商失败

**A:** 检查以下几点：

1. API Key 是否正确配置
2. 网络是否可以访问 API 端点
3. 运行 `yuanbot doctor` 查看诊断信息

```bash
# 测试 OpenAI 连接
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer sk-your-key"
```

### Q: Redis 连接失败

**A:** Redis 是可选依赖。如果未安装 Redis：

1. 安装 Redis：`sudo apt install redis-server` 或 `docker run -d -p 6379:6379 redis:7-alpine`
2. 或者忽略警告，YuanBot 会自动降级为内存缓存

### Q: 如何切换 AI 提供商？

**A:** 编辑 `configs/bot.yaml`：

```yaml
ai:
  default_provider: "deepseek"  # 改为其他提供商
  default_model: "deepseek-chat"
```

并在对应的 `configs/Providers/` 文件中配置 API Key。

### Q: 如何查看记忆数据？

**A:** 使用 CLI 或 API：

```bash
# CLI 方式
yuanbot memory stats

# API 方式
curl http://localhost:8000/api/memory/test_user
```

### Q: 如何清除某个用户的记忆？

**A:**

```bash
yuanbot memory clear --user-id test_user
```

### Q: WebSocket 连接断开

**A:** 检查：

1. 服务是否正常运行（`curl http://localhost:8000/healthz`）
2. 防火墙是否放行了对应端口
3. 如果使用 Nginx 反向代理，确保配置了 WebSocket 支持：

```nginx
location /ws {
    proxy_pass http://localhost:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 3600s;
}
```

### Q: 配置修改后如何生效？

**A:** YuanBot 支持配置热加载：

- `configs/Providers/*.yaml` 和 `configs/Channels/*.yaml` 的修改会自动检测并重载
- `configs/bot.yaml` 的修改需要重启服务

```bash
# 重启服务
# Ctrl+C 停止后重新启动
yuanbot start
```

### Q: 如何在生产环境使用 MySQL？

**A:** 编辑 `configs/database.yaml`：

```yaml
relational:
  type: "mysql"
  mysql:
    host: "your-mysql-host"
    port: 3306
    database: "yuanbot"
    user: "yuanbot"
    password: "${YUAN_DB_MYSQL_PASSWORD}"
    pool_size: 10
```

安装 MySQL 依赖：

```bash
pip install "yuanbot[mysql]"
```

---

## 下一步

- 阅读 [配置参考](configuration.md) 了解所有配置选项
- 阅读 [API 参考](api-reference.md) 了解所有 API 端点
- 阅读 [部署指南](deployment.md) 了解生产环境部署
- 阅读 [架构文档](architecture-v1.4.md) 了解系统设计
