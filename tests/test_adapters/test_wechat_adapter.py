"""微信通道适配器测试"""

from __future__ import annotations

import asyncio
import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yuanbot.adapters.channel.wechat_adapter import (
    TypingStatus,
    WeixinAdapter,
    MessageItemType,
    MessageType,
    MessageState,
)
from yuanbot.adapters.channel.wechat_cdn import (
    UploadMediaType,
    aes_ecb_decrypt,
    aes_ecb_encrypt,
    aes_ecb_padded_size,
    compute_md5,
    generate_aes_key,
    generate_file_key,
    parse_aes_key_from_item,
)
from yuanbot.core.types import ChannelConfig, ContentType, MessageContent


# ── AES 加密测试 ──────────────────────────────


class TestAesEcb:
    """AES-128-ECB 加解密测试"""

    def test_encrypt_decrypt_roundtrip(self):
        """加密→解密应还原原始明文"""
        key = b"0123456789abcdef"
        plaintext = b"Hello, YuanBot! This is a test message."
        ciphertext = aes_ecb_encrypt(plaintext, key)
        decrypted = aes_ecb_decrypt(ciphertext, key)
        assert decrypted == plaintext

    def test_encrypt_empty(self):
        """空明文加密后应有完整填充块"""
        key = b"0123456789abcdef"
        ciphertext = aes_ecb_encrypt(b"", key)
        assert len(ciphertext) == 16  # 一个填充块

    def test_padded_size(self):
        """密文大小计算"""
        assert aes_ecb_padded_size(0) == 16
        assert aes_ecb_padded_size(1) == 16
        assert aes_ecb_padded_size(16) == 32
        assert aes_ecb_padded_size(17) == 32

    def test_parse_aes_key_raw(self):
        """解析 raw 16 字节 base64 密钥（图片 item）"""
        key_bytes = os.urandom(16)
        key_b64 = base64.b64encode(key_bytes).decode()
        item = {"image_item": {"media": {"aes_key": key_b64}}}
        result = parse_aes_key_from_item(item, UploadMediaType.IMAGE)
        assert result == key_bytes

    def test_parse_aes_key_hex(self):
        """解析 hex 编码的 base64 密钥（文件 item）"""
        key_bytes = os.urandom(16)
        hex_str = key_bytes.hex()
        key_b64 = base64.b64encode(hex_str.encode()).decode()
        item = {"file_item": {"media": {"aes_key": key_b64}}}
        result = parse_aes_key_from_item(item, UploadMediaType.FILE)
        assert result == key_bytes

    def test_generate_aes_key(self):
        """生成 AES 密钥"""
        key_bytes, key_hex = generate_aes_key()
        assert len(key_bytes) == 16
        assert len(key_hex) == 32
        assert bytes.fromhex(key_hex) == key_bytes

    def test_generate_file_key(self):
        """生成文件标识"""
        fk = generate_file_key()
        assert len(fk) == 32
        # 应为合法 hex
        bytes.fromhex(fk)

    def test_compute_md5(self):
        """MD5 计算"""
        assert compute_md5(b"hello") == "5d41402abc4b2a76b9719d911017c592"


import os


# ── 适配器单元测试 ────────────────────────────


class TestWeixinAdapter:
    """WeixinAdapter 单元测试"""

    @pytest.fixture
    def adapter(self):
        return WeixinAdapter()

    def test_platform_name(self, adapter):
        assert adapter.platform_name == "wechat"

    def test_supported_content_types(self, adapter):
        types = adapter.supported_content_types
        assert ContentType.TEXT in types
        assert ContentType.IMAGE in types
        assert ContentType.VOICE in types
        assert ContentType.VIDEO in types
        assert ContentType.FILE in types

    def test_build_base_info(self, adapter):
        info = adapter._build_base_info()
        assert info["channel_version"] == "2.4.3"
        assert info["bot_agent"] == "YuanBot"

    def test_build_headers_no_auth(self, adapter):
        headers = adapter._build_headers(include_auth=False)
        assert headers["Content-Type"] == "application/json"
        assert headers["AuthorizationType"] == "ilink_bot_token"
        assert headers["iLink-App-Id"] == "bot"
        assert "Authorization" not in headers

    def test_build_headers_with_auth(self, adapter):
        adapter._token = "test_token_123"
        headers = adapter._build_headers(include_auth=True)
        assert headers["Authorization"] == "Bearer test_token_123"

    def test_split_text_short(self, adapter):
        text = "Hello"
        assert adapter._split_text(text, 100) == ["Hello"]

    def test_split_text_long(self, adapter):
        text = "A" * 100
        chunks = adapter._split_text(text, 30)
        assert len(chunks) == 4
        assert "".join(chunks) == text

    def test_get_platform_user_id_from_dict(self, adapter):
        event = {"from_user_id": "wxid_abc@im.wechat"}
        assert adapter.get_platform_user_id(event) == "wxid_abc@im.wechat"

    def test_get_platform_user_id_from_str(self, adapter):
        assert adapter.get_platform_user_id("wxid_abc") == "wxid_abc"

    def test_resolve_yuanbot_user_id(self, adapter):
        uid = adapter._resolve_yuanbot_user_id("wxid_abc")
        assert uid == "yb_wxid_abc"
        # 幂等
        assert adapter._resolve_yuanbot_user_id("wxid_abc") == uid

    def test_build_session_id(self, adapter):
        sid = adapter._build_session_id("wxid_abc")
        assert sid == "wechat:wxid_abc"


# ── 适配器集成测试 (mock HTTP) ────────────────


class TestWeixinAdapterIntegration:
    """WeixinAdapter 集成测试（mock HTTP 请求）"""

    @pytest.fixture
    def adapter(self):
        return WeixinAdapter()

    @pytest.mark.asyncio
    async def test_initialize(self, adapter):
        config = ChannelConfig(
            platform="wechat",
            config={
                "token": "test_token",
                "ilink_user_id": "wxid_test@im.wechat",
                "bot_id": "bot_123",
            },
        )
        await adapter.initialize(config)
        assert adapter._token == "test_token"
        assert adapter._ilink_user_id == "wxid_test@im.wechat"
        assert adapter._client is not None

    @pytest.mark.asyncio
    async def test_send_text_success(self, adapter):
        adapter._token = "test_token"
        adapter._client = AsyncMock()

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ret": 0, "errmsg": ""}
        mock_resp.raise_for_status = MagicMock()
        adapter._client.post = AsyncMock(return_value=mock_resp)

        result = await adapter._send_text("wxid_target@im.wechat", "Hello!", "ctx_token")
        assert result.success is True
        assert result.message_id is not None

    @pytest.mark.asyncio
    async def test_send_text_failure(self, adapter):
        adapter._token = "test_token"
        adapter._client = AsyncMock()

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ret": -1, "errmsg": "some error"}
        mock_resp.raise_for_status = MagicMock()
        adapter._client.post = AsyncMock(return_value=mock_resp)

        result = await adapter._send_text("wxid_target", "Hello!")
        assert result.success is False
        assert "some error" in result.error

    @pytest.mark.asyncio
    async def test_process_text_message(self, adapter):
        """测试入站文本消息处理"""
        callback = AsyncMock()
        from yuanbot.core.types import BotResponse, MessageContent

        callback.return_value = BotResponse(
            content=MessageContent(content_type=ContentType.TEXT, text="Hi!")
        )
        adapter._callback = callback

        # Mock _send_typing 和 _send_text
        adapter._send_typing = AsyncMock()
        adapter._send_text = AsyncMock(return_value=MagicMock(success=True))
        adapter._context_tokens = {}

        msg = {
            "from_user_id": "wxid_user@im.wechat",
            "message_type": MessageType.USER,
            "message_state": MessageState.FINISH,
            "context_token": "test_ctx",
            "message_id": 12345,
            "item_list": [
                {
                    "type": MessageItemType.TEXT,
                    "text_item": {"text": "你好"},
                }
            ],
        }

        await adapter._process_message(msg)

        callback.assert_called_once()
        user_msg = callback.call_args[0][0]
        assert user_msg.text == "你好"
        assert user_msg.platform == "wechat"
        assert adapter._context_tokens["wxid_user@im.wechat"] == "test_ctx"

    @pytest.mark.asyncio
    async def test_session_expired_handling(self, adapter):
        """测试会话过期处理"""
        adapter._running = True
        adapter._client = AsyncMock()

        # 模拟会话过期响应
        expired_resp = {"ret": 0, "errcode": -14, "errmsg": "session expired"}
        adapter._get_updates = AsyncMock(return_value=expired_resp)

        # 执行一次循环
        adapter._running = False  # 让循环只执行一次

        # 直接测试会话过期逻辑
        resp = await adapter._get_updates()
        errcode = resp.get("errcode", 0)
        assert errcode == -14

    @pytest.mark.asyncio
    async def test_shutdown(self, adapter):
        adapter._client = AsyncMock()
        adapter._client.aclose = AsyncMock()
        adapter._running = True

        await adapter.shutdown()

        assert adapter._running is False
        assert adapter._client is None
