"""QQ 通道适配器测试"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yuanbot.adapters.channel.qq_adapter import (
    FileType,
    MsgType,
    QQAdapter,
)
from yuanbot.core.types import ChannelConfig, ContentType, MessageContent


class TestQQAdapter:
    """QQAdapter 单元测试"""

    @pytest.fixture
    def adapter(self):
        return QQAdapter()

    def test_platform_name(self, adapter):
        assert adapter.platform_name == "qq"

    def test_supported_content_types(self, adapter):
        types = adapter.supported_content_types
        assert ContentType.TEXT in types
        assert ContentType.IMAGE in types
        assert ContentType.VOICE in types

    def test_strip_at_mention(self, adapter):
        assert adapter._strip_at_mention("<@!12345> 你好") == "你好"
        assert adapter._strip_at_mention("<@12345> 你好") == "你好"
        assert adapter._strip_at_mention("你好世界") == "你好世界"

    def test_split_text_short(self, adapter):
        assert adapter._split_text("Hello", 100) == ["Hello"]

    def test_split_text_long(self, adapter):
        text = "A" * 100
        chunks = adapter._split_text(text, 30)
        assert len(chunks) == 4
        assert "".join(chunks) == text

    def test_calc_intents(self, adapter):
        intents = adapter._calc_intents()
        # GUILDS + GROUP_AND_C2C_EVENT + PUBLIC_GUILD_MESSAGES + DIRECT_MESSAGE + GUILD_MEMBERS + INTERACTION
        assert intents & (1 << 0)   # GUILDS
        assert intents & (1 << 25)  # GROUP_AND_C2C_EVENT
        assert intents & (1 << 30)  # PUBLIC_GUILD_MESSAGES
        assert intents & (1 << 12)  # DIRECT_MESSAGE
        assert intents & (1 << 1)   # GUILD_MEMBERS
        assert intents & (1 << 26)  # INTERACTION

    def test_build_auth_headers_no_token(self, adapter):
        headers = adapter._build_auth_headers()
        assert headers["Authorization"] == "QQBot "
        assert headers["Content-Type"] == "application/json"

    def test_build_auth_headers_with_token(self, adapter):
        adapter._access_token = "test_token_abc"
        headers = adapter._build_auth_headers()
        assert headers["Authorization"] == "QQBot test_token_abc"

    def test_get_platform_user_id_from_dict(self, adapter):
        event = {"author": {"user_openid": "openid_abc"}}
        assert adapter.get_platform_user_id(event) == "openid_abc"

    def test_get_platform_user_id_from_dict_member(self, adapter):
        event = {"author": {"member_openid": "member_abc"}}
        assert adapter.get_platform_user_id(event) == "member_abc"

    def test_get_platform_user_id_from_str(self, adapter):
        assert adapter.get_platform_user_id("openid_abc") == "openid_abc"


class TestQQAdapterIntegration:
    """QQAdapter 集成测试（mock HTTP）"""

    @pytest.fixture
    def adapter(self):
        return QQAdapter()

    @pytest.mark.asyncio
    async def test_initialize(self, adapter):
        adapter._client = AsyncMock()
        adapter._refresh_token = AsyncMock()

        config = ChannelConfig(
            platform="qq",
            config={
                "app_id": "test_app_id",
                "app_secret": "test_secret",
            },
        )
        await adapter.initialize(config)
        assert adapter._app_id == "test_app_id"
        assert adapter._app_secret == "test_secret"

    @pytest.mark.asyncio
    async def test_send_text_success(self, adapter):
        adapter._access_token = "test_token"
        adapter._client = AsyncMock()

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "msg_123"}
        mock_resp.raise_for_status = MagicMock()
        adapter._client.post = AsyncMock(return_value=mock_resp)

        result = await adapter._send_text("c2c", "openid_abc", "Hello!")
        assert result.success is True
        assert result.message_id == "msg_123"

    @pytest.mark.asyncio
    async def test_send_text_failure(self, adapter):
        adapter._access_token = "test_token"
        adapter._client = AsyncMock()

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock(side_effect=Exception("HTTP Error"))
        adapter._client.post = AsyncMock(return_value=mock_resp)

        result = await adapter._send_text("c2c", "openid_abc", "Hello!")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_handle_c2c_message(self, adapter):
        callback = AsyncMock()
        from yuanbot.core.types import BotResponse, MessageContent

        callback.return_value = BotResponse(
            content=MessageContent(content_type=ContentType.TEXT, text="Hi!")
        )
        adapter._callback = callback
        adapter._deliver_response = AsyncMock()

        data = {
            "author": {"user_openid": "user_123"},
            "content": "你好",
            "id": "msg_456",
            "timestamp": "1234567890",
        }

        await adapter._handle_c2c_message(data)

        callback.assert_called_once()
        user_msg = callback.call_args[0][0]
        assert user_msg.text == "你好"
        assert user_msg.platform == "qq"
        assert user_msg.metadata["scene"] == "c2c"

    @pytest.mark.asyncio
    async def test_handle_group_at_message(self, adapter):
        callback = AsyncMock()
        from yuanbot.core.types import BotResponse, MessageContent

        callback.return_value = BotResponse(
            content=MessageContent(content_type=ContentType.TEXT, text="Hi!")
        )
        adapter._callback = callback
        adapter._deliver_response = AsyncMock()

        data = {
            "author": {"member_openid": "member_123"},
            "group_openid": "group_456",
            "content": "<@!bot_id> 你好",
            "id": "msg_789",
        }

        await adapter._handle_group_at_message(data)

        callback.assert_called_once()
        user_msg = callback.call_args[0][0]
        assert user_msg.text == "你好"  # @标记被去除
        assert user_msg.metadata["scene"] == "group"
        assert user_msg.metadata["group_openid"] == "group_456"

    @pytest.mark.asyncio
    async def test_shutdown(self, adapter):
        adapter._client = AsyncMock()
        adapter._client.aclose = AsyncMock()
        adapter._running = True

        await adapter.shutdown()

        assert adapter._running is False
        assert adapter._client is None
