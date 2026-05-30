"""钉钉通道适配器测试"""

from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from yuanbot.adapters.channel.dingtalk_adapter import DingTalkAdapter
from yuanbot.core.types import BotResponse, ChannelConfig, ContentType, MessageContent


class TestDingTalkAdapter:
    """DingTalkAdapter 单元测试"""

    @pytest.fixture
    def adapter(self):
        return DingTalkAdapter()

    def test_platform_name(self, adapter):
        assert adapter.platform_name == "dingtalk"

    def test_supported_content_types(self, adapter):
        types = adapter.supported_content_types
        assert ContentType.TEXT in types
        assert len(types) == 1

    def test_split_text_short(self, adapter):
        assert adapter._split_text("Hello", 100) == ["Hello"]

    def test_split_text_long(self, adapter):
        text = "A" * 100
        chunks = adapter._split_text(text, 30)
        assert len(chunks) == 4
        assert "".join(chunks) == text

    def test_split_text_exact_length(self, adapter):
        text = "A" * 30
        chunks = adapter._split_text(text, 30)
        assert chunks == [text]

    def test_get_platform_user_id_from_dict(self, adapter):
        event = {"senderStaffId": "staff_123", "senderId": "sender_456"}
        assert adapter.get_platform_user_id(event) == "staff_123"

    def test_get_platform_user_id_from_dict_fallback(self, adapter):
        event = {"senderId": "sender_456"}
        assert adapter.get_platform_user_id(event) == "sender_456"

    def test_get_platform_user_id_from_str(self, adapter):
        assert adapter.get_platform_user_id("user_abc") == "user_abc"

    def test_get_send_url_session(self, adapter):
        adapter._access_token = "test_token"
        url = adapter._get_send_url("session")
        assert url == "https://oapi.dingtalk.com/robot/sendBySession?access_token=test_token"

    def test_get_send_url_group(self, adapter):
        adapter._access_token = "test_token"
        url = adapter._get_send_url("group")
        assert url == "https://oapi.dingtalk.com/robot/sendByGroup?access_token=test_token"

    def test_get_send_url_unknown(self, adapter):
        assert adapter._get_send_url("unknown") is None

    def test_build_http_response_200(self, adapter):
        writer = MagicMock()
        adapter._send_http_response(writer, 200, '{"ok":true}')
        writer.write.assert_called_once()
        data = writer.write.call_args[0][0]
        assert b"HTTP/1.1 200 OK" in data
        assert b'{"ok":true}' in data

    def test_build_http_response_405(self, adapter):
        writer = MagicMock()
        adapter._send_http_response(writer, 405, "Method Not Allowed")
        writer.write.assert_called_once()
        data = writer.write.call_args[0][0]
        assert b"HTTP/1.1 405 Method Not Allowed" in data


class TestDingTalkAdapterIntegration:
    """DingTalkAdapter 集成测试（mock HTTP）"""

    @pytest.fixture
    def adapter(self):
        return DingTalkAdapter()

    @pytest.mark.asyncio
    async def test_initialize(self, adapter):
        adapter._client = AsyncMock()
        adapter._refresh_token = AsyncMock()

        config = ChannelConfig(
            platform="dingtalk",
            config={
                "app_key": "test_key",
                "app_secret": "test_secret",
                "webhook_token": "test_webhook",
                "webhook_port": 9090,
            },
        )
        await adapter.initialize(config)

        assert adapter._app_key == "test_key"
        assert adapter._app_secret == "test_secret"
        assert adapter._webhook_token == "test_webhook"
        assert adapter._webhook_port == 9090

    @pytest.mark.asyncio
    async def test_initialize_creates_client(self, adapter):
        """测试 initialize 创建 HTTP 客户端"""
        with patch.object(adapter, "_refresh_token", new_callable=AsyncMock):
            config = ChannelConfig(
                platform="dingtalk",
                config={"app_key": "k", "app_secret": "s"},
            )
            await adapter.initialize(config)
            assert adapter._client is not None
            await adapter._client.aclose()

    @pytest.mark.asyncio
    async def test_refresh_token_success(self, adapter):
        adapter._client = AsyncMock()

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "errcode": 0,
            "errmsg": "ok",
            "access_token": "token_abc",
            "expires_in": 7200,
        }
        mock_resp.raise_for_status = MagicMock()
        adapter._client.get = AsyncMock(return_value=mock_resp)

        adapter._app_key = "test_key"
        adapter._app_secret = "test_secret"

        await adapter._refresh_token()

        assert adapter._access_token == "token_abc"
        assert adapter._token_expires_at > 0

    @pytest.mark.asyncio
    async def test_refresh_token_error(self, adapter):
        adapter._client = AsyncMock()

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "errcode": 40001,
            "errmsg": "invalid credential",
        }
        mock_resp.raise_for_status = MagicMock()
        adapter._client.get = AsyncMock(return_value=mock_resp)

        adapter._app_key = "bad_key"
        adapter._app_secret = "bad_secret"

        await adapter._refresh_token()

        assert adapter._access_token == ""

    @pytest.mark.asyncio
    async def test_refresh_token_skips_when_valid(self, adapter):
        adapter._client = AsyncMock()
        adapter._access_token = "existing_token"
        adapter._token_expires_at = time.time() + 3600  # 1 hour from now

        await adapter._refresh_token()

        # Should not make HTTP call
        adapter._client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_text_success(self, adapter):
        adapter._access_token = "test_token"
        adapter._client = AsyncMock()

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"errcode": 0, "errmsg": "ok"}
        mock_resp.raise_for_status = MagicMock()
        adapter._client.post = AsyncMock(return_value=mock_resp)

        result = await adapter._send_text("session", "user_123", "Hello!")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_send_text_failure(self, adapter):
        adapter._access_token = "test_token"
        adapter._client = AsyncMock()

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"errcode": 40001, "errmsg": "error"}
        mock_resp.raise_for_status = MagicMock()
        adapter._client.post = AsyncMock(return_value=mock_resp)

        result = await adapter._send_text("session", "user_123", "Hello!")
        assert result.success is False
        assert "40001" in result.error

    @pytest.mark.asyncio
    async def test_send_markdown_success(self, adapter):
        adapter._access_token = "test_token"
        adapter._client = AsyncMock()

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"errcode": 0, "errmsg": "ok"}
        mock_resp.raise_for_status = MagicMock()
        adapter._client.post = AsyncMock(return_value=mock_resp)

        result = await adapter._send_markdown(
            "group", "group_123", "Title", "# Hello"
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_send_webhook_success(self, adapter):
        adapter._client = AsyncMock()

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"errcode": 0, "errmsg": "ok"}
        mock_resp.raise_for_status = MagicMock()
        adapter._client.post = AsyncMock(return_value=mock_resp)

        result = await adapter._send_webhook(
            "https://hook.example.com/xxx", "text", text="Hello!"
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_send_webhook_markdown(self, adapter):
        adapter._client = AsyncMock()

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"errcode": 0, "errmsg": "ok"}
        mock_resp.raise_for_status = MagicMock()
        adapter._client.post = AsyncMock(return_value=mock_resp)

        result = await adapter._send_webhook(
            "https://hook.example.com/xxx",
            "markdown",
            title="Test",
            text="# Hello",
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_send_message_text(self, adapter):
        adapter._client = AsyncMock()
        adapter._access_token = "token"

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"errcode": 0, "errmsg": "ok"}
        mock_resp.raise_for_status = MagicMock()
        adapter._client.post = AsyncMock(return_value=mock_resp)

        content = MessageContent(content_type=ContentType.TEXT, text="Hi!")
        result = await adapter.send_message("session:user_123", content)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_send_message_markdown(self, adapter):
        adapter._client = AsyncMock()
        adapter._access_token = "token"

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"errcode": 0, "errmsg": "ok"}
        mock_resp.raise_for_status = MagicMock()
        adapter._client.post = AsyncMock(return_value=mock_resp)

        content = MessageContent(
            content_type=ContentType.TEXT,
            text="# Hello",
            metadata={"markdown": True, "title": "Greeting"},
        )
        result = await adapter.send_message("group:group_123", content)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_send_message_invalid_target(self, adapter):
        adapter._client = AsyncMock()
        content = MessageContent(content_type=ContentType.TEXT, text="Hi!")
        result = await adapter.send_message("invalid_target", content)
        assert result.success is False
        assert "Invalid target_id" in result.error

    @pytest.mark.asyncio
    async def test_send_message_not_initialized(self, adapter):
        content = MessageContent(content_type=ContentType.TEXT, text="Hi!")
        result = await adapter.send_message("session:user", content)
        assert result.success is False
        assert "not initialized" in result.error

    @pytest.mark.asyncio
    async def test_process_webhook_event_single(self, adapter):
        """测试处理单聊 Webhook 事件"""
        callback = AsyncMock()
        callback.return_value = BotResponse(
            content=MessageContent(content_type=ContentType.TEXT, text="Hi!")
        )
        adapter._callback = callback
        adapter._deliver_response = AsyncMock()

        event_data = {
            "text": {"content": " 你好 "},
            "senderStaffId": "staff_123",
            "senderNick": "张三",
            "conversationId": "conv_abc",
            "conversationType": "1",
            "msgId": "msg_001",
        }

        await adapter._process_webhook_event(event_data)

        callback.assert_called_once()
        user_msg = callback.call_args[0][0]
        assert user_msg.text == "你好"
        assert user_msg.platform == "dingtalk"
        assert user_msg.platform_user_id == "staff_123"
        assert user_msg.metadata["scene"] == "single"
        assert user_msg.metadata["sender_nick"] == "张三"

    @pytest.mark.asyncio
    async def test_process_webhook_event_group(self, adapter):
        """测试处理群聊 Webhook 事件"""
        callback = AsyncMock()
        callback.return_value = BotResponse(
            content=MessageContent(content_type=ContentType.TEXT, text="Hi!")
        )
        adapter._callback = callback
        adapter._deliver_response = AsyncMock()

        event_data = {
            "text": {"content": "大家好"},
            "senderStaffId": "staff_456",
            "senderNick": "李四",
            "conversationId": "conv_group_001",
            "conversationType": "2",
            "msgId": "msg_002",
        }

        await adapter._process_webhook_event(event_data)

        callback.assert_called_once()
        user_msg = callback.call_args[0][0]
        assert user_msg.metadata["scene"] == "group"
        assert user_msg.session_id == "dingtalk:group:conv_group_001"

    @pytest.mark.asyncio
    async def test_process_webhook_event_empty_text(self, adapter):
        """测试空消息不触发回调"""
        callback = AsyncMock()
        adapter._callback = callback

        event_data = {
            "text": {"content": "   "},
            "senderStaffId": "staff_123",
            "conversationType": "1",
        }

        await adapter._process_webhook_event(event_data)
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_webhook_event_no_sender(self, adapter):
        """测试无发送者 ID 不触发回调"""
        callback = AsyncMock()
        adapter._callback = callback

        event_data = {
            "text": {"content": "Hello"},
            "conversationType": "1",
        }

        await adapter._process_webhook_event(event_data)
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_webhook_event_no_callback(self, adapter):
        """测试无回调时不崩溃"""
        adapter._callback = None
        # Should not raise
        await adapter._process_webhook_event({"text": {"content": "Hi"}})

    @pytest.mark.asyncio
    async def test_process_webhook_event_string_text(self, adapter):
        """测试 text 字段为字符串的情况"""
        callback = AsyncMock()
        callback.return_value = BotResponse(
            content=MessageContent(content_type=ContentType.TEXT, text="ok")
        )
        adapter._callback = callback
        adapter._deliver_response = AsyncMock()

        event_data = {
            "text": "直接文本内容",
            "senderStaffId": "staff_789",
            "conversationType": "1",
        }

        await adapter._process_webhook_event(event_data)

        user_msg = callback.call_args[0][0]
        assert user_msg.text == "直接文本内容"

    @pytest.mark.asyncio
    async def test_deliver_response_single(self, adapter):
        """测试投递单聊回复"""
        adapter.send_message = AsyncMock(
            return_value=MagicMock(success=True)
        )

        response = BotResponse(
            content=MessageContent(content_type=ContentType.TEXT, text="回复内容")
        )

        await adapter._deliver_response("single", "conv_123", "user_456", response)

        adapter.send_message.assert_called_once()
        call_args = adapter.send_message.call_args
        assert call_args[0][0] == "session:user_456"

    @pytest.mark.asyncio
    async def test_deliver_response_group(self, adapter):
        """测试投递群聊回复"""
        adapter.send_message = AsyncMock(
            return_value=MagicMock(success=True)
        )

        response = BotResponse(
            content=MessageContent(content_type=ContentType.TEXT, text="群回复")
        )

        await adapter._deliver_response("group", "conv_group", "user_789", response)

        adapter.send_message.assert_called_once()
        call_args = adapter.send_message.call_args
        assert call_args[0][0] == "group:conv_group"

    @pytest.mark.asyncio
    async def test_deliver_response_empty(self, adapter):
        """测试空回复不发送"""
        adapter.send_message = AsyncMock()

        response = BotResponse(
            content=MessageContent(content_type=ContentType.TEXT, text="")
        )

        await adapter._deliver_response("single", "conv", "user", response)
        adapter.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_deliver_response_long_text(self, adapter):
        """测试长文本分段发送"""
        adapter.send_message = AsyncMock(
            return_value=MagicMock(success=True)
        )

        long_text = "A" * 30000
        response = BotResponse(
            content=MessageContent(content_type=ContentType.TEXT, text=long_text)
        )

        await adapter._deliver_response("single", "conv", "user", response)

        # 30000 / 20000 = 2 segments
        assert adapter.send_message.call_count == 2

    @pytest.mark.asyncio
    async def test_shutdown(self, adapter):
        adapter._client = AsyncMock()
        adapter._client.aclose = AsyncMock()
        adapter._running = True

        await adapter.shutdown()

        assert adapter._running is False
        assert adapter._client is None

    @pytest.mark.asyncio
    async def test_shutdown_with_server(self, adapter):
        adapter._client = AsyncMock()
        adapter._client.aclose = AsyncMock()
        adapter._running = True

        mock_server = MagicMock()
        mock_server.close = MagicMock()
        mock_server.wait_closed = AsyncMock()
        adapter._webhook_server = mock_server

        await adapter.shutdown()

        mock_server.close.assert_called_once()
        mock_server.wait_closed.assert_called_once()
        assert adapter._webhook_server is None

    @pytest.mark.asyncio
    async def test_listen_raises_if_not_initialized(self, adapter):
        """未初始化时调用 listen 应抛出异常"""
        with pytest.raises(RuntimeError, match="not initialized"):
            await listen_noop(adapter)

    @pytest.mark.asyncio
    async def test_post_send_message_http_error(self, adapter):
        """测试 HTTP 错误处理"""
        adapter._client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_resp.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "500", request=MagicMock(), response=mock_resp
            )
        )
        adapter._client.post = AsyncMock(return_value=mock_resp)

        result = await adapter._post_send_message("https://example.com", {})
        assert result.success is False
        assert "500" in result.error


async def listen_noop(adapter: DingTalkAdapter) -> None:
    """Helper to test listen raises when not initialized"""
    await adapter.listen(AsyncMock())


class TestDingTalkAdapterWebhookServer:
    """Webhook HTTP 服务器测试"""

    @pytest.mark.asyncio
    async def test_handle_get_request(self):
        """GET 请求应返回 405"""
        adapter = DingTalkAdapter()
        writer = MagicMock()
        writer.close = MagicMock()

        reader = AsyncMock()
        reader.readline = AsyncMock(return_value=b"GET / HTTP/1.1\r\n")
        reader.readexactly = AsyncMock(return_value=b"")

        # Read headers until empty line
        call_count = 0

        async def mock_readline():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return b"GET / HTTP/1.1\r\n"
            return b"\r\n"

        reader.readline = mock_readline

        await adapter._handle_webhook_connection(reader, writer)

        writer.write.assert_called()
        data = writer.write.call_args[0][0]
        assert b"405" in data

    @pytest.mark.asyncio
    async def test_handle_post_valid_json(self):
        """有效 POST JSON 应返回 200"""
        adapter = DingTalkAdapter()
        adapter._callback = AsyncMock()
        adapter._callback.return_value = BotResponse(
            content=MessageContent(content_type=ContentType.TEXT, text="ok")
        )
        adapter._deliver_response = AsyncMock()

        body = json.dumps({
            "text": {"content": "Hello"},
            "senderStaffId": "staff_1",
            "conversationType": "1",
        }).encode()

        call_count = 0

        async def mock_readline():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return b"POST / HTTP/1.1\r\n"
            if call_count <= 3:
                if call_count == 2:
                    return f"Content-Length: {len(body)}\r\n".encode()
                return b"Content-Type: application/json\r\n"
            return b"\r\n"

        reader = AsyncMock()
        reader.readline = mock_readline
        reader.readexactly = AsyncMock(return_value=body)

        writer = MagicMock()
        writer.close = MagicMock()

        await adapter._handle_webhook_connection(reader, writer)

        writer.write.assert_called()
        data = writer.write.call_args[0][0]
        assert b"200 OK" in data

    @pytest.mark.asyncio
    async def test_handle_post_invalid_json(self):
        """无效 JSON 应返回 400"""
        adapter = DingTalkAdapter()

        body = b"not json"

        call_count = 0

        async def mock_readline():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return b"POST / HTTP/1.1\r\n"
            if call_count <= 3:
                if call_count == 2:
                    return f"Content-Length: {len(body)}\r\n".encode()
                return b"Content-Type: text/plain\r\n"
            return b"\r\n"

        reader = AsyncMock()
        reader.readline = mock_readline
        reader.readexactly = AsyncMock(return_value=body)

        writer = MagicMock()
        writer.close = MagicMock()

        await adapter._handle_webhook_connection(reader, writer)

        writer.write.assert_called()
        data = writer.write.call_args[0][0]
        assert b"400" in data
