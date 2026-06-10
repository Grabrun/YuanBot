---
title: AI 提供商适配系统
description: YuanBot AI 提供商适配系统 v1.4 详细设计
---

🌸 缘·Bot AI 提供商适配系统详细设计文档 (v1.4)

版本历史

| 版本 | 日期 | 修改内容 |
|------|------|----------|
| v1.0 | 2026-05-17 | 初始详细设计，基于总体架构 v1.4 |
---

1. 系统定位与目标

AI 提供商适配系统是 缘·Bot 的“语言皮层”，负责在核心决策系统与各种大语言模型后端之间建立抽象层。它使系统能够无感地在不同模型提供商之间切换，甚至同时使用多个提供商，实现真正的零供应商锁定。

核心目标：

· 接口统一：所有 LLM 调用（对话、流式、嵌入）均通过统一的抽象接口，业务逻辑无需关心后端差异。
· 供应商无关：支持 OpenAI、Anthropic、DeepSeek、Ollama 等，且可通过社区扩展支持任意模型。
· 模型显式管理：每个提供商配置包含明确的模型列表，通过 default 字段指定默认模型，支持细粒度选择。
· 安全隔离：API 密钥等凭证与核心业务逻辑严格隔离，支持文件配置和环境变量覆盖，仅活跃提供商的凭证被加载。
· 灵活切换：可以在运行时通过根配置文件或环境变量动态切换活跃的 AI 提供商和模型，无需重启。

---

2. 系统架构概览

```
┌──────────────────────────────────────────────────────────────┐
│                 AI 提供商适配系统                              │
├──────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌──────────────────────────────────────────────────────┐    │
│  │             适配器注册表 (Adapter Registry)            │    │
│  │  · 扫描 Providers/ 目录  · 加载适配器类  · 维护索引    │    │
│  └──────────────────────────┬───────────────────────────┘    │
│                              │                                 │
│  ┌──────────────────────────▼───────────────────────────┐    │
│  │             提供商管理器 (Provider Manager)            │    │
│  │  · 活跃提供商选择  · 模型列表解析  · 凭据加载          │    │
│  └───────┬──────────────────────────────────┬───────────┘    │
│          │                                  │                 │
│  ┌───────▼──────────┐              ┌────────▼────────────┐  │
│  │  对话适配器池     │              │  嵌入适配器池        │  │
│  │  Chat Pool       │              │  Embedding Pool     │  │
│  └───────┬──────────┘              └────────┬────────────┘  │
│          │                                  │                 │
│  ┌───────▼──────────────────────────────────▼────────────┐  │
│  │              统一适配器接口 (AIProviderAdapter)         │  │
│  │  · chat_completion()  · stream_chat()  · embed()      │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌──────────────────────────────────────────────────────┐    │
│  │          统一 AI API (向编排层暴露)                     │    │
│  │  · generate()  · generate_stream()  · get_embedding() │    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

设计原则：

· 适配器即插件：每个提供商的适配器是独立模块，遵循统一接口，可热插拔。
· 配置驱动：所有提供商的连接参数、模型列表由 configs/Providers/ 下的 YAML 文件定义。
· 惰性加载：只有被激活的提供商的适配器才会实例化，非活跃提供商的凭证不会进入内存。

---

3. 核心模块设计

3.1 统一适配器接口

所有 AI 提供商适配器必须实现 AIProviderAdapter 抽象基类。此接口定义了系统与 LLM 交互的最小契约：

```python
from abc import ABC, abstractmethod
from typing import List, Optional, AsyncIterator, Dict, Any
from dataclasses import dataclass

@dataclass
class Message:
    role: str  # "system", "user", "assistant", "tool"
    content: str

@dataclass
class ToolDefinition:
    """符合 OpenAI function calling 格式的工具定义"""
    type: str = "function"
    function: Dict[str, Any] = None

@dataclass
class ChatResponse:
    content: str
    tool_calls: Optional[List[Dict]] = None
    finish_reason: str = "stop"
    usage: Dict[str, int] = None  # {"prompt_tokens": ..., "completion_tokens": ...}

@dataclass
class ChatChunk:
    delta: str
    finish_reason: Optional[str] = None

class AIProviderAdapter(ABC):
    """AI 提供商适配器统一接口"""

    @abstractmethod
    async def chat_completion(
        self,
        messages: List[Message],
        model: str,
        tools: Optional[List[ToolDefinition]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ChatResponse:
        """发送对话请求并获取完整响应"""
        pass

    @abstractmethod
    async def stream_chat_completion(
        self,
        messages: List[Message],
        model: str,
        tools: Optional[List[ToolDefinition]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[ChatChunk]:
        """流式对话请求，返回异步迭代器"""
        pass

    @abstractmethod
    async def get_embedding(
        self,
        text: str,
        model: str,
    ) -> List[float]:
        """获取文本的向量嵌入"""
        pass

    @abstractmethod
    async def list_models(self) -> List[str]:
        """返回该提供商当前可用的模型列表（从配置中读取）"""
        pass

    @abstractmethod
    def get_max_context_length(self, model: str) -> int:
        """返回指定模型的最大上下文长度（Token 数）"""
        pass

    @abstractmethod
    def validate_config(self) -> bool:
        """验证配置有效性（如 API Key 格式）"""
        pass
```

所有适配器都必须实现上述方法，确保编排层可以透明调用。

3.2 适配器实现规范

一个具体的适配器（如 OpenAI 适配器）需要：

1. 继承 AIProviderAdapter。
2. 在构造函数中接收提供商配置字典，并初始化 HTTP 客户端。
3. 将内部调用翻译为相应提供商的 API 格式。
4. 处理错误与重试逻辑。

OpenAI 适配器示例结构：

```python
class OpenAIAdapter(AIProviderAdapter):
    def __init__(self, config: dict):
        self.api_key = config['api_key']
        self.base_url = config.get('base_url', 'https://api.openai.com/v1')
        self._models = config['models']  # 模型列表
        # 初始化 httpx 客户端...

    async def chat_completion(self, messages, model, tools=None, ...):
        # 构造请求体，调用 /chat/completions
        # 转换响应为 ChatResponse
        pass

    async def get_embedding(self, text, model):
        # 调用 /embeddings
        pass

    # ... 其他实现
```

3.3 配置与模型管理

配置文件存储位置：configs/Providers/

目录结构示例：

```
configs/Providers/
├── openai.yaml
├── claude.yaml
├── deepseek.yaml
└── ollama.yaml
```

每个 YAML 文件代表一个提供商，遵循统一的 Provider 配置 Schema：

```yaml
provider_id: openai           # 唯一标识
adapter: openai-adapter       # 适配器名称（对应类）
enabled: true                 # 是否启用
config:
  api_key: "sk-xxx"           # 敏感信息，可被环境变量覆盖
  base_url: "https://api.openai.com/v1"
  organization: "org-xxx"     # 可选
  models:                     # 模型列表（必须）
    - id: gpt-4o
      type: chat
      max_tokens: 128000
    - id: gpt-4o-mini
      type: chat
      max_tokens: 128000
    - id: text-embedding-3-small
      type: embedding
      dimension: 1536
  default: gpt-4o             # 该提供商的默认模型（必须在models中）
```

模型列表字段说明：

字段 类型 说明
id string 模型标识，与 API 调用时的 model 参数一致
type string 模型类型，chat（对话）或 embedding（嵌入）
max_tokens int 最大上下文长度
dimension int 仅嵌入模型，输出向量维度

default 字段：指定当使用该提供商且未显式指定模型时，默认使用的对话模型。若未配置，系统会选择列表中第一个 type: chat 的模型。

活跃提供商的选择：在根配置 configs/bot.yaml 中指定：

```yaml
ai:
  default_provider: openai   # 使用 openai 提供商的 default 模型
  embedding_provider: openai # 可选，专门用于嵌入的提供商，若未指定则与 default_provider 共用
```

系统启动时，加载所有 enabled: true 的提供商配置，但仅实例化 default_provider 和 embedding_provider 对应的适配器，其他提供商的凭证不会进入内存。

动态切换：环境变量 YUAN_AI_DEFAULT_PROVIDER 可覆盖根配置中的 default_provider，方便容器化部署时无感切换。

模型覆盖：当编排层调用 chat_completion 时，可传入 model 参数动态选择同一提供商下的其他模型（必须在 models 列表中），否则使用该提供商的 default 模型。

3.4 嵌入模型管理

系统需要向量嵌入功能用于记忆检索，嵌入模型同样通过提供商配置管理。

· 嵌入提供商的指定：bot.yaml 中的 embedding_provider 字段，若未指定则回退到 default_provider。
· 嵌入模型的选择：系统自动选取该提供商配置中第一个 type: embedding 的模型。也可以通过 bot.yaml 显式指定 embedding_model。
· 调用流程：记忆系统通过 AIAPI.get_embedding(text) 调用，AI API 层根据 embedding_provider 找到对应适配器，传入嵌入模型 ID。

示例：若 openai.yaml 中定义了 text-embedding-3-small，且 bot.yaml 设置 embedding_provider: openai，则记忆系统自动使用该模型生成向量。

3.5 安全凭证管理

安全是提供商适配系统的重中之重，因为涉及 API 密钥。

凭证加载优先级：

1. 环境变量：如果设置了 YUAN_AI_<PROVIDER>_API_KEY，则覆盖配置文件中的 api_key。
2. 配置文件：直接写在 configs/Providers/*.yaml 中（适用于本地受信环境）。
3. 密钥管理服务：未来可扩展对接 Vault 等。

安全措施：

· 惰性加载：只加载被激活的提供商的 API 密钥到内存。
· 内存安全：适配器实例中的密钥字段在对象销毁时显式清除。
· 日志脱敏：错误日志中绝不输出密钥。
· 文件权限：建议将 Providers/ 目录权限设为 600，并加入 .gitignore。

---

4. 预集成提供商

v1.4 版本预集成以下主流 AI 提供商，并提供开箱即用的适配器：

4.1 OpenAI

· 适配器类：openai-adapter
· 支持模型：GPT-4o, GPT-4o-mini, GPT-4.1 系列, 文本嵌入模型
· 特点：完整支持 function calling，流式响应，高并发。
· 配置示例：

```yaml
provider_id: openai
adapter: openai-adapter
enabled: true
config:
  api_key: "sk-xxx"
  models:
    - id: gpt-4o
      type: chat
      max_tokens: 128000
    - id: text-embedding-3-small
      type: embedding
      dimension: 1536
  default: gpt-4o
```

4.2 Anthropic Claude

· 适配器类：claude-adapter
· 支持模型：Claude Opus 4, Claude Sonnet 4
· 特点：超长上下文（200K），优秀的指令遵循和安全性。
· 配置示例：

```yaml
provider_id: anthropic
adapter: claude-adapter
enabled: false
config:
  api_key: "sk-ant-xxx"
  models:
    - id: claude-sonnet-4-20250514
      type: chat
      max_tokens: 200000
  default: claude-sonnet-4-20250514
```

4.3 DeepSeek

· 适配器类：deepseek-adapter
· 支持模型：DeepSeek-V3, DeepSeek-R1
· 特点：高性价比，中文能力出色。
· 配置示例：

```yaml
provider_id: deepseek
adapter: deepseek-adapter
enabled: false
config:
  api_key: "sk-xxx"
  base_url: "https://api.deepseek.com"
  models:
    - id: deepseek-chat
      type: chat
      max_tokens: 128000
  default: deepseek-chat
```

4.4 Ollama (本地模型)

· 适配器类：ollama-adapter
· 支持模型：任何已拉取的本地模型（Llama 4, Qwen 3, Mistral 等）
· 特点：完全离线，隐私无虞，可自定义模型。
· 配置示例：

```yaml
provider_id: ollama
adapter: ollama-adapter
enabled: false
config:
  base_url: "http://localhost:11434"
  models:
    - id: qwen3:14b
      type: chat
      max_tokens: 32768
    - id: nomic-embed-text
      type: embedding
      dimension: 768
  default: qwen3:14b
```

---

5. 统一 AI API 层

在适配器之上，系统提供统一的 AIService 门面，供决策引擎和记忆系统使用：

```python
class AIService:
    """AI 服务统一接口"""

    def __init__(self, provider_manager):
        self.provider_manager = provider_manager

    async def generate(
        self,
        messages: List[Message],
        tools: Optional[List[ToolDefinition]] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ChatResponse:
        """非流式对话生成，自动选择提供者和模型"""
        provider, actual_model = self.provider_manager.resolve(model)
        return await provider.chat_completion(
            messages, actual_model, tools, temperature, max_tokens
        )

    async def generate_stream(
        self, messages, tools=None, model=None, ...
    ) -> AsyncIterator[ChatChunk]:
        """流式对话生成"""
        provider, actual_model = self.provider_manager.resolve(model)
        async for chunk in provider.stream_chat_completion(
            messages, actual_model, tools, ...
        ):
            yield chunk

    async def embed(self, text: str) -> List[float]:
        """文本嵌入"""
        emb_provider, emb_model = self.provider_manager.resolve_embedding()
        return await emb_provider.get_embedding(text, emb_model)
```

模型解析逻辑：

· 若 model 参数为 None，使用默认提供商的默认模型。
· 若 model 参数指定了模型 ID，且属于当前提供商，则使用该模型。
· 若 model 参数包含提供商前缀（如 openai/gpt-4o），则临时切换到对应提供商。

---

6. 社区开发标准

社区开发者可贡献新的 AI 提供商适配器，必须遵循 Y.E.S. 规范。

6.1 适配器包结构

```
yuanbot-ai-provider-xxx/
├── manifest.json          # 元数据
├── adapter.py             # 适配器主类
├── requirements.txt       # Python 依赖
├── README.md              # 使用文档
└── test_adapter.py        # 单元测试
```

manifest.json 示例：

```json
{
  "type": "ai_provider",
  "id": "openai-adapter",
  "name": "OpenAI 适配器",
  "version": "1.0.0",
  "author": "yuanbot-team",
  "description": "支持 OpenAI GPT-4o 等模型",
  "supported_models": ["gpt-4o", "gpt-4o-mini", "text-embedding-3-small"],
  "config_schema": {
    "type": "object",
    "properties": {
      "api_key": {"type": "string", "description": "OpenAI API Key"},
      "base_url": {"type": "string", "default": "https://api.openai.com/v1"}
    },
    "required": ["api_key"]
  }
}
```

6.2 开发流程

1. 使用 yuanbot-cli create --type ai_provider 生成脚手架。
2. 实现 AIProviderAdapter 的所有抽象方法。
3. 编写 manifest.json 和 README.md。
4. 提交 PR 到 yuanbot-extensions 仓库。
5. 通过 CI 验证（接口合规性、单元测试通过）。
6. 审核通过后上架社区市场。

---

7. 与外部系统的交互

7.1 与人格与行为决策系统

· 决策系统通过 AIService.generate() 发起对话。
· 上下文组装器构造的 messages 列表、Tools 定义直接传入。
· 返回的 ChatResponse 或流式 chunk 直接用于生成最终回复。

7.2 与记忆系统

· 记忆系统调用 AIService.embed() 获取文本向量，用于语义检索。
· 嵌入模型的切换对记忆系统完全透明。

7.3 与能力与工具扩展系统

· 工具定义以标准 ToolDefinition 格式传入 generate()，适配器负责转换为对应提供商的 function calling 格式（OpenAI 直接兼容，Claude 需要转换）。

---

8. 性能与可靠性

· 连接池：每个适配器维护一个 HTTP 连接池（httpx），复用连接减少延迟。
· 重试策略：自动重试网络超时（最多 3 次），指数退避。
· 熔断器：连续失败 5 次后，该提供商标记为不健康，暂停使用 30 秒，并通知管理员。
· 异步 I/O：所有网络请求基于 asyncio，不阻塞主线程。
· 速率限制：适配器可配置每秒钟最大请求数，超出则排队等待。

---

9. 扩展性蓝图

· 多模态支持：未来扩展接口支持图片/音频输入，适配 GPT-4o 等多模态模型。
· 成本跟踪：统计每个模型/用户的 Token 消耗和费用。
· 自适应路由：根据任务类型（闲聊、工具调用、长文生成）自动选择最合适的模型。

---

本详细设计为缘·Bot 的 AI 提供商适配系统提供了坚实、灵活的基座，确保模型层的可插拔性和安全性，同时为社区贡献者打开了便捷的开发通道。