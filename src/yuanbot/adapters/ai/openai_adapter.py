"""OpenAI 兼容 API 适配器

支持所有兼容 OpenAI Chat Completions API 的提供商，
包括 OpenAI、DeepSeek、GLM、Qwen、混元、Mimo、Ollama 等。
通过配置文件中的 base_url 和 api_key 指定具体提供商。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import structlog

from yuanbot.adapters.ai.base import BaseAIProvider
from yuanbot.core.types import (
    ChatChunk,
    ChatResponse,
    FunctionCall,
    Message,
    TokenUsage,
    ToolCall,
    ToolDefinition,
    ValidationResult,
)

logger = structlog.get_logger(__name__)

# OpenAI 模型上下文长度映射
MODEL_CONTEXT_LENGTHS = {
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4.1": 1047576,
    "gpt-4.1-mini": 1047576,
    "gpt-4.1-nano": 1047576,
}


class OpenAIAdapter(BaseAIProvider):
    """OpenAI 兼容 API 适配器

    可服务所有兼容 OpenAI Chat Completions API 的提供商。
    通过 config 中的 base_url、api_key、default 等字段配置。
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self._api_key: str | None = None
        self._base_url: str = "https://api.openai.com/v1"
        self._default_model: str = "gpt-4o"
        self._provider_id: str = "openai"
        self._client: httpx.AsyncClient | None = None
        super().__init__(config)

    def _load_config_from_env(self) -> None:
        """加载配置（支持 OpenAI 兼容的任意提供商）"""
        super()._load_config_from_env()
        self._api_key = self._get_config("api_key")
        self._base_url = self._get_config("base_url", self._base_url)
        # 支持 'default' 和 'default_model' 两种配置键名
        self._default_model = self._get_config(
            "default", self._get_config("default_model", self._default_model)
        )
        self._provider_id = self._get_config("provider_id", self._provider_id)

    async def _ensure_client(self) -> httpx.AsyncClient:
        """延迟初始化 HTTP 客户端"""
        if self._client is None:
            if not self._api_key:
                raise ValueError(
                    "OpenAI API key not configured. "
                    "Set YUAN_AI_OPENAI_API_KEY or pass config['api_key']"
                )
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=120.0,
            )
        return self._client

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def supported_models(self) -> list[str]:
        return list(MODEL_CONTEXT_LENGTHS.keys())

    @property
    def max_context_length(self) -> int:
        return MODEL_CONTEXT_LENGTHS.get(self._default_model, 128000)

    def validate_config(self) -> ValidationResult:
        """验证 OpenAI 适配器配置"""
        errors: list[str] = []
        if not self._api_key:
            errors.append(
                "OpenAI API key not configured. "
                "Set YUAN_AI_OPENAI_API_KEY or pass config['api_key']"
            )
        return ValidationResult(valid=len(errors) == 0, errors=errors)

    async def chat_completion(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system_prompt: str | None = None,
        model: str | None = None,
    ) -> ChatResponse:
        """发送对话请求"""
        client = await self._ensure_client()

        payload = self._build_payload(
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
            system_prompt=system_prompt,
            model=model,
        )

        response = await client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        return self._parse_response(data)

    async def stream_chat_completion(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system_prompt: str | None = None,
        model: str | None = None,
    ) -> AsyncIterator[ChatChunk]:
        """流式对话请求"""
        client = await self._ensure_client()

        payload = self._build_payload(
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            system_prompt=system_prompt,
            model=model,
        )

        async with client.stream("POST", "/chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    chunk_data = json.loads(line[6:])
                    yield self._parse_chunk(chunk_data)

    async def get_embedding(
        self,
        text: str,
        model: str | None = None,
    ) -> list[float]:
        """获取文本向量嵌入"""
        client = await self._ensure_client()
        embedding_model = model or "text-embedding-3-small"

        response = await client.post(
            "/embeddings",
            json={"input": text, "model": embedding_model},
        )
        response.raise_for_status()
        data = response.json()

        return data["data"][0]["embedding"]

    # ──────────────────────────────────────────
    # 内部方法
    # ──────────────────────────────────────────

    def _build_payload(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None,
        temperature: float,
        max_tokens: int,
        stream: bool,
        system_prompt: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """构建 API 请求体"""
        payload: dict[str, Any] = {
            "model": model or self._default_model,
            "messages": [self._message_to_dict(m) for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

        # 注入 system_prompt 为首条系统消息
        if system_prompt:
            payload["messages"].insert(0, {"role": "system", "content": system_prompt})

        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]

        return payload

    @staticmethod
    def _message_to_dict(msg: Message) -> dict[str, Any]:
        """将 Message 转为 OpenAI API 格式"""
        d: dict[str, Any] = {"role": msg.role}
        if msg.content is not None:
            d["content"] = msg.content
        if msg.name:
            d["name"] = msg.name
        if msg.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
        if msg.tool_call_id:
            d["tool_call_id"] = msg.tool_call_id
        return d

    @staticmethod
    def _parse_response(data: dict[str, Any]) -> ChatResponse:
        """解析 API 响应"""
        choice = data["choices"][0]
        message = choice["message"]

        tool_calls = None
        if "tool_calls" in message and message["tool_calls"]:
            tool_calls = [
                ToolCall(
                    id=tc["id"],
                    function=FunctionCall(
                        name=tc["function"]["name"],
                        arguments=tc["function"]["arguments"],
                    ),
                )
                for tc in message["tool_calls"]
            ]

        usage = None
        if "usage" in data:
            usage = TokenUsage(
                prompt_tokens=data["usage"].get("prompt_tokens", 0),
                completion_tokens=data["usage"].get("completion_tokens", 0),
                total_tokens=data["usage"].get("total_tokens", 0),
            )

        return ChatResponse(
            content=message.get("content"),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason"),
            usage=usage,
            model=data.get("model"),
        )

    @staticmethod
    def _parse_chunk(data: dict[str, Any]) -> ChatChunk:
        """解析流式响应块"""
        delta = data["choices"][0]["delta"]
        return ChatChunk(
            delta_content=delta.get("content"),
            finish_reason=data["choices"][0].get("finish_reason"),
        )

    async def close(self) -> None:
        """关闭 HTTP 客户端"""
        if self._client:
            await self._client.aclose()
            self._client = None
