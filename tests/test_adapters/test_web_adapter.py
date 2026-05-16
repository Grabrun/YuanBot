"""Web 通道适配器测试"""

from __future__ import annotations

import json
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.websockets import WebSocketState

from yuanbot.adapters.channel.web_adapter import WebAdapter, WebSession, SESSION_TIMEOUT
from yuanbot.core.types import (
    BotResponse,
    ChannelConfig,
    ContentType,
    MessageContent,
    UserMessage,
)


class MockWebSocket:
    """模拟 WebSocket 连接"""

    def __init__(self):
        self.sent: list[str] = []
        self.client_state = WebSocketState.CONNECTED
        self._receive_queue: asyncio.Queue[str] = asyncio.Queue()

    async def accept(self):
        pass

    async def receive_text(self) -> str:
        return await self._receive_queue.get()

    async def send_text(self, data: str):
        self.sent.append(data)

    async def close(self):
        self.client_state = WebSocketState.DISCONNECTED

    def inject_message(self, text: str):
        """注入客户端消息"""
        self._receive_queue.put_nowait(text)

    @property
    def last_sent_json(self):
        if not self.sent:
            return None
        return json.loads(self.sent[-1])


class TestWebAdapterProperties:
    """属性测试"""

    def test_platform_name(self):
        adapter = WebAdapter()
        assert adapter.platform_name == "web"

    def test_supported_content_types(self):
        adapter = WebAdapter()
        assert ContentType.TEXT in adapter.supported_content_types

    def test_initial_session_count(self):
        adapter = WebAdapter()
        assert adapter.get_active_session_count() == 0


class TestWebSession:
    """会话管理测试"""

    def test_session_creation(self):
        ws = MockWebSocket()
        session = WebSession("sid_1", "uid_1", ws)
        assert session.session_id == "sid_1"
        assert session.user_id == "uid_1"
        assert not session.is_expired

    def test_session_touch(self):
        ws = MockWebSocket()
        session = WebSession("sid_1", "uid_1", ws)
        old_time = session.last_active
        import time
        time.sleep(0.01)
        session.touch()
        assert session.last_active > old_time

    def test_session_is_connected(self):
        ws = MockWebSocket()
        session = WebSession("sid_1", "uid_1", ws)
        assert session.is_connected

        ws.client_state = WebSocketState.DISCONNECTED
        assert not session.is_connected


class TestMessageProtocol:
    """消息协议测试"""

    @pytest.mark.asyncio
    async def test_ping_pong(self):
        """ping 应返回 pong"""
        adapter = WebAdapter()
        ws = MockWebSocket()
        session = WebSession("sid_1", "uid_1", ws)

        ws.inject_message(json.dumps({"type": "ping"}))

        # 处理一条消息
        await adapter._process_message(session, json.dumps({"type": "ping"}))

        assert len(ws.sent) == 1
        data = json.loads(ws.sent[0])
        assert data["type"] == "pong"

    @pytest.mark.asyncio
    async def test_empty_message_error(self):
        """空消息应返回错误"""
        adapter = WebAdapter()
        ws = MockWebSocket()
        session = WebSession("sid_1", "uid_1", ws)

        await adapter._process_message(
            session,
            json.dumps({"type": "message", "text": ""}),
        )

        data = json.loads(ws.sent[0])
        assert data["type"] == "error"
        assert "Empty" in data["message"]

    @pytest.mark.asyncio
    async def test_invalid_json_error(self):
        """无效 JSON 应返回错误"""
        adapter = WebAdapter()
        ws = MockWebSocket()
        session = WebSession("sid_1", "uid_1", ws)

        await adapter._process_message(session, "not json {{{")

        data = json.loads(ws.sent[0])
        assert data["type"] == "error"
        assert "JSON" in data["message"]

    @pytest.mark.asyncio
    async def test_unknown_message_type_error(self):
        """未知消息类型应返回错误"""
        adapter = WebAdapter()
        ws = MockWebSocket()
        session = WebSession("sid_1", "uid_1", ws)

        await adapter._process_message(
            session,
            json.dumps({"type": "unknown"}),
        )

        data = json.loads(ws.sent[0])
        assert data["type"] == "error"

    @pytest.mark.asyncio
    async def test_oversized_message_error(self):
        """超大消息应返回错误"""
        adapter = WebAdapter()
        ws = MockWebSocket()
        session = WebSession("sid_1", "uid_1", ws)

        big_msg = json.dumps({"type": "message", "text": "x" * 100_000})
        await adapter._process_message(session, big_msg)

        data = json.loads(ws.sent[0])
        assert data["type"] == "error"
        assert "too large" in data["message"].lower()


class TestSendMessage:
    """发送消息测试"""

    @pytest.mark.asyncio
    async def test_send_text_message(self):
        adapter = WebAdapter()
        ws = MockWebSocket()
        session = WebSession("sid_1", "uid_1", ws)
        adapter._sessions["sid_1"] = session

        content = MessageContent(content_type=ContentType.TEXT, text="你好呀~")
        result = await adapter.send_message("sid_1", content)

        assert result.success
        assert result.message_id is not None
        data = json.loads(ws.sent[0])
        assert data["type"] == "response"
        assert data["text"] == "你好呀~"

    @pytest.mark.asyncio
    async def test_send_to_nonexistent_session(self):
        adapter = WebAdapter()
        content = MessageContent(content_type=ContentType.TEXT, text="你好")
        result = await adapter.send_message("nonexistent", content)
        assert not result.success
        assert "not found" in result.error.lower()


class TestChatMessageHandling:
    """聊天消息处理测试"""

    @pytest.mark.asyncio
    async def test_chat_message_with_callback(self):
        """带回调的聊天消息处理"""
        adapter = WebAdapter()
        ws = MockWebSocket()
        session = WebSession("sid_1", "uid_1", ws)
        adapter._sessions["sid_1"] = session

        # 设置回调
        async def mock_callback(msg):
            return BotResponse(
                content=MessageContent(
                    content_type=ContentType.TEXT,
                    text=f"收到: {msg.text}",
                ),
            )

        adapter._callback = mock_callback

        await adapter._process_message(
            session,
            json.dumps({"type": "message", "text": "你好"}),
        )

        # 应该有两条消息：回调响应
        assert len(ws.sent) >= 1
        data = json.loads(ws.sent[-1])
        assert data["type"] == "response"
        assert "收到" in data["text"]

    @pytest.mark.asyncio
    async def test_user_id_update(self):
        """客户端提供 user_id 时应更新会话"""
        adapter = WebAdapter()
        ws = MockWebSocket()
        session = WebSession("sid_1", "web_anon_abc", ws)
        adapter._sessions["sid_1"] = session

        # 设置回调避免报错
        async def mock_callback(msg):
            return BotResponse(
                content=MessageContent(content_type=ContentType.TEXT, text="ok"),
            )
        adapter._callback = mock_callback

        await adapter._process_message(
            session,
            json.dumps({"type": "message", "text": "你好", "user_id": "real_user"}),
        )

        assert session.user_id == "real_user"
        assert adapter._user_sessions["real_user"] == "sid_1"


class TestSessionCleanup:
    """会话清理测试"""

    @pytest.mark.asyncio
    async def test_cleanup_session(self):
        adapter = WebAdapter()
        ws = MockWebSocket()
        session = WebSession("sid_1", "uid_1", ws)
        adapter._sessions["sid_1"] = session
        adapter._user_sessions["uid_1"] = "sid_1"

        await adapter._cleanup_session(session)

        assert "sid_1" not in adapter._sessions
        assert "uid_1" not in adapter._user_sessions

    @pytest.mark.asyncio
    async def test_close_adapter(self):
        adapter = WebAdapter()
        ws = MockWebSocket()
        session = WebSession("sid_1", "uid_1", ws)
        adapter._sessions["sid_1"] = session

        await adapter.close()

        assert len(adapter._sessions) == 0
        assert len(adapter._user_sessions) == 0
