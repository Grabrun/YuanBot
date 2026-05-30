"""身份链接服务

维护 platform + platform_user_id → yuanbot_user_id 的映射，
支持跨平台身份关联。

支持 SQLite 持久化：传入 SQLiteStore 时，所有映射自动持久化到数据库，
同时保持内存缓存以提升查询性能。
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from yuanbot.infrastructure.sqlite_store import SQLiteStore

logger = structlog.get_logger(__name__)


class IdentityService:
    """身份链接服务

    职责：
    1. 将 (platform, platform_user_id) 映射为统一的 yuanbot_user_id
    2. 支持跨平台身份关联（如绑定 Telegram 和 Discord 为同一用户）
    3. 首次交互时自动创建映射
    4. 可选 SQLite 持久化，重启后数据不丢失
    """

    def __init__(self, store: SQLiteStore | None = None) -> None:
        self._store = store
        # (platform, platform_user_id) → yuanbot_user_id
        self._identity_map: dict[tuple[str, str], str] = {}
        # yuanbot_user_id → set of (platform, platform_user_id)
        self._reverse_map: dict[str, set[tuple[str, str]]] = {}
        self._loaded = False

    async def _ensure_loaded(self) -> None:
        """从数据库加载所有身份映射到内存（懒加载，仅执行一次）"""
        if self._loaded or self._store is None:
            self._loaded = True
            return
        try:
            mappings = await self._store.get_all_identity_mappings()
            for m in mappings:
                key = (m["platform"], m["platform_user_id"])
                uid = m["yuanbot_user_id"]
                self._identity_map[key] = uid
                self._reverse_map.setdefault(uid, set()).add(key)
            if mappings:
                logger.info(
                    "identity_loaded_from_db",
                    count=len(mappings),
                    users=len(self._reverse_map),
                )
        except Exception as exc:
            logger.warning("identity_load_failed", error=str(exc))
        finally:
            self._loaded = True

    async def resolve_user_id(
        self,
        platform: str,
        platform_user_id: str,
    ) -> str:
        """解析平台用户 ID 为统一用户 ID

        如果是首次交互，自动创建新的映射。
        优先查内存缓存 → 数据库 → 新建。
        """
        await self._ensure_loaded()

        key = (platform, platform_user_id)
        # 1. 内存缓存命中
        if key in self._identity_map:
            return self._identity_map[key]

        # 2. 数据库命中
        if self._store is not None:
            try:
                db_uid = await self._store.get_yuanbot_user_id(platform, platform_user_id)
                if db_uid:
                    self._identity_map[key] = db_uid
                    self._reverse_map.setdefault(db_uid, set()).add(key)
                    return db_uid
            except Exception as exc:
                logger.warning("identity_db_lookup_failed", error=str(exc))

        # 3. 新建映射
        yuanbot_user_id = f"yb_{uuid.uuid4().hex[:12]}"
        self._identity_map[key] = yuanbot_user_id
        self._reverse_map.setdefault(yuanbot_user_id, set()).add(key)

        # 持久化
        if self._store is not None:
            try:
                await self._store.save_identity_mapping(
                    platform=platform,
                    platform_user_id=platform_user_id,
                    yuanbot_user_id=yuanbot_user_id,
                )
            except Exception as exc:
                logger.warning("identity_save_failed", error=str(exc))

        logger.info(
            "identity_created",
            platform=platform,
            platform_user_id=platform_user_id,
            yuanbot_user_id=yuanbot_user_id,
        )
        return yuanbot_user_id

    def build_session_id(
        self,
        platform: str,
        platform_user_id: str,
    ) -> str:
        """构建会话 ID"""
        return f"{platform}:{platform_user_id}"

    async def link_accounts(
        self,
        primary_yuanbot_id: str,
        platform: str,
        platform_user_id: str,
    ) -> bool:
        """将新的平台账号关联到已有的统一用户 ID

        Returns:
            True if linked successfully, False if primary_id not found.
        """
        await self._ensure_loaded()

        if primary_yuanbot_id not in self._reverse_map:
            return False

        key = (platform, platform_user_id)
        old_yuanbot_id = self._identity_map.get(key)

        # 如果该平台账号已关联到其他用户，先解除
        if old_yuanbot_id and old_yuanbot_id != primary_yuanbot_id:
            self._reverse_map.get(old_yuanbot_id, set()).discard(key)

        self._identity_map[key] = primary_yuanbot_id
        self._reverse_map[primary_yuanbot_id].add(key)

        # 持久化
        if self._store is not None:
            try:
                await self._store.save_identity_mapping(
                    platform=platform,
                    platform_user_id=platform_user_id,
                    yuanbot_user_id=primary_yuanbot_id,
                )
            except Exception as exc:
                logger.warning("identity_link_save_failed", error=str(exc))

        logger.info(
            "identity_linked",
            primary_id=primary_yuanbot_id,
            platform=platform,
            platform_user_id=platform_user_id,
        )
        return True

    async def get_linked_platforms(self, yuanbot_user_id: str) -> list[dict[str, str]]:
        """获取用户关联的所有平台账号"""
        await self._ensure_loaded()

        # 优先从内存获取
        keys = self._reverse_map.get(yuanbot_user_id, set())
        if keys:
            return [{"platform": platform, "platform_user_id": pid} for platform, pid in keys]

        # 回退到数据库查询
        if self._store is not None:
            try:
                rows = await self._store.get_platforms_for_user(yuanbot_user_id)
                return [{"platform": p, "platform_user_id": pid} for p, pid in rows]
            except Exception as exc:
                logger.warning("identity_query_failed", error=str(exc))

        return []

    async def get_all_identities(self) -> dict[str, Any]:
        """获取所有身份映射（用于调试和管理）"""
        await self._ensure_loaded()
        return {
            "total_mappings": len(self._identity_map),
            "total_users": len(self._reverse_map),
            "persisted": self._store is not None,
        }
