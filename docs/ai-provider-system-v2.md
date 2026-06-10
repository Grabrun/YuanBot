---
title: AI 提供商适配系统 v2
description: YuanBot AI 提供商适配系统 v2.0 详细设计
---

🌸 缘·Bot AI 提供商适配系统详细设计文档 v2.0

版本历史

| 版本 | 日期 | 修改内容 |
|------|------|----------|
| v1.0 | 2026-05-17 | 初始详细设计，基于总体架构 v1.4 |
| v2.0 | 2026-05-22 | 重大重构：适配器复用机制，配置文件定义 Provider。基于 v1.5 新架构。 |
---

1. 系统定位与目标

AI 提供商适配系统是 缘·Bot 的“语言皮层”，负责接入各种大语言模型后端。v2.0 进行了根本性重构：将 适配器 (Adapter) 与 提供商 (Provider) 彻底解耦。

核心目标：

· 适配器复用：同一个适配器类（如 OpenAIAdapter）可服务于所有兼容 OpenAI Chat Completions API 的提供商。新增模型提供商通常只需一个 YAML 配置文件，零代码。
· 配置文件即 Provider：Provider 完全由 configs/Providers/ 下的 YAML 文件定义，包含提供商名称、API 端点、认证密钥、模型列表、默认模型等。
· 统一接口：对上层（决策系统、记忆系统）完全屏蔽底层差异，调用逻辑不变。
· 安全隔离：API 密钥等敏感信息存放在独立的 Provider 配置文件中，支持环境变量注入，仅活跃提供商的凭证被加载到内存。
· 灵活切换：通过根配置 bot.yaml 中的 ai.default_provider 全局切换，或通过 API/CLI 动态覆盖。

---

2. 核心概念重构

概念 旧定义 新定义 (v2.0)
适配器 (Adapter) 一对一绑定某个服务商（如 OpenAIAdapter 仅用于 OpenAI） 可复用的协议实现，封装对某种 API 协议（如 OpenAI Chat Completions）的通信细节、鉴权逻辑、重试策略。一个适配器可被多个 Provider 使用。
提供商 (Provider) 以前由适配器隐式代表 配置文件定义的实体，包含 provider_id、adapter 引用、base_url、api_key、模型列表、默认模型。一个 Provider 明确指定使用哪个适配器。
模型 散落在代码或单一配置中 Provider 配置中的 models 列表，每个模型有 id、type（chat/embedding）、max_tokens 等。

关系示意图：

```
 ┌────────────────────────────────────────────────────┐
 │  Provider: openai       Provider: deepseek          │
 │  adapter: openai-adp   adapter: openai-adp          │
 │  base_url: api.openai  base_url: api.deepseek       │
 │  models: [gpt-4o, ...]  models: [deepseek-chat,...] │
 └────────┬──────────────────────┬─────────────────────┘
          │                      │
          └──────────┬───────────┘
                     │ 使用同一个适配器类
          ┌──────────▼──────────────────┐
          │   Adapter: OpenAIAdapter    │
          │   · 实现 /chat/completions  │
          │   · 鉴权头: Authorization   │
          │   · 流式处理                │
          └─────────────────────────────┘
```

---

3. 统一适配器接口

所有适配器仍需实现 AIProviderAdapter 抽象基类。v2.0 对接口进行了微调，使适配器接收 Provider 配置中提取的参数，而不再自己持有固定端点。

```python
class AIProviderAdapter(ABC):
    """AI 提供商适配器统一接口 (v2.0)"""

    def __init__(self, provider_config: dict):
        """
        provider_config 包含来自 Provider YAML 的 config 字段，
        如 api_key, base_url, organization 等。
        """
        self.config = provider_config

    @abstractmethod
    async def chat_completion(
        self,
        messages: List[Message],
        model: str,
        tools: Optional[List[ToolDefinition]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ChatResponse:
        """非流式对话请求"""
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
        """流式对话请求"""
        pass

    @abstractmethod
    async def get_embedding(
        self,
        text: str,
        model: str,
    ) -> List[float]:
        """获取向量嵌入"""
        pass

    @abstractmethod
    def validate_config(self) -> bool:
        """验证配置有效性（如 API Key 格式、base_url 可达）"""
        pass

    @abstractmethod
    def get_max_context_length(self, model: str) -> int:
        """返回模型的最大上下文长度"""
        pass
```

适配器的职责边界：

· 仅处理协议细节：如何构造 HTTP 请求、如何解析响应、如何处理流。
· 不关心模型列表、默认模型等业务概念（这些由 Provider 配置文件定义）。
· 通过构造函数接收运行时所需的 base_url, api_key 等。

---

4. Provider 配置文件规范

4.1 位置与格式

· 存放于 configs/Providers/ 目录下，每个 .yaml 文件代表一个 Provider。
· 文件名可任意（建议与 provider_id 一致），如 openai.yaml。

4.2 完整 Schema

```yaml
provider_id: openai            # 唯一标识，必填
name: "OpenAI"                 # 显示名称，必填
adapter: openai-adapter        # 指定使用的适配器标识，必填
enabled: true                  # 是否启用，默认 true
config:
  api_key: "${OPENAI_API_KEY}" # 认证密钥，支持环境变量引用
  base_url: "https://api.openai.com/v1"   # API 基础地址
  organization: "org-xxx"      # 可选，某些服务商需要
  models:                      # 模型列表，必填
    - id: gpt-4o
      type: chat               # chat 或 embedding
      max_tokens: 128000
    - id: gpt-4o-mini
      type: chat
      max_tokens: 128000
    - id: text-embedding-3-small
      type: embedding
      dimension: 1536         # 仅嵌入模型需要
  default: gpt-4o              # 默认模型，必须在 models 列表中
  embedding_model: text-embedding-3-small  # 可选，嵌入模型
```

字段说明：

字段 必需 说明
provider_id 是 全局唯一 ID，用于 bot.yaml 中的 default_provider 引用。
name 是 显示名称，用于 UI。
adapter 是 指向已安装的适配器 ID（如 openai-adapter）。系统从适配器注册表中查找对应类。
enabled 否 默认 true。若为 false，系统启动时跳过该 Provider。
config.api_key 是 API 密钥。支持 ${ENV_VAR} 占位符，启动时自动替换。
config.base_url 是 API 的基础 URL，适配器会将请求发往此地址。
config.organization 否 部分服务商（如 OpenAI）的组织 ID。
config.models 是 该 Provider 提供的模型列表，每个模型至少包含 id 和 type。
config.default 是 默认使用的对话模型 ID，必须存在于 models 列表中。
config.embedding_model 否 若未指定，系统自动选择第一个 type: embedding 的模型。

4.3 模型条目字段

字段 类型 说明
id string 模型标识，调用 API 时传给 model 参数。
type string chat 或 embedding。
max_tokens int 模型支持的最大上下文长度（总 token 数）。
dimension int 仅嵌入模型，输出向量的维度。

4.4 环境变量注入

· 配置文件中使用 ${VAR_NAME} 引用环境变量。
· 系统启动时自动替换为实际环境变量值。
· 若环境变量不存在且无默认值，该 Provider 加载失败（记录错误日志，但不影响其他 Provider 启动）。

---

5. 内置通用适配器

系统预置两个适配器，覆盖绝大多数 API 协议。

5.1 openai-adapter

· 兼容协议：OpenAI Chat Completions API (/chat/completions, /embeddings)。
· 认证方式：Bearer Token (Authorization: Bearer {api_key})。
· 特性：支持流式、function calling、多模态输入（若模型支持）。
· 适用 Provider：OpenAI、DeepSeek、GLM、Qwen、混元、Mimo、Ollama、vLLM 等。

5.2 anthropic-adapter

· 兼容协议：Anthropic Messages API。
· 认证方式：x-api-key 头。
· 特性：超长上下文、native tool use（需要转换为标准 ToolCall 格式）。

5.3 适配器注册表

适配器通过以下方式注册：

· 核心内置：openai-adapter、anthropic-adapter。
· 社区扩展：按 Y.E.S. 规范开发的适配器包，安装后出现在注册表中。

系统启动时构建适配器注册表（字典 {adapter_id: adapter_class}）。

---

6. Provider 管理器

职责：

· 扫描 configs/Providers/ 目录，加载所有 enabled: true 的 Provider 配置。
· 根据每个 Provider 的 adapter 字段，从适配器注册表获取适配器类并实例化（传入配置）。
· 维护一份活跃 Provider 列表：default_provider（对话）和 embedding_provider（嵌入）。
· 提供模型解析服务：根据请求的模型 ID 或 Provider ID，路由到正确的适配器实例。

核心数据结构：

```python
@dataclass
class LoadedProvider:
    provider_id: str
    name: str
    adapter_instance: AIProviderAdapter
    config: dict                # 完整的配置字典
    models: List[ModelSpec]     # 模型规格列表
    default_model: str
    embedding_model: str | None
```

管理器关键方法：

```python
class ProviderManager:
    def load_providers(self) -> None: ...
    def get_chat_provider(self, provider_id: str = None) -> LoadedProvider: ...
    def get_embedding_provider(self) -> LoadedProvider: ...
    def resolve_model(self, model_ref: str) -> Tuple[LoadedProvider, str]: ...
    def list_providers(self) -> List[LoadedProvider]: ...
    def reload_provider(self, provider_id: str) -> None: ...
```

---

7. 配置加载与切换流程

7.1 启动流程

1. 读取 configs/bot.yaml，获得 ai.default_provider 和 ai.embedding_provider（可选）。
2. 扫描 configs/Providers/ 目录下所有 .yaml 文件。
3. 对每个文件：
   · 验证 YAML 结构，检查必需字段。
   · 替换 ${ENV} 占位符。
   · 根据 adapter 字段查找适配器类。
   · 实例化适配器，传入 config 字典。
   · 创建 LoadedProvider 对象。
4. 若 default_provider 指定的 Provider ID 存在且已启用，将其标记为活跃对话 Provider。
5. 若 embedding_provider 指定了 Provider ID，则使用该 Provider 的嵌入模型；否则使用对话 Provider 中的第一个嵌入模型。
6. 若活跃 Provider 加载失败，尝试 fallback_provider（若配置），否则系统启动报错。

7.2 模型解析逻辑

AIService.generate(model="deepseek-chat") 时：

1. 若 model 参数为 None，使用活跃对话 Provider 的 default_model。
2. 若 model 参数不包含 /，认为该模型属于当前活跃对话 Provider，直接使用。
3. 若 model 参数包含 /（如 openai/gpt-4o-mini），则临时切换到对应 Provider，并使用该 Provider 中的对应模型。
4. 嵌入调用类似，优先使用 embedding_provider。

7.3 动态切换

· 通过 API PUT /api/providers/active 或 CLI 命令 yuanbot-cli provider set default <provider_id> 可实时切换活跃 Provider。
· 切换后，后续对话立即使用新 Provider 的默认模型。
· 不影响正在进行的流式请求。

---

8. 预集成 Provider 列表

v1.5 内置以下 Provider 配置文件模板（随发布包提供示例，用户自行填写 API Key 并启用）。

文件 Provider ID 适配器 默认模型
openai.yaml openai openai-adapter gpt-4o
deepseek.yaml deepseek openai-adapter deepseek-chat
glm.yaml glm openai-adapter glm-4
qwen.yaml qwen openai-adapter qwen-max
hunyuan.yaml hunyuan openai-adapter hunyuan-pro
mimo.yaml mimo openai-adapter mimo-chat
ollama.yaml ollama openai-adapter (用户填写本地模型)
claude.yaml anthropic anthropic-adapter claude-sonnet-4-20250514

用户添加新 Provider 只需复制一个模板，修改 provider_id、base_url、api_key、models 等字段即可。

---

9. 安全与凭证管理

· 环境变量注入：敏感信息（api_key）通过 ${ENV} 引用，配置文件本身可安全提交到版本控制（.yaml 不含真实密钥）。
· 惰性加载：仅活跃 Provider 的适配器实例及其密钥存在于内存中。非活跃 Provider 的配置文件仅被解析但不会保留密钥原始值。
· 日志脱敏：适配器错误日志中自动过滤 API Key 和 Authorization 头。
· 权限建议：建议用户将 configs/Providers/ 目录权限设为 600，防止未授权访问。

---

10. CLI 扩展

yuanbot-cli provider 命令组：

命令 说明
provider list 列出所有已配置的 Provider 及其状态（启用/禁用，活跃）
provider info <id> 显示 Provider 的详细信息（模型列表、API 端点）
provider set default <id> 设置默认对话 Provider
provider set embedding <id> 设置嵌入专用 Provider
provider install <name> 从市场安装一个 Provider 配置文件
provider create 交互式创建新的 Provider 配置文件

---

11. 与外部系统的交互

· 与人格与行为决策系统：通过 AIService 统一调用，对 Provider 机制无感知。
· 与记忆系统：记忆系统通过 AIService.embed() 获取向量，底层由 Provider 管理器路由到嵌入模型。
· 与能力系统：Tool 的 function calling 请求经由适配器转换为模型可识别的格式。
· 与 UI API：/api/providers 端点返回当前 Provider 列表、模型、状态等，供 WebUI 管理界面展示和修改。

---

12. 配置文件目录结构示例

```
configs/Providers/
├── openai.yaml
├── deepseek.yaml
├── glm.yaml
├── qwen.yaml
├── hunyuan.yaml
├── mimo.yaml
├── ollama.yaml
├── claude.yaml
└── custom-provider.yaml       # 用户自定义
```

每个文件独立，可随时增删，系统启动时自动识别。

---

本 v2.0 设计将 Provider 从适配器中彻底解放，使接入新的大语言模型成为纯粹的配置工作，极大地降低了维护成本与社区贡献门槛。