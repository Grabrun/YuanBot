"""身份链接服务

维护 platform + platform_user_id → yuanbot_user_id 的映射，
支持跨平台身份关联。
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class IdentityService:
    """身份链接服务

    职责：
    1. 将 (platform, platform_user_id) 映射为统一的 yuanbot_user_id
    2. 支持跨平台身份关联（如绑定 Telegram 和 Discord 为同一用户）
    3. 首次交互时自动创建映射
    """

    def __init__(self) -> None:
        # (platform, platform_user_id) → yuanbot_user_id
        self._identity_map: dict[tuple[str, str], str] = {}
        # yuanbot_user_id → set of (platform, platform_user_id)
        self._reverse_map: dict[str, set[tuple[str, str]]] = {}

    def resolve_user_id(
        self,
        platform: str,
        platform_user_id: str,
    ) -> str:
        """解析平台用户 ID 为统一用户 ID

        如果是首次交互，自动创建新的映射。
        """
        key = (platform, platform_user_id)
        if key not in self._identity_map:
            yuanbot_user_id = f"yb_{uuid.uuid4().hex[:12]}"
            self._identity_map[key] = yuanbot_user_id
            self._reverse_map.setdefault(yuanbot_user_id, set()).add(key)
            logger.info(
                "identity_created",
                platform=platform,
                platform_user_id=platform_user_id,
                yuanbot_user_id=yuanbot_user_id,
            )
        return self._identity_map[key]

    def build_session_id(
        self,
        platform: str,
        platform_user_id: str,
    ) -> str:
        """构建会话 ID"""
        return f"{platform}:{platform_user_id}"

    def link_accounts(
        self,
        primary_yuanbot_id: str,
        platform: str,
        platform_user_id: str,
    ) -> bool:
        """将新的平台账号关联到已有的统一用户 ID

        Returns:
            True if linked successfully, False if primary_id not found.
        """
        if primary_yuanbot_id not in self._reverse_map:
            return False

        key = (platform, platform_user_id)
        old_yuanbot_id = self._identity_map.get(key)

        # 如果该平台账号已关联到其他用户，先解除
        if old_yuanbot_id and old_yuanbot_id != primary_yuanbot_id:
            self._reverse_map.get(old_yuanbot_id, set()).discard(key)

        self._identity_map[key] = primary_yuanbot_id
        self._reverse_map[primary_yuanbot_id].add(key)

        logger.info(
            "identity_linked",
            primary_id=primary_yuanbot_id,
            platform=platform,
            platform_user_id=platform_user_id,
        )
        return True

    def get_linked_platforms(self, yuanbot_user_id: str) -> list[dict[str, str]]:
        """获取用户关联的所有平台账号"""
        keys = self._reverse_map.get(yuanbot_user_id, set())
        return [{"platform": platform, "platform_user_id": pid} for platform, pid in keys]

    def get_all_identities(self) -> dict[str, Any]:
        """获取所有身份映射（用于调试和管理）"""
        return {
            "total_mappings": len(self._identity_map),
            "total_users": len(self._reverse_map),
        }
