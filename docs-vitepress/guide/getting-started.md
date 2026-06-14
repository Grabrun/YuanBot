# 快速开始指南

本指南帮助你在 5 分钟内完成 YuanBot 的安装、配置和首次运行。

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

## 安装

### 源码安装（推荐）

::: code-group

```bash [Linux / macOS]
# 1. 克隆仓库
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot

# 2. 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 3. 安装依赖
pip install -e ".[dev]"

# 4. 验证
yuanbot version
```

```powershell [Windows]
# 1. 克隆仓库
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot

# 2. 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate

# 3. 安装依赖
pip install -e ".[dev]"

# 4. 验证
yuanbot version
```

:::

### Docker 部署（推荐生产）

```bash
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot
cp .env.example .env
docker-compose up -d
```

## 配置

```bash
yuanbot config init
```

生成的目录结构：

```
configs/
├── bot.yaml              # 主配置
├── database.yaml         # 数据库连接配置
├── memory.yaml           # 记忆系统参数
├── tts.yaml              # 语音合成配置
├── Providers/            # AI 提供商配置
└── Channels/             # 消息通道配置
```

::: tip
建议通过环境变量传入 API Key，避免硬编码：

```bash
export OPENAI_API_KEY="sk-..."
```
:::

## 启动

```bash
yuanbot start
```

其他方式：

```bash
python -m yuanbot          # 等价于 yuanbot start
yuanbot tui                # TUI 终端界面
yuanbot webui              # 独立 WebUI
docker-compose up -d       # Docker 后台启动
```

## 验证服务

```bash
curl http://localhost:8000/healthz
# → {"status":"ok"}
```

## CLI 命令速查

| 命令 | 用途 |
|------|------|
| `yuanbot start` | 启动服务 |
| `yuanbot tui` | TUI 终端界面 |
| `yuanbot webui` | WebUI |
| `yuanbot doctor` | 系统诊断 |
| `yuanbot version` | 查看版本 |
| `yuanbot config show` | 查看配置 |
| `yuanbot provider list` | 列出 AI 提供商 |
| `yuanbot persona list` | 列出人设 |
| `yuanbot memory stats` | 记忆统计 |
| `yuanbot logs` | 查看日志 |

## 常见问题

### 找不到 `yuanbot` 命令

确认已激活虚拟环境：

```bash
which yuanbot
```

### AI Provider 连接失败

1. 检查 API Key 是否正确
2. 确认网络可访问端点
3. 运行 `yuanbot doctor` 诊断

### 端口 8000 被占用

```bash
yuanbot start --port 8080
```

## 下一步

- [配置说明](./configuration) — 所有配置项详解
- [API 参考](../api/reference) — HTTP / WebSocket 接口文档
- [参与贡献](../community/contributing) — 为 YuanBot 添砖加瓦
