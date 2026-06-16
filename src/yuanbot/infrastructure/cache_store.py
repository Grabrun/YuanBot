"""缓存存储实现

支持 Redis（生产环境）和内存字典缓存（开发/本地环境）。
用于工作记忆缓存、主动交互锁等。
"""

from __future__ import annotations

import contextlib
import time
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class CacheStore:
    """缓存存储统一接口

    首选 Redis，回退到内存字典缓存。
    """

    def __init__(self, redis_url: str | None = None):
        # 自动检测 Redis URL: 显式参数 > 环境变量 > None（内存模式）
        if redis_url is None:
            import os

            redis_url = os.environ.get("YUAN_REDIS_URL") or os.environ.get("REDIS_URL")
        self._redis_url = redis_url
        self._redis: Any = None
        self._memory_cache: InMemoryCacheStore | None = None
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def backend(self) -> str:
        """当前使用的缓存后端"""
        if self._redis:
            return "redis"
        return "memory"

    async def initialize(self) -> None:
        """初始化缓存存储"""
        if self._initialized:
            return

        if self._redis_url:
            try:
                await self._init_redis()
                self._initialized = True
                logger.info("cache_store_initialized", backend="redis")
                return
            except Exception as e:
                logger.warning(
                    "redis_init_failed_fallback_memory",
                    error=str(e),
                )

        # 回退到内存缓存
        self._memory_cache = InMemoryCacheStore()
        self._initialized = True
        logger.info("cache_store_initialized", backend="memory")

    async def close(self) -> None:
        """关闭缓存存储"""
        if self._redis:
            with contextlib.suppress(Exception):
                await self._redis.close()
            self._redis = None
        self._memory_cache = None
        self._initialized = False
        logger.info("cache_store_closed")

    async def _init_redis(self) -> None:
        """初始化 Redis 连接"""
        try:
            import redis.asyncio as aioredis
        except ImportError:
            raise ImportError(
                "redis is required for Redis cache. Install it with: pip install redis"
            ) from None

        self._redis = aioredis.from_url(
            self._redis_url,
            decode_responses=True,
        )
        # 测试连接
        await self._redis.ping()

    # ──────────────────────────────────────────
    # 通用缓存操作
    # ──────────────────────────────────────────

    async def get(self, key: str) -> Any | None:
        """获取缓存值"""
        if not self._initialized:
            await self.initialize()

        if self._redis:
            return await self._get_redis(key)
        elif self._memory_cache:
            return self._memory_cache.get(key)
        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> None:
        """设置缓存值

        Args:
            key: 缓存键
            value: 缓存值（会被 JSON 序列化）
            ttl: 过期时间（秒），None 表示不过期
        """
        if not self._initialized:
            await self.initialize()

        if self._redis:
            await self._set_redis(key, value, ttl)
        elif self._memory_cache:
            self._memory_cache.set(key, value, ttl)

    async def delete(self, key: str) -> None:
        """删除缓存"""
        if not self._initialized:
            await self.initialize()

        if self._redis:
            await self._redis.delete(key)
        elif self._memory_cache:
            self._memory_cache.delete(key)

    async def exists(self, key: str) -> bool:
        """检查缓存是否存在"""
        if not self._initialized:
            await self.initialize()

        if self._redis:
            return bool(await self._redis.exists(key))
        elif self._memory_cache:
            return self._memory_cache.exists(key)
        return False

    async def keys(self, pattern: str = "*") -> list[str]:
        """获取匹配的键"""
        if not self._initialized:
            await self.initialize()

        if self._redis:
            return [k async for k in self._redis.scan_iter(match=pattern)]
        elif self._memory_cache:
            return self._memory_cache.keys(pattern)
        return []

    # ──────────────────────────────────────────
    # 工作记忆专用操作
    # ──────────────────────────────────────────

    async def get_working_memory(self, session_id: str) -> list[dict[str, Any]]:
        """获取工作记忆"""
        key = f"working_memory:{session_id}"
        data = await self.get(key)
        return data if isinstance(data, list) else []

    async def set_working_memory(
        self,
        session_id: str,
        memories: list[dict[str, Any]],
        ttl: int = 3600,
    ) -> None:
        """设置工作记忆"""
        key = f"working_memory:{session_id}"
        await self.set(key, memories, ttl=ttl)

    async def clear_working_memory(self, session_id: str) -> None:
        """清除工作记忆"""
        key = f"working_memory:{session_id}"
        await self.delete(key)

    # ──────────────────────────────────────────
    # 主动交互锁操作
    # ──────────────────────────────────────────

    async def acquire_interaction_lock(
        self,
        user_id: str,
        lock_type: str,
        ttl: int = 300,
    ) -> bool:
        """获取主动交互锁（防止重复触发）

        Args:
            user_id: 用户 ID
            lock_type: 锁类型（如 "greeting", "care"）
            ttl: 锁持续时间（秒）

        Returns:
            是否成功获取锁
        """
        key = f"interaction_lock:{user_id}:{lock_type}"
        if await self.exists(key):
            return False
        await self.set(key, "locked", ttl=ttl)
        return True

    async def release_interaction_lock(
        self,
        user_id: str,
        lock_type: str,
    ) -> None:
        """释放主动交互锁"""
        key = f"interaction_lock:{user_id}:{lock_type}"
        await self.delete(key)

    # ──────────────────────────────────────────
    # Redis 专用操作
    # ──────────────────────────────────────────

    async def _get_redis(self, key: str) -> Any | None:
        """从 Redis 获取值"""
        import json

        data = await self._redis.get(key)
        if data is None:
            return None
        try:
            return json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return data

    async def _set_redis(self, key: str, value: Any, ttl: int | None) -> None:
        """设置 Redis 值"""
        import json

        serialized = json.dumps(value, ensure_ascii=False, default=str)
        if ttl:
            await self._redis.setex(key, ttl, serialized)
        else:
            await self._redis.set(key, serialized)


class InMemoryCacheStore:
    """内存缓存存储（回退方案）

    使用字典实现，支持 TTL 过期。
    默认最大 1000 条，超出时按最后访问时间淘汰。
    """

    def __init__(self, max_entries: int = 1000):
        self._cache: dict[str, Any] = {}
        self._expires: dict[str, float] = {}  # key -> expiry timestamp
        self._access_order: list[str] = []  # LRU 顺序
        self._max_entries = max_entries

    def _cleanup_expired(self) -> None:
        """清理过期的缓存"""
        now = time.time()
        expired_keys = [k for k, exp in self._expires.items() if exp <= now]
        for key in expired_keys:
            self._cache.pop(key, None)
            self._expires.pop(key, None)
        if expired_keys:
            self._access_order = [k for k in self._access_order if k in self._cache]

    def _touch(self, key: str) -> None:
        """更新访问顺序（LRU）"""
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)

    def _evict(self) -> None:
        """淘汰最久未访问的条目"""
        while len(self._cache) > self._max_entries:
            # 淘汰最久未访问的（访问顺序列表最前面）
            oldest = self._access_order.pop(0) if self._access_order else None
            if oldest is None:
                break
            self._cache.pop(oldest, None)
            self._expires.pop(oldest, None)

    def get(self, key: str) -> Any | None:
        """获取缓存值"""
        self._cleanup_expired()
        if key in self._expires and self._expires[key] <= time.time():
            self._cache.pop(key, None)
            self._expires.pop(key, None)
            return None
        if key in self._cache:
            self._touch(key)
        return self._cache.get(key)

    def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> None:
        """设置缓存值"""
        self._cache[key] = value
        if ttl:
            self._expires[key] = time.time() + ttl
        else:
            self._expires.pop(key, None)
        self._touch(key)
        self._evict()

    def delete(self, key: str) -> None:
        """删除缓存"""
        self._cache.pop(key, None)
        self._expires.pop(key, None)
        if key in self._access_order:
            self._access_order.remove(key)

    def exists(self, key: str) -> bool:
        """检查是否存在"""
        self._cleanup_expired()
        return key in self._cache

    def keys(self, pattern: str = "*") -> list[str]:
        """获取匹配的键（简化实现，仅支持 * 通配符）"""
        self._cleanup_expired()
        if pattern == "*":
            return list(self._cache.keys())
        # 简化前缀/后缀匹配
        if "*" in pattern:
            prefix = pattern[: pattern.index("*")]
            suffix = pattern[pattern.index("*") + 1 :]
            return [
                k
                for k in self._cache
                if (not prefix or k.startswith(prefix)) and (not suffix or k.endswith(suffix))
            ]
        # 精确匹配
        return [k for k in self._cache if k == pattern]
