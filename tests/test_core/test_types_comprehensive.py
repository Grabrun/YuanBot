"""YuanBot 核心类型综合测试"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from yuanbot.core.types import (
    BotResponse,
    ChannelConfig,
    ChatChunk,
    ChatResponse,
    ContentType,
    FunctionCall,
    MemoryNode,
    MemorySearchResult,
    MemoryType,
    Message,
    MessageContent,
    ProactiveTask,
    SendResult,
    TokenUsage,
    ToolCall,
    ToolDefinition,
    ToolInvocation,
    ToolResult,
    UserMessage,
    UserProfile,
)


class TestContentType:
    def test_enum_values(self):
        assert ContentType.TEXT == "text"
        assert ContentType.IMAGE == "image"
        assert ContentType.VOICE == "voice"
        assert ContentType.VIDEO == "video"
        assert ContentType.FILE == "file"

    def test_enum_from_value(self):
        assert ContentType("text") == ContentType.TEXT
        assert ContentType("image") == ContentType.IMAGE

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            ContentType("invalid")


class TestMemoryType:
    def test_enum_values(self):
        assert MemoryType.WORKING == "working"
        assert MemoryType.FACT == "fact"
        assert MemoryType.EPISODIC == "episodic"
        assert MemoryType.SEMANTIC == "semantic"


class TestMessage:
    def test_minimal_message(self):
        msg = Message(role="user")
        assert msg.role == "user"
        assert msg.content is None
        assert msg.tool_calls is None

    def test_full_message(self):
        msg = Message(
            role="assistant",
            content="Hello",
            name="bot",
            tool_call_id="tc_123",
        )
        assert msg.role == "assistant"
        assert msg.content == "Hello"
        assert msg.name == "bot"
        assert msg.tool_call_id == "tc_123"

    def test_message_with_tool_calls(self):
        tc = ToolCall(
            id="tc_1",
            function=FunctionCall(name="search", arguments='{"q": "test"}'),
        )
        msg = Message(role="assistant", tool_calls=[tc])
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].function.name == "search"


class TestToolCall:
    def test_auto_id(self):
        tc1 = ToolCall(function=FunctionCall(name="fn", arguments="{}"))
        tc2 = ToolCall(function=FunctionCall(name="fn", arguments="{}"))
        assert tc1.id != tc2.id
        assert len(tc1.id) > 0

    def test_default_type(self):
        tc = ToolCall(function=FunctionCall(name="fn", arguments="{}"))
        assert tc.type == "function"


class TestFunctionCall:
    def test_creation(self):
        fc = FunctionCall(name="get_weather", arguments='{"city": "成都"}')
        assert fc.name == "get_weather"
        parsed = json.loads(fc.arguments)
        assert parsed["city"] == "成都"


class TestTokenUsage:
    def test_defaults(self):
        usage = TokenUsage()
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0

    def test_custom_values(self):
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        assert usage.total_tokens == 150


class TestChatResponse:
    def test_minimal(self):
        resp = ChatResponse()
        assert resp.content is None
        assert resp.tool_calls is None
        assert resp.finish_reason is None

    def test_full(self):
        resp = ChatResponse(
            content="Hello!",
            finish_reason="stop",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            model="gpt-4o",
        )
        assert resp.content == "Hello!"
        assert resp.model == "gpt-4o"


class TestChatChunk:
    def test_text_delta(self):
        chunk = ChatChunk(delta_content="Hello")
        assert chunk.delta_content == "Hello"
        assert chunk.finish_reason is None

    def test_finish_chunk(self):
        chunk = ChatChunk(finish_reason="stop")
        assert chunk.delta_content is None
        assert chunk.finish_reason == "stop"


class TestMessageContent:
    def test_text_content(self):
        content = MessageContent(content_type=ContentType.TEXT, text="Hello")
        assert content.text == "Hello"
        assert content.media_url is None

    def test_image_content(self):
        content = MessageContent(
            content_type=ContentType.IMAGE,
            media_url="https://example.com/img.png",
            metadata={"width": 100},
        )
        assert content.media_url == "https://example.com/img.png"
        assert content.metadata["width"] == 100

    def test_default_metadata(self):
        content = MessageContent(content_type=ContentType.TEXT)
        assert content.metadata == {}


class TestToolDefinition:
    def test_creation(self):
        td = ToolDefinition(
            name="search",
            description="搜索网页",
            parameters={"type": "object", "properties": {"q": {"type": "string"}}},
        )
        assert td.name == "search"
        assert td.permission_level == "safe"

    def test_custom_permission(self):
        td = ToolDefinition(
            name="delete",
            description="删除文件",
            parameters={},
            permission_level="dangerous",
        )
        assert td.permission_level == "dangerous"


class TestToolInvocation:
    def test_defaults(self):
        inv = ToolInvocation(tool_id="search")
        assert inv.params == {}
        assert inv.sandbox_level == "standard"

    def test_custom(self):
        inv = ToolInvocation(
            tool_id="search",
            params={"q": "test"},
            sandbox_level="isolated",
        )
        assert inv.params["q"] == "test"


class TestToolResult:
    def test_success(self):
        result = ToolResult(
            tool_id="search",
            success=True,
            output={"results": []},
            execution_time_ms=123.4,
        )
        assert result.success is True
        assert result.error is None

    def test_failure(self):
        result = ToolResult(
            tool_id="search",
            success=False,
            error="Timeout",
        )
        assert result.success is False
        assert result.output is None


class TestUserMessage:
    def test_minimal(self):
        msg = UserMessage(
            platform="telegram",
            platform_user_id="tg_123",
            yuanbot_user_id="yb_tg_123",
            session_id="telegram:tg_123",
            content_type=ContentType.TEXT,
        )
        assert msg.platform == "telegram"
        assert msg.text is None
        assert isinstance(msg.timestamp, datetime)

    def test_with_metadata(self):
        msg = UserMessage(
            platform="web",
            platform_user_id="u1",
            yuanbot_user_id="yb_u1",
            session_id="web:u1",
            content_type=ContentType.TEXT,
            text="Hello",
            metadata={"key": "value"},
        )
        assert msg.metadata["key"] == "value"


class TestBotResponse:
    def test_minimal(self):
        content = MessageContent(content_type=ContentType.TEXT, text="Hi")
        resp = BotResponse(content=content)
        assert resp.suggested_tools is None
        assert resp.proactive_followups is None

    def test_with_proactive(self):
        content = MessageContent(content_type=ContentType.TEXT, text="Hi")
        task = ProactiveTask(
            task_type="care",
            scheduled_at=datetime.now(),
            content_hint="Check in later",
            priority=1,
        )
        resp = BotResponse(content=content, proactive_followups=[task])
        assert len(resp.proactive_followups) == 1
        assert resp.proactive_followups[0].task_type == "care"


class TestProactiveTask:
    def test_defaults(self):
        task = ProactiveTask(task_type="greeting", scheduled_at=datetime.now())
        assert task.priority == 0
        assert task.content_hint is None


class TestChannelConfig:
    def test_defaults(self):
        config = ChannelConfig(platform="telegram")
        assert config.enabled is True
        assert config.config == {}


class TestMemoryNode:
    def test_auto_id(self):
        n1 = MemoryNode(memory_type=MemoryType.WORKING, content="a")
        n2 = MemoryNode(memory_type=MemoryType.WORKING, content="b")
        assert n1.id != n2.id

    def test_defaults(self):
        node = MemoryNode(memory_type=MemoryType.FACT, content="test")
        assert node.importance_score == 0.5
        assert node.access_count == 0
        assert node.key_entities == []
        assert node.topic_tags == []
        assert node.embedding is None

    def test_full_node(self):
        node = MemoryNode(
            memory_type=MemoryType.EPISODIC,
            content="用户喜欢猫",
            summary="猫相关对话",
            emotional_tone="positive",
            importance_score=0.9,
            key_entities=["猫"],
            topic_tags=["宠物"],
            embedding=[0.1, 0.2, 0.3],
        )
        assert node.emotional_tone == "positive"
        assert len(node.embedding) == 3


class TestUserProfile:
    def test_defaults(self):
        profile = UserProfile(user_id="u1")
        assert profile.relationship_stage == "initial"
        assert profile.trust_score == 0.0
        assert profile.total_interactions == 0
        assert profile.first_interaction is None

    def test_full_profile(self):
        now = datetime.now()
        profile = UserProfile(
            user_id="u1",
            display_name="小明",
            preferences={"color": "blue"},
            relationship_stage="intimate",
            trust_score=0.8,
            total_interactions=100,
            first_interaction=now,
            last_interaction=now,
            platform_ids={"telegram": "tg_123"},
        )
        assert profile.display_name == "小明"
        assert profile.relationship_stage == "intimate"


class TestMemorySearchResult:
    def test_creation(self):
        node = MemoryNode(memory_type=MemoryType.FACT, content="test")
        result = MemorySearchResult(node=node, score=0.85, match_type="semantic")
        assert result.score == 0.85
        assert result.match_type == "semantic"


class TestSendResult:
    def test_success(self):
        r = SendResult(success=True, message_id="msg_1")
        assert r.error is None

    def test_failure(self):
        r = SendResult(success=False, error="timeout")
        assert r.message_id is None
