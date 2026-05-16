"""消息通道适配器基类"""

from __future__ import annotations

from abc import ABC
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from yuanbot.core.interfaces import ChannelAdapter
from yuanbot.core.types import BotResponse, ChannelConfig, UserMessage

logger = structlog.get_logger(__name__)


class BaseChannelAdapter(ChannelAdapter, ABC):
    """消息通道适配器基类
    
    提供通用的用户 ID 映射和会话管理。
    """

    def __init__(self, config: ChannelConfig | None = None):
        self._config = config
        self._callback: Callable[[UserMessage], Awaitable[BotResponse]] | None = None
        self._user_id_map: dict[str, str] = {}  # platform_user_id -> yuanbot_user_id

    def _resolve_yuanbot_user_id(self, platform_user_id: str) -> str:
        """将平台用户 ID 映射为 YuanBot 统一用户 ID
        
        简单实现：直接使用平台用户 ID 作为 YuanBot 用户 ID。
        后续可通过数据库实现跨平台身份关联。
        """
        if platform_user_id not in self._user_id_map:
            self._user_id_map[platform_user_id] = f"yb_{platform_user_id}"
        return self._user_id_map[platform_user_id]

    def _build_session_id(self, platform_user_id: str) -> str:
        """构建会话 ID"""
        return f"{self.platform_name}:{platform_user_id}"
