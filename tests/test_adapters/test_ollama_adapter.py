"""Ollama 适配器测试"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from yuanbot.adapters.ai.ollama_adapter import OllamaAdapter
from yuanbot.core.types import (
    FunctionCall,
    Message,
    ToolCall,
    ToolDefinition,
)


class TestOllamaAdapterProperties:
    def test_provider_id(self):
        adapter = OllamaAdapter(config={})
        assert adapter.provider_id == "ollama"

    def test_supported_models_from_config(self):
        adapter = OllamaAdapter(
            config={
                "models": [
                    {"id": "qwen3:14b", "type": "chat"},
                    {"id": "nomic-embed-text", "type": "embedding"},
                ]
            }
        )
        models = adapter.supported_models
        assert "qwen3:14b" in models
        assert "nomic-embed-text" in models

    def test_supported_models_empty(self):
        adapter = OllamaAdapter(config={})
        assert adapter.supported_models == []

    def test_max_context_length_default(self):
        adapter = OllamaAdapter(config={})
        assert adapter.max_context_length == 32768

    def test_default_base_url(self):
        adapter = OllamaAdapter(config={})
        assert adapter._base_url == "http://localhost:11434"

    def test_custom_base_url(self):
        adapter = OllamaAdapter(config={"base_url": "http://192.168.1.100:11434"})
        assert adapter._base_url == "http://192.168.1.100:11434"

    def test_default_model(self):
        adapter = OllamaAdapter(config={"default": "qwen3:14b"})
        assert adapter._default_model == "qwen3:14b"


class TestMessageToOllama:
    def test_basic_user_message(self):
        msg = Message(role="user", content="Hello")
        result = OllamaAdapter._message_to_ollama(msg)
        assert result == {"role": "user", "content": "Hello"}

    def test_system_message(self):
        msg = Message(role="system", content="You are helpful")
        result = OllamaAdapter._message_to_ollama(msg)
        assert result == {"role": "system", "content": "You are helpful"}

    def test_assistant_message(self):
        msg = Message(role="assistant", content="Hi!")
        result = OllamaAdapter._message_to_ollama(msg)
        assert result == {"role": "assistant", "content": "Hi!"}

    def test_tool_result_message(self):
        msg = Message(role="tool", content="result data", tool_call_id="tc_1")
        result = OllamaAdapter._message_to_ollama(msg)
        assert result["role"] == "tool"
        assert result["content"] == "result data"
        assert result["tool_call_id"] == "tc_1"

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
        result = OllamaAdapter._message_to_ollama(msg)
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["function"]["name"] == "search"

    def test_none_content(self):
        msg = Message(role="assistant", content=None)
        result = OllamaAdapter._message_to_ollama(msg)
        assert "content" not in result


class TestParseChatResponse:
    def test_text_response(self):
        data = {
            "model": "qwen3:14b",
            "message": {"role": "assistant", "content": "Hello!"},
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 10,
            "eval_count": 5,
        }
        result = OllamaAdapter._parse_chat_response(data)
        assert result.content == "Hello!"
        assert result.finish_reason == "stop"
        assert result.model == "qwen3:14b"
        assert result.usage is not None
        assert result.usage.prompt_tokens == 10
        assert result.usage.completion_tokens == 5
        assert result.usage.total_tokens == 15

    def test_tool_call_response(self):
        data = {
            "model": "qwen3:14b",
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "tc_1",
                        "function": {
                            "name": "search",
                            "arguments": {"q": "test"},
                        },
                    }
                ],
            },
            "done": True,
        }
        result = OllamaAdapter._parse_chat_response(data)
        assert result.tool_calls is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].function.name == "search"
        # Arguments should be JSON string
        assert isinstance(result.tool_calls[0].function.arguments, str)

    def test_streaming_chunk_not_done(self):
        data = {
            "model": "qwen3:14b",
            "message": {"role": "assistant", "content": "Hello"},
            "done": False,
        }
        result = OllamaAdapter._parse_chat_response(data)
        assert result.content == "Hello"
        assert result.finish_reason is None

    def test_no_usage_info(self):
        data = {
            "model": "qwen3:14b",
            "message": {"role": "assistant", "content": "Hi"},
            "done": True,
        }
        result = OllamaAdapter._parse_chat_response(data)
        assert result.usage is None


class TestParseChatChunk:
    def test_text_delta(self):
        data = {
            "model": "qwen3:14b",
            "message": {"role": "assistant", "content": "Hello"},
            "done": False,
        }
        chunk = OllamaAdapter._parse_chat_chunk(data)
        assert chunk.delta_content == "Hello"
        assert chunk.finish_reason is None

    def test_finish_chunk(self):
        data = {
            "model": "qwen3:14b",
            "message": {"role": "assistant", "content": ""},
            "done": True,
            "done_reason": "stop",
        }
        chunk = OllamaAdapter._parse_chat_chunk(data)
        assert chunk.finish_reason == "stop"

    def test_tool_call_chunk(self):
        data = {
            "model": "qwen3:14b",
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "tc_1",
                        "function": {
                            "name": "search",
                            "arguments": {"q": "test"},
                        },
                    }
                ],
            },
            "done": False,
        }
        chunk = OllamaAdapter._parse_chat_chunk(data)
        assert chunk.delta_tool_calls is not None
        assert len(chunk.delta_tool_calls) == 1


class TestBuildChatPayload:
    def test_basic_payload(self):
        adapter = OllamaAdapter(config={"default": "qwen3:14b"})
        messages = [Message(role="user", content="Hello")]
        payload = adapter._build_chat_payload(
            messages=messages,
            tools=None,
            temperature=0.7,
            stream=False,
        )
        assert payload["model"] == "qwen3:14b"
        assert payload["stream"] is False
        assert payload["options"]["temperature"] == 0.7
        assert len(payload["messages"]) == 1

    def test_with_system_prompt(self):
        adapter = OllamaAdapter(config={"default": "qwen3:14b"})
        messages = [Message(role="user", content="Hello")]
        payload = adapter._build_chat_payload(
            messages=messages,
            tools=None,
            temperature=0.7,
            stream=False,
            system_prompt="You are helpful",
        )
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][0]["content"] == "You are helpful"
        assert len(payload["messages"]) == 2

    def test_with_tools(self):
        adapter = OllamaAdapter(config={"default": "qwen3:14b"})
        messages = [Message(role="user", content="Hello")]
        tools = [
            ToolDefinition(
                name="search",
                description="Search",
                parameters={"type": "object"},
            )
        ]
        payload = adapter._build_chat_payload(
            messages=messages,
            tools=tools,
            temperature=0.5,
            stream=True,
        )
        assert len(payload["tools"]) == 1
        assert payload["tools"][0]["function"]["name"] == "search"
        assert payload["stream"] is True

    def test_multi_turn(self):
        adapter = OllamaAdapter(config={"default": "qwen3:14b"})
        messages = [
            Message(role="user", content="Hi"),
            Message(role="assistant", content="Hello!"),
            Message(role="user", content="How are you?"),
        ]
        payload = adapter._build_chat_payload(
            messages=messages,
            tools=None,
            temperature=0.7,
            stream=False,
        )
        assert len(payload["messages"]) == 3


class TestFindEmbeddingModel:
    def test_find_embedding_model(self):
        adapter = OllamaAdapter(
            config={
                "models": [
                    {"id": "qwen3:14b", "type": "chat"},
                    {"id": "nomic-embed-text", "type": "embedding", "dimension": 768},
                ]
            }
        )
        assert adapter._find_embedding_model() == "nomic-embed-text"

    def test_no_embedding_model(self):
        adapter = OllamaAdapter(
            config={
                "models": [
                    {"id": "qwen3:14b", "type": "chat"},
                ]
            }
        )
        assert adapter._find_embedding_model() is None

    def test_no_models(self):
        adapter = OllamaAdapter(config={})
        assert adapter._find_embedding_model() is None


class TestEnsureClient:
    @pytest.mark.asyncio
    async def test_creates_client(self):
        adapter = OllamaAdapter(config={})
        client = await adapter._ensure_client()
        assert client is not None
        await adapter.close()

    @pytest.mark.asyncio
    async def test_reuses_client(self):
        adapter = OllamaAdapter(config={})
        client1 = await adapter._ensure_client()
        client2 = await adapter._ensure_client()
        assert client1 is client2
        await adapter.close()

    @pytest.mark.asyncio
    async def test_close(self):
        adapter = OllamaAdapter(config={})
        await adapter._ensure_client()
        await adapter.close()
        assert adapter._client is None

    @pytest.mark.asyncio
    async def test_close_when_not_opened(self):
        adapter = OllamaAdapter(config={})
        await adapter.close()  # Should not raise


class TestGetEmbedding:
    @pytest.mark.asyncio
    async def test_no_embedding_model_raises(self):
        adapter = OllamaAdapter(config={"models": [{"id": "qwen3:14b", "type": "chat"}]})
        mock_client = AsyncMock()
        adapter._client = mock_client
        with pytest.raises(ValueError, match="No embedding model configured"):
            await adapter.get_embedding("test text")

    @pytest.mark.asyncio
    async def test_embedding_with_configured_model(self):
        adapter = OllamaAdapter(
            config={
                "models": [
                    {"id": "nomic-embed-text", "type": "embedding", "dimension": 768},
                ]
            }
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"embedding": [0.1, 0.2, 0.3]}
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        adapter._client = mock_client

        result = await adapter.get_embedding("test text")
        assert result == [0.1, 0.2, 0.3]
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "/api/embeddings"
        assert call_args[1]["json"]["model"] == "nomic-embed-text"


class TestChatCompletion:
    @pytest.mark.asyncio
    async def test_chat_completion(self):
        adapter = OllamaAdapter(config={"default": "qwen3:14b"})
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "model": "qwen3:14b",
            "message": {"role": "assistant", "content": "Hi there!"},
            "done": True,
            "done_reason": "stop",
        }
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        adapter._client = mock_client

        result = await adapter.chat_completion(messages=[Message(role="user", content="Hi")])
        assert result.content == "Hi there!"
        assert result.model == "qwen3:14b"
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "/api/chat"
