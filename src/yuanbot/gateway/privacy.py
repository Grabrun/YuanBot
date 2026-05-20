"""隐私模式与数据管理

实现隐私保护相关功能：
1. 隐私模式：会话不进入长期记忆
2. 数据导出：用户可导出所有个人数据（GDPR 合规）
3. 数据删除：用户可一键删除所有个人数据

设计参考: architecture-v1.4.md 10.4 安全与隐私设计
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class PrivacyManager:
    """隐私管理器

    职责：
    1. 管理隐私模式会话（不记录长期记忆）
    2. 提供数据导出功能（JSON 格式）
    3. 提供数据删除功能（一键清除）

    设计参考: architecture-v1.4.md 10.4
    """

    def __init__(self, memory_manager: Any = None, db_manager: Any = None):
        self._memory = memory_manager
        self._db = db_manager
        self._private_sessions: set[str] = set()  # 隐私模式会话 ID 集合

    # ── 隐私模式 ──────────────────────────────

    def enable_private_session(self, session_id: str) -> None:
        """启用隐私模式：该会话的对话不会进入长期记忆"""
        self._private_sessions.add(session_id)
        logger.info("private_session_enabled", session_id=session_id)

    def disable_private_session(self, session_id: str) -> None:
        """禁用隐私模式"""
        self._private_sessions.discard(session_id)
        logger.info("private_session_disabled", session_id=session_id)

    def is_private_session(self, session_id: str) -> bool:
        """检查会话是否为隐私模式"""
        return session_id in self._private_sessions

    def should_record_memory(self, session_id: str) -> bool:
        """判断是否应该记录记忆

        隐私模式下，工作记忆仍然保留（用于当次对话），
        但不会归档到情景记忆或事实记忆。
        """
        return not self.is_private_session(session_id)

    # ── 数据导出 ──────────────────────────────

    async def export_user_data(self, user_id: str) -> dict[str, Any]:
        """导出用户所有个人数据

        符合 GDPR 数据可携带权要求，导出格式为 JSON。

        导出内容：
        - 用户画像
        - 事实记忆
        - 情景记忆
        - 情感记录
        - 主动交互配置

        Args:
            user_id: 用户 ID

        Returns:
            包含所有用户数据的字典
        """
        export: dict[str, Any] = {
            "user_id": user_id,
            "exported_at": datetime.now().isoformat(),
            "version": "1.0",
        }

        if not self._memory:
            export["error"] = "Memory manager not available"
            return export

        try:
            # 用户画像
            profile = await self._memory.get_or_create_user_profile(user_id)
            export["profile"] = {
                "display_name": profile.display_name,
                "relationship_stage": profile.relationship_stage,
                "trust_score": profile.trust_score,
                "total_interactions": profile.total_interactions,
                "first_interaction": profile.first_interaction.isoformat()
                if profile.first_interaction
                else None,
                "last_interaction": profile.last_interaction.isoformat()
                if profile.last_interaction
                else None,
                "preferences": profile.preferences,
                "platform_ids": profile.platform_ids,
                "typical_mood_patterns": profile.typical_mood_patterns,
            }

            # 事实记忆
            facts = await self._memory.get_fact_memories(user_id)
            export["fact_memories"] = [
                {
                    "id": f.id,
                    "content": f.content,
                    "importance": f.importance_score,
                    "created_at": f.created_at.isoformat(),
                    "metadata": f.metadata,
                }
                for f in facts
            ]

            # 情景记忆
            episodic = await self._memory.get_episodic_memories(user_id)
            export["episodic_memories"] = [
                {
                    "id": e.id,
                    "summary": e.summary,
                    "content": e.content,
                    "emotional_tone": e.emotional_tone,
                    "created_at": e.created_at.isoformat(),
                    "topic_tags": e.topic_tags,
                    "key_entities": e.key_entities,
                }
                for e in episodic
            ]

            # 语义记忆
            semantic = await self._memory.get_semantic_memories(user_id)
            export["semantic_memories"] = [
                {
                    "id": s.id,
                    "content": s.content,
                    "relation_type": s.metadata.get("relation_type"),
                    "importance": s.importance_score,
                }
                for s in semantic
            ]

            # 情感趋势
            emotion_trend = await self._memory.get_emotion_trend(user_id, days=365)
            if emotion_trend:
                export["emotion_trend"] = {
                    "dominant_emotion": emotion_trend.dominant_emotion.value
                    if hasattr(emotion_trend.dominant_emotion, "value")
                    else str(emotion_trend.dominant_emotion),
                    "mood_stability": emotion_trend.mood_stability,
                    "emotional_variety": emotion_trend.emotional_variety,
                }

            # 主动交互配置
            if hasattr(self._memory, "get_user_proactive_settings"):
                proactive_settings = await self._memory.get_user_proactive_settings(user_id)
                export["proactive_settings"] = proactive_settings

            logger.info("user_data_exported", user_id=user_id)
            return export

        except Exception as e:
            logger.error("data_export_failed", user_id=user_id, error=str(e))
            export["error"] = str(e)
            return export

    # ── 数据删除 ──────────────────────────────

    async def delete_user_data(self, user_id: str) -> dict[str, Any]:
        """删除用户所有个人数据

        符合 GDPR 被遗忘权要求。

        删除内容：
        - 用户画像
        - 事实记忆
        - 情景记忆（元数据 + 向量）
        - 语义记忆
        - 情感记录
        - 主动交互配置

        Args:
            user_id: 用户 ID

        Returns:
            删除结果摘要
        """
        result: dict[str, Any] = {
            "user_id": user_id,
            "deleted_at": datetime.now().isoformat(),
            "items_deleted": {},
        }

        if not self._memory:
            result["error"] = "Memory manager not available"
            return result

        try:
            # 删除事实记忆
            facts = await self._memory.get_fact_memories(user_id)
            for f in facts:
                if self._db and hasattr(self._db, "sqlite"):
                    await self._db.sqlite.delete_fact_memory(f.id)
            result["items_deleted"]["fact_memories"] = len(facts)

            # 删除情景记忆
            episodic = await self._memory.get_episodic_memories(user_id)
            for e in episodic:
                if self._db and hasattr(self._db, "sqlite"):
                    await self._db.sqlite.delete_episodic_metadata(e.id)
                if self._db and hasattr(self._db, "vector"):
                    try:
                        await self._db.vector.delete_vector(e.id)
                    except Exception:
                        pass
            result["items_deleted"]["episodic_memories"] = len(episodic)

            # 删除语义记忆（从事实记忆表中的 semantic category）
            semantic = await self._memory.get_semantic_memories(user_id)
            for s in semantic:
                if self._db and hasattr(self._db, "sqlite"):
                    await self._db.sqlite.delete_fact_memory(s.id)
            result["items_deleted"]["semantic_memories"] = len(semantic)

            # 删除用户画像
            if self._db and hasattr(self._db, "sqlite"):
                try:
                    await self._db.sqlite.delete_user_profile(user_id)
                except Exception:
                    pass
            result["items_deleted"]["user_profile"] = 1

            # 清除内存缓存
            self._memory._fact_memories.pop(user_id, None)
            self._memory._episodic_memories.pop(user_id, None)
            self._memory._semantic_memories.pop(user_id, None)
            self._memory._user_profiles.pop(user_id, None)

            logger.info("user_data_deleted", user_id=user_id)
            return result

        except Exception as e:
            logger.error("data_deletion_failed", user_id=user_id, error=str(e))
            result["error"] = str(e)
            return result

    def export_to_json(self, data: dict[str, Any], file_path: str) -> None:
        """将导出数据写入 JSON 文件"""
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("data_exported_to_file", path=file_path)
