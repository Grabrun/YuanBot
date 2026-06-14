# 安装指南

YuanBot 提供多种安装方式，满足不同场景需求。

## 环境要求

- **Python 3.12+** — 核心运行时
- **pip** 或 **uv** — 包管理器（推荐 uv）
- **AI Provider API Key** — 至少配置一个 AI 提供商

## pip 安装

```bash
# 核心功能
pip install yuanbot

# 全部可选依赖
pip install "yuanbot[all]"
```

按需安装特定扩展：

```bash
pip install "yuanbot[openai]"       # OpenAI 支持
pip install "yuanbot[anthropic]"    # Claude 支持
pip install "yuanbot[cli]"          # 完整 CLI
pip install "yuanbot[mysql]"        # MySQL 数据库
```

## 源码安装

```bash
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot

# 使用 uv 安装（推荐）
uv sync --all-extras

# 验证
yuanbot version
```

## Docker 部署

```bash
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot

cp .env.example .env
# 编辑 .env，填入 API Key

docker-compose up -d
```

## 验证安装

```bash
# 查看版本
yuanbot version

# 系统诊断
yuanbot doctor
```

安装成功会显示版本号和系统状态信息。
