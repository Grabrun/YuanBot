"""Claude (Anthropic) 适配器测试"""

from __future__ import annotations

import json

from yuanbot.adapters.ai.anthropic_adapter import AnthropicAdapter
from yuanbot.core.types import (
    FunctionCall,
    Message,
    ToolCall,
    ToolDefinition,
)


class TestAnthropicAdapterProperties:
    """属性测试"""

    def test_provider_id(self):
        adapter = AnthropicAdapter(config={"api_key": "test"})
        assert adapter.provider_id == "anthropic"

    def test_supported_models(self):
        adapter = AnthropicAdapter(config={"api_key": "test"})
        models = adapter.supported_models
        assert "claude-sonnet-4-20250514" in models
        assert "claude-opus-4-20250514" in models

    def test_max_context_length_default(self):
        adapter = AnthropicAdapter(config={"api_key": "test"})
        assert adapter.max_context_length == 200000

    def test_max_context_length_custom_model(self):
        adapter = AnthropicAdapter(config={
            "api_key": "test",
            "default_model": "claude-opus-4-20250514",
        })
        assert adapter.max_context_length == 200000


class TestMessageConversion:
    """消息格式转换测试"""

    def test_convert_system_messages_skipped(self):
        """系统消息应被跳过（通过顶层参数传递）"""
        messages = [
            Message(role="system", content="你是助手"),
            Message(role="user", content="你好"),
        ]
        result = AnthropicAdapter._convert_messages(messages)
        assert len(result) == 1
        assert result[0]["role"] == "user"

    def test_convert_user_message(self):
        messages = [Message(role="user", content="你好")]
        result = AnthropicAdapter._convert_messages(messages)
        assert result == [{"role": "user", "content": "你好"}]

    def test_convert_assistant_message(self):
        messages = [Message(role="assistant", content="你好呀")]
        result = AnthropicAdapter._convert_messages(messages)
        assert result == [{"role": "assistant", "content": "你好呀"}]

    def test_convert_tool_result_message(self):
        """工具结果消息应转为 user 消息中的 tool_result 内容块"""
        messages = [Message(role="tool", content="搜索结果", tool_call_id="tc_123")]
        result = AnthropicAdapter._convert_messages(messages)
        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert result[0]["content"][0]["type"] == "tool_result"
        assert result[0]["content"][0]["tool_use_id"] == "tc_123"
        assert result[0]["content"][0]["content"] == "搜索结果"

    def test_convert_assistant_with_tool_calls(self):
        """助手工具调用应转为 tool_use 内容块"""
        messages = [
            Message(
                role="assistant",
                content="让我搜索一下",
                tool_calls=[
                    ToolCall(
                        id="tc_abc",
                        function=FunctionCall(
                            name="search",
                            arguments='{"query": "天气"}',
                        ),
                    )
                ],
            )
        ]
        result = AnthropicAdapter._convert_messages(messages)
        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        content_blocks = result[0]["content"]
        assert len(content_blocks) == 2
        assert content_blocks[0] == {"type": "text", "text": "让我搜索一下"}
        assert content_blocks[1]["type"] == "tool_use"
        assert content_blocks[1]["id"] == "tc_abc"
        assert content_blocks[1]["name"] == "search"
        assert content_blocks[1]["input"] == {"query": "天气"}

    def test_convert_empty_content(self):
        """空内容消息应正常处理"""
        messages = [Message(role="user", content=None)]
        result = AnthropicAdapter._convert_messages(messages)
        assert result[0]["content"] == ""


class TestResponseParsing:
    """响应解析测试"""

    def test_parse_text_response(self):
        data = {
            "id": "msg_123",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "你好呀~"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        result = AnthropicAdapter._parse_response(data)
        assert result.content == "你好呀~"
        assert result.tool_calls is None
        assert result.finish_reason == "stop"
        assert result.usage.prompt_tokens == 10
        assert result.usage.completion_tokens == 5
        assert result.usage.total_tokens == 15

    def test_parse_tool_use_response(self):
        data = {
            "id": "msg_456",
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "text", "text": "让我帮你查一下"},
                {
                    "type": "tool_use",
                    "id": "tu_abc",
                    "name": "weather",
                    "input": {"city": "成都"},
                },
            ],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 20, "output_tokens": 15},
        }
        result = AnthropicAdapter._parse_response(data)
        assert result.content == "让我帮你查一下"
        assert result.tool_calls is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].id == "tu_abc"
        assert result.tool_calls[0].function.name == "weather"
        assert json.loads(result.tool_calls[0].function.arguments) == {"city": "成都"}
        assert result.finish_reason == "tool_calls"

    def test_parse_multiple_text_blocks(self):
        data = {
            "id": "msg_789",
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "text", "text": "第一段"},
                {"type": "text", "text": "第二段"},
            ],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 10},
        }
        result = AnthropicAdapter._parse_response(data)
        assert result.content == "第一段\n第二段"

    def test_parse_empty_content(self):
        data = {
            "id": "msg_empty",
            "type": "message",
            "role": "assistant",
            "content": [],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 5, "output_tokens": 0},
        }
        result = AnthropicAdapter._parse_response(data)
        assert result.content is None


class TestStreamParsing:
    """流式响应解析测试"""

    def test_parse_text_delta(self):
        event = {
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "你好"},
        }
        chunk = AnthropicAdapter._parse_stream_event(event)
        assert chunk is not None
        assert chunk.delta_content == "你好"
        assert chunk.finish_reason is None

    def test_parse_message_delta_stop(self):
        event = {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn"},
        }
        chunk = AnthropicAdapter._parse_stream_event(event)
        assert chunk is not None
        assert chunk.finish_reason == "stop"

    def test_parse_unknown_event(self):
        event = {"type": "message_start"}
        chunk = AnthropicAdapter._parse_stream_event(event)
        assert chunk is None

    def test_parse_tool_use_delta_ignored(self):
        """tool_use_delta 在流式中暂不处理"""
        event = {
            "type": "content_block_delta",
            "delta": {"type": "input_json_delta", "partial_json": '{"q":'},
        }
        chunk = AnthropicAdapter._parse_stream_event(event)
        assert chunk is None


class TestPayloadBuilding:
    """请求构建测试"""

    def test_build_basic_payload(self):
        adapter = AnthropicAdapter(config={"api_key": "test"})
        messages = [Message(role="user", content="你好")]
        payload = adapter._build_payload(
            messages=messages,
            tools=None,
            temperature=0.7,
            max_tokens=1024,
            system_prompt="你是助手",
            stream=False,
        )
        assert payload["model"] == "claude-sonnet-4-20250514"
        assert payload["system"] == "你是助手"
        assert payload["temperature"] == 0.7
        assert payload["max_tokens"] == 1024
        assert payload["stream"] is False
        assert len(payload["messages"]) == 1
        assert "tools" not in payload

    def test_build_payload_with_tools(self):
        adapter = AnthropicAdapter(config={"api_key": "test"})
        messages = [Message(role="user", content="查天气")]
        tools = [
            ToolDefinition(
                name="weather",
                description="查询天气",
                parameters={"type": "object", "properties": {"city": {"type": "string"}}},
            )
        ]
        payload = adapter._build_payload(
            messages=messages,
            tools=tools,
            temperature=0.5,
            max_tokens=2048,
            system_prompt=None,
            stream=True,
        )
        assert "tools" in payload
        assert len(payload["tools"]) == 1
        assert payload["tools"][0]["name"] == "weather"
        assert payload["tools"][0]["input_schema"] == {
            "type": "object",
            "properties": {"city": {"type": "string"}},
        }
        assert payload["stream"] is True
        assert "system" not in payload

    def test_build_payload_no_system(self):
        adapter = AnthropicAdapter(config={"api_key": "test"})
        messages = [Message(role="user", content="你好")]
        payload = adapter._build_payload(
            messages=messages,
            tools=None,
            temperature=0.7,
            max_tokens=4096,
            system_prompt=None,
            stream=False,
        )
        assert "system" not in payload


class TestMessageMerging:
    """消息合并测试（修复连续同角色消息问题）"""

    def test_consecutive_tool_results_merged(self):
        """多个工具结果应合并到同一条 user 消息中"""
        messages = [
            Message(role="tool", content="result1", tool_call_id="tc_1"),
            Message(role="tool", content="result2", tool_call_id="tc_2"),
        ]
        result = AnthropicAdapter._convert_messages(messages)
        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert len(result[0]["content"]) == 2
        assert result[0]["content"][0]["tool_use_id"] == "tc_1"
        assert result[0]["content"][1]["tool_use_id"] == "tc_2"

    def test_consecutive_user_messages_merged(self):
        """连续 user 消息应合并"""
        messages = [
            Message(role="user", content="Hello"),
            Message(role="user", content="World"),
        ]
        result = AnthropicAdapter._convert_messages(messages)
        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert "Hello" in result[0]["content"]
        assert "World" in result[0]["content"]

    def test_user_then_tool_result_merged(self):
        """user 消息后跟 tool_result 应合并"""
        messages = [
            Message(role="user", content="请帮我查询"),
            Message(role="tool", content="查询结果", tool_call_id="tc_1"),
        ]
        result = AnthropicAdapter._convert_messages(messages)
        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert isinstance(result[0]["content"], list)
        assert result[0]["content"][0]["type"] == "text"
        assert result[0]["content"][1]["type"] == "tool_result"

    def test_alternating_roles_preserved(self):
        """正常交替的角色不应被合并"""
        messages = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi"),
            Message(role="user", content="How are you?"),
        ]
        result = AnthropicAdapter._convert_messages(messages)
        assert len(result) == 3
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"
        assert result[2]["role"] == "user"
