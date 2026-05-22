"""Ollama 本地模型适配器

连接本地 Ollama 服务 (默认 http://localhost:11434)。
API 格式与 OpenAI 不同，需要单独处理。

Ollama API:
- 对话: POST /api/chat
- 嵌入: POST /api/embeddings
- 模型列表: GET /api/tags
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

# 重试配置
_MAX_RETRIES = 3
_RETRY_DELAY = 2.0  # 秒（本地模型推理较慢，给更多时间）


class OllamaAdapter(BaseAIProvider):
    """Ollama 本地模型适配器

    连接本地 Ollama 服务 (默认 http://localhost:11434)，
    支持任何已拉取的本地模型。
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self._base_url: str = "http://localhost:11434"
        self._default_model: str = ""
        self._models: list[dict[str, Any]] = []
        self._client: httpx.AsyncClient | None = None
        self._model_cache: dict[str, int] = {}  # model -> context_length
        super().__init__(config)

    def _load_config_from_env(self) -> None:
        """加载 Ollama 特定配置"""
        super()._load_config_from_env()
        self._base_url = self._get_config("base_url", self._base_url)
        self._default_model = self._get_config("default", self._default_model)
        self._models = self._get_config("models", [])

    async def _ensure_client(self) -> httpx.AsyncClient:
        """延迟初始化 HTTP 客户端"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=300.0,  # 本地模型推理可能很慢
            )
        return self._client

    @property
    def provider_id(self) -> str:
        return "ollama"

    @property
    def supported_models(self) -> list[str]:
        """返回配置中的模型列表

        如果配置为空，返回常用本地模型名称提示。
        实际可用模型取决于 Ollama 已拉取的模型。
        """
        if self._models:
            return [m["id"] if isinstance(m, dict) else m for m in self._models]
        return []

    @property
    def max_context_length(self) -> int:
        """返回最大上下文长度

        从已知模型映射或缓存中获取，默认 32768。
        """
        if self._default_model in self._model_cache:
            return self._model_cache[self._default_model]
        return 32768

    def validate_config(self) -> ValidationResult:
        """验证 Ollama 适配器配置"""
        errors: list[str] = []
        if not self._base_url:
            errors.append("Ollama base_url not configured.")
        if not self._default_model and not self._models:
            errors.append(
                "Ollama default_model or models list not configured. "
                "Set YUAN_AI_OLLAMA_DEFAULT or pass config['default']"
            )
        return ValidationResult(valid=len(errors) == 0, errors=errors)

    async def chat_completion(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system_prompt: str | None = None,
    ) -> ChatResponse:
        """发送对话请求"""
        client = await self._ensure_client()

        payload = self._build_chat_payload(
            messages=messages,
            tools=tools,
            temperature=temperature,
            stream=False,
            system_prompt=system_prompt,
        )

        for attempt in range(_MAX_RETRIES):
            try:
                response = await client.post("/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()
                return self._parse_chat_response(data)
            except httpx.HTTPError as e:
                if attempt < _MAX_RETRIES - 1:
                    import asyncio

                    logger.warning(
                        "ollama_request_failed",
                        error=str(e),
                        attempt=attempt + 1,
                    )
                    await asyncio.sleep(_RETRY_DELAY * (attempt + 1))
                    continue
                raise

        raise RuntimeError("Ollama API request failed after retries")

    async def stream_chat_completion(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system_prompt: str | None = None,
    ) -> AsyncIterator[ChatChunk]:
        """流式对话请求"""
        client = await self._ensure_client()

        payload = self._build_chat_payload(
            messages=messages,
            tools=tools,
            temperature=temperature,
            stream=True,
            system_prompt=system_prompt,
        )

        for attempt in range(_MAX_RETRIES):
            try:
                async with client.stream("POST", "/api/chat", json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk_data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        yield self._parse_chat_chunk(chunk_data)
                return
            except httpx.HTTPError as e:
                if attempt < _MAX_RETRIES - 1:
                    import asyncio

                    logger.warning(
                        "ollama_stream_request_failed",
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
        """获取文本向量嵌入"""
        client = await self._ensure_client()
        embedding_model = model or self._find_embedding_model()

        if not embedding_model:
            raise ValueError(
                "No embedding model configured for Ollama. "
                "Add an embedding model to config['models'] or specify model parameter."
            )

        for attempt in range(_MAX_RETRIES):
            try:
                response = await client.post(
                    "/api/embeddings",
                    json={"prompt": text, "model": embedding_model},
                )
                response.raise_for_status()
                data = response.json()
                return data["embedding"]
            except httpx.HTTPError as e:
                if attempt < _MAX_RETRIES - 1:
                    import asyncio

                    logger.warning(
                        "ollama_embedding_failed",
                        error=str(e),
                        attempt=attempt + 1,
                    )
                    await asyncio.sleep(_RETRY_DELAY * (attempt + 1))
                    continue
                raise

        raise RuntimeError("Ollama embedding request failed after retries")

    async def list_models(self) -> list[str]:
        """获取 Ollama 已拉取的模型列表"""
        client = await self._ensure_client()
        response = await client.get("/api/tags")
        response.raise_for_status()
        data = response.json()
        return [m["name"] for m in data.get("models", [])]

    # ──────────────────────────────────────────
    # 内部方法
    # ──────────────────────────────────────────

    def _find_embedding_model(self) -> str | None:
        """从配置中查找 embedding 模型"""
        for model in self._models:
            if isinstance(model, dict) and model.get("type") == "embedding":
                return model["id"]
        return None

    def _build_chat_payload(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None,
        temperature: float,
        stream: bool,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        """构建 Ollama /api/chat 请求体"""
        ollama_messages: list[dict[str, Any]] = []

        # 注入 system prompt
        if system_prompt:
            ollama_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            ollama_msg = self._message_to_ollama(msg)
            if ollama_msg:
                ollama_messages.append(ollama_msg)

        payload: dict[str, Any] = {
            "model": self._default_model,
            "messages": ollama_messages,
            "stream": stream,
            "options": {
                "temperature": temperature,
            },
        }

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
    def _message_to_ollama(msg: Message) -> dict[str, Any] | None:
        """将 Message 转为 Ollama 消息格式"""
        if msg.role == "tool":
            # Ollama 使用 role="tool" 表示工具结果
            d: dict[str, Any] = {"role": "tool", "content": msg.content or ""}
            if msg.tool_call_id:
                d["tool_call_id"] = msg.tool_call_id
            return d

        d = {"role": msg.role}
        if msg.content is not None:
            d["content"] = msg.content

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

        return d

    @staticmethod
    def _parse_chat_response(data: dict[str, Any]) -> ChatResponse:
        """解析 Ollama /api/chat 响应"""
        message = data.get("message", {})

        tool_calls = None
        if "tool_calls" in message and message["tool_calls"]:
            tool_calls = [
                ToolCall(
                    id=tc.get("id", ""),
                    function=FunctionCall(
                        name=tc["function"]["name"],
                        arguments=json.dumps(tc["function"]["arguments"])
                        if isinstance(tc["function"]["arguments"], dict)
                        else tc["function"]["arguments"],
                    ),
                )
                for tc in message["tool_calls"]
            ]

        # Ollama 返回 eval_count 等统计信息
        usage = None
        if "prompt_eval_count" in data or "eval_count" in data:
            usage = TokenUsage(
                prompt_tokens=data.get("prompt_eval_count", 0),
                completion_tokens=data.get("eval_count", 0),
                total_tokens=data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            )

        # Ollama 使用 "done_reason" 映射到 finish_reason
        finish_reason = "stop" if data.get("done") else None
        if data.get("done_reason"):
            finish_reason = data["done_reason"]

        return ChatResponse(
            content=message.get("content"),
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            model=data.get("model"),
        )

    @staticmethod
    def _parse_chat_chunk(data: dict[str, Any]) -> ChatChunk:
        """解析 Ollama 流式响应块"""
        message = data.get("message", {})

        delta_tool_calls = None
        if "tool_calls" in message and message["tool_calls"]:
            delta_tool_calls = [
                ToolCall(
                    id=tc.get("id", ""),
                    function=FunctionCall(
                        name=tc["function"]["name"],
                        arguments=json.dumps(tc["function"]["arguments"])
                        if isinstance(tc["function"]["arguments"], dict)
                        else tc["function"]["arguments"],
                    ),
                )
                for tc in message["tool_calls"]
            ]

        finish_reason = None
        if data.get("done"):
            finish_reason = data.get("done_reason", "stop")

        return ChatChunk(
            delta_content=message.get("content"),
            delta_tool_calls=delta_tool_calls,
            finish_reason=finish_reason,
        )

    async def close(self) -> None:
        """关闭 HTTP 客户端"""
        if self._client:
            await self._client.aclose()
            self._client = None
