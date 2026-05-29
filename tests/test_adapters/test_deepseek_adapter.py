"""DeepSeek 适配器测试 (v2.0 - 废弃后)

DeepSeekAdapter 已废弃，委托给 OpenAIAdapter。
测试验证废弃警告和委托行为。
"""

from __future__ import annotations

import warnings
from unittest.mock import AsyncMock, MagicMock

import pytest

from yuanbot.adapters.ai.deepseek_adapter import DeepSeekAdapter
from yuanbot.adapters.ai.openai_adapter import OpenAIAdapter
from yuanbot.core.types import (
    FunctionCall,
    Message,
    ToolCall,
    ToolDefinition,
)


@pytest.fixture(autouse=True)
def _suppress_deprecation():
    """自动抑制 DeepSeekAdapter 的废弃警告"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        yield


class TestDeepSeekAdapterDeprecation:
    """验证 DeepSeekAdapter 废弃行为"""

    def test_is_openai_adapter_subclass(self):
        adapter = DeepSeekAdapter(config={"api_key": "test"})
        assert isinstance(adapter, OpenAIAdapter)

    def test_deprecation_warning_raised(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            DeepSeekAdapter(config={"api_key": "test"})
            assert len(w) >= 1
            assert any(
                issubclass(x.category, DeprecationWarning) and "deprecated" in str(x.message).lower()
                for x in w
            )

    def test_provider_id_is_deepseek(self):
        adapter = DeepSeekAdapter(config={"api_key": "test"})
        assert adapter.provider_id == "deepseek"

    def test_default_base_url_is_deepseek(self):
        adapter = DeepSeekAdapter(config={"api_key": "test"})
        assert "deepseek" in adapter._base_url

    def test_custom_base_url_preserved(self):
        adapter = DeepSeekAdapter(config={"api_key": "test", "base_url": "https://custom.api.com"})
        assert adapter._base_url == "https://custom.api.com"


class TestDeepSeekAdapterBehavior:
    """验证 DeepSeekAdapter 作为 OpenAIAdapter 子类的行为"""

    def test_supported_models_are_openai(self):
        """现在使用 OpenAIAdapter 的模型列表"""
        adapter = DeepSeekAdapter(config={"api_key": "test"})
        models = adapter.supported_models
        # OpenAIAdapter 的模型列表
        assert "gpt-4o" in models

    def test_default_model_is_openai_default(self):
        """默认模型来自 OpenAIAdapter"""
        adapter = DeepSeekAdapter(config={"api_key": "test"})
        assert adapter._default_model == "gpt-4o"

    def test_default_model_overridable(self):
        adapter = DeepSeekAdapter(config={"api_key": "test", "default": "deepseek-chat"})
        assert adapter._default_model == "deepseek-chat"


class TestMessageToDict:
    """消息转换测试 (继承自 OpenAIAdapter)"""

    def test_basic_message(self):
        msg = Message(role="user", content="Hello")
        result = DeepSeekAdapter._message_to_dict(msg)
        assert result == {"role": "user", "content": "Hello"}

    def test_system_message(self):
        msg = Message(role="system", content="You are helpful")
        result = DeepSeekAdapter._message_to_dict(msg)
        assert result == {"role": "system", "content": "You are helpful"}

    def test_message_with_name(self):
        msg = Message(role="user", content="Hi", name="test_user")
        result = DeepSeekAdapter._message_to_dict(msg)
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
        result = DeepSeekAdapter._message_to_dict(msg)
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["id"] == "tc_1"
        assert result["tool_calls"][0]["function"]["name"] == "search"

    def test_message_with_tool_call_id(self):
        msg = Message(role="tool", content="result", tool_call_id="tc_1")
        result = DeepSeekAdapter._message_to_dict(msg)
        assert result["tool_call_id"] == "tc_1"

    def test_none_content_omitted(self):
        msg = Message(role="assistant", content=None)
        result = DeepSeekAdapter._message_to_dict(msg)
        assert "content" not in result


class TestParseResponse:
    """响应解析测试 (继承自 OpenAIAdapter)"""

    def test_text_response(self):
        data = {
            "choices": [
                {
                    "message": {"content": "Hello!", "role": "assistant"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "model": "deepseek-chat",
        }
        result = DeepSeekAdapter._parse_response(data)
        assert result.content == "Hello!"
        assert result.finish_reason == "stop"
        assert result.usage.total_tokens == 15
        assert result.model == "deepseek-chat"

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
            "model": "deepseek-chat",
        }
        result = DeepSeekAdapter._parse_response(data)
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
        result = DeepSeekAdapter._parse_response(data)
        assert result.usage is None


class TestParseChunk:
    """流式响应块解析测试 (继承自 OpenAIAdapter)"""

    def test_text_delta(self):
        data = {
            "choices": [
                {
                    "delta": {"content": "Hello"},
                    "finish_reason": None,
                }
            ]
        }
        chunk = DeepSeekAdapter._parse_chunk(data)
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
        chunk = DeepSeekAdapter._parse_chunk(data)
        assert chunk.finish_reason == "stop"


class TestBuildPayload:
    """请求构建测试 (继承自 OpenAIAdapter)"""

    def test_basic_payload(self):
        adapter = DeepSeekAdapter(config={"api_key": "test", "default": "deepseek-chat"})
        messages = [Message(role="user", content="Hello")]
        payload = adapter._build_payload(
            messages=messages,
            tools=None,
            temperature=0.7,
            max_tokens=1024,
            stream=False,
        )
        assert payload["model"] == "deepseek-chat"
        assert payload["temperature"] == 0.7
        assert payload["max_tokens"] == 1024
        assert payload["stream"] is False
        assert len(payload["messages"]) == 1

    def test_with_tools(self):
        adapter = DeepSeekAdapter(config={"api_key": "test"})
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
        adapter = DeepSeekAdapter(config={"api_key": "test"})
        messages = [Message(role="user", content="Hello")]
        payload = adapter._build_payload(
            messages=messages,
            tools=None,
            temperature=0.7,
            max_tokens=4096,
            stream=False,
            system_prompt="You are helpful",
        )
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][0]["content"] == "You are helpful"
        assert len(payload["messages"]) == 2


class TestEnsureClient:
    @pytest.mark.asyncio
    async def test_no_api_key_raises(self):
        adapter = DeepSeekAdapter(config={})
        with pytest.raises(ValueError, match="API key not configured"):
            await adapter._ensure_client()

    @pytest.mark.asyncio
    async def test_with_api_key(self):
        adapter = DeepSeekAdapter(config={"api_key": "sk-test"})
        client = await adapter._ensure_client()
        assert client is not None
        await adapter.close()

    @pytest.mark.asyncio
    async def test_close(self):
        adapter = DeepSeekAdapter(config={"api_key": "sk-test"})
        await adapter._ensure_client()
        await adapter.close()
        assert adapter._client is None

    @pytest.mark.asyncio
    async def test_close_when_not_opened(self):
        adapter = DeepSeekAdapter(config={"api_key": "sk-test"})
        await adapter.close()


class TestChatCompletion:
    @pytest.mark.asyncio
    async def test_chat_completion(self):
        adapter = DeepSeekAdapter(config={"api_key": "sk-test"})
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {"content": "Hi there!", "role": "assistant"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            "model": "deepseek-chat",
        }
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        adapter._client = mock_client

        result = await adapter.chat_completion(messages=[Message(role="user", content="Hi")])
        assert result.content == "Hi there!"
        assert result.model == "deepseek-chat"
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_completion_uses_openai_endpoint(self):
        """使用 OpenAI 兼容端点 /chat/completions（不是 /v1/chat/completions）"""
        adapter = DeepSeekAdapter(config={"api_key": "sk-test"})
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
        }
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        adapter._client = mock_client

        await adapter.chat_completion(messages=[Message(role="user", content="Hi")])
        call_args = mock_client.post.call_args
        # OpenAIAdapter 使用 /chat/completions 端点
        assert call_args[0][0] == "/chat/completions"
