"""DeepSeek AI 提供商适配器

DeepSeek 使用与 OpenAI 兼容的 API 格式，
base_url 默认为 https://api.deepseek.com。
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

# DeepSeek 模型上下文长度映射
MODEL_CONTEXT_LENGTHS: dict[str, int] = {
    "deepseek-chat": 128000,
    "deepseek-reasoner": 128000,
}

# 重试配置
_MAX_RETRIES = 3
_RETRY_DELAY = 1.0  # 秒


class DeepSeekAdapter(BaseAIProvider):
    """DeepSeek AI 提供商适配器

    DeepSeek 使用与 OpenAI 兼容的 API 格式，
    base_url 默认为 https://api.deepseek.com。
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self._api_key: str | None = None
        self._base_url: str = "https://api.deepseek.com"
        self._default_model: str = "deepseek-chat"
        self._models: list[dict[str, Any]] = []
        self._client: httpx.AsyncClient | None = None
        super().__init__(config)

    def _load_config_from_env(self) -> None:
        """加载 DeepSeek 特定配置"""
        super()._load_config_from_env()
        self._api_key = self._get_config("api_key")
        self._base_url = self._get_config("base_url", self._base_url)
        self._default_model = self._get_config("default", self._default_model)
        self._models = self._get_config("models", [])

    async def _ensure_client(self) -> httpx.AsyncClient:
        """延迟初始化 HTTP 客户端"""
        if self._client is None:
            if not self._api_key:
                raise ValueError(
                    "DeepSeek API key not configured. "
                    "Set YUAN_AI_DEEPSEEK_API_KEY or pass config['api_key']"
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
        return "deepseek"

    @property
    def supported_models(self) -> list[str]:
        return list(MODEL_CONTEXT_LENGTHS.keys())

    @property
    def max_context_length(self) -> int:
        return MODEL_CONTEXT_LENGTHS.get(self._default_model, 128000)

    def validate_config(self) -> ValidationResult:
        """验证 DeepSeek 适配器配置"""
        errors: list[str] = []
        if not self._api_key:
            errors.append(
                "DeepSeek API key not configured. "
                "Set YUAN_AI_DEEPSEEK_API_KEY or pass config['api_key']"
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

        for attempt in range(_MAX_RETRIES):
            try:
                response = await client.post("/v1/chat/completions", json=payload)
                response.raise_for_status()
                data = response.json()
                return self._parse_response(data)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt < _MAX_RETRIES - 1:
                    import asyncio

                    retry_after = float(e.response.headers.get("Retry-After", _RETRY_DELAY))
                    logger.warning(
                        "rate_limited",
                        provider="deepseek",
                        retry_after=retry_after,
                        attempt=attempt + 1,
                    )
                    await asyncio.sleep(retry_after)
                    continue
                raise
            except httpx.HTTPError as e:
                if attempt < _MAX_RETRIES - 1:
                    import asyncio

                    logger.warning(
                        "request_failed",
                        provider="deepseek",
                        error=str(e),
                        attempt=attempt + 1,
                    )
                    await asyncio.sleep(_RETRY_DELAY * (attempt + 1))
                    continue
                raise

        raise RuntimeError("DeepSeek API request failed after retries")

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

        for attempt in range(_MAX_RETRIES):
            try:
                async with client.stream("POST", "/v1/chat/completions", json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.startswith("data: ") and line != "data: [DONE]":
                            chunk_data = json.loads(line[6:])
                            yield self._parse_chunk(chunk_data)
                return
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt < _MAX_RETRIES - 1:
                    import asyncio

                    retry_after = float(e.response.headers.get("Retry-After", _RETRY_DELAY))
                    logger.warning(
                        "rate_limited_stream",
                        provider="deepseek",
                        retry_after=retry_after,
                        attempt=attempt + 1,
                    )
                    await asyncio.sleep(retry_after)
                    continue
                raise
            except httpx.HTTPError as e:
                if attempt < _MAX_RETRIES - 1:
                    import asyncio

                    logger.warning(
                        "stream_request_failed",
                        provider="deepseek",
                        error=str(e),
                        attempt=attempt + 1,
                    )
                    await asyncio.sleep(_RETRY_DELAY * (attempt + 1))
                    continue
                raise

    async def get_embedding(
        self,
        text: str,
        model: str | None = None,
    ) -> list[float]:
        """获取文本向量嵌入

        DeepSeek 目前不提供独立的 embedding API，
        此方法通过 /v1/embeddings 端点调用（如果可用）。
        """
        client = await self._ensure_client()
        embedding_model = model or "deepseek-embedding"

        response = await client.post(
            "/v1/embeddings",
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
        """将 Message 转为 OpenAI 兼容 API 格式"""
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
