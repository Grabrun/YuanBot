"""yuanbot_testkit fixtures 集成测试"""
from __future__ import annotations

import pytest

from yuanbot.core.types import ChatResponse, ContentType
from yuanbot_testkit import MockCore, TestAdapter


@pytest.mark.asyncio
async def test_mock_core_fixture(mock_core: MockCore):
    """mock_core fixture 返回 MockCore 实例"""
    assert isinstance(mock_core, MockCore)
    result = await mock_core.chat_completion(messages=[])
    assert isinstance(result, ChatResponse)


@pytest.mark.asyncio
async def test_test_adapter_fixture(test_adapter: TestAdapter):
    """test_adapter fixture 返回 TestAdapter 实例"""
    assert isinstance(test_adapter, TestAdapter)
    assert test_adapter.platform_name == "test"


def test_sample_messages_fixture(sample_messages):
    """sample_messages fixture 返回对话消息列表"""
    assert len(sample_messages) == 2
    assert sample_messages[0].role == "system"
    assert sample_messages[1].role == "user"


def test_sample_user_message_fixture(sample_user_message):
    """sample_user_message fixture 返回 UserMessage"""
    assert sample_user_message.platform == "test"
    assert sample_user_message.text is not None
    assert sample_user_message.content_type == ContentType.TEXT


def test_sample_config_fixture(sample_config):
    """sample_config fixture 返回 ChannelConfig"""
    assert sample_config.platform == "test"
    assert sample_config.enabled is True


def test_sample_message_content_fixture(sample_message_content):
    """sample_message_content fixture 返回 MessageContent"""
    assert sample_message_content.content_type == ContentType.TEXT
    assert sample_message_content.text is not None


@pytest.mark.asyncio
async def test_configured_mock_core_fixture(configured_mock_core: MockCore):
    """configured_mock_core fixture 已预配置响应"""
    result = await configured_mock_core.chat_completion(messages=[])
    assert result.content == "Mock response from configured fixture"

    embedding = await configured_mock_core.get_embedding(text="test")
    assert embedding == [0.1, 0.2, 0.3]
