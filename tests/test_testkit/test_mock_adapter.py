"""TestAdapter 单元测试"""
from __future__ import annotations

import pytest

from yuanbot.core.types import (
    BotResponse,
    ChannelConfig,
    ContentType,
    MessageContent,
    SendResult,
    UserMessage,
)
from yuanbot_testkit import SentMessage, TestAdapter


@pytest.mark.asyncio
async def test_initialize():
    """initialize 正确设置状态"""
    adapter = TestAdapter()
    config = ChannelConfig(platform="test")
    await adapter.initialize(config)
    assert adapter.is_initialized


@pytest.mark.asyncio
async def test_send_message_records_sent_message():
    """send_message 记录已发送消息"""
    adapter = TestAdapter()
    content = MessageContent(
        content_type=ContentType.TEXT,
        text="Hello!",
    )
    result = await adapter.send_message("user_123", content)
    assert isinstance(result, SendResult)
    assert result.success
    assert len(adapter.sent_messages) == 1
    assert adapter.sent_messages[0].target_id == "user_123"
    assert adapter.sent_messages[0].content.text == "Hello!"


@pytest.mark.asyncio
async def test_send_message_multiple():
    """多次发送消息正确记录"""
    adapter = TestAdapter()
    content = MessageContent(content_type=ContentType.TEXT, text="Msg 1")
    await adapter.send_message("user_1", content)
    await adapter.send_message("user_2", content)
    assert len(adapter.sent_messages) == 2
    assert adapter.sent_messages[0].target_id == "user_1"
    assert adapter.sent_messages[1].target_id == "user_2"


@pytest.mark.asyncio
async def test_simulate_message_triggers_callback():
    """simulate_message 触发已注册的 listen 回调"""
    adapter = TestAdapter()

    async def handler(msg: UserMessage) -> BotResponse:
        return BotResponse(
            content=MessageContent(content_type=ContentType.TEXT, text=f"Echo: {msg.text}")
        )

    await adapter.listen(handler)

    user_msg = UserMessage(
        platform="test",
        platform_user_id="user_1",
        yuanbot_user_id="yb_user_1",
        session_id="sess_1",
        content_type=ContentType.TEXT,
        text="Hi there!",
    )
    response = await adapter.simulate_message(user_msg)
    assert response is not None
    assert response.content.text == "Echo: Hi there!"


@pytest.mark.asyncio
async def test_simulate_message_no_callback():
    """没有注册回调时，simulate_message 返回 None"""
    adapter = TestAdapter()
    user_msg = UserMessage(
        platform="test",
        platform_user_id="user_1",
        yuanbot_user_id="yb_user_1",
        session_id="sess_1",
        content_type=ContentType.TEXT,
        text="Hello",
    )
    response = await adapter.simulate_message(user_msg)
    assert response is None


@pytest.mark.asyncio
async def test_simulate_message_records_received_message():
    """simulate_message 记录收到的消息"""
    adapter = TestAdapter()

    async def handler(msg: UserMessage) -> BotResponse:
        return BotResponse(
            content=MessageContent(content_type=ContentType.TEXT, text="ok")
        )

    await adapter.listen(handler)

    user_msg = UserMessage(
        platform="test",
        platform_user_id="user_1",
        yuanbot_user_id="yb_user_1",
        session_id="sess_1",
        content_type=ContentType.TEXT,
        text="Hello",
    )
    await adapter.simulate_message(user_msg)
    assert len(adapter.received_messages) == 1
    assert adapter.received_messages[0].text == "Hello"


@pytest.mark.asyncio
async def test_listen_registers_callback():
    """listen 注册回调后 callback_registered 为 True"""
    adapter = TestAdapter()

    async def handler(msg: UserMessage) -> BotResponse:
        return BotResponse(
            content=MessageContent(content_type=ContentType.TEXT, text="ok")
        )

    assert not adapter.callback_registered
    await adapter.listen(handler)
    assert adapter.callback_registered


def test_platform_name():
    """platform_name 可读写"""
    adapter = TestAdapter()
    assert adapter.platform_name == "test"

    adapter2 = TestAdapter(platform_name="my_custom_platform")
    assert adapter2.platform_name == "my_custom_platform"

    adapter2.platform_name = "renamed"
    assert adapter2.platform_name == "renamed"


def test_supported_content_types():
    """supported_content_types 可读写"""
    adapter = TestAdapter()
    assert ContentType.TEXT in adapter.supported_content_types
    assert ContentType.IMAGE in adapter.supported_content_types

    adapter.supported_content_types = [ContentType.VOICE]
    assert adapter.supported_content_types == [ContentType.VOICE]


def test_supported_content_types_default():
    """默认支持 TEXT 和 IMAGE"""
    adapter = TestAdapter()
    types = adapter.supported_content_types
    assert ContentType.TEXT in types
    assert ContentType.IMAGE in types


@pytest.mark.asyncio
async def test_reset_clears_messages():
    """reset 清空收发消息记录"""
    adapter = TestAdapter()
    content = MessageContent(content_type=ContentType.TEXT, text="Test")
    await adapter.send_message("u1", content)
    assert len(adapter.sent_messages) == 1

    adapter.reset()
    assert len(adapter.sent_messages) == 0


def test_clear_sent_messages():
    """clear_sent_messages 只清空发送记录"""
    adapter = TestAdapter()
    # Directly append for testing
    adapter._sent_messages.append(
        SentMessage(
            target_id="u1",
            content=MessageContent(content_type=ContentType.TEXT, text="test"),
        )
    )
    adapter.clear_sent_messages()
    assert len(adapter.sent_messages) == 0


def test_get_platform_user_id_with_user_message():
    """get_platform_user_id 正确处理 UserMessage"""
    adapter = TestAdapter()
    msg = UserMessage(
        platform="test",
        platform_user_id="wechat_user_123",
        yuanbot_user_id="yb_123",
        session_id="s1",
        content_type=ContentType.TEXT,
        text="Hello",
    )
    result = adapter.get_platform_user_id(msg)
    assert result == "wechat_user_123"


def test_get_platform_user_id_with_raw():
    """get_platform_user_id 正确处理非 UserMessage 参数"""
    adapter = TestAdapter()
    result = adapter.get_platform_user_id("raw_user_id")
    assert result == "raw_user_id"


@pytest.mark.asyncio
async def test_send_message_id_increments():
    """每次 send_message 返回递增的消息 ID"""
    adapter = TestAdapter()
    content = MessageContent(content_type=ContentType.TEXT, text="Msg")
    r1 = await adapter.send_message("u1", content)
    r2 = await adapter.send_message("u1", content)
    assert r1.message_id == "mock_msg_1"
    assert r2.message_id == "mock_msg_2"
