"""pytest fixtures for yuanbot_testkit

提供开箱即用的测试夹具，简化扩展测试的编写。
"""

from __future__ import annotations

from datetime import datetime

import pytest

from yuanbot.core.types import (
    ChannelConfig,
    ChatResponse,
    ContentType,
    Message,
    MessageContent,
    UserMessage,
)
from yuanbot_testkit.mock_adapter import TestAdapter
from yuanbot_testkit.mock_core import MockCore


@pytest.fixture
def mock_core() -> MockCore:
    """MockCore 实例：模拟 AI 对话、嵌入和记忆

    默认返回空/占位响应，可通过 ``mock_core.mock_response(method, value)`` 配置。

    用法::

        def test_my_skill(mock_core):
            mock_core.mock_response("chat_completion", ChatResponse(content="你好！"))
            result = await my_skill.execute(mock_core, {})
            assert result == ...
    """
    return MockCore()


@pytest.fixture
def test_adapter() -> TestAdapter:
    """TestAdapter 实例：模拟消息通道的发送与接收

    默认平台名为 "test"，支持 TEXT 和 IMAGE 内容类型。

    用法::

        def test_send(test_adapter):
            await test_adapter.send_message("user_1", MessageContent(...))
            assert len(test_adapter.sent_messages) == 1
    """
    return TestAdapter(platform_name="test")


@pytest.fixture
def sample_messages() -> list[Message]:
    """示例对话消息（用于 MockCore.chat_completion 测试）"""
    return [
        Message(role="system", content="你是一个测试助手。"),
        Message(role="user", content="你好！"),
    ]


@pytest.fixture
def sample_user_message() -> UserMessage:
    """示例用户消息"""
    return UserMessage(
        platform="test",
        platform_user_id="test_user",
        yuanbot_user_id="yb_test_user",
        session_id="test_session",
        content_type=ContentType.TEXT,
        text="你好，请问今天天气怎么样？",
        timestamp=datetime.now(),
    )


@pytest.fixture
def sample_bot_response_text() -> str:
    """示例机器人回复文本"""
    return "今天天气晴朗，适合出门散步！"


@pytest.fixture
def sample_config() -> ChannelConfig:
    """示例通道配置"""
    return ChannelConfig(
        platform="test",
        enabled=True,
        config={
            "api_key": "test-api-key",
            "bot_token": "test-bot-token",
        },
    )


@pytest.fixture
def sample_message_content() -> MessageContent:
    """示例消息内容"""
    return MessageContent(
        content_type=ContentType.TEXT,
        text="这是一条测试消息",
    )


@pytest.fixture
def configured_mock_core(mock_core: MockCore) -> MockCore:
    """预先配置了响应的 MockCore 实例

    - chat_completion → 返回带 "Mock response" 的 ChatResponse
    - get_embedding → 返回 [0.1, 0.2, 0.3]
    - get_memory → 返回包含一条记忆的列表
    """
    mock_core.mock_response(
        "chat_completion",
        ChatResponse(content="Mock response from configured fixture"),
    )
    mock_core.mock_response("get_embedding", [0.1, 0.2, 0.3])
    return mock_core
