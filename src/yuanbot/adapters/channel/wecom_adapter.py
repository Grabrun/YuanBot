"""企业微信消息通道适配器

基于企业微信机器人 API，支持文本、图片、语音等消息类型。
通过 HTTP 回调接收消息，支持消息加解密（AES-256-CBC）。
"""

from __future__ import annotations

import asyncio
import hashlib
import time
import xml.etree.ElementTree as ET
from base64 import b64decode, b64encode
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import structlog

from yuanbot.adapters.channel.base import BaseChannelAdapter
from yuanbot.core.types import (
    BotResponse,
    ChannelConfig,
    ContentType,
    MessageContent,
    SendResult,
    UserMessage,
)

logger = structlog.get_logger(__name__)

# 企业微信 API 基础 URL
WECOM_API_BASE = "https://qyapi.weixin.qq.com/cgi-bin"

# access_token 缓存有效期（秒），实际为 7200，预留 buffer
TOKEN_CACHE_TTL = 6000

# 消息类型映射
_MSG_TYPE_MAP: dict[str, ContentType] = {
    "text": ContentType.TEXT,
    "image": ContentType.IMAGE,
    "voice": ContentType.VOICE,
    "video": ContentType.VIDEO,
    "file": ContentType.FILE,
}


class WeComAdapter(BaseChannelAdapter):
    """企业微信消息通道适配器

    使用企业微信机器人 API 进行消息收发。
    支持文本、图片、语音等消息类型。
    """

    def __init__(self, config: ChannelConfig | None = None):
        super().__init__(config)
        self._corp_id: str = ""
        self._corp_secret: str = ""
        self._agent_id: str = ""
        self._token: str = ""
        self._encoding_aes_key: str = ""
        self._session: httpx.AsyncClient | None = None
        self._access_token: str = ""
        self._token_expires_at: float = 0.0
        self._callback: Callable[[UserMessage], Awaitable[BotResponse]] | None = None

    @property
    def platform_name(self) -> str:
        return "wecom"

    @property
    def supported_content_types(self) -> list[ContentType]:
        return [
            ContentType.TEXT,
            ContentType.IMAGE,
            ContentType.VOICE,
            ContentType.VIDEO,
            ContentType.FILE,
        ]

    async def initialize(self, config: ChannelConfig) -> None:
        """初始化企业微信适配器"""
        self._config = config
        cfg = config.config

        self._corp_id = cfg.get("corp_id", "")
        self._corp_secret = cfg.get("corp_secret", "")
        self._agent_id = cfg.get("agent_id", "")
        self._token = cfg.get("token", "")
        self._encoding_aes_key = cfg.get("encoding_aes_key", "")

        if not self._corp_id:
            raise ValueError("WeCom corp_id is required")
        if not self._corp_secret:
            raise ValueError("WeCom corp_secret is required")
        if not self._agent_id:
            raise ValueError("WeCom agent_id is required")

        self._session = httpx.AsyncClient(
            base_url=WECOM_API_BASE,
            timeout=30.0,
        )

        # 获取 access_token
        await self._refresh_access_token()
        logger.info("wecom_initialized", corp_id=self._corp_id)

    async def listen(
        self,
        callback: Callable[[UserMessage], Awaitable[BotResponse]],
    ) -> None:
        """监听企业微信消息

        企业微信通过 HTTP 回调推送消息，此方法启动 token 刷新任务。
        实际的消息接收通过 handle_callback 方法处理。
        """
        self._callback = callback
        logger.info("wecom_listening")
        # 启动 token 自动刷新
        asyncio.create_task(self._token_refresh_loop())

    async def handle_callback(
        self,
        raw_body: str,
        msg_signature: str,
        timestamp: str,
        nonce: str,
    ) -> str:
        """处理企业微信回调消息

        由 HTTP 路由调用：
            @app.post("/wecom/callback")
            async def wecom_callback(request):
                return await wecom_adapter.handle_callback(...)

        Args:
            raw_body: 原始请求体（XML）
            msg_signature: URL 参数中的 msg_signature
            timestamp: URL 参数中的 timestamp
            nonce: URL 参数中的 nonce

        Returns:
            响应 XML 字符串
        """
        try:
            # 验证签名
            if not self._verify_signature(msg_signature, timestamp, nonce, raw_body):
                logger.warning("wecom_signature_verification_failed")
                return "success"

            # 解密消息
            encrypted_xml = ET.fromstring(raw_body)
            encrypt_node = encrypted_xml.find("Encrypt")
            if encrypt_node is None or encrypt_node.text is None:
                return "success"

            decrypted_xml = self._decrypt_message(encrypt_node.text)
            msg_root = ET.fromstring(decrypted_xml)

            msg_type = msg_root.findtext("MsgType", "")
            from_user = msg_root.findtext("FromUserName", "")
            content = msg_root.findtext("Content", "")

            if not from_user:
                return "success"

            # 构建标准化消息
            content_type = _MSG_TYPE_MAP.get(msg_type, ContentType.TEXT)
            text = content if content else None
            media_url = None

            if msg_type == "image":
                pic_url = msg_root.findtext("PicUrl", "")
                media_url = pic_url if pic_url else None
            elif msg_type == "voice":
                media_url = msg_root.findtext("MediaId", "")

            user_message = UserMessage(
                platform="wecom",
                platform_user_id=from_user,
                yuanbot_user_id=self._resolve_yuanbot_user_id(from_user),
                session_id=self._build_session_id(from_user),
                content_type=content_type,
                text=text,
                media_url=media_url,
                metadata={
                    "agent_id": self._agent_id,
                    "msg_type": msg_type,
                },
            )

            if self._callback:
                try:
                    response = await self._callback(user_message)
                    await self.send_message(
                        target_id=from_user,
                        content=response.content,
                    )
                except Exception as e:
                    logger.error("wecom_handle_error", error=str(e))

            return "success"

        except Exception as e:
            logger.error("wecom_callback_error", error=str(e))
            return "success"

    async def send_message(
        self,
        target_id: str,
        content: MessageContent,
    ) -> SendResult:
        """发送消息到企业微信"""
        if not self._session:
            return SendResult(success=False, error="Client not initialized")

        # 确保 token 有效
        await self._ensure_token()

        try:
            payload: dict[str, Any] = {
                "touser": target_id,
                "msgtype": "text",
                "agentid": int(self._agent_id),
            }

            if content.content_type == ContentType.TEXT and content.text:
                payload["msgtype"] = "text"
                payload["text"] = {"content": content.text}
            elif content.content_type == ContentType.IMAGE and content.media_url:
                payload["msgtype"] = "image"
                payload["image"] = {"media_id": content.media_url}
            elif content.content_type == ContentType.VOICE and content.media_url:
                payload["msgtype"] = "voice"
                payload["voice"] = {"media_id": content.media_url}
            elif content.content_type == ContentType.VIDEO and content.media_url:
                payload["msgtype"] = "video"
                payload["video"] = {"media_id": content.media_url}
            elif content.content_type == ContentType.FILE and content.media_url:
                payload["msgtype"] = "file"
                payload["file"] = {"media_id": content.media_url}
            else:
                # 降级为文本
                payload["msgtype"] = "text"
                payload["text"] = {"content": content.text or ""}

            response = await self._session.post(
                "/message/send",
                params={"access_token": self._access_token},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            errcode = data.get("errcode", 0)
            if errcode != 0:
                errmsg = data.get("errmsg", "Unknown error")
                logger.error("wecom_send_api_error", errcode=errcode, errmsg=errmsg)
                return SendResult(success=False, error=f"API error {errcode}: {errmsg}")

            return SendResult(
                success=True,
                message_id=str(data.get("msgid", "")),
            )
        except httpx.HTTPStatusError as e:
            logger.error(
                "wecom_send_http_error",
                status=e.response.status_code,
                body=e.response.text,
            )
            return SendResult(
                success=False,
                error=f"HTTP {e.response.status_code}: {e.response.text}",
            )
        except Exception as e:
            logger.error("wecom_send_error", error=str(e))
            return SendResult(success=False, error=str(e))

    def get_platform_user_id(self, raw_event: Any) -> str:
        """从企业微信事件提取用户 ID"""
        if isinstance(raw_event, dict):
            return raw_event.get("FromUserName", "")
        if isinstance(raw_event, str):
            # 可能是 XML 字符串
            try:
                root = ET.fromstring(raw_event)
                return root.findtext("FromUserName", "")
            except ET.ParseError:
                return ""
        return ""

    def verify_callback_signature(
        self,
        msg_signature: str,
        timestamp: str,
        nonce: str,
        echo_str: str,
    ) -> str | None:
        """验证回调 URL 验证请求

        企业微信配置回调 URL 时会发送验证请求。
        返回解密后的 echostr，或 None 表示验证失败。
        """
        if not self._verify_signature(msg_signature, timestamp, nonce, echo_str):
            return None
        return self._decrypt_message(echo_str)

    async def close(self) -> None:
        """关闭适配器"""
        if self._session:
            await self._session.aclose()
            self._session = None
        logger.info("wecom_adapter_closed")

    # ──────────────────────────────────────────
    # 内部方法 — Token 管理
    # ──────────────────────────────────────────

    async def _refresh_access_token(self) -> None:
        """刷新 access_token"""
        if not self._session:
            return

        response = await self._session.get(
            "/gettoken",
            params={
                "corpid": self._corp_id,
                "corpsecret": self._corp_secret,
            },
        )
        response.raise_for_status()
        data = response.json()

        errcode = data.get("errcode", 0)
        if errcode != 0:
            raise RuntimeError(f"Failed to get access_token: {data.get('errmsg', 'Unknown error')}")

        self._access_token = data.get("access_token", "")
        expires_in = data.get("expires_in", 7200)
        self._token_expires_at = time.time() + expires_in - 300  # 提前 5 分钟刷新
        logger.info("wecom_token_refreshed")

    async def _ensure_token(self) -> None:
        """确保 access_token 有效"""
        if time.time() >= self._token_expires_at:
            await self._refresh_access_token()

    async def _token_refresh_loop(self) -> None:
        """定期刷新 access_token"""
        while True:
            try:
                await asyncio.sleep(TOKEN_CACHE_TTL)
                await self._refresh_access_token()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("wecom_token_refresh_error", error=str(e))
                await asyncio.sleep(60)

    # ──────────────────────────────────────────
    # 内部方法 — 消息加解密
    # ──────────────────────────────────────────

    def _verify_signature(
        self,
        msg_signature: str,
        timestamp: str,
        nonce: str,
        encrypt: str,
    ) -> bool:
        """验证消息签名（SHA1）"""
        if not self._token:
            return False
        params = sorted([self._token, timestamp, nonce, encrypt])
        sha1 = hashlib.sha1("".join(params).encode("utf-8")).hexdigest()
        return sha1 == msg_signature

    def _decrypt_message(self, encrypted_text: str) -> str:
        """解密消息（AES-256-CBC）

        企业微信使用自定义的 AES 加密方案：
        - 密钥: encoding_aes_key (Base64 编码，32 字节)
        - IV: 密钥前 16 字节
        - 填充: PKCS#7
        - 明文结构: random(16B) + msg_len(4B, network order) + msg + corp_id
        """
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

            # 解码 AES key
            aes_key = b64decode(self._encoding_aes_key + "=")
            iv = aes_key[:16]

            # Base64 解码密文
            cipher_data = b64decode(encrypted_text)

            # AES-256-CBC 解密
            cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
            decryptor = cipher.decryptor()
            plain_padded = decryptor.update(cipher_data) + decryptor.finalize()

            # 去除 PKCS#7 填充
            pad_len = plain_padded[-1]
            plain = plain_padded[:-pad_len]

            # 解析明文: random(16) + msg_len(4) + msg + corp_id
            msg_len = int.from_bytes(plain[16:20], byteorder="big")
            message = plain[20 : 20 + msg_len].decode("utf-8")

            return message

        except ImportError:
            raise RuntimeError(
                "cryptography package is required for WeCom message encryption. "
                "Install it with: pip install cryptography",
            )

    def _encrypt_message(self, message: str) -> str:
        """加密消息（AES-256-CBC）"""
        try:
            import random
            import struct

            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

            aes_key = b64decode(self._encoding_aes_key + "=")
            iv = aes_key[:16]

            # 构造明文: random(16) + msg_len(4) + msg + corp_id
            random_bytes = bytes(random.randint(0, 255) for _ in range(16))
            msg_bytes = message.encode("utf-8")
            msg_len = struct.pack(">I", len(msg_bytes))
            corp_id_bytes = self._corp_id.encode("utf-8")

            plain = random_bytes + msg_len + msg_bytes + corp_id_bytes

            # PKCS#7 填充
            block_size = 32
            pad_len = block_size - (len(plain) % block_size)
            plain += bytes([pad_len] * pad_len)

            # AES-256-CBC 加密
            cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
            encryptor = cipher.encryptor()
            encrypted = encryptor.update(plain) + encryptor.finalize()

            return b64encode(encrypted).decode("utf-8")

        except ImportError:
            raise RuntimeError(
                "cryptography package is required for WeCom message encryption. "
                "Install it with: pip install cryptography",
            )
