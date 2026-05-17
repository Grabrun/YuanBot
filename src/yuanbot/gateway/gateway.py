"""统一网关 (YuanGateway)

系统的单一入口点，负责请求路由、会话管理和认证鉴权。
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from yuanbot.core.types import ChannelConfig
from yuanbot.gateway.adapter_manager import AdapterManager
from yuanbot.gateway.identity_service import IdentityService
from yuanbot.gateway.push_dispatcher import PushDispatcher

logger = structlog.get_logger(__name__)


class YuanGateway:
    """统一网关

    职责：
    1. 入口收敛：所有外部消息通过网关进入
    2. 会话绑定：将平台用户映射为统一身份
    3. 认证鉴权：验证各平台请求的合法性
    4. 健康检查：提供各通道适配器连通性状态
    """

    def __init__(self) -> None:
        self._adapter_manager = AdapterManager()
        self._identity_service = IdentityService()
        self._push_dispatcher = PushDispatcher()
        self._started_at: float | None = None
        self._message_handler: Any = None  # Callable[[UserMessage], Awaitable[BotResponse]]

    @property
    def adapter_manager(self) -> AdapterManager:
        return self._adapter_manager

    @property
    def identity_service(self) -> IdentityService:
        return self._identity_service

    @property
    def push_dispatcher(self) -> PushDispatcher:
        return self._push_dispatcher

    def set_message_handler(self, handler: Any) -> None:
        """设置消息处理回调（通常是编排引擎的 process_message）"""
        self._message_handler = handler

    async def start(self) -> None:
        """启动网关"""
        self._started_at = time.time()
        logger.info("gateway_started")

    async def stop(self) -> None:
        """停止网关"""
        await self._adapter_manager.shutdown_all()
        self._started_at = None
        logger.info("gateway_stopped")

    async def load_channel(
        self,
        platform: str,
        config: dict[str, Any],
    ) -> None:
        """加载消息通道

        Args:
            platform: 平台标识
            config: 通道配置字典
        """
        channel_config = ChannelConfig(
            platform=platform,
            enabled=config.get("enabled", True),
            config=config.get("config", {}),
        )
        await self._adapter_manager.load_adapter(platform, channel_config)

    def resolve_identity(
        self,
        platform: str,
        platform_user_id: str,
    ) -> tuple[str, str]:
        """解析用户身份

        Returns:
            (yuanbot_user_id, session_id) 元组
        """
        yuanbot_user_id = self._identity_service.resolve_user_id(platform, platform_user_id)
        session_id = self._identity_service.build_session_id(platform, platform_user_id)
        return yuanbot_user_id, session_id

    def get_health_status(self) -> dict[str, Any]:
        """获取网关及各通道健康状态"""
        adapter_health = self._adapter_manager.get_health_status()
        uptime = time.time() - self._started_at if self._started_at else 0

        return {
            "status": "ok" if self._started_at else "stopped",
            "uptime_seconds": round(uptime, 2),
            "adapters": adapter_health,
            "identities": self._identity_service.get_all_identities(),
        }
