"""通道认证与安全模块

为各消息通道提供请求验证、限流和防滥用机制。

设计参考: gateway-communication-system.md 第8节
"""

from __future__ import annotations

import hashlib
import hmac
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class RateLimitConfig:
    """限流配置"""

    max_requests_per_second: float = 10.0
    max_requests_per_user_per_minute: float = 30.0
    burst_size: int = 20


class TokenBucket:
    """令牌桶限流器"""

    def __init__(self, rate: float, burst: int):
        self._rate = rate  # 每秒产生的令牌数
        self._burst = burst  # 桶容量
        self._tokens = float(burst)
        self._last_refill = time.monotonic()

    def try_consume(self, tokens: int = 1) -> bool:
        """尝试消费令牌

        Returns:
            True 如果令牌足够，False 如果被限流
        """
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
        self._last_refill = now

        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False


class ChannelAuthenticator:
    """通道认证器

    为每个消息通道提供独立的请求验证逻辑。

    支持:
    - Telegram: X-Telegram-Bot-Api-Secret-Token 头验证
    - Discord: Ed25519 签名验证
    - 企业微信: SHA1 消息签名验证
    - Web Chat: 可选 JWT 认证
    """

    def verify_telegram(
        self,
        secret_token: str,
        request_headers: dict[str, str],
    ) -> bool:
        """验证 Telegram Webhook 请求

        检查 X-Telegram-Bot-Api-Secret-Token 头是否匹配。

        Args:
            secret_token: 配置的 secret token
            request_headers: 请求头字典

        Returns:
            验证是否通过
        """
        received_token = request_headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not received_token:
            logger.warning("telegram_auth_missing_header")
            return False

        is_valid = hmac.compare_digest(received_token, secret_token)
        if not is_valid:
            logger.warning("telegram_auth_invalid_token")
        return is_valid

    def verify_discord(
        self,
        public_key: str,
        signature: str,
        timestamp: str,
        body: str,
    ) -> bool:
        """验证 Discord 交互请求

        使用 Ed25519 公钥验证 HTTP 签名。

        Args:
            public_key: Discord 应用公钥（hex 格式）
            signature: 请求签名（hex 格式）
            timestamp: 请求时间戳
            body: 请求体原文

        Returns:
            验证是否通过
        """
        try:
            from nacl.exceptions import BadSignatureError
            from nacl.signing import VerifyKey

            verify_key = VerifyKey(bytes.fromhex(public_key))
            message = f"{timestamp}{body}".encode()
            verify_key.verify(message, bytes.fromhex(signature))
            return True

        except ImportError:
            logger.error("pynacl_not_installed", hint="pip install pynacl")
            return False
        except BadSignatureError:
            logger.warning("discord_auth_invalid_signature")
            return False
        except Exception as e:
            logger.error("discord_auth_error", error=str(e))
            return False

    def verify_wecom(
        self,
        token: str,
        signature: str,
        timestamp: str,
        nonce: str,
    ) -> bool:
        """验证企业微信回调签名

        使用 SHA1 算法验证消息签名。

        Args:
            token: 企业微信配置的 Token
            signature: 请求中的签名
            timestamp: 请求时间戳
            nonce: 随机字符串

        Returns:
            验证是否通过
        """
        # 按字典序排序
        items = sorted([token, timestamp, nonce])
        raw = "".join(items)

        # SHA1 哈希
        computed = hashlib.sha1(raw.encode()).hexdigest()

        is_valid = hmac.compare_digest(computed, signature)
        if not is_valid:
            logger.warning("wecom_auth_invalid_signature")
        return is_valid

    def verify_webchat(
        self,
        auth_required: bool,
        token: str | None = None,
        request_token: str | None = None,
    ) -> bool:
        """验证 Web Chat 请求

        Args:
            auth_required: 是否需要认证
            token: 配置的认证令牌
            request_token: 请求中的认证令牌

        Returns:
            验证是否通过
        """
        if not auth_required:
            return True

        if not token:
            logger.warning("webchat_auth_no_configured_token")
            return True  # 未配置 token 则放行

        if not request_token:
            logger.warning("webchat_auth_missing_token")
            return False

        is_valid = hmac.compare_digest(request_token, token)
        if not is_valid:
            logger.warning("webchat_auth_invalid_token")
        return is_valid


class RateLimiter:
    """限流器

    双层限流:
    1. 全局限流: 每个通道的最大每秒消息数
    2. 用户级限流: 每个用户每分钟最大消息数

    设计参考: gateway-communication-system.md 8.3
    """

    def __init__(self, config: dict[str, RateLimitConfig] | None = None):
        self._config = config or {}
        self._global_buckets: dict[str, TokenBucket] = {}
        self._user_buckets: dict[str, TokenBucket] = {}
        self._user_timestamps: dict[str, list[float]] = defaultdict(list)

    def _get_or_create_global_bucket(self, channel: str) -> TokenBucket:
        """获取或创建通道级全局令牌桶"""
        if channel not in self._global_buckets:
            config = self._config.get(channel, RateLimitConfig())
            self._global_buckets[channel] = TokenBucket(
                rate=config.max_requests_per_second,
                burst=config.burst_size,
            )
        return self._global_buckets[channel]

    def _get_or_create_user_bucket(self, user_key: str) -> TokenBucket:
        """获取或创建用户级令牌桶"""
        if user_key not in self._user_buckets:
            self._user_buckets[user_key] = TokenBucket(
                rate=0.5,  # 每分钟 30 条 = 每秒 0.5 条
                burst=5,
            )
        return self._user_buckets[user_key]

    def try_acquire(self, channel: str, user_id: str) -> bool:
        """尝试获取请求许可

        Args:
            channel: 通道名称
            user_id: 用户 ID

        Returns:
            True 如果允许，False 如果被限流
        """
        # 全局限流
        global_bucket = self._get_or_create_global_bucket(channel)
        if not global_bucket.try_consume():
            logger.warning(
                "rate_limit_global",
                channel=channel,
                user_id=user_id,
            )
            return False

        # 用户级限流
        user_key = f"{channel}:{user_id}"
        user_bucket = self._get_or_create_user_bucket(user_key)
        if not user_bucket.try_consume():
            logger.warning(
                "rate_limit_user",
                channel=channel,
                user_id=user_id,
            )
            return False

        return True

    def get_stats(self) -> dict[str, Any]:
        """获取限流统计"""
        return {
            "channels": list(self._global_buckets.keys()),
            "tracked_users": len(self._user_buckets),
        }
