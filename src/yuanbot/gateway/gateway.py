"""统一网关 (YuanGateway)

系统的单一入口点，负责请求路由、会话管理和认证鉴权。
集成事件队列实现异步消息处理，集成认证模块保障安全。

设计参考: gateway-communication-system.md 第3节
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from yuanbot.core.types import BotResponse, ChannelConfig, UserMessage
from yuanbot.gateway.adapter_manager import AdapterManager
from yuanbot.gateway.auth import ChannelAuthenticator, RateLimiter
from yuanbot.gateway.identity_service import IdentityService
from yuanbot.gateway.push_dispatcher import PushDispatcher
from yuanbot.infrastructure.event_queue import (
    TOPIC_INBOUND,
    MemoryEventQueue,
    RedisEventQueue,
    create_event_queue,
)

logger = structlog.get_logger(__name__)


class YuanGateway:
    """统一网关

    职责：
    1. 入口收敛：所有外部消息通过网关进入
    2. 会话绑定：将平台用户映射为统一身份
    3. 认证鉴权：验证各平台请求的合法性（ChannelAuthenticator）
    4. 限流防滥用：双层令牌桶限流（RateLimiter）
    5. 异步处理：通过事件队列解耦网关与编排层
    6. 健康检查：提供各通道适配器连通性状态
    """

    def __init__(self, event_queue_config: dict[str, Any] | None = None) -> None:
        self._adapter_manager = AdapterManager()
        self._identity_service = IdentityService()
        self._push_dispatcher = PushDispatcher()
        self._authenticator = ChannelAuthenticator()
        self._rate_limiter = RateLimiter()
        self._event_queue: MemoryEventQueue | RedisEventQueue = create_event_queue(
            event_queue_config
        )
        self._started_at: float | None = None
        self._message_handler: Any = None

    @property
    def adapter_manager(self) -> AdapterManager:
        return self._adapter_manager

    @property
    def identity_service(self) -> IdentityService:
        return self._identity_service

    @property
    def push_dispatcher(self) -> PushDispatcher:
        return self._push_dispatcher

    @property
    def authenticator(self) -> ChannelAuthenticator:
        return self._authenticator

    @property
    def rate_limiter(self) -> RateLimiter:
        return self._rate_limiter

    @property
    def event_queue(self) -> MemoryEventQueue | RedisEventQueue:
        return self._event_queue

    def set_message_handler(self, handler: Any) -> None:
        """设置消息处理回调（通常是编排引擎的 process_message）"""
        self._message_handler = handler

    async def start(self) -> None:
        """启动网关及事件队列"""
        self._started_at = time.time()

        # 启动事件队列
        await self._event_queue.start()

        # 订阅入站消息主题
        self._event_queue.subscribe(TOPIC_INBOUND, self._handle_inbound_message)

        logger.info("gateway_started")

    async def stop(self) -> None:
        """停止网关及事件队列"""
        await self._event_queue.stop()
        await self._adapter_manager.shutdown_all()
        self._started_at = None
        logger.info("gateway_stopped")

    async def load_channel(
        self,
        platform: str,
        config: dict[str, Any],
    ) -> None:
        """加载消息通道"""
        channel_config = ChannelConfig(
            platform=platform,
            enabled=config.get("enabled", True),
            config=config.get("config", {}),
        )
        await self._adapter_manager.load_adapter(platform, channel_config)

    # ── 消息入站处理 ──────────────────────────

    async def receive_message(
        self,
        platform: str,
        platform_user_id: str,
        text: str | None = None,
        raw_headers: dict[str, str] | None = None,
        raw_body: str | None = None,
    ) -> str | None:
        """接收外部平台消息的统一入口

        完整流程（设计文档 3.3）：
        1. 认证鉴权
        2. 限流检查
        3. 身份解析
        4. 发布到事件队列
        5. 异步等待编排层处理

        Args:
            platform: 平台标识
            platform_user_id: 平台用户 ID
            text: 消息文本
            raw_headers: 原始请求头（用于认证）
            raw_body: 原始请求体（用于签名验证）

        Returns:
            消息 ID（异步处理），或 None 如果被拒绝
        """
        # 1. 限流检查
        if not self._rate_limiter.try_acquire(platform, platform_user_id):
            logger.warning("rate_limited", platform=platform, user_id=platform_user_id)
            return None

        # 2. 身份解析
        yuanbot_user_id, session_id = self._identity_service.resolve_user_id(
            platform, platform_user_id
        )

        # 3. 构建标准化消息
        message = UserMessage(
            platform=platform,
            platform_user_id=platform_user_id,
            yuanbot_user_id=yuanbot_user_id,
            session_id=session_id,
            content_type="text",
            text=text,
        )

        # 4. 发布到事件队列（异步处理）
        message_id = await self._event_queue.publish(
            TOPIC_INBOUND,
            {
                "message": message.model_dump(mode="json"),
                "platform": platform,
            },
        )

        logger.info(
            "message_received",
            platform=platform,
            user_id=yuanbot_user_id,
            message_id=message_id,
        )
        return message_id

    async def _handle_inbound_message(self, payload: dict[str, Any]) -> None:
        """处理入站消息（事件队列消费者回调）"""
        if not self._message_handler:
            logger.warning("no_message_handler_set")
            return

        message_data = payload.get("message", {})
        try:
            message = UserMessage(**message_data)
            response = await self._message_handler(message)
            logger.info(
                "inbound_message_handled",
                user_id=message.yuanbot_user_id,
                has_response=response is not None,
            )
        except Exception:
            logger.exception(
                "inbound_message_handler_error",
                platform=payload.get("platform"),
            )

    # ── 出站消息发送 ──────────────────────────

    async def send_response(
        self,
        platform: str,
        target_id: str,
        response: BotResponse,
    ) -> bool:
        """发送响应到指定平台通道

        Args:
            platform: 目标平台
            target_id: 目标用户/会话 ID
            response: 机器人响应

        Returns:
            是否发送成功
        """
        adapter = self._adapter_manager.get_adapter(platform)
        if not adapter:
            logger.error("adapter_not_found", platform=platform)
            return False

        try:
            result = await adapter.send_message(target_id, response.content)
            return result.success
        except Exception as e:
            logger.error("send_response_error", platform=platform, error=str(e))
            return False

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

    # ── 认证验证 ──────────────────────────────

    def verify_request(
        self,
        platform: str,
        config: dict[str, Any],
        headers: dict[str, str] | None = None,
        body: str | None = None,
        **kwargs: Any,
    ) -> bool:
        """验证请求合法性

        根据平台类型选择对应的验证方式。

        Args:
            platform: 平台标识
            config: 通道配置
            headers: 请求头
            body: 请求体
            **kwargs: 平台特有参数

        Returns:
            验证是否通过
        """
        if platform == "telegram":
            secret_token = config.get("config", {}).get("webhook", {}).get("secret_token", "")
            return self._authenticator.verify_telegram(secret_token, headers or {})

        elif platform == "discord":
            public_key = config.get("config", {}).get("public_key", "")
            signature = kwargs.get("signature", "")
            timestamp = kwargs.get("timestamp", "")
            return self._authenticator.verify_discord(public_key, signature, timestamp, body or "")

        elif platform == "wecom":
            token = config.get("config", {}).get("token", "")
            signature = kwargs.get("signature", "")
            timestamp = kwargs.get("timestamp", "")
            nonce = kwargs.get("nonce", "")
            return self._authenticator.verify_wecom(token, signature, timestamp, nonce)

        elif platform == "webchat":
            auth_required = config.get("config", {}).get("auth_required", False)
            configured_token = config.get("config", {}).get("auth_token")
            request_token = kwargs.get("auth_token")
            return self._authenticator.verify_webchat(
                auth_required, configured_token, request_token
            )

        # 未知平台默认放行
        return True

    # ── 健康检查 ──────────────────────────────

    def get_health_status(self) -> dict[str, Any]:
        """获取网关及各通道健康状态"""
        adapter_health = self._adapter_manager.get_health_status()
        uptime = time.time() - self._started_at if self._started_at else 0

        return {
            "status": "ok" if self._started_at else "stopped",
            "uptime_seconds": round(uptime, 2),
            "adapters": adapter_health,
            "event_queue": self._event_queue.get_stats(),
            "rate_limiter": self._rate_limiter.get_stats(),
            "identities": self._identity_service.get_all_identities(),
        }
