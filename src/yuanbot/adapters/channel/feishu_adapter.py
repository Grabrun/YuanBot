"""飞书 (Feishu/Lark) 通道适配器

基于飞书开放平台 API 实现。
支持 Webhook 回调接收消息，通过 REST API 发送消息。
支持文本 (text) 和富文本 (post) 消息类型。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
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

# ── 常量 ──────────────────────────────────────

FEISHU_API_BASE = "https://open.feishu.cn/open-apis"
TOKEN_URL = f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal/"
SEND_MSG_URL = f"{FEISHU_API_BASE}/im/v1/messages"
REPLY_MSG_URL_TPL = f"{FEISHU_API_BASE}/im/v1/messages/{{message_id}}/reply"

# 飞书消息类型
class FeishuMsgType:
    TEXT = "text"
    POST = "post"
    IMAGE = "image"
    INTERACTIVE = "interactive"

# 超时
TOKEN_TIMEOUT_S = 10
API_TIMEOUT_S = 15


class FeishuAdapter(BaseChannelAdapter):
    """飞书 (Feishu/Lark) 通道适配器

    实现 ChannelAdapter 接口，桥接飞书开放平台 API 与 YuanBot。
    使用 Webhook 模式接收消息事件，通过 REST API 发送消息。
    """

    def __init__(self) -> None:
        super().__init__()
        self._app_id: str = ""
        self._app_secret: str = ""
        self._verification_token: str = ""
        self._encrypt_key: str = ""
        self._tenant_access_token: str = ""
        self._token_expires_at: float = 0
        self._client: httpx.AsyncClient | None = None
        self._callback: Callable[[UserMessage], Awaitable[BotResponse]] | None = None
        self._running: bool = False
        self._receive_id_type: str = "open_id"

        # Webhook 服务器
        self._webhook_server: asyncio.AbstractServer | None = None
        self._webhook_host: str = "0.0.0.0"
        self._webhook_port: int = 9000

    # ── ChannelAdapter 接口实现 ────────────────

    @property
    def platform_name(self) -> str:
        return "feishu"

    @property
    def supported_content_types(self) -> list[ContentType]:
        return [ContentType.TEXT]

    async def initialize(self, config: ChannelConfig) -> None:
        """初始化飞书适配器

        Args:
            config: 通道配置，包含 app_id、app_secret 等字段。

        Raises:
            ValueError: 当缺少必要配置项时。
        """
        cfg = config.config
        self._app_id = cfg.get("app_id", "")
        self._app_secret = cfg.get("app_secret", "")
        self._verification_token = cfg.get("verification_token", "")
        self._encrypt_key = cfg.get("encrypt_key", "")
        self._receive_id_type = cfg.get("receive_id_type", "open_id")

        # Webhook 服务器配置
        webhook_cfg = cfg.get("webhook", {})
        self._webhook_host = webhook_cfg.get("host", "0.0.0.0")
        self._webhook_port = webhook_cfg.get("port", 9000)

        if not self._app_id or not self._app_secret:
            raise ValueError("Feishu app_id and app_secret are required")

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(API_TIMEOUT_S),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

        # 获取 tenant_access_token
        await self._refresh_token()

        logger.info(
            "feishu_adapter_initialized",
            app_id=self._app_id,
            receive_id_type=self._receive_id_type,
        )

    async def listen(
        self,
        callback: Callable[[UserMessage], Awaitable[BotResponse]],
    ) -> None:
        """启动消息监听（Webhook HTTP 回调模式）

        启动一个轻量 HTTP 服务器接收飞书事件回调。

        Args:
            callback: 消息回调函数，接收 UserMessage 返回 BotResponse。
        """
        if not self._client:
            raise RuntimeError("Feishu adapter not initialized. Call initialize() first.")

        self._callback = callback
        self._running = True

        self._webhook_server = await asyncio.start_server(
            self._handle_webhook_connection,
            self._webhook_host,
            self._webhook_port,
        )
        logger.info(
            "feishu_webhook_started",
            host=self._webhook_host,
            port=self._webhook_port,
        )

        # 保持服务器运行
        async with self._webhook_server:
            await self._webhook_server.serve_forever()

    async def send_message(
        self,
        target_id: str,
        content: MessageContent,
    ) -> SendResult:
        """发送消息到飞书

        Args:
            target_id: 接收者 ID（open_id / user_id / union_id / chat_id）。
            content: 消息内容。

        Returns:
            SendResult: 发送结果。
        """
        if not self._client:
            return SendResult(success=False, error="Adapter not initialized")

        await self._refresh_token()

        if content.content_type == ContentType.TEXT:
            return await self._send_text(target_id, content.text or "")
        else:
            return SendResult(
                success=False,
                error=f"Unsupported content type: {content.content_type}",
            )

    async def reply_message(
        self,
        message_id: str,
        content: MessageContent,
    ) -> SendResult:
        """回复指定消息

        Args:
            message_id: 要回复的消息 ID。
            content: 回复内容。

        Returns:
            SendResult: 发送结果。
        """
        if not self._client:
            return SendResult(success=False, error="Adapter not initialized")

        await self._refresh_token()

        if content.content_type != ContentType.TEXT:
            return SendResult(
                success=False,
                error=f"Unsupported content type: {content.content_type}",
            )

        url = REPLY_MSG_URL_TPL.format(message_id=message_id)
        body: dict[str, Any] = {
            "content": json.dumps({"text": content.text or ""}),
            "msg_type": FeishuMsgType.TEXT,
        }

        return await self._post_message(url, body)

    def get_platform_user_id(self, raw_event: Any) -> str:
        """从原始事件中提取飞书用户 ID

        Args:
            raw_event: 飞书事件原始数据。

        Returns:
            str: 用户的 open_id。
        """
        if isinstance(raw_event, dict):
            event = raw_event.get("event", {})
            sender = event.get("sender", {})
            sender_id = sender.get("sender_id", {})
            return sender_id.get("open_id", "")
        return str(raw_event)

    # ── Access Token 管理 ──────────────────────

    async def _refresh_token(self) -> None:
        """获取/刷新 tenant_access_token

        飞书 tenant_access_token 有效期 7200 秒，
        提前 60 秒刷新以避免过期。
        """
        if not self._client:
            return

        now = time.time()
        if self._tenant_access_token and now < self._token_expires_at - 60:
            return  # Token 仍然有效

        try:
            resp = await self._client.post(
                TOKEN_URL,
                json={
                    "app_id": self._app_id,
                    "app_secret": self._app_secret,
                },
                timeout=TOKEN_TIMEOUT_S,
            )
            resp.raise_for_status()
            data = resp.json()

            code = data.get("code", -1)
            if code != 0:
                logger.error("feishu_token_error", code=code, msg=data.get("msg", ""))
                return

            self._tenant_access_token = data.get("tenant_access_token", "")
            expires_in = data.get("expire", 7200)
            self._token_expires_at = now + expires_in

            logger.info("feishu_token_refreshed", expires_in=expires_in)

        except Exception as exc:
            logger.error("feishu_token_refresh_failed", error=str(exc))

    def _build_auth_headers(self) -> dict[str, str]:
        """构建认证请求头"""
        return {
            "Authorization": f"Bearer {self._tenant_access_token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    # ── 消息发送 ──────────────────────────────

    async def _send_text(
        self,
        receive_id: str,
        text: str,
    ) -> SendResult:
        """发送文本消息

        Args:
            receive_id: 接收者 ID。
            text: 文本内容。

        Returns:
            SendResult: 发送结果。
        """
        body: dict[str, Any] = {
            "receive_id": receive_id,
            "content": json.dumps({"text": text}),
            "msg_type": FeishuMsgType.TEXT,
        }

        url = f"{SEND_MSG_URL}?receive_id_type={self._receive_id_type}"
        return await self._post_message(url, body)

    async def _send_post(
        self,
        receive_id: str,
        title: str,
        content_blocks: list[list[dict[str, Any]]],
    ) -> SendResult:
        """发送富文本 (post) 消息

        Args:
            receive_id: 接收者 ID。
            title: 富文本标题。
            content_blocks: 富文本内容块，二维数组结构。

        Returns:
            SendResult: 发送结果。
        """
        post_content: dict[str, Any] = {
            "zh_cn": {
                "title": title,
                "content": content_blocks,
            }
        }
        body: dict[str, Any] = {
            "receive_id": receive_id,
            "content": json.dumps(post_content),
            "msg_type": FeishuMsgType.POST,
        }

        url = f"{SEND_MSG_URL}?receive_id_type={self._receive_id_type}"
        return await self._post_message(url, body)

    async def _post_message(self, url: str, body: dict[str, Any]) -> SendResult:
        """发送 HTTP 请求到飞书消息 API

        Args:
            url: 请求 URL。
            body: 请求体。

        Returns:
            SendResult: 发送结果。
        """
        if not self._client:
            return SendResult(success=False, error="HTTP client not available")

        try:
            resp = await self._client.post(
                url,
                json=body,
                headers=self._build_auth_headers(),
                timeout=API_TIMEOUT_S,
            )
            resp.raise_for_status()
            data = resp.json()

            code = data.get("code", -1)
            if code != 0:
                logger.error(
                    "feishu_send_message_error",
                    code=code,
                    msg=data.get("msg", ""),
                )
                return SendResult(
                    success=False,
                    error=f"Feishu API error: code={code}, msg={data.get('msg', '')}",
                )

            msg_id = data.get("data", {}).get("message_id", "")
            logger.info("feishu_message_sent", message_id=msg_id)
            return SendResult(success=True, message_id=msg_id)

        except httpx.HTTPStatusError as exc:
            logger.error(
                "feishu_send_http_error",
                status=exc.response.status_code,
                body=exc.response.text,
            )
            return SendResult(
                success=False,
                error=f"HTTP {exc.response.status_code}",
            )
        except Exception as exc:
            logger.error("feishu_send_error", error=str(exc))
            return SendResult(success=False, error=str(exc))

    # ── Webhook 回调处理 ──────────────────────

    async def _handle_webhook_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """处理 Webhook HTTP 连接

        解析 HTTP 请求，提取 JSON body 并分发到事件处理器。

        Args:
            reader: 读取流。
            writer: 写入流。
        """
        try:
            # 读取 HTTP 请求行和头
            request_line = await reader.readline()
            if not request_line:
                return

            parts = request_line.decode("utf-8").strip().split(" ")
            if len(parts) < 2:
                return

            # 读取所有 headers
            headers: dict[str, str] = {}
            content_length = 0
            while True:
                line = await reader.readline()
                line_str = line.decode("utf-8").strip()
                if not line_str:
                    break
                if ":" in line_str:
                    key, _, value = line_str.partition(":")
                    key = key.strip().lower()
                    value = value.strip()
                    headers[key] = value
                    if key == "content-length":
                        content_length = int(value)

            # 读取 body
            body_bytes = b""
            if content_length > 0:
                body_bytes = await reader.readexactly(content_length)

            # 解析 JSON
            body: dict[str, Any] = {}
            if body_bytes:
                try:
                    body = json.loads(body_bytes)
                except json.JSONDecodeError:
                    logger.warning("feishu_webhook_invalid_json")

            # 处理飞书 URL 验证（首次配置回调时飞书会发送验证请求）
            if body.get("type") == "url_verification":
                challenge = body.get("challenge", "")
                response_body = json.dumps({"challenge": challenge})
                writer.write(
                    f"HTTP/1.1 200 OK\r\n"
                    f"Content-Type: application/json\r\n"
                    f"Content-Length: {len(response_body)}\r\n"
                    f"\r\n"
                    f"{response_body}".encode()
                )
                await writer.drain()
                writer.close()
                return

            # 处理事件回调
            if self._running and self._callback:
                asyncio.create_task(self._handle_event(body))

            # 返回 200 OK
            writer.write(
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: application/json\r\n"
                b'Content-Length: 2\r\n'
                b"\r\n"
                b"{}"
            )
            await writer.drain()
            writer.close()

        except Exception as exc:
            logger.error("feishu_webhook_error", error=str(exc))
            with contextlib.suppress(Exception):
                writer.close()

    async def _handle_event(self, body: dict[str, Any]) -> None:
        """处理飞书事件回调

        飞书事件格式 v2.0:
        {
            "schema": "2.0",
            "header": { "event_type": "im.message.receive_v1", ... },
            "event": { "sender": {...}, "message": {...} }
        }

        Args:
            body: 事件回调请求体。
        """
        header = body.get("header", {})
        event_type = header.get("event_type", "")

        # 验证 token（可选安全校验）
        if self._verification_token:
            token = header.get("token", "")
            if token and token != self._verification_token:
                logger.warning("feishu_event_token_mismatch")
                return

        if event_type == "im.message.receive_v1":
            await self._handle_message_event(body)
        else:
            logger.debug("feishu_unhandled_event", event_type=event_type)

    async def _handle_message_event(self, body: dict[str, Any]) -> None:
        """处理 im.message.receive_v1 事件

        解析消息内容，构建 UserMessage 并通过回调传递给编排层。

        Args:
            body: 完整事件回调体。
        """
        if not self._callback:
            return

        event = body.get("event", {})
        sender = event.get("sender", {})
        message = event.get("message", {})

        sender_id = sender.get("sender_id", {})
        open_id = sender_id.get("open_id", "")
        sender_type = sender.get("sender_type", "")

        # 忽略机器人自身发送的消息
        if sender_type == "app":
            logger.debug("feishu_ignore_bot_message")
            return

        message_id = message.get("message_id", "")
        chat_id = message.get("chat_id", "")
        msg_type = message.get("message_type", "")
        create_time = message.get("create_time", "")

        if not open_id:
            logger.warning("feishu_no_open_id")
            return

        # 解析消息内容
        text = self._extract_message_text(message)

        if not text:
            logger.debug("feishu_empty_message", msg_type=msg_type)
            return

        yuanbot_uid = self._resolve_yuanbot_user_id(open_id)

        user_msg = UserMessage(
            platform="feishu",
            platform_user_id=open_id,
            yuanbot_user_id=yuanbot_uid,
            session_id=f"feishu:{chat_id or open_id}",
            content_type=ContentType.TEXT,
            text=text,
            metadata={
                "message_id": message_id,
                "chat_id": chat_id,
                "msg_type": msg_type,
                "create_time": create_time,
            },
        )

        try:
            response = await self._callback(user_msg)
            await self._deliver_response(message_id, chat_id, response)
        except Exception as exc:
            logger.error("feishu_callback_error", error=str(exc))

    def _extract_message_text(self, message: dict[str, Any]) -> str:
        """从飞书消息中提取文本内容

        支持 text 和 post 两种消息类型。

        Args:
            message: 飞书消息体。

        Returns:
            str: 提取的纯文本内容。
        """
        msg_type = message.get("message_type", "")
        content_str = message.get("content", "")

        if not content_str:
            return ""

        try:
            content = json.loads(content_str)
        except (json.JSONDecodeError, TypeError):
            return ""

        if msg_type == FeishuMsgType.TEXT:
            return content.get("text", "").strip()

        if msg_type == FeishuMsgType.POST:
            return self._extract_post_text(content)

        return ""

    @staticmethod
    def _extract_post_text(post_content: dict[str, Any]) -> str:
        """从富文本 (post) 消息中提取纯文本

        飞书 post 结构:
        {
            "zh_cn": {
                "title": "...",
                "content": [[{"tag": "text", "text": "..."}, ...], ...]
            }
        }

        Args:
            post_content: 富文本消息内容。

        Returns:
            str: 提取的纯文本。
        """
        parts: list[str] = []

        # 支持多语言，取第一个可用的
        for lang_content in post_content.values():
            title = lang_content.get("title", "")
            if title:
                parts.append(title)

            blocks = lang_content.get("content", [])
            for block in blocks:
                for element in block:
                    tag = element.get("tag", "")
                    if tag == "text":
                        parts.append(element.get("text", ""))
                    elif tag == "a":
                        parts.append(element.get("text", element.get("href", "")))
                    elif tag == "at":
                        parts.append(element.get("user_name", ""))
                    elif tag == "img":
                        parts.append("[image]")
                    elif tag == "media":
                        parts.append("[media]")
                    elif tag == "emotion":
                        parts.append(element.get("emoji_type", ""))
            break  # 只处理第一种语言

        return "".join(parts).strip()

    async def _deliver_response(
        self,
        message_id: str,
        chat_id: str,
        response: BotResponse,
    ) -> None:
        """投递 AI 回复

        优先使用回复消息接口，若无 message_id 则直接发送。

        Args:
            message_id: 被回复的消息 ID。
            chat_id: 会话 ID。
            response: 机器人响应。
        """
        if response.content.content_type == ContentType.TEXT:
            text = response.content.text or ""
            if not text:
                return

            # 分段发送（飞书单条消息有长度限制）
            chunks = self._split_text(text, max_len=4000)
            for i, chunk in enumerate(chunks):
                if i == 0 and message_id:
                    # 第一条使用回复模式
                    result = await self.reply_message(
                        message_id,
                        MessageContent(content_type=ContentType.TEXT, text=chunk),
                    )
                elif chat_id:
                    result = await self._send_text(chat_id, chunk)
                else:
                    logger.warning("feishu_no_target_for_reply")
                    break

                if not result.success:
                    logger.error("feishu_deliver_failed", error=result.error)
                    break
        else:
            logger.warning(
                "feishu_unsupported_response_type",
                content_type=response.content.content_type,
            )

    @staticmethod
    def _split_text(text: str, max_len: int = 4000) -> list[str]:
        """分段长文本

        Args:
            text: 原始文本。
            max_len: 每段最大长度。

        Returns:
            list[str]: 分段后的文本列表。
        """
        if len(text) <= max_len:
            return [text]
        chunks: list[str] = []
        while text:
            chunks.append(text[:max_len])
            text = text[max_len:]
        return chunks

    # ── 清理 ──────────────────────────────────

    async def shutdown(self) -> None:
        """关闭适配器

        停止 Webhook 服务器并释放 HTTP 客户端资源。
        """
        self._running = False

        if self._webhook_server:
            self._webhook_server.close()
            await self._webhook_server.wait_closed()
            self._webhook_server = None

        if self._client:
            await self._client.aclose()
            self._client = None

        logger.info("feishu_adapter_shutdown")
