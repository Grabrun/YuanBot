"""企业微信通道适配器测试"""

from __future__ import annotations

import hashlib
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yuanbot.adapters.channel.wecom_adapter import (
    WeComAdapter,
)
from yuanbot.core.types import ChannelConfig, ContentType, MessageContent, SendResult


class TestWeComAdapterProperties:
    def test_platform_name(self):
        adapter = WeComAdapter()
        assert adapter.platform_name == "wecom"

    def test_supported_content_types(self):
        adapter = WeComAdapter()
        assert ContentType.TEXT in adapter.supported_content_types
        assert ContentType.IMAGE in adapter.supported_content_types
        assert ContentType.VOICE in adapter.supported_content_types
        assert ContentType.VIDEO in adapter.supported_content_types
        assert ContentType.FILE in adapter.supported_content_types


class TestGetPlatformUserId:
    def test_from_dict(self):
        adapter = WeComAdapter()
        event = {"FromUserName": "user_abc"}
        assert adapter.get_platform_user_id(event) == "user_abc"

    def test_from_xml(self):
        adapter = WeComAdapter()
        xml_str = "<xml><FromUserName>user_xyz</FromUserName></xml>"
        assert adapter.get_platform_user_id(xml_str) == "user_xyz"

    def test_empty_dict(self):
        adapter = WeComAdapter()
        assert adapter.get_platform_user_id({}) == ""

    def test_invalid_xml(self):
        adapter = WeComAdapter()
        assert adapter.get_platform_user_id("not xml") == ""

    def test_non_dict_non_string(self):
        adapter = WeComAdapter()
        assert adapter.get_platform_user_id(None) == ""
        assert adapter.get_platform_user_id(123) == ""


class TestInitialize:
    @pytest.mark.asyncio
    async def test_no_corp_id_raises(self):
        adapter = WeComAdapter()
        config = ChannelConfig(platform="wecom", config={})
        with pytest.raises(ValueError, match="corp_id"):
            await adapter.initialize(config)

    @pytest.mark.asyncio
    async def test_no_corp_secret_raises(self):
        adapter = WeComAdapter()
        config = ChannelConfig(platform="wecom", config={"corp_id": "corp_123"})
        with pytest.raises(ValueError, match="corp_secret"):
            await adapter.initialize(config)

    @pytest.mark.asyncio
    async def test_no_agent_id_raises(self):
        adapter = WeComAdapter()
        config = ChannelConfig(
            platform="wecom",
            config={"corp_id": "corp_123", "corp_secret": "secret_456"},
        )
        with pytest.raises(ValueError, match="agent_id"):
            await adapter.initialize(config)

    @pytest.mark.asyncio
    async def test_initialize_success(self):
        adapter = WeComAdapter()
        config = ChannelConfig(
            platform="wecom",
            config={
                "corp_id": "corp_123",
                "corp_secret": "secret_456",
                "agent_id": "agent_789",
                "token": "verify_token",
                "encoding_aes_key": "test_aes_key_32_chars_padding!!",
            },
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "errcode": 0,
            "errmsg": "ok",
            "access_token": "test_token",
            "expires_in": 7200,
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            await adapter.initialize(config)

        assert adapter._corp_id == "corp_123"
        assert adapter._corp_secret == "secret_456"
        assert adapter._agent_id == "agent_789"
        assert adapter._access_token == "test_token"


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_send_text_message(self):
        adapter = WeComAdapter()
        adapter._agent_id = "1000002"
        adapter._session = AsyncMock()
        adapter._access_token = "valid_token"
        adapter._token_expires_at = time.time() + 3600

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"errcode": 0, "errmsg": "ok", "msgid": "msg_123"}
        mock_response.raise_for_status = MagicMock()
        adapter._session.post = AsyncMock(return_value=mock_response)

        content = MessageContent(content_type=ContentType.TEXT, text="Hello!")
        result = await adapter.send_message("user_abc", content)

        assert result.success is True
        assert result.message_id == "msg_123"
        call_args = adapter._session.post.call_args
        payload = call_args[1]["json"]
        assert payload["touser"] == "user_abc"
        assert payload["msgtype"] == "text"
        assert payload["text"]["content"] == "Hello!"

    @pytest.mark.asyncio
    async def test_send_image_message(self):
        adapter = WeComAdapter()
        adapter._agent_id = "1000002"
        adapter._session = AsyncMock()
        adapter._access_token = "valid_token"
        adapter._token_expires_at = time.time() + 3600

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"errcode": 0, "errmsg": "ok", "msgid": "msg_456"}
        mock_response.raise_for_status = MagicMock()
        adapter._session.post = AsyncMock(return_value=mock_response)

        content = MessageContent(
            content_type=ContentType.IMAGE,
            media_url="media_id_123",
        )
        result = await adapter.send_message("user_abc", content)

        assert result.success is True
        call_args = adapter._session.post.call_args
        payload = call_args[1]["json"]
        assert payload["msgtype"] == "image"
        assert payload["image"]["media_id"] == "media_id_123"

    @pytest.mark.asyncio
    async def test_send_no_session_returns_error(self):
        adapter = WeComAdapter()
        adapter._session = None

        content = MessageContent(content_type=ContentType.TEXT, text="Hello!")
        result = await adapter.send_message("user_abc", content)

        assert result.success is False
        assert "not initialized" in result.error

    @pytest.mark.asyncio
    async def test_send_api_error(self):
        adapter = WeComAdapter()
        adapter._agent_id = "1000002"
        adapter._session = AsyncMock()
        adapter._access_token = "valid_token"
        adapter._token_expires_at = time.time() + 3600

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"errcode": 40003, "errmsg": "invalid user"}
        mock_response.raise_for_status = MagicMock()
        adapter._session.post = AsyncMock(return_value=mock_response)

        content = MessageContent(content_type=ContentType.TEXT, text="Hello!")
        result = await adapter.send_message("user_abc", content)

        assert result.success is False
        assert "40003" in result.error

    @pytest.mark.asyncio
    async def test_send_no_session_not_initialized(self):
        adapter = WeComAdapter()
        content = MessageContent(content_type=ContentType.TEXT, text="test")
        result = await adapter.send_message("user_abc", content)
        assert result.success is False


class TestVerifySignature:
    def test_valid_signature(self):
        adapter = WeComAdapter()
        adapter._token = "test_token"

        timestamp = "1234567890"
        nonce = "nonce_abc"
        encrypt = "encrypted_data"

        params = sorted([adapter._token, timestamp, nonce, encrypt])
        expected_sig = hashlib.sha1("".join(params).encode("utf-8")).hexdigest()

        assert adapter._verify_signature(expected_sig, timestamp, nonce, encrypt) is True

    def test_invalid_signature(self):
        adapter = WeComAdapter()
        adapter._token = "test_token"

        assert adapter._verify_signature("wrong_sig", "123", "nonce", "data") is False

    def test_empty_token_returns_false(self):
        adapter = WeComAdapter()
        adapter._token = ""

        assert adapter._verify_signature("sig", "123", "nonce", "data") is False


class TestVerifyCallbackSignature:
    def test_returns_decrypted_echostr(self):
        adapter = WeComAdapter()
        adapter._token = "test_token"
        adapter._encoding_aes_key = "test_key_32_chars_padding_here!!"

        # Mock the decrypt to avoid crypto dependency in this test
        with patch.object(adapter, "_verify_signature", return_value=True):
            with patch.object(adapter, "_decrypt_message", return_value="echo_str_decrypted"):
                result = adapter.verify_callback_signature("sig", "123", "nonce", "echo")
                assert result == "echo_str_decrypted"

    def test_returns_none_on_invalid_signature(self):
        adapter = WeComAdapter()
        adapter._token = "test_token"

        with patch.object(adapter, "_verify_signature", return_value=False):
            result = adapter.verify_callback_signature("sig", "123", "nonce", "echo")
            assert result is None


class TestHandleCallback:
    @pytest.mark.asyncio
    async def test_invalid_signature_returns_success(self):
        adapter = WeComAdapter()
        adapter._token = "test_token"

        with patch.object(adapter, "_verify_signature", return_value=False):
            result = await adapter.handle_callback("<xml/>", "bad_sig", "123", "nonce")
            assert result == "success"

    @pytest.mark.asyncio
    async def test_text_message_callback(self):
        adapter = WeComAdapter()
        adapter._agent_id = "1000002"
        callback = AsyncMock()
        adapter._callback = callback

        from yuanbot.core.types import BotResponse

        callback.return_value = BotResponse(
            content=MessageContent(content_type=ContentType.TEXT, text="Hi!"),
        )
        adapter.send_message = AsyncMock(return_value=SendResult(success=True))

        decrypted_xml = (
            "<xml>"
            "<ToUserName>corp_id</ToUserName>"
            "<FromUserName>user_abc</FromUserName>"
            "<CreateTime>1234567890</CreateTime>"
            "<MsgType>text</MsgType>"
            "<Content>Hello bot</Content>"
            "<MsgId>12345</MsgId>"
            "</xml>"
        )

        with (
            patch.object(
                WeComAdapter,
                "_verify_signature",
                return_value=True,
            ),
            patch.object(
                WeComAdapter,
                "_decrypt_message",
                return_value=decrypted_xml,
            ),
        ):
            result = await adapter.handle_callback(
                "<xml><Encrypt>test</Encrypt></xml>",
                "sig",
                "123",
                "nonce",
            )

        assert result == "success"
        callback.assert_called_once()
        user_msg = callback.call_args[0][0]
        assert user_msg.platform == "wecom"
        assert user_msg.platform_user_id == "user_abc"
        assert user_msg.text == "Hello bot"
        assert user_msg.content_type == ContentType.TEXT


class TestEncryptDecrypt:
    def test_decrypt_requires_cryptography(self):
        adapter = WeComAdapter()
        adapter._encoding_aes_key = "test_key_32_chars_padding_here!!"

        with patch.dict(
            "sys.modules",
            {
                "cryptography": None,
                "cryptography.hazmat": None,
                "cryptography.hazmat.primitives": None,
                "cryptography.hazmat.primitives.ciphers": None,
            },
        ):
            with pytest.raises(RuntimeError, match="cryptography"):
                adapter._decrypt_message("dGVzdA==")

    def test_encrypt_requires_cryptography(self):
        adapter = WeComAdapter()
        adapter._encoding_aes_key = "test_key_32_chars_padding_here!!"

        with patch.dict(
            "sys.modules",
            {
                "cryptography": None,
                "cryptography.hazmat": None,
                "cryptography.hazmat.primitives": None,
                "cryptography.hazmat.primitives.ciphers": None,
            },
        ):
            with pytest.raises(RuntimeError, match="cryptography"):
                adapter._encrypt_message("hello")


class TestRefreshAccessToken:
    @pytest.mark.asyncio
    async def test_successful_refresh(self):
        adapter = WeComAdapter()
        adapter._session = AsyncMock()
        adapter._corp_id = "corp_123"
        adapter._corp_secret = "secret_456"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "errcode": 0,
            "errmsg": "ok",
            "access_token": "new_token",
            "expires_in": 7200,
        }
        mock_response.raise_for_status = MagicMock()
        adapter._session.get = AsyncMock(return_value=mock_response)

        await adapter._refresh_access_token()

        assert adapter._access_token == "new_token"
        assert adapter._token_expires_at > time.time()

    @pytest.mark.asyncio
    async def test_failed_refresh_raises(self):
        adapter = WeComAdapter()
        adapter._session = AsyncMock()
        adapter._corp_id = "corp_123"
        adapter._corp_secret = "secret_456"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "errcode": 40013,
            "errmsg": "invalid appid",
        }
        mock_response.raise_for_status = MagicMock()
        adapter._session.get = AsyncMock(return_value=mock_response)

        with pytest.raises(RuntimeError, match="Failed to get access_token"):
            await adapter._refresh_access_token()


class TestEnsureToken:
    @pytest.mark.asyncio
    async def test_refreshes_when_expired(self):
        adapter = WeComAdapter()
        adapter._access_token = "old_token"
        adapter._token_expires_at = time.time() - 100  # already expired

        with patch.object(adapter, "_refresh_access_token", new_callable=AsyncMock) as mock_refresh:
            await adapter._ensure_token()
            mock_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_when_valid(self):
        adapter = WeComAdapter()
        adapter._access_token = "valid_token"
        adapter._token_expires_at = time.time() + 3600

        with patch.object(adapter, "_refresh_access_token", new_callable=AsyncMock) as mock_refresh:
            await adapter._ensure_token()
            mock_refresh.assert_not_called()


class TestClose:
    @pytest.mark.asyncio
    async def test_close(self):
        adapter = WeComAdapter()
        mock_session = AsyncMock()
        adapter._session = mock_session

        await adapter.close()

        mock_session.aclose.assert_called_once()
        assert adapter._session is None
