# 安装指南

YuanBot 提供多种安装方式，满足不同场景需求。

## 环境要求

- **Python 3.12+** — 核心运行时
- **git** — 克隆源码
- **pip** 或 **uv** — 包管理器（推荐 uv）
- **AI Provider API Key** — 至少配置一个 AI 提供商

## 源码安装（推荐）

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

按需安装特定扩展：

::: code-group

```bash [Linux / macOS]
pip install -e ".[openai]"       # OpenAI 支持
pip install -e ".[anthropic]"    # Claude 支持
pip install -e ".[cli]"          # 完整 CLI
```

```powershell [Windows]
pip install -e ".\[openai]"       # OpenAI 支持
pip install -e ".\[anthropic]"    # Claude 支持
pip install -e ".\[cli]"          # 完整 CLI
```

:::

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
