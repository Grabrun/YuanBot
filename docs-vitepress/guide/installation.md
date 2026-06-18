# 安装指南

> **推荐使用虚拟环境 + uv 包管理器**，隔离干净、速度极快。

## 环境要求

| 项目 | 要求 |
|------|------|
| Python | **3.12 或 3.13** |
| 操作系统 | Linux / macOS / Windows |
| Git | 用于克隆源码和自动更新 |
| 内存 | 建议 ≥ 2GB（运行本地模型 ≥ 8GB） |
| AI API Key | 至少配置一个 AI 提供商（DeepSeek / OpenAI / Claude） |

---

## 方式一：源码安装（推荐）

完整的 YuanBot 只能**源码安装**，因为需要配置文件目录结构和可选扩展包。

### 1. 克隆仓库

```bash
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot
```

### 2. 创建虚拟环境

::: code-group

```bash [Linux / macOS]
python3 -m venv .venv
source .venv/bin/activate
```

```powershell [Windows]
python -m venv .venv
.venv\Scripts\activate
```

:::

> 💡 **提示**：激活虚拟环境后，命令提示符前会出现 `(.venv)` 标识。

### 3. 安装核心依赖

```bash
pip install -e .
```

验证安装：
```bash
yuanbot version
# 输出: yuanbot v1.2.2
```

### 4. 按需安装扩展

YuanBot 使用 **Optional Dependencies (extras)** 管理可选功能：

| Extra | 功能 | 安装命令 |
|-------|------|---------|
| `cli` | TUI 终端界面 + `rich` 增强输出 | `pip install -e ".[cli]"` |
| `openai` | OpenAI GPT 模型支持 | `pip install -e ".[openai]"` |
| `anthropic` | Anthropic Claude 支持 | `pip install -e ".[anthropic]"` |
| `tts` | 语音合成（Edge TTS / Piper） | `pip install -e ".[tts]"` |
| `wechat` | 微信 iLink 通道 | `pip install -e ".[wechat]"` |
| `discord` | Discord 机器人（需要 websockets） | `pip install -e ".[discord]"` |
| `qq` | QQ 官方 API 机器人 | `pip install -e ".[qq]"` |
| `mysql` | MySQL 数据库支持 | `pip install -e ".[mysql]"` |
| `redis` | Redis 缓存/队列 | `pip install -e ".[redis]"` |
| `milvus` | Milvus 向量数据库 | `pip install -e ".[milvus]"` |
| `qdrant` | Qdrant 向量数据库 | `pip install -e ".[qdrant]"` |
| `graph` | 图数据库（Kuzu / Neo4j） | `pip install -e ".[graph]"` |
| `onnx` | 本地 ONNX 意图分类模型 | `pip install -e ".[onnx]"` |
| `jwt` | JWT 认证 | `pip install -e ".[jwt]"` |
| `grpc` | gRPC 沙箱（工具安全执行） | `pip install -e ".[grpc]"` |
| `wasm` | WebAssembly 沙箱 | `pip install -e ".[wasm]"` |
| `serverless` | Serverless 部署 | `pip install -e ".[serverless]"` |

常用组合：

::: code-group

```bash [Linux / macOS — 完整 TUI + AI]
pip install -e ".[cli,openai,anthropic]"
```

```powershell [Windows — 完整 TUI + AI]
pip install -e ".[cli,openai,anthropic]"
```

```bash [全部安装]
pip install -e ".[all]"
```

:::

### 5. 配置 AI 提供商

```bash
# 一键安装引导（交互式）
yuanbot install
```

或手动编辑 `configs/Providers/deepseek.yaml`：
```yaml
provider_id: deepseek
name: "DeepSeek"
adapter: deepseek
enabled: true
config:
  api_key: "sk-你的API密钥"
  base_url: "https://api.deepseek.com"
  models:
    - id: deepseek-v4-flash
      type: chat
      max_tokens: 128000
  default_model: deepseek-v4-flash
```

> 💡 支持 `${ENV_VAR}` 环境变量占位符，例如：`api_key: "${DEEPSEEK_API_KEY}"`

---

## 方式二：yuanbot-cli 一键安装（适合新用户）

```bash
pip install yuanbot-cli
yuanbot install
```

CLI 会引导你完成：
1. 克隆源码 + 创建虚拟环境
2. 选择 AI 提供商并填入 API Key
3. 配置消息通道（微信/QQ/Telegram 等）
4. 生成配置文件

---

## 方式三：Docker 部署（适合服务器）

```bash
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot
cp .env.example .env
# 编辑 .env 填入 API Key
docker-compose up -d
```

> ⚠️ Docker 方式不支持 TUI 界面和部分通道适配器。

---

## 验证安装

```bash
# 查看版本
yuanbot version

# 系统诊断（检查所有配置和依赖）
yuanbot doctor

# 启动服务
yuanbot start

# TUI 终端界面（需安装 cli extra）
yuanbot tui
```

---

## 常见问题

### Q: Windows 上报 "gbk codec can't decode byte"

**原因**：YAML 配置文件包含中文，Windows 默认编码 GBK 不兼容 UTF-8。
**解决**：已从 v1.2.2 起全面修复。如有问题请升级：`pip install -e . --upgrade`

### Q: 「rich 模块未找到」

**原因**：TUI 功能需要 `cli` extra。
**解决**：`pip install -e ".[cli]"`

### Q: 如何更新到最新版？

```bash
# 源码安装的
cd YuanBot
git pull
source .venv/bin/activate  # Linux
# 或 .venv\Scripts\activate  # Windows
pip install -e . --upgrade

# 或使用 yuanbot-cli
yuanbot update
```

### Q: 使用 uv 代替 pip？

```bash
# 安装 uv
pip install uv

# 安装依赖（速度比 pip 快 10-100x）
uv sync --all-extras

# 只安装特定 extras
uv sync --extra cli --extra openai
```
