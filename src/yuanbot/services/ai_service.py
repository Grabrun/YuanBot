"""统一 AI 服务门面

对编排层和记忆系统暴露统一的 AI 调用接口，
屏蔽底层提供商差异，实现零供应商锁定。

设计参考: ai-provider-system.md 第5节
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import structlog

from yuanbot.core.interfaces import AIProviderAdapter
from yuanbot.core.types import (
    ChatChunk,
    ChatResponse,
    Message,
    ToolDefinition,
)
from yuanbot.providers.manager import ProviderManager

logger = structlog.get_logger(__name__)

# ── 重试与熔断配置 ──────────────────────────
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_CIRCUIT_BREAKER_THRESHOLD = 5
_DEFAULT_CIRCUIT_BREAKER_COOLDOWN_SECONDS = 30


class CircuitBreakerState:
    """熔断器状态追踪"""

    def __init__(
        self,
        threshold: int = _DEFAULT_CIRCUIT_BREAKER_THRESHOLD,
        cooldown_seconds: int = _DEFAULT_CIRCUIT_BREAKER_COOLDOWN_SECONDS,
    ):
        self._threshold = threshold
        self._cooldown_seconds = cooldown_seconds
        self._consecutive_failures: dict[str, int] = {}
        self._open_until: dict[str, float] = {}  # provider_id -> timestamp

    def record_success(self, provider_id: str) -> None:
        """记录成功调用，重置失败计数"""
        self._consecutive_failures.pop(provider_id, None)

    def record_failure(self, provider_id: str) -> None:
        """记录失败调用"""
        count = self._consecutive_failures.get(provider_id, 0) + 1
        self._consecutive_failures[provider_id] = count

        if count >= self._threshold:
            import time

            self._open_until[provider_id] = time.time() + self._cooldown_seconds
            logger.warning(
                "circuit_breaker_opened",
                provider_id=provider_id,
                failures=count,
                cooldown_seconds=self._cooldown_seconds,
            )

    def is_open(self, provider_id: str) -> bool:
        """检查熔断器是否打开（提供商不可用）"""
        import time

        open_until = self._open_until.get(provider_id)
        if open_until is None:
            return False
        if time.time() >= open_until:
            # 冷却期结束，半开状态
            self._open_until.pop(provider_id, None)
            self._consecutive_failures.pop(provider_id, None)
            logger.info("circuit_breaker_half_open", provider_id=provider_id)
            return False
        return True


class RateLimitError(Exception):
    """速率限制错误

    当 AI 服务请求超过速率限制时抛出。
    """

    def __init__(self, message: str = "Rate limit exceeded", retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class AIService:
    """统一 AI 服务门面

    对外暴露三个核心方法：
    - generate(): 非流式对话生成
    - generate_stream(): 流式对话生成
    - embed(): 文本向量嵌入

    内部处理：
    - 提供商和模型的自动解析
    - 网络重试（指数退避）
    - 熔断器（连续失败后暂停调用）
    - 速率限制（可选）
    """

    def __init__(
        self,
        provider_manager: ProviderManager,
        config: dict[str, Any] | None = None,
    ):
        self._pm = provider_manager
        self._config = config or {}

        # 重试配置
        self._max_retries = self._config.get("max_retries", _DEFAULT_MAX_RETRIES)

        # 熔断器
        self._circuit_breaker = CircuitBreakerState(
            threshold=self._config.get(
                "circuit_breaker_threshold", _DEFAULT_CIRCUIT_BREAKER_THRESHOLD
            ),
            cooldown_seconds=self._config.get(
                "circuit_breaker_cooldown", _DEFAULT_CIRCUIT_BREAKER_COOLDOWN_SECONDS
            ),
        )

        # 速率限制（每秒最大请求数，0 表示不限制）
        self._rate_limit = self._config.get("rate_limit_per_second", 0)
        self._rate_limiter: Any = None
        if self._rate_limit > 0:
            from yuanbot.gateway.auth import TokenBucket

            burst = self._config.get("rate_limit_burst", max(int(self._rate_limit * 2), 5))
            self._rate_limiter = TokenBucket(rate=float(self._rate_limit), burst=burst)
            logger.info(
                "rate_limiter_initialized",
                rate_per_second=self._rate_limit,
                burst=burst,
            )

    # ── 核心接口 ──────────────────────────────

    async def generate(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system_prompt: str | None = None,
    ) -> ChatResponse:
        """非流式对话生成

        自动选择提供者和模型，支持重试和熔断。

        Args:
            messages: 对话消息列表
            tools: 工具定义列表（function calling）
            model: 模型 ID（可选，支持 "provider/model" 格式）
            temperature: 温度参数
            max_tokens: 最大输出 token 数
            system_prompt: 系统提示词（可选）

        Returns:
            ChatResponse: 对话响应

        Raises:
            RuntimeError: 所有重试均失败
            ValueError: 提供商未找到
        """
        provider_id, actual_model = self._resolve_model(model)
        self._check_rate_limit()
        adapter = await self._get_healthy_adapter(provider_id)

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await adapter.chat_completion(
                    messages=messages,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    system_prompt=system_prompt,
                )
                self._circuit_breaker.record_success(provider_id)
                return response

            except Exception as e:
                last_error = e
                self._circuit_breaker.record_failure(provider_id)
                if attempt < self._max_retries:
                    wait_seconds = min(2**attempt, 8)
                    logger.warning(
                        "ai_generate_retry",
                        provider_id=provider_id,
                        attempt=attempt + 1,
                        error=str(e),
                        wait_seconds=wait_seconds,
                    )
                    import asyncio

                    await asyncio.sleep(wait_seconds)

        raise RuntimeError(
            f"AI generation failed after {self._max_retries + 1} attempts "
            f"(provider={provider_id}): {last_error}"
        )

    async def generate_stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system_prompt: str | None = None,
    ) -> AsyncIterator[ChatChunk]:
        """流式对话生成

        Args:
            messages: 对话消息列表
            tools: 工具定义列表
            model: 模型 ID
            temperature: 温度参数
            max_tokens: 最大输出 token 数
            system_prompt: 系统提示词

        Yields:
            ChatChunk: 流式响应块
        """
        provider_id, actual_model = self._resolve_model(model)
        self._check_rate_limit()
        adapter = await self._get_healthy_adapter(provider_id)

        try:
            async for chunk in adapter.stream_chat_completion(
                messages=messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
                system_prompt=system_prompt,
            ):
                yield chunk
            self._circuit_breaker.record_success(provider_id)
        except Exception:
            self._circuit_breaker.record_failure(provider_id)
            raise

    async def embed(
        self,
        text: str,
        model: str | None = None,
        provider_id: str | None = None,
    ) -> list[float]:
        """文本向量嵌入

        Args:
            text: 待嵌入文本
            model: 嵌入模型 ID（可选）
            provider_id: 提供商 ID（可选，不指定则使用 embedding_provider）

        Returns:
            向量列表
        """
        # 嵌入提供商优先使用配置的 embedding_provider
        self._check_rate_limit()
        pid = provider_id or self._config.get("embedding_provider")
        if not pid:
            # 回退到默认提供商
            default_config = self._pm.get_default_provider()
            pid = default_config.provider_id if default_config else None

        if not pid:
            raise ValueError("No provider available for embedding")

        adapter = await self._get_healthy_adapter(pid)

        # 确定嵌入模型
        emb_model = model
        if not emb_model:
            emb_model_info = self._pm.get_embedding_model(pid)
            if emb_model_info:
                emb_model = emb_model_info.id

        if not emb_model:
            raise ValueError(f"No embedding model found for provider '{pid}'")

        try:
            result = await adapter.get_embedding(text=text, model=emb_model)
            self._circuit_breaker.record_success(pid)
            return result
        except Exception:
            self._circuit_breaker.record_failure(pid)
            raise

    # ── 速率限制 ──────────────────────────────

    def _check_rate_limit(self) -> None:
        """检查速率限制

        如果超限，抛出 RateLimitError。
        """
        if self._rate_limiter is None:
            return
        if not self._rate_limiter.try_consume():
            logger.warning("rate_limit_exceeded", rate_per_second=self._rate_limit)
            raise RateLimitError(
                f"Rate limit exceeded: max {self._rate_limit} requests/second",
                retry_after=1.0 / self._rate_limit if self._rate_limit > 0 else None,
            )

    # ── 模型解析 ──────────────────────────────

    def _resolve_model(self, model: str | None) -> tuple[str, str]:
        """解析模型参数，返回 (provider_id, model_id)

        委托给 ProviderManager.resolve_model()。
        支持格式：
        - None: 使用默认提供商的默认模型
        - "gpt-4o": 在默认提供商中查找
        - "openai/gpt-4o": 指定提供商+模型
        """
        return self._pm.resolve_model(model)

    async def _get_healthy_adapter(self, provider_id: str) -> AIProviderAdapter:
        """获取健康的适配器实例（检查熔断器状态）"""
        if self._circuit_breaker.is_open(provider_id):
            # 尝试找备用提供商
            for config in self._pm.get_enabled_providers():
                if (
                    config.provider_id != provider_id
                    and not self._circuit_breaker.is_open(config.provider_id)
                ):
                    logger.warning(
                        "failover_to_provider",
                        from_provider=provider_id,
                        to_provider=config.provider_id,
                    )
                    return await self._pm.get_adapter(config.provider_id)
            raise RuntimeError(
                f"Circuit breaker open for '{provider_id}' and no healthy fallback"
            )
        return await self._pm.get_adapter(provider_id)

    # ── 健康检查 ──────────────────────────────

    def get_health_status(self) -> dict[str, Any]:
        """获取 AI 服务健康状态"""
        providers = {}
        for config in self._pm.get_enabled_providers():
            providers[config.provider_id] = {
                "enabled": config.enabled,
                "circuit_breaker_open": self._circuit_breaker.is_open(
                    config.provider_id
                ),
                "default_model": config.default_model,
            }
        return {
            "providers": providers,
            "max_retries": self._max_retries,
        }
