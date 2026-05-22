"""Anthropic Claude 适配器

支持 Claude Opus 4, Claude Sonnet 4, Claude Haiku 等。
使用 Anthropic Messages API。
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

# Claude 模型上下文长度映射
MODEL_CONTEXT_LENGTHS = {
    "claude-opus-4-20250514": 200000,
    "claude-sonnet-4-20250514": 200000,
    "claude-3-5-haiku-20241022": 200000,
    "claude-3-5-sonnet-20241022": 200000,
    "claude-3-opus-20240229": 200000,
}

# Anthropic API 的 stop_reason → 标准 finish_reason 映射
_STOP_REASON_MAP = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "tool_use": "tool_calls",
}


class AnthropicAdapter(BaseAIProvider):
    """Anthropic Claude API 适配器

    使用 Messages API，与 OpenAI Chat Completions API 有显著差异：
    - 系统提示词通过顶层 `system` 参数传递
    - 工具调用使用 `tool_use` / `tool_result` 内容块
    - 响应中 `stop_reason` 替代 `finish_reason`
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self._api_key: str | None = None
        self._base_url: str = "https://api.anthropic.com"
        self._default_model: str = "claude-sonnet-4-20250514"
        self._client: httpx.AsyncClient | None = None
        self._api_version: str = "2023-06-01"
        super().__init__(config)

    def _load_config_from_env(self) -> None:
        """加载 Anthropic 特定配置"""
        super()._load_config_from_env()
        self._api_key = self._get_config("api_key")
        self._base_url = self._get_config("base_url", self._base_url)
        self._default_model = self._get_config("default_model", self._default_model)

    async def _ensure_client(self) -> httpx.AsyncClient:
        """延迟初始化 HTTP 客户端"""
        if self._client is None:
            if not self._api_key:
                raise ValueError(
                    "Anthropic API key not configured. "
                    "Set YUAN_AI_ANTHROPIC_API_KEY or pass config['api_key']"
                )
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": self._api_version,
                    "Content-Type": "application/json",
                },
                timeout=120.0,
            )
        return self._client

    @property
    def provider_id(self) -> str:
        return "anthropic"

    @property
    def supported_models(self) -> list[str]:
        return list(MODEL_CONTEXT_LENGTHS.keys())

    @property
    def max_context_length(self) -> int:
        return MODEL_CONTEXT_LENGTHS.get(self._default_model, 200000)

    def validate_config(self) -> ValidationResult:
        """验证 Anthropic 适配器配置"""
        errors: list[str] = []
        if not self._api_key:
            errors.append(
                "Anthropic API key not configured. "
                "Set YUAN_AI_ANTHROPIC_API_KEY or pass config['api_key']"
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
            system_prompt=system_prompt,
            stream=False,
            model=model,
        )

        response = await client.post("/v1/messages", json=payload)
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
            system_prompt=system_prompt,
            stream=True,
            model=model,
        )

        async with client.stream("POST", "/v1/messages", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    event_data = json.loads(line[6:])
                    chunk = self._parse_stream_event(event_data)
                    if chunk is not None:
                        yield chunk

    async def get_embedding(
        self,
        text: str,
        model: str | None = None,
    ) -> list[float]:
        """获取文本向量嵌入

        注意：Anthropic 原生不提供 embedding API。
        此方法抛出 NotImplementedError，建议使用 OpenAI 等其他提供商获取嵌入。
        """
        raise NotImplementedError(
            "Anthropic does not provide a native embedding API. "
            "Use OpenAI or another provider for embeddings."
        )

    # ──────────────────────────────────────────
    # 内部方法：请求构建
    # ──────────────────────────────────────────

    def _build_payload(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None,
        temperature: float,
        max_tokens: int,
        system_prompt: str | None,
        stream: bool,
        model: str | None = None,
    ) -> dict[str, Any]:
        """构建 Anthropic Messages API 请求体

        关键差异：
        - system 提示词通过顶层 `system` 参数传递
        - messages 中不能有 system 角色的消息
        - 工具调用使用不同的格式
        """
        payload: dict[str, Any] = {
            "model": model or self._default_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }

        # 系统提示词（顶层参数）
        if system_prompt:
            payload["system"] = system_prompt

        # 转换消息格式
        anthropic_messages = self._convert_messages(messages)
        payload["messages"] = anthropic_messages

        # 工具定义
        if tools:
            payload["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters,
                }
                for t in tools
            ]

        return payload

    @staticmethod
    def _convert_messages(messages: list[Message]) -> list[dict[str, Any]]:
        """将标准 Message 转为 Anthropic 消息格式

        Anthropic 要求：
        - 不能有 system 角色消息（已通过顶层参数处理）
        - user/assistant 交替出现
        - 工具调用使用 tool_use / tool_result 内容块
        - 连续同角色消息需要合并
        """
        converted: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == "system":
                # 系统消息已通过顶层 system 参数处理，跳过
                continue

            if msg.role == "tool":
                # 工具结果消息 → 转为 user 消息中的 tool_result 内容块
                tool_result_block = {
                    "type": "tool_result",
                    "tool_use_id": msg.tool_call_id or "",
                    "content": msg.content or "",
                }
                # 如果前一条也是 user 消息，合并到其 content 数组中
                if converted and converted[-1]["role"] == "user":
                    prev_content = converted[-1]["content"]
                    if isinstance(prev_content, list):
                        prev_content.append(tool_result_block)
                    else:
                        converted[-1]["content"] = [
                            {"type": "text", "text": prev_content},
                            tool_result_block,
                        ]
                else:
                    converted.append(
                        {
                            "role": "user",
                            "content": [tool_result_block],
                        }
                    )
                continue

            if msg.role == "assistant" and msg.tool_calls:
                # 助手消息包含工具调用 → 转为 tool_use 内容块
                content_blocks: list[dict[str, Any]] = []
                if msg.content:
                    content_blocks.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                    content_blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.function.name,
                            "input": args,
                        }
                    )
                converted.append({"role": "assistant", "content": content_blocks})
                continue

            # 普通 user/assistant 消息
            # 如果与前一条同角色，合并内容
            content = msg.content or ""
            if converted and converted[-1]["role"] == msg.role:
                prev = converted[-1]
                if isinstance(prev["content"], str):
                    prev["content"] += "\n" + content
                else:
                    # 前一条是 content blocks，追加 text block
                    prev["content"].append({"type": "text", "text": content})
            else:
                converted.append(
                    {
                        "role": msg.role,
                        "content": content,
                    }
                )

        return converted

    # ──────────────────────────────────────────
    # 内部方法：响应解析
    # ──────────────────────────────────────────

    @staticmethod
    def _parse_response(data: dict[str, Any]) -> ChatResponse:
        """解析 Anthropic Messages API 响应

        响应格式示例：
        {
            "id": "msg_xxx",
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "text", "text": "你好！"},
                {"type": "tool_use", "id": "tu_xxx", "name": "search", "input": {...}}
            ],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 100, "output_tokens": 50}
        }
        """
        content_parts: list[str] = []
        tool_calls: list[ToolCall] | None = None

        for block in data.get("content", []):
            block_type = block.get("type")
            if block_type == "text":
                content_parts.append(block["text"])
            elif block_type == "tool_use":
                if tool_calls is None:
                    tool_calls = []
                tool_calls.append(
                    ToolCall(
                        id=block["id"],
                        function=FunctionCall(
                            name=block["name"],
                            arguments=json.dumps(block["input"], ensure_ascii=False),
                        ),
                    )
                )

        # stop_reason → finish_reason 映射
        stop_reason = data.get("stop_reason")
        finish_reason = _STOP_REASON_MAP.get(stop_reason, stop_reason)

        # 使用统计
        usage = None
        if "usage" in data:
            usage_data = data["usage"]
            usage = TokenUsage(
                prompt_tokens=usage_data.get("input_tokens", 0),
                completion_tokens=usage_data.get("output_tokens", 0),
                total_tokens=(
                    usage_data.get("input_tokens", 0) + usage_data.get("output_tokens", 0)
                ),
            )

        return ChatResponse(
            content="\n".join(content_parts) if content_parts else None,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            model=data.get("model"),
        )

    @staticmethod
    def _parse_stream_event(event_data: dict[str, Any]) -> ChatChunk | None:
        """解析 Anthropic 流式事件

        事件类型：
        - message_start: 消息开始
        - content_block_start: 内容块开始
        - content_block_delta: 内容增量
        - content_block_stop: 内容块结束
        - message_delta: 消息级增量（stop_reason 等）
        - message_stop: 消息结束
        """
        event_type = event_data.get("type")

        if event_type == "content_block_delta":
            delta = event_data.get("delta", {})
            delta_type = delta.get("type")

            if delta_type == "text_delta":
                return ChatChunk(delta_content=delta.get("text"))
            # tool_use_delta 暂不在流式中处理工具调用

        elif event_type == "message_delta":
            delta = event_data.get("delta", {})
            stop_reason = delta.get("stop_reason")
            if stop_reason:
                return ChatChunk(finish_reason=_STOP_REASON_MAP.get(stop_reason, stop_reason))

        return None

    async def close(self) -> None:
        """关闭 HTTP 客户端"""
        if self._client:
            await self._client.aclose()
            self._client = None
