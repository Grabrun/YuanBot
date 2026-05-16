"""Telegram 消息通道适配器

基于 Telegram Bot API，支持文本/图片/语音消息。
"""

from __future__ import annotations

import asyncio
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


class TelegramAdapter(BaseChannelAdapter):
    """Telegram Bot API 适配器"""

    def __init__(self, config: ChannelConfig | None = None):
        super().__init__(config)
        self._bot_token: str | None = None
        self._base_url: str = "https://api.telegram.org"
        self._client: httpx.AsyncClient | None = None
        self._offset: int = 0

    @property
    def platform_name(self) -> str:
        return "telegram"

    @property
    def supported_content_types(self) -> list[ContentType]:
        return [ContentType.TEXT, ContentType.IMAGE, ContentType.VOICE]

    async def initialize(self, config: ChannelConfig) -> None:
        """初始化 Telegram 适配器"""
        self._config = config
        self._bot_token = config.config.get("bot_token")
        if not self._bot_token:
            raise ValueError("Telegram bot_token is required")

        self._client = httpx.AsyncClient(
            base_url=f"{self._base_url}/bot{self._bot_token}",
            timeout=60.0,
        )

        # 验证 bot token
        me = await self._client.get("/getMe")
        me.raise_for_status()
        bot_info = me.json()
        logger.info(
            "telegram_initialized",
            bot_username=bot_info["result"]["username"],
        )

    async def listen(
        self,
        callback: Callable[[UserMessage], Awaitable[BotResponse]],
    ) -> None:
        """启动消息监听（长轮询模式）"""
        self._callback = callback
        logger.info("telegram_listening")

        while True:
            try:
                updates = await self._get_updates()
                for update in updates:
                    await self._handle_update(update)
            except Exception as e:
                logger.error("telegram_poll_error", error=str(e))
                await asyncio.sleep(5)

    async def send_message(
        self,
        target_id: str,
        content: MessageContent,
    ) -> SendResult:
        """发送消息到 Telegram"""
        if not self._client:
            return SendResult(success=False, error="Client not initialized")

        try:
            if content.content_type == ContentType.TEXT:
                response = await self._client.post(
                    "/sendMessage",
                    json={
                        "chat_id": target_id,
                        "text": content.text,
                        "parse_mode": "Markdown",
                    },
                )
            elif content.content_type == ContentType.IMAGE:
                response = await self._client.post(
                    "/sendPhoto",
                    json={
                        "chat_id": target_id,
                        "photo": content.media_url,
                        "caption": content.text,
                    },
                )
            else:
                return SendResult(
                    success=False,
                    error=f"Unsupported content type: {content.content_type}",
                )

            response.raise_for_status()
            data = response.json()
            return SendResult(
                success=True,
                message_id=str(data["result"]["message_id"]),
            )
        except Exception as e:
            return SendResult(success=False, error=str(e))

    def get_platform_user_id(self, raw_event: Any) -> str:
        """从 Telegram update 中提取用户 ID"""
        message = raw_event.get("message", {})
        user = message.get("from", {})
        return str(user.get("id", ""))

    # ──────────────────────────────────────────
    # 内部方法
    # ──────────────────────────────────────────

    async def _get_updates(self) -> list[dict[str, Any]]:
        """获取 Telegram 更新"""
        if not self._client:
            return []

        response = await self._client.get(
            "/getUpdates",
            params={"offset": self._offset, "timeout": 30},
        )
        response.raise_for_status()
        data = response.json()

        updates = data.get("result", [])
        if updates:
            self._offset = updates[-1]["update_id"] + 1
        return updates

    async def _handle_update(self, update: dict[str, Any]) -> None:
        """处理单个 Telegram 更新"""
        if "message" not in update:
            return

        message = update["message"]
        platform_user_id = self.get_platform_user_id(update)

        if not platform_user_id:
            return

        # 构建标准化消息
        text = message.get("text", "")
        content_type = ContentType.TEXT
        media_url = None

        if "photo" in message:
            content_type = ContentType.IMAGE
            media_url = message["photo"][-1]["file_id"]  # 最大尺寸
        elif "voice" in message:
            content_type = ContentType.VOICE
            media_url = message["voice"]["file_id"]

        user_message = UserMessage(
            platform="telegram",
            platform_user_id=platform_user_id,
            yuanbot_user_id=self._resolve_yuanbot_user_id(platform_user_id),
            session_id=self._build_session_id(platform_user_id),
            content_type=content_type,
            text=text if text else None,
            media_url=media_url,
            metadata={
                "chat_id": str(message["chat"]["id"]),
                "message_id": str(message["message_id"]),
            },
        )

        # 通过回调交给编排层处理
        if self._callback:
            try:
                response = await self._callback(user_message)
                # 自动回复
                chat_id = message["chat"]["id"]
                await self.send_message(
                    target_id=str(chat_id),
                    content=response.content,
                )
            except Exception as e:
                logger.error("telegram_handle_error", error=str(e))
