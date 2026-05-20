"""Discord 通道适配器测试"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yuanbot.adapters.channel.discord_adapter import (
    OP_DISPATCH,
    OP_HEARTBEAT,
    OP_HEARTBEAT_ACK,
    OP_INVALID_SESSION,
    OP_RECONNECT,
    DiscordAdapter,
)
from yuanbot.core.types import ChannelConfig, ContentType, MessageContent, SendResult


class TestDiscordAdapterProperties:
    def test_platform_name(self):
        adapter = DiscordAdapter()
        assert adapter.platform_name == "discord"

    def test_supported_content_types(self):
        adapter = DiscordAdapter()
        assert ContentType.TEXT in adapter.supported_content_types
        assert ContentType.IMAGE in adapter.supported_content_types
        assert ContentType.FILE in adapter.supported_content_types


class TestGetPlatformUserId:
    def test_valid_event(self):
        adapter = DiscordAdapter()
        event = {"author": {"id": "123456789"}}
        assert adapter.get_platform_user_id(event) == "123456789"

    def test_empty_event(self):
        adapter = DiscordAdapter()
        assert adapter.get_platform_user_id({}) == ""

    def test_no_author(self):
        adapter = DiscordAdapter()
        assert adapter.get_platform_user_id({"content": "hello"}) == ""

    def test_non_dict_event(self):
        adapter = DiscordAdapter()
        assert adapter.get_platform_user_id(None) == ""
        assert adapter.get_platform_user_id("string") == ""
        assert adapter.get_platform_user_id(123) == ""

    def test_author_without_id(self):
        adapter = DiscordAdapter()
        assert adapter.get_platform_user_id({"author": {}}) == ""


class TestResolveIntents:
    def test_single_intent(self):
        result = DiscordAdapter._resolve_intents(["GUILDS"])
        assert result == 1 << 0

    def test_multiple_intents(self):
        result = DiscordAdapter._resolve_intents(["GUILDS", "GUILD_MESSAGES", "MESSAGE_CONTENT"])
        expected = (1 << 0) | (1 << 9) | (1 << 15)
        assert result == expected

    def test_unknown_intent_ignored(self):
        result = DiscordAdapter._resolve_intents(["UNKNOWN_INTENT", "GUILDS"])
        assert result == 1 << 0

    def test_empty_intents(self):
        result = DiscordAdapter._resolve_intents([])
        assert result == 0

    def test_intent_case_insensitive(self):
        result = DiscordAdapter._resolve_intents(["guilds"])
        assert result == 1 << 0

    def test_direct_messages_intent(self):
        result = DiscordAdapter._resolve_intents(["DIRECT_MESSAGES"])
        assert result == 1 << 12


class TestInitialize:
    @pytest.mark.asyncio
    async def test_no_token_raises(self):
        adapter = DiscordAdapter()
        config = ChannelConfig(platform="discord", config={})
        with pytest.raises(ValueError, match="bot_token"):
            await adapter.initialize(config)

    @pytest.mark.asyncio
    async def test_initialize_sets_config(self):
        adapter = DiscordAdapter()
        config = ChannelConfig(
            platform="discord",
            config={
                "bot_token": "test_token_123",
                "public_key": "test_pub_key",
                "intents": ["GUILD_MESSAGES", "MESSAGE_CONTENT"],
            },
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"username": "TestBot", "id": "111"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            await adapter.initialize(config)

        assert adapter._bot_token == "test_token_123"
        assert adapter._public_key == "test_pub_key"


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_send_text_message(self):
        adapter = DiscordAdapter()
        adapter._session = AsyncMock()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "msg_123"}
        mock_response.raise_for_status = MagicMock()
        adapter._session.post = AsyncMock(return_value=mock_response)

        content = MessageContent(content_type=ContentType.TEXT, text="Hello!")
        result = await adapter.send_message("channel_456", content)

        assert result.success is True
        assert result.message_id == "msg_123"
        adapter._session.post.assert_called_once_with(
            "/channels/channel_456/messages",
            json={"content": "Hello!"},
        )

    @pytest.mark.asyncio
    async def test_send_image_message(self):
        adapter = DiscordAdapter()
        adapter._session = AsyncMock()

        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "msg_789"}
        mock_response.raise_for_status = MagicMock()
        adapter._session.post = AsyncMock(return_value=mock_response)

        content = MessageContent(
            content_type=ContentType.IMAGE,
            text="Look at this",
            media_url="https://example.com/image.png",
        )
        result = await adapter.send_message("channel_456", content)

        assert result.success is True
        call_args = adapter._session.post.call_args
        payload = call_args[1]["json"] if "json" in call_args[1] else call_args[0][1]
        assert "embeds" in payload

    @pytest.mark.asyncio
    async def test_send_no_session_returns_error(self):
        adapter = DiscordAdapter()
        adapter._session = None

        content = MessageContent(content_type=ContentType.TEXT, text="Hello!")
        result = await adapter.send_message("channel_456", content)

        assert result.success is False
        assert "not initialized" in result.error

    @pytest.mark.asyncio
    async def test_send_http_error(self):
        adapter = DiscordAdapter()
        adapter._session = AsyncMock()

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        mock_response.raise_for_status = MagicMock(
            side_effect=Exception("HTTP 403"),
        )
        adapter._session.post = AsyncMock(return_value=mock_response)

        # Simulate HTTPStatusError
        import httpx

        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Forbidden",
            request=MagicMock(),
            response=mock_response,
        )

        content = MessageContent(content_type=ContentType.TEXT, text="Hello!")
        result = await adapter.send_message("channel_456", content)

        assert result.success is False
        assert result.error is not None


class TestHandleMessageCreate:
    @pytest.mark.asyncio
    async def test_ignores_bot_messages(self):
        adapter = DiscordAdapter()
        callback = AsyncMock()
        adapter._callback = callback

        message = {
            "id": "123",
            "content": "I am a bot",
            "channel_id": "456",
            "author": {"id": "789", "bot": True},
        }
        await adapter._handle_message_create(message)

        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_text_message(self):
        adapter = DiscordAdapter()
        callback = AsyncMock()
        adapter._callback = callback

        # Mock the callback return
        from yuanbot.core.types import BotResponse

        callback.return_value = BotResponse(
            content=MessageContent(content_type=ContentType.TEXT, text="Hi!"),
        )

        # Mock send_message
        adapter.send_message = AsyncMock(return_value=SendResult(success=True))

        message = {
            "id": "123",
            "content": "Hello bot",
            "channel_id": "456",
            "author": {"id": "789", "username": "user1"},
        }
        await adapter._handle_message_create(message)

        callback.assert_called_once()
        user_msg = callback.call_args[0][0]
        assert user_msg.platform == "discord"
        assert user_msg.platform_user_id == "789"
        assert user_msg.text == "Hello bot"
        assert user_msg.content_type == ContentType.TEXT

    @pytest.mark.asyncio
    async def test_image_attachment(self):
        adapter = DiscordAdapter()
        callback = AsyncMock()
        adapter._callback = callback

        from yuanbot.core.types import BotResponse

        callback.return_value = BotResponse(
            content=MessageContent(content_type=ContentType.TEXT, text="Nice pic!"),
        )
        adapter.send_message = AsyncMock(return_value=SendResult(success=True))

        message = {
            "id": "123",
            "content": "",
            "channel_id": "456",
            "author": {"id": "789"},
            "attachments": [
                {
                    "id": "att_1",
                    "filename": "photo.png",
                    "content_type": "image/png",
                    "url": "https://cdn.discord.com/attachments/photo.png",
                },
            ],
        }
        await adapter._handle_message_create(message)

        user_msg = callback.call_args[0][0]
        assert user_msg.content_type == ContentType.IMAGE
        assert user_msg.media_url == "https://cdn.discord.com/attachments/photo.png"


class TestHandleGatewayMessage:
    @pytest.mark.asyncio
    async def test_dispatch_ready(self):
        adapter = DiscordAdapter()
        ws = AsyncMock()

        message = {
            "op": OP_DISPATCH,
            "t": "READY",
            "s": 1,
            "d": {
                "session_id": "sess_abc",
                "resume_gateway_url": "wss://gateway.discord.gg",
                "user": {"username": "TestBot"},
            },
        }
        await adapter._handle_gateway_message(ws, message)

        assert adapter._session_id == "sess_abc"
        assert adapter._resume_url is not None

    @pytest.mark.asyncio
    async def test_heartbeat_ack(self):
        adapter = DiscordAdapter()
        adapter._heartbeat_acknowledged = False
        ws = AsyncMock()

        message = {"op": OP_HEARTBEAT_ACK, "d": None}
        await adapter._handle_gateway_message(ws, message)

        assert adapter._heartbeat_acknowledged is True

    @pytest.mark.asyncio
    async def test_reconnect_closes_ws(self):
        adapter = DiscordAdapter()
        ws = AsyncMock()

        message = {"op": OP_RECONNECT, "d": None}
        await adapter._handle_gateway_message(ws, message)

        ws.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_session_clears_state(self):
        adapter = DiscordAdapter()
        adapter._session_id = "old_session"
        adapter._resume_url = "wss://old.url"
        ws = AsyncMock()

        message = {"op": OP_INVALID_SESSION, "d": False}
        await adapter._handle_gateway_message(ws, message)

        assert adapter._session_id is None
        assert adapter._resume_url is None

    @pytest.mark.asyncio
    async def test_sequence_tracking(self):
        adapter = DiscordAdapter()
        ws = AsyncMock()

        message = {"op": OP_DISPATCH, "t": "MESSAGE_CREATE", "s": 42, "d": {}}
        await adapter._handle_gateway_message(ws, message)

        assert adapter._last_sequence == 42


class TestClose:
    @pytest.mark.asyncio
    async def test_close_cancels_tasks(self):
        adapter = DiscordAdapter()

        # Create a real cancelled task
        async def _dummy():
            await asyncio.sleep(100)

        task = asyncio.ensure_future(_dummy())
        adapter._heartbeat_task = task
        adapter._ws_connection = AsyncMock()
        mock_session = AsyncMock()
        adapter._session = mock_session

        await adapter.close()

        assert task.cancelled()
        mock_session.aclose.assert_called_once()


class TestSendHeartbeat:
    @pytest.mark.asyncio
    async def test_sends_heartbeat_with_sequence(self):
        adapter = DiscordAdapter()
        adapter._last_sequence = 42
        ws = AsyncMock()

        await adapter._send_heartbeat(ws)

        ws.send.assert_called_once()
        sent = json.loads(ws.send.call_args[0][0])
        assert sent["op"] == OP_HEARTBEAT
        assert sent["d"] == 42

    @pytest.mark.asyncio
    async def test_sends_heartbeat_with_null_sequence(self):
        adapter = DiscordAdapter()
        adapter._last_sequence = None
        ws = AsyncMock()

        await adapter._send_heartbeat(ws)

        sent = json.loads(ws.send.call_args[0][0])
        assert sent["op"] == OP_HEARTBEAT
        assert sent["d"] is None
