# 开发指南

## 环境准备

### 系统要求

- Python 3.12+
- Redis（可选，用于缓存和事件队列）
- PostgreSQL / SQLite（数据存储）

### 快速开始

```bash
# 克隆项目
git clone https://github.com/your-org/yuanbot.git
cd yuanbot

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate

# 安装开发依赖
pip install -e ".[dev]"

# 复制环境配置
cp .env.example .env
```

### 项目结构

```
yuanbot/
├── src/yuanbot/            # 源代码
│   ├── adapters/           # 适配器层
│   │   ├── ai/             # AI 提供商适配器
│   │   └── channel/        # 消息通道适配器
│   ├── capabilities/       # 能力系统（gRPC sandbox）
│   ├── core/               # 核心类型和接口
│   ├── deployment/         # 部署支持（serverless）
│   ├── gateway/            # 统一网关
│   ├── infrastructure/     # 基础设施（数据库、缓存、事件队列）
│   ├── memory/             # 记忆系统
│   ├── orchestrator/       # 编排引擎
│   ├── persona/            # 人格系统
│   ├── proactive/          # 主动陪伴系统
│   ├── providers/          # AI 提供商管理
│   ├── services/           # 业务服务
│   ├── skills/             # 技能管理
│   ├── tools/              # 工具管理
│   ├── app.py              # FastAPI 应用入口
│   ├── cli.py              # CLI 入口
│   └── config.py           # 配置管理
├── tests/                  # 测试
├── configs/                # 配置文件
├── docs/                   # 文档
└── pyproject.toml          # 项目配置
```

## 开发工作流

### 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行特定模块测试
pytest tests/test_memory/ -v

# 带覆盖率
pytest tests/ --cov=yuanbot --cov-report=term-missing

# 只运行失败的测试
pytest tests/ --lf
```

### 代码质量检查

```bash
# Lint 检查
ruff check src/ tests/

# 自动修复
ruff check --fix src/ tests/

# 格式化
ruff format src/ tests/
```

### 运行服务

```bash
# 开发模式
uvicorn yuanbot.app:create_app --factory --reload

# 或使用 CLI
yuanbot serve --reload
```

## 核心概念

### 适配器模式

YuanBot 使用适配器模式统一不同 AI 提供商和消息通道的接口：

- **AI 适配器** (`adapters/ai/`): 封装 OpenAI、Claude、DeepSeek、Ollama 等
- **通道适配器** (`adapters/channel/`): 封装 Telegram、Discord、企业微信、WebChat 等

所有适配器实现 `core/interfaces.py` 中定义的抽象接口。

### 记忆系统

三层记忆架构：

1. **工作记忆**: 当前对话上下文（短期）
2. **情景记忆**: 对话事件记录（中期，向量存储）
3. **事实记忆**: 用户画像和偏好（长期，结构化存储）

### 编排引擎

`OrchestratorEngine` 是消息处理的核心：

1. 接收用户消息
2. 构建上下文（记忆 + 人格 + 能力）
3. 决策引擎选择响应策略
4. 调用 AI 服务生成回复
5. 更新记忆和情感状态

## 添加新的 AI 提供商

1. 在 `src/yuanbot/adapters/ai/` 创建适配器文件
2. 实现 `AIProviderAdapter` 接口
3. 在 `configs/Providers/` 添加配置文件
4. 在 `tests/test_adapters/` 添加测试

```python
# 示例: adapters/ai/my_provider.py
from yuanbot.adapters.ai.base import BaseAIAdapter

class MyProviderAdapter(BaseAIAdapter):
    @property
    def provider_id(self) -> str:
        return "my_provider"

    @property
    def supported_models(self) -> list[str]:
        return ["my-model-v1"]

    async def chat_completion(self, messages, **kwargs):
        # 实现对话补全
        ...
```

## 添加新的消息通道

1. 在 `src/yuanbot/adapters/channel/` 创建适配器文件
2. 实现 `ChannelAdapter` 接口
3. 在 `configs/Channels/` 添加配置文件
4. 编写测试

## 配置系统

配置文件位于 `configs/` 目录，支持热加载：

- `default.yaml`: 全局默认配置
- `bot.yaml`: 机器人基础配置
- `Providers/*.yaml`: AI 提供商配置
- `Channels/*.yaml`: 消息通道配置
- `Personas/*.yaml`: 人设配置

配置变更会自动检测并热加载，无需重启服务。

## 扩展开发

参见 [YuanBot Extension Standard (Y.E.S.)](../src/yuanbot/services/extension_standard.py)。

使用脚手架快速创建扩展：

```python
from yuanbot.services.extension_standard import create_scaffold

create_scaffold("skill", "my_skill", "extensions/")
```

## 调试技巧

### 日志

YuanBot 使用 `structlog` 进行结构化日志：

```python
import structlog
logger = structlog.get_logger(__name__)
logger.info("event_name", key="value")
```

### 指标

访问 `/metrics` 端点查看 Prometheus 指标。

### 健康检查

- `/healthz`: 存活探针
- `/readyz`: 就绪探针（检查所有依赖）
