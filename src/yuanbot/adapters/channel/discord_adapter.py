"""Discord 消息通道适配器

基于 Discord Bot API，通过 HTTP 和 WebSocket Gateway 与 Discord 通信。
支持文本、图片、文件等消息类型。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import random
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

# Discord API 基础 URL
DISCORD_API_BASE = "https://discord.com/api/v10"
DISCORD_GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"

# 心跳间隔（秒）— Discord 要求约 41.25s
HEARTBEAT_INTERVAL = 41.25

# Gateway Opcodes
OP_DISPATCH = 0
OP_HEARTBEAT = 1
OP_IDENTIFY = 2
OP_PRESENCE_UPDATE = 3
OP_RESUME = 6
OP_RECONNECT = 7
OP_REQUEST_GUILD_MEMBERS = 8
OP_INVALID_SESSION = 9
OP_HELLO = 10
OP_HEARTBEAT_ACK = 11

# 重连参数
MAX_RECONNECT_DELAY = 60.0
INITIAL_RECONNECT_DELAY = 1.0


class DiscordAdapter(BaseChannelAdapter):
    """Discord 消息通道适配器

    使用 Discord Bot API 通过 HTTP 和 WebSocket 与 Discord 通信。
    支持文本、图片、文件等消息类型。
    """

    def __init__(self, config: ChannelConfig | None = None):
        super().__init__(config)
        self._bot_token: str = ""
        self._public_key: str = ""
        self._intents: int = 0
        self._session: httpx.AsyncClient | None = None
        self._ws_connection: Any = None
        self._heartbeat_task: asyncio.Task | None = None
        self._listen_task: asyncio.Task | None = None
        self._last_sequence: int | None = None
        self._heartbeat_acknowledged: bool = True
        self._session_id: str | None = None
        self._resume_url: str | None = None
        self._gateway_url: str = DISCORD_GATEWAY_URL

    @property
    def platform_name(self) -> str:
        return "discord"

    @property
    def supported_content_types(self) -> list[ContentType]:
        return [ContentType.TEXT, ContentType.IMAGE, ContentType.FILE]

    async def initialize(self, config: ChannelConfig) -> None:
        """初始化 Discord 适配器"""
        self._config = config
        self._bot_token = config.config.get("bot_token", "")
        if not self._bot_token:
            raise ValueError("Discord bot_token is required")

        self._public_key = config.config.get("public_key", "")
        self._intents = self._resolve_intents(
            config.config.get("intents", []),
        )

        self._session = httpx.AsyncClient(
            base_url=DISCORD_API_BASE,
            headers={
                "Authorization": f"Bot {self._bot_token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

        # 验证 bot token
        response = await self._session.get("/users/@me")
        response.raise_for_status()
        bot_info = response.json()
        logger.info(
            "discord_initialized",
            bot_username=bot_info.get("username", ""),
            bot_id=bot_info.get("id", ""),
        )

    async def listen(
        self,
        callback: Callable[[UserMessage], Awaitable[BotResponse]],
    ) -> None:
        """启动消息监听（WebSocket Gateway 模式）"""
        self._callback = callback
        logger.info("discord_listening")

        reconnect_delay = INITIAL_RECONNECT_DELAY

        while True:
            try:
                await self._connect_gateway()
                reconnect_delay = INITIAL_RECONNECT_DELAY
            except Exception as e:
                logger.error(
                    "discord_gateway_error",
                    error=str(e),
                    reconnect_in=reconnect_delay,
                )
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(
                    reconnect_delay * 2 + random.uniform(0, 1),
                    MAX_RECONNECT_DELAY,
                )

    async def send_message(
        self,
        target_id: str,
        content: MessageContent,
    ) -> SendResult:
        """发送消息到 Discord"""
        if not self._session:
            return SendResult(success=False, error="Client not initialized")

        try:
            payload: dict[str, Any] = {}

            if content.content_type == ContentType.TEXT and content.text:
                payload["content"] = content.text
            elif content.content_type == ContentType.IMAGE and content.media_url:
                payload["content"] = content.text or ""
                payload["embeds"] = [{"image": {"url": content.media_url}}]
            elif content.content_type == ContentType.FILE and content.media_url:
                payload["content"] = content.text or ""
                # 文件上传需要 multipart，这里简化处理
                payload["content"] += f"\n{content.media_url}"
            else:
                payload["content"] = content.text or ""

            response = await self._session.post(
                f"/channels/{target_id}/messages",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            return SendResult(
                success=True,
                message_id=str(data.get("id", "")),
            )
        except httpx.HTTPStatusError as e:
            logger.error(
                "discord_send_http_error",
                status=e.response.status_code,
                body=e.response.text,
            )
            return SendResult(
                success=False,
                error=f"HTTP {e.response.status_code}: {e.response.text}",
            )
        except Exception as e:
            logger.error("discord_send_error", error=str(e))
            return SendResult(success=False, error=str(e))

    def get_platform_user_id(self, raw_event: Any) -> str:
        """从 Discord 事件提取用户 ID"""
        if not isinstance(raw_event, dict):
            return ""
        author = raw_event.get("author")
        if not isinstance(author, dict):
            return ""
        user_id = author.get("id")
        return str(user_id) if user_id is not None else ""

    async def close(self) -> None:
        """关闭适配器"""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task

        if self._ws_connection:
            with contextlib.suppress(Exception):
                await self._ws_connection.close()

        if self._session:
            await self._session.aclose()
            self._session = None

        logger.info("discord_adapter_closed")

    # ──────────────────────────────────────────
    # 内部方法 — Gateway WebSocket
    # ──────────────────────────────────────────

    async def _connect_gateway(self) -> None:
        """连接到 Discord Gateway"""
        try:
            import websockets

            url = self._resume_url or self._gateway_url
            logger.info("discord_connecting_gateway", url=url)

            async with websockets.connect(url) as ws:
                self._ws_connection = ws

                # 接收 Hello
                hello_raw = await asyncio.wait_for(ws.recv(), timeout=30.0)
                hello = json.loads(hello_raw)

                if hello.get("op") != OP_HELLO:
                    raise RuntimeError(f"Expected Hello, got: {hello}")

                heartbeat_interval = hello["d"]["heartbeat_interval"] / 1000.0

                # 启动心跳
                self._heartbeat_acknowledged = True
                self._heartbeat_task = asyncio.create_task(
                    self._heartbeat_loop(ws, heartbeat_interval),
                )

                # Identify 或 Resume
                if self._session_id and self._resume_url:
                    await self._send_resume(ws)
                else:
                    await self._send_identify(ws)

                # 事件循环
                await self._event_loop(ws)

        except ImportError as err:
            raise RuntimeError(
                "websockets package is required for Discord adapter. "
                "Install it with: pip install websockets",
            ) from err

    async def _send_identify(self, ws: Any) -> None:
        """发送 Identify 负载"""
        identify = {
            "op": OP_IDENTIFY,
            "d": {
                "token": self._bot_token,
                "intents": self._intents,
                "properties": {
                    "os": "linux",
                    "library": "yuanbot",
                },
            },
        }
        await ws.send(json.dumps(identify))
        logger.info("discord_identify_sent")

    async def _send_resume(self, ws: Any) -> None:
        """发送 Resume 负载"""
        resume = {
            "op": OP_RESUME,
            "d": {
                "token": self._bot_token,
                "session_id": self._session_id,
                "seq": self._last_sequence,
            },
        }
        await ws.send(json.dumps(resume))
        logger.info("discord_resume_sent", session_id=self._session_id)

    async def _event_loop(self, ws: Any) -> None:
        """主事件循环"""
        async for raw_message in ws:
            try:
                message = json.loads(raw_message)
                await self._handle_gateway_message(ws, message)
            except json.JSONDecodeError:
                logger.warning("discord_invalid_json", raw=raw_message[:200])
            except Exception as e:
                logger.error("discord_event_error", error=str(e))

    async def _handle_gateway_message(
        self,
        ws: Any,
        message: dict[str, Any],
    ) -> None:
        """处理 Gateway 消息"""
        op = message.get("op")
        data = message.get("d")
        event_name = message.get("t")
        seq = message.get("s")

        if seq is not None:
            self._last_sequence = seq

        if op == OP_DISPATCH:
            await self._handle_dispatch(event_name, data)
        elif op == OP_RECONNECT:
            logger.info("discord_reconnect_requested")
            await ws.close()
        elif op == OP_INVALID_SESSION:
            logger.warning("discord_invalid_session", resumable=data)
            if not data:
                self._session_id = None
                self._resume_url = None
            await ws.close()
        elif op == OP_HEARTBEAT:
            await self._send_heartbeat(ws)
        elif op == OP_HEARTBEAT_ACK:
            self._heartbeat_acknowledged = True

    async def _handle_dispatch(
        self,
        event_name: str | None,
        data: Any,
    ) -> None:
        """处理 Dispatch 事件"""
        if event_name == "READY":
            self._session_id = data.get("session_id")
            self._resume_url = data.get("resume_gateway_url")
            if self._resume_url:
                self._resume_url = self._resume_url.rstrip("/") + "/?v=10&encoding=json"
            logger.info(
                "discord_ready",
                session_id=self._session_id,
                user=data.get("user", {}).get("username"),
            )
        elif event_name == "MESSAGE_CREATE":
            await self._handle_message_create(data)
        elif event_name == "RESUMED":
            logger.info("discord_resumed")

    async def _handle_message_create(self, message: dict[str, Any]) -> None:
        """处理 MESSAGE_CREATE 事件"""
        # 忽略 bot 自身的消息
        author = message.get("author", {})
        if author.get("bot", False):
            return

        platform_user_id = self.get_platform_user_id(message)
        if not platform_user_id:
            return

        # 解析消息内容
        text = message.get("content", "")
        content_type = ContentType.TEXT
        media_url = None

        # 检查附件
        attachments = message.get("attachments", [])
        if attachments:
            attachment = attachments[0]
            content_type_str = attachment.get("content_type", "")
            if content_type_str.startswith("image/"):
                content_type = ContentType.IMAGE
                media_url = attachment.get("url")
            else:
                content_type = ContentType.FILE
                media_url = attachment.get("url")

        user_message = UserMessage(
            platform="discord",
            platform_user_id=platform_user_id,
            yuanbot_user_id=self._resolve_yuanbot_user_id(platform_user_id),
            session_id=self._build_session_id(platform_user_id),
            content_type=content_type,
            text=text if text else None,
            media_url=media_url,
            metadata={
                "channel_id": str(message.get("channel_id", "")),
                "message_id": str(message.get("id", "")),
                "guild_id": str(message.get("guild_id", "")),
            },
        )

        if self._callback:
            try:
                response = await self._callback(user_message)
                channel_id = message.get("channel_id", "")
                await self.send_message(
                    target_id=str(channel_id),
                    content=response.content,
                )
            except Exception as e:
                logger.error("discord_handle_error", error=str(e))

    async def _heartbeat_loop(self, ws: Any, interval: float) -> None:
        """心跳循环"""
        try:
            while True:
                await asyncio.sleep(interval)

                if not self._heartbeat_acknowledged:
                    logger.warning("discord_heartbeat_not_acked")
                    # 连接可能已断开，event_loop 会处理
                    break

                self._heartbeat_acknowledged = False
                await self._send_heartbeat(ws)
        except asyncio.CancelledError:
            pass

    async def _send_heartbeat(self, ws: Any) -> None:
        """发送心跳"""
        heartbeat = {
            "op": OP_HEARTBEAT,
            "d": self._last_sequence,
        }
        try:
            await ws.send(json.dumps(heartbeat))
        except Exception as e:
            logger.error("discord_heartbeat_send_error", error=str(e))

    @staticmethod
    def _resolve_intents(intent_names: list[str]) -> int:
        """将 intent 名称列表解析为位标志整数"""
        intent_map = {
            "GUILDS": 1 << 0,
            "GUILD_MEMBERS": 1 << 1,
            "GUILD_MODERATION": 1 << 2,
            "GUILD_EMOJIS_AND_STICKERS": 1 << 3,
            "GUILD_INTEGRATIONS": 1 << 4,
            "GUILD_WEBHOOKS": 1 << 5,
            "GUILD_INVITES": 1 << 6,
            "GUILD_VOICE_STATES": 1 << 7,
            "GUILD_PRESENCES": 1 << 8,
            "GUILD_MESSAGES": 1 << 9,
            "GUILD_MESSAGE_REACTIONS": 1 << 10,
            "GUILD_MESSAGE_TYPING": 1 << 11,
            "DIRECT_MESSAGES": 1 << 12,
            "DIRECT_MESSAGE_REACTIONS": 1 << 13,
            "DIRECT_MESSAGE_TYPING": 1 << 14,
            "MESSAGE_CONTENT": 1 << 15,
            "GUILD_SCHEDULED_EVENTS": 1 << 16,
            "AUTO_MODERATION_CONFIGURATION": 1 << 20,
            "AUTO_MODERATION_EXECUTION": 1 << 21,
        }
        intents = 0
        for name in intent_names:
            name_upper = name.upper().replace(" ", "_")
            if name_upper in intent_map:
                intents |= intent_map[name_upper]
            else:
                logger.warning("discord_unknown_intent", intent=name)
        return intents
