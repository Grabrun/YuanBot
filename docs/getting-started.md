---
title: 快速开始指南
description: 5 分钟完成 YuanBot 安装、配置和首次运行
---

# 快速开始指南

本指南帮助你在 5 分钟内完成 YuanBot 的安装、配置和首次运行。

---

## 环境要求

| 要求 | 最低版本 | 说明 |
|------|----------|------|
| Python | 3.12+ | 核心运行时 |
| 包管理器 | pip / uv | uv 推荐用于源码开发 |
| AI Provider API Key | — | OpenAI / DeepSeek / Claude 等，至少配一个 |

可选组件（按需安装）：

- **Redis** — 工作记忆缓存和会话状态（未安装时自动降级为内存缓存）
- **MySQL** — 生产环境关系数据库（默认使用 SQLite）
- **Docker** — 容器化部署

---

## 安装

=== "源码安装（推荐）"

    ```bash
    # 1. 克隆仓库
    git clone https://github.com/Grabrun/YuanBot.git
    cd YuanBot

    # 2. 创建虚拟环境（Python 3.12+）
    #    如果 python3 -m venv 没反应，先装 sudo apt install python3-venv python3-full -y
    python3 -m venv .venv
    source .venv/bin/activate

    # 3. 安装依赖（推荐 uv）
    pip install -e ".[dev]"

    # 或用 uv
    # pip install uv
    # uv sync --all-extras
    ```

    安装特定扩展：

    ```bash
    pip install -e ".[openai]"       # OpenAI 支持
    pip install -e ".[anthropic]"    # Claude 支持
    pip install -e ".[cli]"          # 完整 CLI
    pip install -e ".[mysql]"        # MySQL 数据库
    ```

=== "Docker 部署（推荐生产）"

    ```bash
    git clone https://github.com/Grabrun/YuanBot.git
    cd YuanBot
    cp .env.example .env
    docker-compose up -d
    ```

    # 验证安装
    yuanbot version
    ```

=== "Docker 部署（推荐生产）"

    ```bash
    git clone https://github.com/Grabrun/YuanBot.git
    cd YuanBot

    # 配置环境变量
    cp .env.example .env
    # 编辑 .env，填入 API Key

    # 启动
    docker-compose up -d
    ```

---

## 配置

### 初始化配置目录

```bash
yuanbot config init
```

生成的目录结构：

```
configs/
├── bot.yaml              # 主配置（模型选择、日志级别等）
├── database.yaml         # 数据库连接配置
├── memory.yaml           # 记忆系统参数
├── tts.yaml              # 语音合成配置
├── Providers/            # AI 提供商配置
│   ├── openai.yaml
│   ├── deepseek.yaml
│   ├── claude.yaml
│   ├── glm.yaml
│   ├── mimo.yaml
│   ├── qwen.yaml
│   ├── hunyuan.yaml
│   └── ollama.yaml       # 本地模型
└── Channels/             # 消息通道配置
    ├── webchat.yaml       # 默认启用
    ├── telegram.yaml
    ├── discord.yaml
    ├── wecom.yaml
    ├── wechat.yaml
    ├── qq.yaml
    ├── dingtalk.yaml
    └── feishu.yaml
```

### 配置 AI 提供商（必须）

至少配置一个提供商。以 OpenAI 为例，编辑 `configs/Providers/openai.yaml`：

```yaml
provider_id: "openai"
display_name: "OpenAI"
enabled: true
default: true

api:
  base_url: "https://api.openai.com/v1"
  api_key: "sk-…"        # 填入你的 Key
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

> **安全提示**：建议通过环境变量传入 API Key，避免硬编码：
>
> ```bash
> export OPENAI_API_KEY="sk-…"
> ```
>
> ```yaml
> api:
>   api_key: "${OPENAI_API_KEY}"
> ```

### 配置消息通道（可选）

默认已启用 Web Chat，无需额外配置。如需 Telegram：

```yaml
# configs/Channels/telegram.yaml
platform: "telegram"
enabled: true
config:
  bot_token: "${YUAN_TELEGRAM_BOT_TOKEN}"
```

### 环境变量速查

| 变量名 | 用途 |
|--------|------|
| `YUANBOT_ADMIN_PASSWORD` | 首次启动时的管理员密码 |
| `OPENAI_API_KEY` | OpenAI API Key |
| `YUAN_TELEGRAM_BOT_TOKEN` | Telegram Bot Token |
| `YUAN_DB_MYSQL_PASSWORD` | MySQL 密码 |

---

## 启动

### 命令行启动

```bash
yuanbot start
```

启动成功输出示例：

```
🌸 缘·Bot (YuanBot) — 启动中...

  版本:     v1.1.1
  地址:     0.0.0.0:8000
  AI 提供商: openai
  调试模式:  关

🌸 YuanBot 启动完成
```

常用启动参数：

```bash
yuanbot start --port 8080      # 指定端口
yuanbot start --reload          # 开发模式，代码变更自动重载
```

### 其他启动方式

```bash
python -m yuanbot               # 等价于 yuanbot start
yuanbot tui                     # TUI 终端交互界面
yuanbot webui                   # 独立 WebUI 模式
docker-compose up -d            # Docker 后台启动
```

### 验证服务

```bash
# 健康检查
curl http://localhost:8000/healthz
# → {"status":"ok"}

# 发送第一条消息
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test_user", "message": "你好"}'
```

首次使用可在浏览器打开 **http://localhost:8000**，使用 `admin` 和 `YUANBOT_ADMIN_PASSWORD` 环境变量设置的密码登录 WebUI。

---

## CLI 命令速查

| 命令 | 用途 |
|------|------|
| `yuanbot start` | 启动服务 |
| `yuanbot tui` | 启动 TUI 终端界面 |
| `yuanbot webui` | 启动 WebUI |
| `yuanbot doctor` | 系统诊断 |
| `yuanbot version` | 查看版本 |
| `yuanbot config show` | 查看当前配置 |
| `yuanbot config init` | 初始化配置目录 |
| `yuanbot provider list` | 列出 AI 提供商 |
| `yuanbot provider set <name>` | 设置默认提供商 |
| `yuanbot persona list` | 列出可用人设 |
| `yuanbot persona switch <name>` | 切换人设 |
| `yuanbot memory stats` | 查看记忆统计 |
| `yuanbot memory clear --user-id <id>` | 清除用户记忆 |
| `yuanbot logs` | 查看服务日志 |
| `yuanbot create` | 创建扩展脚手架 |
| `yuanbot validate` | 验证扩展 |
| `yuanbot install <name>` | 安装扩展 |
| `yuanbot search <keyword>` | 搜索扩展 |

---

## 常见问题

### 安装后找不到 `yuanbot` 命令

确认已激活虚拟环境，且使用 `pip install -e .` 或 `uv sync` 安装：

```bash
# 检查安装位置
which yuanbot
# 应输出类似: /path/to/.venv/bin/yuanbot

# 如果使用 uv，确认在项目目录下
uv sync --all-extras
```

### 连接 AI Provider 失败

1. 检查 API Key 是否正确填写
2. 确认网络可访问对应端点（国内访问 OpenAI 可能需要代理）
3. 运行诊断命令查看详细信息：

```bash
yuanbot doctor
```

### Redis 连接失败

Redis 为可选组件。未安装时 YuanBot 自动降级为内存缓存，不影响核心功能。如需使用：

```bash
# Ubuntu/Debian
sudo apt install redis-server

# 或 Docker 启动
docker run -d -p 6379:6379 redis:7-alpine
```

### 端口 8000 被占用

```bash
# 查看占用进程
lsof -i :8000

# 换端口启动
yuanbot start --port 8080
```

### 配置修改后未生效

- `configs/Providers/*.yaml` 和 `configs/Channels/*.yaml` 的修改支持热加载，无需重启
- `configs/bot.yaml` 的修改需要重启服务

### 如何切换到其他 AI Provider

编辑 `configs/bot.yaml`：

```yaml
ai:
  default_provider: "deepseek"
  default_model: "deepseek-chat"
```

同时确保对应的 `configs/Providers/deepseek.yaml` 已配置并 `enabled: true`。

### WebSocket 连接断开

如果是 Nginx 反向代理，需配置 WebSocket 支持：

```nginx
location /ws {
    proxy_pass http://localhost:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 3600s;
}
```

---

## 下一步

- [配置参考](configuration.md) — 所有配置项详解
- [API 参考](api-reference.md) — HTTP / WebSocket 接口文档
- [部署指南](deployment.md) — 生产环境部署方案
- [架构文档](architecture-v1.5.md) — 系统设计与模块说明
