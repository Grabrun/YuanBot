"""OpenAI 适配器测试"""

from __future__ import annotations

import pytest

from yuanbot.adapters.ai.openai_adapter import OpenAIAdapter
from yuanbot.core.types import (
    FunctionCall,
    Message,
    ToolCall,
    ToolDefinition,
)


class TestOpenAIAdapterProperties:
    def test_provider_id(self):
        adapter = OpenAIAdapter(config={"api_key": "test"})
        assert adapter.provider_id == "openai"

    def test_supported_models(self):
        adapter = OpenAIAdapter(config={"api_key": "test"})
        models = adapter.supported_models
        assert "gpt-4o" in models
        assert "gpt-4.1" in models

    def test_max_context_length_default(self):
        adapter = OpenAIAdapter(config={"api_key": "test"})
        assert adapter.max_context_length == 128000

    def test_max_context_length_custom_model(self):
        adapter = OpenAIAdapter(config={"api_key": "test", "default_model": "gpt-4.1"})
        assert adapter.max_context_length == 1047576

    def test_max_context_length_unknown_model(self):
        adapter = OpenAIAdapter(config={"api_key": "test", "default_model": "unknown"})
        assert adapter.max_context_length == 128000


class TestMessageToDict:
    def test_basic_message(self):
        msg = Message(role="user", content="Hello")
        result = OpenAIAdapter._message_to_dict(msg)
        assert result == {"role": "user", "content": "Hello"}

    def test_system_message(self):
        msg = Message(role="system", content="You are helpful")
        result = OpenAIAdapter._message_to_dict(msg)
        assert result == {"role": "system", "content": "You are helpful"}

    def test_message_with_name(self):
        msg = Message(role="user", content="Hi", name="test_user")
        result = OpenAIAdapter._message_to_dict(msg)
        assert result["name"] == "test_user"

    def test_message_with_tool_calls(self):
        msg = Message(
            role="assistant",
            content=None,
            tool_calls=[
                ToolCall(
                    id="tc_1",
                    function=FunctionCall(name="search", arguments='{"q": "test"}'),
                )
            ],
        )
        result = OpenAIAdapter._message_to_dict(msg)
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["id"] == "tc_1"
        assert result["tool_calls"][0]["function"]["name"] == "search"

    def test_message_with_tool_call_id(self):
        msg = Message(role="tool", content="result", tool_call_id="tc_1")
        result = OpenAIAdapter._message_to_dict(msg)
        assert result["tool_call_id"] == "tc_1"

    def test_none_content_omitted(self):
        msg = Message(role="assistant", content=None)
        result = OpenAIAdapter._message_to_dict(msg)
        assert "content" not in result


class TestParseResponse:
    def test_text_response(self):
        data = {
            "choices": [
                {
                    "message": {"content": "Hello!", "role": "assistant"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "model": "gpt-4o",
        }
        result = OpenAIAdapter._parse_response(data)
        assert result.content == "Hello!"
        assert result.finish_reason == "stop"
        assert result.usage.total_tokens == 15
        assert result.model == "gpt-4o"

    def test_tool_call_response(self):
        data = {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": "tc_1",
                                "type": "function",
                                "function": {
                                    "name": "search",
                                    "arguments": '{"q": "test"}',
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "model": "gpt-4o",
        }
        result = OpenAIAdapter._parse_response(data)
        assert result.content is None
        assert result.tool_calls is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].function.name == "search"
        assert result.finish_reason == "tool_calls"

    def test_no_usage(self):
        data = {
            "choices": [
                {
                    "message": {"content": "Hi", "role": "assistant"},
                    "finish_reason": "stop",
                }
            ],
        }
        result = OpenAIAdapter._parse_response(data)
        assert result.usage is None


class TestParseChunk:
    def test_text_delta(self):
        data = {
            "choices": [
                {
                    "delta": {"content": "Hello"},
                    "finish_reason": None,
                }
            ]
        }
        chunk = OpenAIAdapter._parse_chunk(data)
        assert chunk.delta_content == "Hello"
        assert chunk.finish_reason is None

    def test_finish_chunk(self):
        data = {
            "choices": [
                {
                    "delta": {},
                    "finish_reason": "stop",
                }
            ]
        }
        chunk = OpenAIAdapter._parse_chunk(data)
        assert chunk.finish_reason == "stop"


class TestBuildPayload:
    def test_basic_payload(self):
        adapter = OpenAIAdapter(config={"api_key": "test"})
        messages = [Message(role="user", content="Hello")]
        payload = adapter._build_payload(
            messages=messages,
            tools=None,
            temperature=0.7,
            max_tokens=1024,
            stream=False,
        )
        assert payload["model"] == "gpt-4o"
        assert payload["temperature"] == 0.7
        assert payload["max_tokens"] == 1024
        assert payload["stream"] is False
        assert len(payload["messages"]) == 1

    def test_with_tools(self):
        adapter = OpenAIAdapter(config={"api_key": "test"})
        messages = [Message(role="user", content="Hello")]
        tools = [
            ToolDefinition(
                name="search",
                description="Search",
                parameters={"type": "object"},
            )
        ]
        payload = adapter._build_payload(
            messages=messages,
            tools=tools,
            temperature=0.5,
            max_tokens=2048,
            stream=True,
        )
        assert len(payload["tools"]) == 1
        assert payload["tools"][0]["function"]["name"] == "search"
        assert payload["stream"] is True

    def test_with_system_prompt(self):
        adapter = OpenAIAdapter(config={"api_key": "test"})
        messages = [Message(role="user", content="Hello")]
        payload = adapter._build_payload(
            messages=messages,
            tools=None,
            temperature=0.7,
            max_tokens=4096,
            stream=False,
            system_prompt="You are helpful",
        )
        # system_prompt should be injected as first message
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][0]["content"] == "You are helpful"
        assert len(payload["messages"]) == 2

    def test_without_system_prompt(self):
        adapter = OpenAIAdapter(config={"api_key": "test"})
        messages = [Message(role="user", content="Hello")]
        payload = adapter._build_payload(
            messages=messages,
            tools=None,
            temperature=0.7,
            max_tokens=4096,
            stream=False,
            system_prompt=None,
        )
        assert len(payload["messages"]) == 1
        assert payload["messages"][0]["role"] == "user"


class TestEnsureClient:
    @pytest.mark.asyncio
    async def test_no_api_key_raises(self):
        adapter = OpenAIAdapter(config={})
        with pytest.raises(ValueError, match="API key not configured"):
            await adapter._ensure_client()

    @pytest.mark.asyncio
    async def test_with_api_key(self):
        adapter = OpenAIAdapter(config={"api_key": "sk-test"})
        client = await adapter._ensure_client()
        assert client is not None
        await adapter.close()

    @pytest.mark.asyncio
    async def test_close(self):
        adapter = OpenAIAdapter(config={"api_key": "sk-test"})
        await adapter._ensure_client()
        await adapter.close()
        assert adapter._client is None

    @pytest.mark.asyncio
    async def test_close_when_not_opened(self):
        adapter = OpenAIAdapter(config={"api_key": "sk-test"})
        await adapter.close()  # Should not raise
