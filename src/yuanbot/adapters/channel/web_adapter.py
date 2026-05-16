"""Web 消息通道适配器

基于 FastAPI WebSocket，提供实时双向聊天。
支持文本消息、心跳保活、会话管理。
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

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

# 会话超时时间（秒）
SESSION_TIMEOUT = 300  # 5 分钟
# 心跳间隔（秒）
PING_INTERVAL = 30
# 消息大小限制（字节）
MAX_MESSAGE_SIZE = 64 * 1024  # 64KB


class WebSession:
    """Web 会话管理"""

    def __init__(self, session_id: str, user_id: str, ws: WebSocket):
        self.session_id = session_id
        self.user_id = user_id
        self.ws = ws
        self.created_at = time.time()
        self.last_active = time.time()
        self.metadata: dict[str, Any] = {}

    def touch(self) -> None:
        """更新最后活跃时间"""
        self.last_active = time.time()

    @property
    def is_expired(self) -> bool:
        """会话是否已过期"""
        return (time.time() - self.last_active) > SESSION_TIMEOUT

    @property
    def is_connected(self) -> bool:
        """WebSocket 是否仍然连接"""
        return self.ws.client_state == WebSocketState.CONNECTED


class WebAdapter(BaseChannelAdapter):
    """Web (WebSocket) 消息通道适配器

    提供基于 WebSocket 的实时聊天通道。
    客户端通过 WebSocket 连接进行双向消息通信。

    消息协议（JSON）：
    - 客户端 → 服务端：
        {"type": "message", "content_type": "text", "text": "你好", "user_id": "xxx"}
        {"type": "ping"}
    - 服务端 → 客户端：
        {"type": "response", "content_type": "text", "text": "你好呀~", "message_id": "xxx"}
        {"type": "pong"}
        {"type": "error", "message": "..."}
    """

    def __init__(self, config: ChannelConfig | None = None):
        super().__init__(config)
        self._sessions: dict[str, WebSession] = {}  # session_id -> WebSession
        self._user_sessions: dict[str, str] = {}    # user_id -> session_id
        self._ping_task: asyncio.Task | None = None

    @property
    def platform_name(self) -> str:
        return "web"

    @property
    def supported_content_types(self) -> list[ContentType]:
        return [ContentType.TEXT]

    async def initialize(self, config: ChannelConfig) -> None:
        """初始化 Web 适配器"""
        self._config = config
        logger.info("web_adapter_initialized")

    async def listen(
        self,
        callback: Callable[[UserMessage], Awaitable[BotResponse]],
    ) -> None:
        """启动消息监听

        注意：Web 适配器不主动 listen，而是通过 handle_websocket 被动接收。
        此方法启动心跳清理任务。
        """
        self._callback = callback
        self._ping_task = asyncio.create_task(self._session_cleanup_loop())
        logger.info("web_adapter_listening")

    async def handle_websocket(self, ws: WebSocket) -> None:
        """处理 WebSocket 连接

        这是 Web 适配器的核心入口，由 FastAPI 路由调用：
            @app.websocket("/ws")
            async def websocket_endpoint(ws: WebSocket):
                await web_adapter.handle_websocket(ws)
        """
        await ws.accept()

        # 生成会话
        session_id = str(uuid.uuid4())
        # 等待客户端发送 user_id，或生成匿名 ID
        user_id = f"web_anon_{uuid.uuid4().hex[:8]}"
        session = WebSession(session_id, user_id, ws)

        logger.info("ws_connected", session_id=session_id)

        try:
            while True:
                raw = await ws.receive_text()
                await self._process_message(session, raw)
        except WebSocketDisconnect:
            logger.info("ws_disconnected", session_id=session_id)
        except Exception as e:
            logger.error("ws_error", session_id=session_id, error=str(e))
        finally:
            await self._cleanup_session(session)

    async def send_message(
        self,
        target_id: str,
        content: MessageContent,
    ) -> SendResult:
        """向指定会话发送消息"""
        session = self._sessions.get(target_id)
        if not session or not session.is_connected:
            return SendResult(success=False, error="Session not found or disconnected")

        try:
            payload: dict[str, Any] = {
                "type": "response",
                "content_type": content.content_type.value,
            }
            if content.text:
                payload["text"] = content.text
            if content.media_url:
                payload["media_url"] = content.media_url
            if content.metadata:
                payload["metadata"] = content.metadata

            await session.ws.send_text(json.dumps(payload, ensure_ascii=False))
            session.touch()

            return SendResult(
                success=True,
                message_id=f"msg_{uuid.uuid4().hex[:12]}",
            )
        except Exception as e:
            return SendResult(success=False, error=str(e))

    def get_platform_user_id(self, raw_event: Any) -> str:
        """从原始事件中提取用户 ID"""
        if isinstance(raw_event, dict):
            return raw_event.get("user_id", "")
        return ""

    def get_session(self, session_id: str) -> WebSession | None:
        """获取会话"""
        return self._sessions.get(session_id)

    def get_active_session_count(self) -> int:
        """获取活跃会话数量"""
        return len(self._sessions)

    # ──────────────────────────────────────────
    # 内部方法
    # ──────────────────────────────────────────

    async def _process_message(self, session: WebSession, raw: str) -> None:
        """处理客户端消息"""
        session.touch()

        # 消息大小检查
        if len(raw) > MAX_MESSAGE_SIZE:
            await self._send_error(session, "Message too large")
            return

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            await self._send_error(session, "Invalid JSON")
            return

        msg_type = data.get("type", "message")

        if msg_type == "ping":
            await session.ws.send_text(json.dumps({"type": "pong"}))
            return

        if msg_type == "message":
            await self._handle_chat_message(session, data)
            return

        await self._send_error(session, f"Unknown message type: {msg_type}")

    async def _handle_chat_message(
        self,
        session: WebSession,
        data: dict[str, Any],
    ) -> None:
        """处理聊天消息"""
        text = data.get("text", "")
        if not text:
            await self._send_error(session, "Empty message")
            return

        # 更新用户 ID（如果客户端提供了）
        client_user_id = data.get("user_id")
        if client_user_id and session.user_id.startswith("web_anon_"):
            old_user_id = session.user_id
            session.user_id = client_user_id
            self._user_sessions[client_user_id] = session.session_id
            if old_user_id in self._user_sessions:
                del self._user_sessions[old_user_id]

        # 注册会话
        self._sessions[session.session_id] = session
        self._user_sessions[session.user_id] = session.session_id

        # 构建标准化消息
        content_type = ContentType.TEXT
        raw_content_type = data.get("content_type", "text")
        try:
            content_type = ContentType(raw_content_type)
        except ValueError:
            content_type = ContentType.TEXT

        user_message = UserMessage(
            platform="web",
            platform_user_id=session.user_id,
            yuanbot_user_id=self._resolve_yuanbot_user_id(session.user_id),
            session_id=session.session_id,
            content_type=content_type,
            text=text,
            metadata=data.get("metadata", {}),
        )

        # 通过回调交给编排层处理
        if self._callback:
            try:
                response = await self._callback(user_message)
                await self.send_message(
                    target_id=session.session_id,
                    content=response.content,
                )
            except Exception as e:
                logger.error("web_handle_error", error=str(e))
                await self._send_error(session, "Internal error")

    async def _send_error(self, session: WebSession, message: str) -> None:
        """发送错误消息"""
        try:
            await session.ws.send_text(
                json.dumps({"type": "error", "message": message})
            )
        except Exception:
            pass

    async def _cleanup_session(self, session: WebSession) -> None:
        """清理会话"""
        if session.session_id in self._sessions:
            del self._sessions[session.session_id]
        if session.user_id in self._user_sessions:
            if self._user_sessions[session.user_id] == session.session_id:
                del self._user_sessions[session.user_id]
        logger.info(
            "session_cleaned",
            session_id=session.session_id,
            user_id=session.user_id,
        )

    async def _session_cleanup_loop(self) -> None:
        """定期清理过期会话"""
        while True:
            await asyncio.sleep(60)
            expired = [
                sid for sid, session in self._sessions.items()
                if session.is_expired or not session.is_connected
            ]
            for sid in expired:
                session = self._sessions[sid]
                await self._cleanup_session(session)

    async def close(self) -> None:
        """关闭适配器"""
        if self._ping_task:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass

        # 关闭所有会话
        for session in list(self._sessions.values()):
            try:
                if session.is_connected:
                    await session.ws.close()
            except Exception:
                pass
        self._sessions.clear()
        self._user_sessions.clear()
        logger.info("web_adapter_closed")
