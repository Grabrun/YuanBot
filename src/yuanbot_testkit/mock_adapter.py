"""TestAdapter — 用于扩展测试的模拟通道适配器

模拟消息通道发送与接收行为，记录所有发送消息，
支持测试驱动的消息注入。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from yuanbot.core.types import (
    BotResponse,
    ChannelConfig,
    ContentType,
    MessageContent,
    SendResult,
    UserMessage,
)


@dataclass
class SentMessage:
    """已发送的消息记录"""

    target_id: str
    content: MessageContent
    timestamp: float = 0.0


class TestAdapter:
    """测试用消息通道适配器

    在测试中替代真实的消息通道适配器（Telegram、微信等），
    让 Adapter/Skill 的测试用例无需连接真实消息平台。

    发送消息的记录可通过 ``sent_messages`` 访问，便于断言。

    支持通过 ``simulate_message()`` 方法模拟接收用户消息，
    触发已注册的 ``listen()`` 回调。

    用法::

        adapter = TestAdapter(platform_name="test_bot")
        assert adapter.platform_name == "test_bot"

        # 发送消息
        result = await adapter.send_message("user_123", MessageContent(
            content_type=ContentType.TEXT,
            text="Hello!",
        ))
        assert result.success
        assert len(adapter.sent_messages) == 1
        assert adapter.sent_messages[0].content.text == "Hello!"
    """

    def __init__(
        self,
        platform_name: str = "test",
        supported_types: list[ContentType] | None = None,
        config: ChannelConfig | None = None,
    ) -> None:
        self._platform_name = platform_name
        self._supported_types = supported_types or [
            ContentType.TEXT,
            ContentType.IMAGE,
        ]
        self._config = config
        self._callback: Callable[[UserMessage], Awaitable[BotResponse]] | None = None
        self._sent_messages: list[SentMessage] = []
        self._initialized: bool = False
        self._received_messages: list[UserMessage] = []

    # ── 属性 ──────────────────────────────────

    @property
    def platform_name(self) -> str:
        """返回平台名称"""
        return self._platform_name

    @platform_name.setter
    def platform_name(self, name: str) -> None:
        self._platform_name = name

    @property
    def supported_content_types(self) -> list[ContentType]:
        """返回支持的内容类型"""
        return list(self._supported_types)

    @supported_content_types.setter
    def supported_content_types(self, types: list[ContentType]) -> None:
        self._supported_types = list(types)

    @property
    def sent_messages(self) -> list[SentMessage]:
        """返回所有已发送消息（用于断言）"""
        return list(self._sent_messages)

    @property
    def received_messages(self) -> list[UserMessage]:
        """返回所有已接收的用户消息"""
        return list(self._received_messages)

    @property
    def is_initialized(self) -> bool:
        """适配器是否已初始化"""
        return self._initialized

    @property
    def callback_registered(self) -> bool:
        """是否已注册消息回调"""
        return self._callback is not None

    # ── 重置 ──────────────────────────────────

    def reset(self) -> None:
        """重置适配器状态（清空消息记录，保留配置）"""
        self._sent_messages.clear()
        self._received_messages.clear()

    def clear_sent_messages(self) -> None:
        """仅清空已发送消息记录"""
        self._sent_messages.clear()

    def clear_received_messages(self) -> None:
        """仅清空已接收消息记录"""
        self._received_messages.clear()

    # ── 初始化和监听 ──────────────────────────

    async def initialize(self, config: ChannelConfig) -> None:
        """模拟适配器初始化

        Args:
            config: 通道配置
        """
        self._config = config
        self._initialized = True

    async def listen(
        self,
        callback: Callable[[UserMessage], Awaitable[BotResponse]],
    ) -> None:
        """注册消息处理回调

        测试中可以通过 ``simulate_message()`` 触发此回调。

        Args:
            callback: 用户消息处理回调
        """
        self._callback = callback

    # ── 消息发送 ──────────────────────────────

    async def send_message(
        self,
        target_id: str,
        content: MessageContent,
    ) -> SendResult:
        """模拟发送消息

        记录发送消息到 ``sent_messages`` 列表。

        Args:
            target_id: 目标 ID
            content: 消息内容

        Returns:
            SendResult: 发送结果
        """
        self._sent_messages.append(
            SentMessage(target_id=target_id, content=content)
        )
        return SendResult(success=True, message_id=f"mock_msg_{len(self._sent_messages)}")

    # ── 模拟接收 ──────────────────────────────

    async def simulate_message(self, message: UserMessage) -> BotResponse | None:
        """模拟接收用户消息

        如果已注册 ``listen()`` 回调，将触发回调处理该消息。

        Args:
            message: 要模拟接收的用户消息

        Returns:
            回调返回的 BotResponse，如果没有注册回调则返回 None
        """
        self._received_messages.append(message)
        if self._callback is not None:
            return await self._callback(message)
        return None

    # ── 用户 ID ───────────────────────────────

    def get_platform_user_id(self, raw_event: Any) -> str:
        """从原始事件中提取平台用户 ID

        对于测试适配器，如果 raw_event 是 UserMessage 则返回其 platform_user_id，
        否则返回字符串表示。

        Args:
            raw_event: 原始事件

        Returns:
            平台用户 ID
        """
        if isinstance(raw_event, UserMessage):
            return raw_event.platform_user_id
        return str(raw_event)
