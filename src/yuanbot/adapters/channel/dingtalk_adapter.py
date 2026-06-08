"""钉钉 (DingTalk) 通道适配器

基于钉钉开放平台 API 实现。
支持 Webhook 回调模式接收消息，通过 REST API 发送消息。
支持 text 和 markdown 消息类型。
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

TOKEN_URL = "https://oapi.dingtalk.com/gettoken"
SEND_BY_SESSION_URL = "https://oapi.dingtalk.com/robot/sendBySession"
SEND_BY_GROUP_URL = "https://oapi.dingtalk.com/robot/sendByGroup"

# 超时
OAUTH_TIMEOUT_S = 10
API_TIMEOUT_S = 15

# Token 提前刷新余量（秒）
TOKEN_REFRESH_MARGIN_S = 120


class DingTalkAdapter(BaseChannelAdapter):
    """钉钉通道适配器

    实现 ChannelAdapter 接口，桥接钉钉开放平台 API 与 YuanBot。
    使用 Webhook 回调模式接收消息，支持单聊和群聊消息收发。
    """

    def __init__(self) -> None:
        super().__init__()
        self._app_key: str = ""
        self._app_secret: str = ""
        self._webhook_token: str = ""
        self._access_token: str = ""
        self._token_expires_at: float = 0
        self._client: httpx.AsyncClient | None = None
        self._callback: Callable[[UserMessage], Awaitable[BotResponse]] | None = None
        self._running = False
        self._webhook_server: asyncio.AbstractServer | None = None
        self._webhook_host: str = "0.0.0.0"
        self._webhook_port: int = 8080

    # ── ChannelAdapter 接口实现 ────────────────

    @property
    def platform_name(self) -> str:
        """返回平台名称"""
        return "dingtalk"

    @property
    def supported_content_types(self) -> list[ContentType]:
        """返回支持的消息内容类型"""
        return [ContentType.TEXT]

    async def initialize(self, config: ChannelConfig) -> None:
        """初始化适配器

        从配置中读取 app_key、app_secret 和 webhook 相关参数，
        创建 HTTP 客户端并获取初始 access_token。

        Args:
            config: 通道配置，包含钉钉应用凭证和 webhook 设置。
        """
        cfg = config.config
        self._app_key = cfg.get("app_key", "")
        self._app_secret = cfg.get("app_secret", "")
        self._webhook_token = cfg.get("webhook_token", "")
        self._webhook_host = cfg.get("webhook_host", "0.0.0.0")
        self._webhook_port = cfg.get("webhook_port", 8080)

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(API_TIMEOUT_S),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

        # 获取 Access Token
        await self._refresh_token()

        logger.info(
            "dingtalk_adapter_initialized",
            app_key=self._app_key,
            webhook_port=self._webhook_port,
        )

    async def listen(
        self,
        callback: Callable[[UserMessage], Awaitable[BotResponse]],
    ) -> None:
        """启动消息监听（Webhook HTTP 服务器）

        启动一个 HTTP 服务器监听钉钉回调请求。
        钉钉会将用户消息以 POST 请求发送到该服务器。

        Args:
            callback: 收到用户消息后的回调函数。
        """
        if not self._client:
            raise RuntimeError("DingTalk adapter not initialized. Call initialize() first.")

        self._callback = callback
        self._running = True

        # 启动 Webhook HTTP 服务器
        self._webhook_server = await asyncio.start_server(
            self._handle_webhook_connection,
            self._webhook_host,
            self._webhook_port,
        )
        logger.info(
            "dingtalk_listen_started",
            host=self._webhook_host,
            port=self._webhook_port,
        )

    async def send_message(
        self,
        target_id: str,
        content: MessageContent,
    ) -> SendResult:
        """发送消息到指定目标

        target_id 格式:
          - 单聊: "session:sender_id"
          - 群聊: "group:chatbot_corpkey"
          - Webhook: "webhook:webhook_url"

        Args:
            target_id: 目标标识，格式为 "type:id"。
            content: 消息内容。

        Returns:
            SendResult: 发送结果。
        """
        if not self._client:
            return SendResult(success=False, error="Adapter not initialized")

        parts = target_id.split(":", 1)
        if len(parts) != 2:
            return SendResult(success=False, error=f"Invalid target_id format: {target_id}")

        target_type, target_value = parts

        if content.content_type == ContentType.TEXT:
            if content.metadata.get("markdown"):
                return await self._send_markdown(
                    target_type, target_value,
                    content.metadata.get("title", ""),
                    content.text or "",
                )
            return await self._send_text(target_type, target_value, content.text or "")
        else:
            return SendResult(
                success=False,
                error=f"Unsupported content type: {content.content_type}",
            )

    def get_platform_user_id(self, raw_event: Any) -> str:
        """从原始事件中提取用户 ID

        Args:
            raw_event: 钉钉回调的原始事件数据。

        Returns:
            str: 平台用户 ID。
        """
        if isinstance(raw_event, dict):
            return raw_event.get("senderStaffId", raw_event.get("senderId", ""))
        return str(raw_event)

    async def shutdown(self) -> None:
        """关闭适配器

        停止 Webhook 服务器并关闭 HTTP 客户端。
        """
        self._running = False

        if self._webhook_server:
            self._webhook_server.close()
            await self._webhook_server.wait_closed()
            self._webhook_server = None

        if self._client:
            await self._client.aclose()
            self._client = None

        logger.info("dingtalk_adapter_shutdown")

    # ── Access Token 管理 ──────────────────────

    async def _refresh_token(self) -> None:
        """获取/刷新 Access Token

        钉钉 access_token 有效期 7200 秒，提前 TOKEN_REFRESH_MARGIN_S 秒刷新。
        """
        if not self._client:
            return

        now = time.time()
        if self._access_token and now < self._token_expires_at - TOKEN_REFRESH_MARGIN_S:
            return  # Token 仍然有效

        try:
            resp = await self._client.get(
                TOKEN_URL,
                params={
                    "appkey": self._app_key,
                    "appsecret": self._app_secret,
                },
                timeout=OAUTH_TIMEOUT_S,
            )
            resp.raise_for_status()
            data = resp.json()

            errcode = data.get("errcode", 0)
            if errcode != 0:
                logger.error(
                    "dingtalk_token_error",
                    errcode=errcode,
                    errmsg=data.get("errmsg", ""),
                )
                return

            self._access_token = data.get("access_token", "")
            expires_in = data.get("expires_in", 7200)
            self._token_expires_at = now + expires_in

            logger.info("dingtalk_token_refreshed", expires_in=expires_in)

        except Exception as exc:
            logger.error("dingtalk_token_refresh_failed", error=str(exc))

    # ── Webhook HTTP 服务器 ────────────────────

    async def _handle_webhook_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """处理 Webhook HTTP 连接

        解析 HTTP 请求，提取钉钉回调的 JSON body，
        构造 UserMessage 并调用回调函数。

        Args:
            reader: 读取流。
            writer: 写入流。
        """
        try:
            # 读取 HTTP 请求
            request_line = await reader.readline()
            if not request_line:
                writer.close()
                return

            # 读取 headers
            headers: dict[str, str] = {}
            content_length = 0
            while True:
                line = await reader.readline()
                if line == b"\r\n" or not line:
                    break
                line_str = line.decode("utf-8", errors="replace").strip()
                if ":" in line_str:
                    key, value = line_str.split(":", 1)
                    headers[key.strip().lower()] = value.strip()
                    if key.strip().lower() == "content-length":
                        content_length = int(value.strip())

            # 读取 body
            body = b""
            if content_length > 0:
                body = await reader.readexactly(content_length)

            # 只处理 POST 请求
            request_parts = request_line.decode("utf-8", errors="replace").strip().split()
            if len(request_parts) < 2 or request_parts[0] != "POST":
                self._send_http_response(writer, 405, "Method Not Allowed")
                return

            # 解析 JSON body
            try:
                event_data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self._send_http_response(writer, 400, "Invalid JSON")
                return

            # 处理钉钉回调事件
            await self._process_webhook_event(event_data)

            # 返回成功响应（钉钉要求 200 OK）
            self._send_http_response(writer, 200, '{"errcode":0,"errmsg":"ok"}')

        except Exception as exc:
            logger.error("dingtalk_webhook_error", error=str(exc))
            with contextlib.suppress(Exception):
                self._send_http_response(writer, 500, "Internal Server Error")
        finally:
            with contextlib.suppress(Exception):
                writer.close()

    def _send_http_response(
        self,
        writer: asyncio.StreamWriter,
        status_code: int,
        body: str,
    ) -> None:
        """发送 HTTP 响应

        Args:
            writer: 写入流。
            status_code: HTTP 状态码。
            body: 响应体。
        """
        status_texts = {
            200: "OK",
            400: "Bad Request",
            405: "Method Not Allowed",
            500: "Internal Server Error",
        }
        status_text = status_texts.get(status_code, "Unknown")
        response = (
            f"HTTP/1.1 {status_code} {status_text}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(body.encode())}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
            f"{body}"
        )
        writer.write(response.encode())

    async def _process_webhook_event(self, event_data: dict[str, Any]) -> None:
        """处理钉钉 Webhook 事件

        解析事件类型，构造标准化 UserMessage 并调用回调。

        Args:
            event_data: 钉钉回调的事件数据。
        """
        if not self._callback:
            return

        # 提取消息内容
        text_content = event_data.get("text", {})
        if isinstance(text_content, dict):
            text = text_content.get("content", "").strip()
        else:
            text = str(text_content).strip()

        if not text:
            logger.debug("dingtalk_empty_message")
            return

        # 提取用户信息
        sender_id = event_data.get("senderStaffId", event_data.get("senderId", ""))
        sender_nick = event_data.get("senderNick", "")
        conversation_id = event_data.get("conversationId", "")
        conversation_type = event_data.get("conversationType", "")
        msg_id = event_data.get("msgId", "")

        if not sender_id:
            logger.debug("dingtalk_no_sender_id")
            return

        # 判断消息场景
        scene = "single" if conversation_type == "1" else "group"

        yuanbot_uid = self._resolve_yuanbot_user_id(sender_id)
        session_id = f"dingtalk:{scene}:{conversation_id or sender_id}"

        user_msg = UserMessage(
            platform="dingtalk",
            platform_user_id=sender_id,
            yuanbot_user_id=yuanbot_uid,
            session_id=session_id,
            content_type=ContentType.TEXT,
            text=text,
            metadata={
                "scene": scene,
                "sender_nick": sender_nick,
                "conversation_id": conversation_id,
                "conversation_type": conversation_type,
                "msg_id": msg_id,
            },
        )

        logger.info(
            "dingtalk_message_received",
            scene=scene,
            sender_id=sender_id,
            text_len=len(text),
        )

        response = await self._callback(user_msg)
        await self._deliver_response(scene, conversation_id, sender_id, response)

    # ── 消息发送 ──────────────────────────────

    async def _send_text(
        self,
        target_type: str,
        target_value: str,
        text: str,
    ) -> SendResult:
        """发送文本消息

        Args:
            target_type: 目标类型 ("session" | "group" | "webhook")。
            target_value: 目标值。
            text: 文本内容。

        Returns:
            SendResult: 发送结果。
        """
        await self._refresh_token()

        if target_type == "webhook":
            return await self._send_webhook(target_value, "text", text=text)

        url = self._get_send_url(target_type)
        if not url:
            return SendResult(success=False, error=f"Unsupported target type: {target_type}")

        body: dict[str, Any] = {
            "msgtype": "text",
            "text": {"content": text},
        }

        if target_type == "session":
            body["senderStaffId"] = target_value
        elif target_type == "group":
            body["chatbotCorpId"] = target_value

        return await self._post_send_message(url, body)

    async def _send_markdown(
        self,
        target_type: str,
        target_value: str,
        title: str,
        text: str,
    ) -> SendResult:
        """发送 Markdown 消息

        Args:
            target_type: 目标类型 ("session" | "group" | "webhook")。
            target_value: 目标值。
            title: Markdown 消息标题。
            text: Markdown 内容。

        Returns:
            SendResult: 发送结果。
        """
        await self._refresh_token()

        if target_type == "webhook":
            return await self._send_webhook(
                target_value, "markdown", title=title, text=text,
            )

        url = self._get_send_url(target_type)
        if not url:
            return SendResult(success=False, error=f"Unsupported target type: {target_type}")

        body: dict[str, Any] = {
            "msgtype": "markdown",
            "markdown": {"title": title, "text": text},
        }

        if target_type == "session":
            body["senderStaffId"] = target_value
        elif target_type == "group":
            body["chatbotCorpId"] = target_value

        return await self._post_send_message(url, body)

    def _get_send_url(self, target_type: str) -> str | None:
        """根据目标类型获取发送 URL

        Args:
            target_type: 目标类型。

        Returns:
            str | None: 发送 URL，不支持的类型返回 None。
        """
        if target_type == "session":
            return f"{SEND_BY_SESSION_URL}?access_token={self._access_token}"
        elif target_type == "group":
            return f"{SEND_BY_GROUP_URL}?access_token={self._access_token}"
        return None

    async def _post_send_message(
        self,
        url: str,
        body: dict[str, Any],
    ) -> SendResult:
        """发送 HTTP POST 请求

        Args:
            url: 请求 URL。
            body: 请求体。

        Returns:
            SendResult: 发送结果。
        """
        if not self._client:
            return SendResult(success=False, error="Client not available")

        try:
            resp = await self._client.post(
                url,
                json=body,
                timeout=API_TIMEOUT_S,
            )
            resp.raise_for_status()
            data = resp.json()

            errcode = data.get("errcode", 0)
            if errcode != 0:
                logger.error(
                    "dingtalk_send_error",
                    errcode=errcode,
                    errmsg=data.get("errmsg", ""),
                )
                return SendResult(
                    success=False,
                    error=f"DingTalk error {errcode}: {data.get('errmsg', '')}",
                )

            return SendResult(success=True)
        except httpx.HTTPStatusError as exc:
            logger.error(
                "dingtalk_send_http_error",
                status=exc.response.status_code,
                body=exc.response.text,
            )
            return SendResult(success=False, error=f"HTTP {exc.response.status_code}")
        except Exception as exc:
            logger.error("dingtalk_send_error", error=str(exc))
            return SendResult(success=False, error=str(exc))

    async def _send_webhook(
        self,
        webhook_url: str,
        msg_type: str,
        **kwargs: Any,
    ) -> SendResult:
        """通过 Webhook 机器人发送消息

        Args:
            webhook_url: Webhook URL。
            msg_type: 消息类型 ("text" | "markdown")。
            **kwargs: 消息参数。

        Returns:
            SendResult: 发送结果。
        """
        if not self._client:
            return SendResult(success=False, error="Client not available")

        body: dict[str, Any] = {"msgtype": msg_type}

        if msg_type == "text":
            body["text"] = {"content": kwargs.get("text", "")}
        elif msg_type == "markdown":
            body["markdown"] = {
                "title": kwargs.get("title", ""),
                "text": kwargs.get("text", ""),
            }

        try:
            resp = await self._client.post(
                webhook_url,
                json=body,
                timeout=API_TIMEOUT_S,
            )
            resp.raise_for_status()
            data = resp.json()

            errcode = data.get("errcode", 0)
            if errcode != 0:
                return SendResult(
                    success=False,
                    error=f"Webhook error {errcode}: {data.get('errmsg', '')}",
                )

            return SendResult(success=True)
        except Exception as exc:
            logger.error("dingtalk_webhook_send_error", error=str(exc))
            return SendResult(success=False, error=str(exc))

    # ── 回复投递 ──────────────────────────────

    async def _deliver_response(
        self,
        scene: str,
        conversation_id: str,
        sender_id: str,
        response: BotResponse,
    ) -> None:
        """投递 AI 回复

        根据消息场景选择发送方式，长文本自动分段。

        Args:
            scene: 消息场景 ("single" | "group")。
            conversation_id: 会话 ID。
            sender_id: 发送者 ID。
            response: AI 回复内容。
        """
        text = response.content.text or ""
        if not text:
            return

        # 分段发送
        chunks = self._split_text(text, max_len=20000)
        for chunk in chunks:
            target_id = f"session:{sender_id}" if scene == "single" else f"group:{conversation_id}"

            result = await self.send_message(
                target_id,
                MessageContent(content_type=ContentType.TEXT, text=chunk),
            )
            if not result.success:
                logger.error("dingtalk_deliver_failed", error=result.error)
                break

    @staticmethod
    def _split_text(text: str, max_len: int = 20000) -> list[str]:
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
