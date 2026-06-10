---
title: AI 提供商适配器规范
description: YuanBot AI 提供商适配器标准化接口规范
---

# AI 提供商适配器规范 v1.0

## 1. 概述

AI 提供商适配器是 YuanBot 与各种 LLM 后端之间的标准化接口层。
每个适配器封装特定提供商的 API 差异，对外暴露统一的 `AIProviderAdapter` 接口。

## 2. 标准化接口

所有适配器必须实现以下接口：

```python
class AIProviderAdapter(ABC):
    # 对话请求
    async def chat_completion(messages, tools, temperature, max_tokens, system_prompt) -> ChatResponse
    async def stream_chat_completion(messages, tools, temperature, max_tokens, system_prompt) -> AsyncIterator[ChatChunk]

    # 向量嵌入
    async def get_embedding(text, model) -> list[float]

    # 元数据
    @property
    def provider_id(self) -> str           # 如 "openai", "anthropic", "deepseek"
    @property
    def supported_models(self) -> list[str]
    @property
    def max_context_length(self) -> int
```

## 3. 环境变量命名规范

```
YUAN_AI_{PROVIDER_ID}_{PARAM}
```

示例：
- `YUAN_AI_ANTHROPIC_API_KEY`
- `YUAN_AI_ANTHROPIC_DEFAULT_MODEL`
- `YUAN_AI_DEEPSEEK_BASE_URL`

## 4. 适配器文件结构

```text
adapters/ai/
├── base.py              # 基类（通用配置加载）
├── openai_adapter.py    # OpenAI 适配器
├── anthropic_adapter.py # Anthropic Claude 适配器
└── __init__.py          # 统一导出
```

## 5. 消息格式映射

### 5.1 Anthropic Claude 特殊处理

Claude API 与 OpenAI API 有以下关键差异：
- 系统提示词通过顶层 `system` 参数传递，不在 `messages` 数组中
- 不支持 `name` 字段
- 工具调用格式使用 `tool_use` / `tool_result` 类型
- 响应中 `stop_reason` 替代 `finish_reason`

### 5.2 向后兼容

所有适配器返回统一的 `ChatResponse` / `ChatChunk` 类型，
编排层无需感知底层提供商差异。
