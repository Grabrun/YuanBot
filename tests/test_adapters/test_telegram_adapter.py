"""Telegram 通道适配器测试"""

from __future__ import annotations

import pytest

from yuanbot.adapters.channel.telegram_adapter import TelegramAdapter
from yuanbot.core.types import ChannelConfig, ContentType


class TestTelegramAdapterProperties:
    def test_platform_name(self):
        adapter = TelegramAdapter()
        assert adapter.platform_name == "telegram"

    def test_supported_content_types(self):
        adapter = TelegramAdapter()
        assert ContentType.TEXT in adapter.supported_content_types
        assert ContentType.IMAGE in adapter.supported_content_types
        assert ContentType.VOICE in adapter.supported_content_types


class TestGetPlatformUserId:
    def test_valid_event(self):
        adapter = TelegramAdapter()
        event = {"message": {"from": {"id": 12345}}}
        assert adapter.get_platform_user_id(event) == "12345"

    def test_empty_event(self):
        adapter = TelegramAdapter()
        assert adapter.get_platform_user_id({}) == ""

    def test_no_message(self):
        adapter = TelegramAdapter()
        assert adapter.get_platform_user_id({"update_id": 1}) == ""

    def test_no_from(self):
        adapter = TelegramAdapter()
        assert adapter.get_platform_user_id({"message": {}}) == ""

    def test_non_dict_event(self):
        adapter = TelegramAdapter()
        assert adapter.get_platform_user_id(None) == ""
        assert adapter.get_platform_user_id("string") == ""
        assert adapter.get_platform_user_id(123) == ""

    def test_from_without_id(self):
        adapter = TelegramAdapter()
        assert adapter.get_platform_user_id({"message": {"from": {}}}) == ""


class TestHandleUpdate:
    @pytest.mark.asyncio
    async def test_non_message_update_ignored(self):
        adapter = TelegramAdapter()
        # Should not raise
        await adapter._handle_update({"update_id": 1})

    @pytest.mark.asyncio
    async def test_message_without_user_ignored(self):
        adapter = TelegramAdapter()
        await adapter._handle_update({"message": {}})


class TestInitialize:
    @pytest.mark.asyncio
    async def test_no_token_raises(self):
        adapter = TelegramAdapter()
        config = ChannelConfig(platform="telegram", config={})
        with pytest.raises(ValueError, match="bot_token"):
            await adapter.initialize(config)
