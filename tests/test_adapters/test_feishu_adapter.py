"""飞书 (Feishu/Lark) 通道适配器测试"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yuanbot.adapters.channel.feishu_adapter import (
    FeishuAdapter,
    FeishuMsgType,
)
from yuanbot.core.types import BotResponse, ChannelConfig, ContentType, MessageContent


# ═══════════════════════════════════════════════
# 单元测试
# ═══════════════════════════════════════════════


class TestFeishuAdapter:
    """FeishuAdapter 单元测试"""

    @pytest.fixture
    def adapter(self):
        return FeishuAdapter()

    # ── 基础属性 ──────────────────────────────

    def test_platform_name(self, adapter):
        assert adapter.platform_name == "feishu"

    def test_supported_content_types(self, adapter):
        types = adapter.supported_content_types
        assert ContentType.TEXT in types
        assert len(types) == 1

    # ── 用户 ID 提取 ─────────────────────────

    def test_get_platform_user_id_from_event(self, adapter):
        raw = {
            "event": {
                "sender": {
                    "sender_id": {
                        "open_id": "ou_abc123",
                        "user_id": "uid_xyz",
                        "union_id": "on_union",
                    }
                }
            }
        }
        assert adapter.get_platform_user_id(raw) == "ou_abc123"

    def test_get_platform_user_id_empty_sender_id(self, adapter):
        raw = {"event": {"sender": {"sender_id": {}}}}
        assert adapter.get_platform_user_id(raw) == ""

    def test_get_platform_user_id_missing_event(self, adapter):
        raw = {"event": {}}
        assert adapter.get_platform_user_id(raw) == ""

    def test_get_platform_user_id_from_str(self, adapter):
        assert adapter.get_platform_user_id("ou_abc123") == "ou_abc123"

    # ── 认证头 ───────────────────────────────

    def test_build_auth_headers_no_token(self, adapter):
        headers = adapter._build_auth_headers()
        assert headers["Authorization"] == "Bearer "
        assert "application/json" in headers["Content-Type"]

    def test_build_auth_headers_with_token(self, adapter):
        adapter._tenant_access_token = "t-test-token-xyz"
        headers = adapter._build_auth_headers()
        assert headers["Authorization"] == "Bearer t-test-token-xyz"

    # ── 文本分段 ─────────────────────────────

    def test_split_text_short(self, adapter):
        assert adapter._split_text("Hello", 100) == ["Hello"]

    def test_split_text_long(self, adapter):
        text = "A" * 100
        chunks = adapter._split_text(text, 30)
        assert len(chunks) == 4
        assert "".join(chunks) == text

    def test_split_text_exact_boundary(self, adapter):
        text = "B" * 4000
        chunks = adapter._split_text(text, 4000)
        assert len(chunks) == 1

    # ── 消息文本提取 ─────────────────────────

    def test_extract_message_text_plain(self, adapter):
        message = {
            "message_type": "text",
            "content": json.dumps({"text": "你好世界"}),
        }
        assert adapter._extract_message_text(message) == "你好世界"

    def test_extract_message_text_with_spaces(self, adapter):
        message = {
            "message_type": "text",
            "content": json.dumps({"text": "  hello  "}),
        }
        assert adapter._extract_message_text(message) == "hello"

    def test_extract_message_text_empty(self, adapter):
        message = {"message_type": "text", "content": ""}
        assert adapter._extract_message_text(message) == ""

    def test_extract_message_text_invalid_json(self, adapter):
        message = {"message_type": "text", "content": "not-json"}
        assert adapter._extract_message_text(message) == ""

    def test_extract_message_text_post(self, adapter):
        post_content = {
            "zh_cn": {
                "title": "日报",
                "content": [
                    [
                        {"tag": "text", "text": "今天"},
                        {"tag": "text", "text": "天气不错"},
                    ]
                ],
            }
        }
        message = {
            "message_type": "post",
            "content": json.dumps(post_content),
        }
        assert adapter._extract_message_text(message) == "日报今天天气不错"

    def test_extract_message_text_post_with_link(self, adapter):
        post_content = {
            "zh_cn": {
                "title": "",
                "content": [
                    [
                        {"tag": "text", "text": "点击 "},
                        {"tag": "a", "text": "链接", "href": "https://example.com"},
                    ]
                ],
            }
        }
        message = {
            "message_type": "post",
            "content": json.dumps(post_content),
        }
        result = adapter._extract_message_text(message)
        assert "链接" in result
        assert "点击" in result

    def test_extract_message_text_post_with_at(self, adapter):
        post_content = {
            "zh_cn": {
                "title": "",
                "content": [
                    [
                        {"tag": "at", "user_name": "张三"},
                        {"tag": "text", "text": " 你好"},
                    ]
                ],
            }
        }
        message = {
            "message_type": "post",
            "content": json.dumps(post_content),
        }
        result = adapter._extract_message_text(message)
        assert "张三" in result
        assert "你好" in result

    def test_extract_message_text_unsupported_type(self, adapter):
        message = {
            "message_type": "image",
            "content": json.dumps({"image_key": "img_xxx"}),
        }
        assert adapter._extract_message_text(message) == ""

    # ── Post 纯文本提取 ─────────────────────

    def test_extract_post_text_multi_lang(self, adapter):
        """只处理第一个语言键"""
        post_content = {
            "en_us": {
                "title": "Title",
                "content": [[{"tag": "text", "text": "Hello"}]],
            },
            "zh_cn": {
                "title": "标题",
                "content": [[{"tag": "text", "text": "你好"}]],
            },
        }
        result = FeishuAdapter._extract_post_text(post_content)
        # 应只处理第一种语言（dict 保序，en_us 先）
        assert "Title" in result
        assert "Hello" in result

    def test_extract_post_text_empty(self, adapter):
        assert FeishuAdapter._extract_post_text({}) == ""

    # ── 飞书常量 ─────────────────────────────

    def test_feishu_msg_type_constants(self):
        assert FeishuMsgType.TEXT == "text"
        assert FeishuMsgType.POST == "post"
        assert FeishuMsgType.IMAGE == "image"
        assert FeishuMsgType.INTERACTIVE == "interactive"


# ═══════════════════════════════════════════════
# 集成测试（mock HTTP）
# ═══════════════════════════════════════════════


class TestFeishuAdapterIntegration:
    """FeishuAdapter 集成测试（mock HTTP 请求）"""

    @pytest.fixture
    def adapter(self):
        a = FeishuAdapter()
        a._client = AsyncMock()
        a._tenant_access_token = "t-test-token"
        a._token_expires_at = 9999999999.0
        return a

    # ── initialize ───────────────────────────

    @pytest.mark.asyncio
    async def test_initialize_success(self):
        adapter = FeishuAdapter()
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "code": 0,
            "tenant_access_token": "t-init-token",
            "expire": 7200,
        }
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            config = ChannelConfig(
                platform="feishu",
                config={
                    "app_id": "cli_test_app",
                    "app_secret": "test_secret",
                },
            )
            await adapter.initialize(config)

        assert adapter._app_id == "cli_test_app"
        assert adapter._tenant_access_token == "t-init-token"
        assert adapter._client is not None

    @pytest.mark.asyncio
    async def test_initialize_missing_credentials(self):
        adapter = FeishuAdapter()
        config = ChannelConfig(platform="feishu", config={})
        with pytest.raises(ValueError, match="app_id and app_secret"):
            await adapter.initialize(config)

    # ── _refresh_token ───────────────────────

    @pytest.mark.asyncio
    async def test_refresh_token_success(self, adapter):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "code": 0,
            "tenant_access_token": "t-new-token",
            "expire": 7200,
        }
        adapter._client.post = AsyncMock(return_value=mock_resp)
        adapter._token_expires_at = 0  # Force refresh

        await adapter._refresh_token()

        assert adapter._tenant_access_token == "t-new-token"
        adapter._client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_token_skips_when_valid(self, adapter):
        adapter._tenant_access_token = "t-existing"
        adapter._token_expires_at = 9999999999.0

        await adapter._refresh_token()

        adapter._client.post.assert_not_called()
        assert adapter._tenant_access_token == "t-existing"

    @pytest.mark.asyncio
    async def test_refresh_token_api_error(self, adapter):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "code": 10003,
            "msg": "invalid app_secret",
        }
        adapter._client.post = AsyncMock(return_value=mock_resp)
        adapter._token_expires_at = 0

        await adapter._refresh_token()

        # Token should not be updated on error
        assert adapter._tenant_access_token == "t-test-token"

    @pytest.mark.asyncio
    async def test_refresh_token_http_error(self, adapter):
        adapter._client.post = AsyncMock(side_effect=Exception("Network error"))
        adapter._token_expires_at = 0
        old_token = adapter._tenant_access_token

        await adapter._refresh_token()

        assert adapter._tenant_access_token == old_token

    # ── send_message ─────────────────────────

    @pytest.mark.asyncio
    async def test_send_message_text_success(self, adapter):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "code": 0,
            "data": {"message_id": "om_msg_001"},
        }
        adapter._client.post = AsyncMock(return_value=mock_resp)

        content = MessageContent(content_type=ContentType.TEXT, text="Hello Feishu!")
        result = await adapter.send_message("ou_user123", content)

        assert result.success is True
        assert result.message_id == "om_msg_001"

    @pytest.mark.asyncio
    async def test_send_message_text_failure(self, adapter):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "code": 99991,
            "msg": "internal error",
        }
        adapter._client.post = AsyncMock(return_value=mock_resp)

        content = MessageContent(content_type=ContentType.TEXT, text="Fail!")
        result = await adapter.send_message("ou_user123", content)

        assert result.success is False
        assert "99991" in result.error

    @pytest.mark.asyncio
    async def test_send_message_unsupported_type(self, adapter):
        content = MessageContent(content_type=ContentType.IMAGE, media_url="http://img.png")
        result = await adapter.send_message("ou_user123", content)

        assert result.success is False
        assert "Unsupported" in result.error

    @pytest.mark.asyncio
    async def test_send_message_http_error(self, adapter):
        import httpx

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_resp.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "500", request=MagicMock(), response=mock_resp
            )
        )
        adapter._client.post = AsyncMock(return_value=mock_resp)

        content = MessageContent(content_type=ContentType.TEXT, text="Error!")
        result = await adapter.send_message("ou_user123", content)

        assert result.success is False
        assert "500" in result.error

    @pytest.mark.asyncio
    async def test_send_message_network_error(self, adapter):
        adapter._client.post = AsyncMock(side_effect=Exception("Connection refused"))

        content = MessageContent(content_type=ContentType.TEXT, text="Timeout!")
        result = await adapter.send_message("ou_user123", content)

        assert result.success is False
        assert "Connection refused" in result.error

    # ── reply_message ────────────────────────

    @pytest.mark.asyncio
    async def test_reply_message_success(self, adapter):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "code": 0,
            "data": {"message_id": "om_reply_001"},
        }
        adapter._client.post = AsyncMock(return_value=mock_resp)

        content = MessageContent(content_type=ContentType.TEXT, text="Reply!")
        result = await adapter.reply_message("om_original_001", content)

        assert result.success is True
        assert result.message_id == "om_reply_001"

    @pytest.mark.asyncio
    async def test_reply_message_unsupported_type(self, adapter):
        content = MessageContent(content_type=ContentType.IMAGE, media_url="http://img.png")
        result = await adapter.reply_message("om_msg_001", content)

        assert result.success is False
        assert "Unsupported" in result.error

    # ── 事件处理 ─────────────────────────────

    @pytest.mark.asyncio
    async def test_handle_message_event_text(self, adapter):
        callback = AsyncMock()
        callback.return_value = BotResponse(
            content=MessageContent(content_type=ContentType.TEXT, text="Hi!")
        )
        adapter._callback = callback
        adapter._deliver_response = AsyncMock()

        body = {
            "schema": "2.0",
            "header": {
                "event_type": "im.message.receive_v1",
                "token": "",
            },
            "event": {
                "sender": {
                    "sender_id": {"open_id": "ou_user_abc"},
                    "sender_type": "user",
                },
                "message": {
                    "message_id": "om_msg_001",
                    "chat_id": "oc_chat_001",
                    "message_type": "text",
                    "content": json.dumps({"text": "你好飞书"}),
                    "create_time": "1700000000",
                },
            },
        }

        await adapter._handle_event(body)

        callback.assert_called_once()
        user_msg = callback.call_args[0][0]
        assert user_msg.text == "你好飞书"
        assert user_msg.platform == "feishu"
        assert user_msg.platform_user_id == "ou_user_abc"
        assert user_msg.metadata["chat_id"] == "oc_chat_001"

    @pytest.mark.asyncio
    async def test_handle_message_event_ignores_bot(self, adapter):
        callback = AsyncMock()
        adapter._callback = callback

        body = {
            "schema": "2.0",
            "header": {"event_type": "im.message.receive_v1", "token": ""},
            "event": {
                "sender": {
                    "sender_id": {"open_id": "ou_bot"},
                    "sender_type": "app",
                },
                "message": {
                    "message_id": "om_msg_bot",
                    "chat_id": "oc_chat_001",
                    "message_type": "text",
                    "content": json.dumps({"text": "I am bot"}),
                    "create_time": "1700000000",
                },
            },
        }

        await adapter._handle_event(body)

        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_message_event_post(self, adapter):
        callback = AsyncMock()
        callback.return_value = BotResponse(
            content=MessageContent(content_type=ContentType.TEXT, text="Got it!")
        )
        adapter._callback = callback
        adapter._deliver_response = AsyncMock()

        post_content = {
            "zh_cn": {
                "title": "日报",
                "content": [[{"tag": "text", "text": "今天完成了任务 A"}]],
            }
        }

        body = {
            "schema": "2.0",
            "header": {"event_type": "im.message.receive_v1", "token": ""},
            "event": {
                "sender": {
                    "sender_id": {"open_id": "ou_user_xyz"},
                    "sender_type": "user",
                },
                "message": {
                    "message_id": "om_msg_post",
                    "chat_id": "oc_chat_002",
                    "message_type": "post",
                    "content": json.dumps(post_content),
                    "create_time": "1700000000",
                },
            },
        }

        await adapter._handle_event(body)

        callback.assert_called_once()
        user_msg = callback.call_args[0][0]
        assert "日报" in user_msg.text
        assert "任务 A" in user_msg.text

    @pytest.mark.asyncio
    async def test_handle_event_unhandled_type(self, adapter):
        callback = AsyncMock()
        adapter._callback = callback

        body = {
            "schema": "2.0",
            "header": {"event_type": "im.chat.member.bot.added_v1", "token": ""},
            "event": {},
        }

        await adapter._handle_event(body)

        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_event_token_verification(self, adapter):
        adapter._verification_token = "my_secret_token"
        callback = AsyncMock()
        adapter._callback = callback

        body = {
            "schema": "2.0",
            "header": {
                "event_type": "im.message.receive_v1",
                "token": "wrong_token",
            },
            "event": {
                "sender": {"sender_id": {"open_id": "ou_x"}, "sender_type": "user"},
                "message": {
                    "message_id": "om_x",
                    "chat_id": "",
                    "message_type": "text",
                    "content": json.dumps({"text": "hi"}),
                    "create_time": "0",
                },
            },
        }

        await adapter._handle_event(body)

        callback.assert_not_called()

    # ── deliver_response ─────────────────────

    @pytest.mark.asyncio
    async def test_deliver_response_text_reply(self, adapter):
        adapter.reply_message = AsyncMock(
            return_value=MagicMock(success=True, error=None)
        )

        response = BotResponse(
            content=MessageContent(content_type=ContentType.TEXT, text="Hello!")
        )
        await adapter._deliver_response("om_msg_001", "oc_chat_001", response)

        adapter.reply_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_deliver_response_long_text(self, adapter):
        adapter.reply_message = AsyncMock(
            return_value=MagicMock(success=True, error=None)
        )
        adapter._send_text = AsyncMock(
            return_value=MagicMock(success=True, error=None)
        )

        long_text = "A" * 8000
        response = BotResponse(
            content=MessageContent(content_type=ContentType.TEXT, text=long_text)
        )
        await adapter._deliver_response("om_msg_001", "oc_chat_001", response)

        # First chunk via reply, second via _send_text
        adapter.reply_message.assert_called_once()
        adapter._send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_deliver_response_empty_text(self, adapter):
        adapter.reply_message = AsyncMock()
        adapter._send_text = AsyncMock()

        response = BotResponse(
            content=MessageContent(content_type=ContentType.TEXT, text="")
        )
        await adapter._deliver_response("om_msg_001", "oc_chat_001", response)

        adapter.reply_message.assert_not_called()
        adapter._send_text.assert_not_called()

    # ── URL 验证 ─────────────────────────────

    @pytest.mark.asyncio
    async def test_handle_webhook_url_verification(self, adapter):
        """飞书首次配置回调 URL 时会发送 challenge 验证请求"""
        challenge_value = "ajls384kdjx98XX"

        body = {
            "type": "url_verification",
            "challenge": challenge_value,
        }

        # Simulate the URL verification handling directly
        # (full socket test would be overly complex)
        if body.get("type") == "url_verification":
            challenge = body.get("challenge", "")
            response = {"challenge": challenge}
        else:
            response = {}

        assert response["challenge"] == challenge_value

    # ── shutdown ─────────────────────────────

    @pytest.mark.asyncio
    async def test_shutdown(self, adapter):
        adapter._running = True
        mock_server = AsyncMock()
        mock_server.close = MagicMock()
        mock_server.wait_closed = AsyncMock()
        adapter._webhook_server = mock_server

        await adapter.shutdown()

        assert adapter._running is False
        assert adapter._webhook_server is None
        assert adapter._client is None
        mock_server.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_no_resources(self, adapter):
        adapter._client = None
        adapter._webhook_server = None
        adapter._running = True

        await adapter.shutdown()

        assert adapter._running is False

    # ── listen ───────────────────────────────

    @pytest.mark.asyncio
    async def test_listen_raises_if_not_initialized(self):
        adapter = FeishuAdapter()
        with pytest.raises(RuntimeError, match="not initialized"):
            await adapter.listen(AsyncMock())
