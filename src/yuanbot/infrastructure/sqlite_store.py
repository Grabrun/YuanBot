"""SQLite 异步存储实现

使用 aiosqlite 实现事实记忆、情景记忆元数据、用户画像、情感记录、身份映射的持久化存储。
支持 WAL 模式提升并发性能。
"""

from __future__ import annotations

import contextlib
import json
import time
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# 建表 SQL
_CREATE_TABLES = [
    """CREATE TABLE IF NOT EXISTS fact_memories (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        category TEXT NOT NULL,
        key TEXT NOT NULL,
        value TEXT NOT NULL,
        confidence REAL DEFAULT 1.0,
        source TEXT,
        importance REAL DEFAULT 0.5,
        first_mentioned_at REAL,
        last_updated_at REAL,
        access_count INTEGER DEFAULT 0,
        is_deleted INTEGER DEFAULT 0,
        metadata TEXT DEFAULT '{}'
    )""",
    """CREATE TABLE IF NOT EXISTS episodic_metadata (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        date TEXT NOT NULL,
        time_of_day TEXT,
        topic TEXT,
        summary TEXT,
        emotional_tone TEXT,
        emotional_intensity REAL DEFAULT 0.5,
        key_entities TEXT DEFAULT '[]',
        user_state TEXT,
        ai_response_style TEXT,
        importance REAL DEFAULT 0.5,
        access_count INTEGER DEFAULT 0,
        created_at REAL,
        last_accessed_at REAL
    )""",
    """CREATE TABLE IF NOT EXISTS user_profiles (
        user_id TEXT PRIMARY KEY,
        display_name TEXT,
        preferences TEXT DEFAULT '{}',
        relationship_stage TEXT DEFAULT 'initial',
        trust_score REAL DEFAULT 0.0,
        total_interactions INTEGER DEFAULT 0,
        first_interaction REAL,
        last_interaction REAL,
        typical_mood_patterns TEXT DEFAULT '{}',
        platform_ids TEXT DEFAULT '{}',
        metadata TEXT DEFAULT '{}'
    )""",
    """CREATE TABLE IF NOT EXISTS emotion_records (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        timestamp REAL,
        emotion TEXT NOT NULL,
        intensity REAL DEFAULT 0.5,
        valence TEXT DEFAULT 'neutral',
        arousal TEXT DEFAULT 'medium',
        dominance TEXT DEFAULT 'medium',
        needs_immediate_comfort INTEGER DEFAULT 0,
        confidence REAL DEFAULT 0.8,
        trigger_text TEXT,
        context_summary TEXT,
        analysis_method TEXT DEFAULT 'rule_based',
        raw_scores TEXT DEFAULT '{}'
    )""",
    """CREATE TABLE IF NOT EXISTS identity_mappings (
        platform TEXT NOT NULL,
        platform_user_id TEXT NOT NULL,
        yuanbot_user_id TEXT NOT NULL,
        created_at REAL,
        metadata TEXT DEFAULT '{}',
        PRIMARY KEY (platform, platform_user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS user_proactive_settings (
        user_id TEXT PRIMARY KEY,
        proactive_greeting_enabled INTEGER DEFAULT 1,
        proactive_frequency TEXT DEFAULT 'medium',
        quiet_hours TEXT DEFAULT '["23:00-07:00"]',
        max_proactive_per_day INTEGER DEFAULT 5,
        event_trigger_enabled INTEGER DEFAULT 1,
        custom_wake_up_time TEXT,
        custom_sleep_time TEXT,
        important_dates TEXT DEFAULT '[]',
        updated_at REAL
    )""",
]

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_fact_memories_user ON fact_memories(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_fact_memories_category ON fact_memories(category)",
    # Composite index: most queries filter by (user_id, is_deleted)
    (
        "CREATE INDEX IF NOT EXISTS idx_fact_user_deleted"
        " ON fact_memories(user_id, is_deleted)"
    ),
    "CREATE INDEX IF NOT EXISTS idx_episodic_user ON episodic_metadata(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_episodic_date ON episodic_metadata(date)",
    # Composite index: get_episodic_metadata filters by (user_id, date)
    "CREATE INDEX IF NOT EXISTS idx_episodic_user_date ON episodic_metadata(user_id, date)",
    "CREATE INDEX IF NOT EXISTS idx_emotion_user ON emotion_records(user_id)",
    # Composite index: emotion trend queries filter by (user_id, timestamp)
    "CREATE INDEX IF NOT EXISTS idx_emotion_user_ts ON emotion_records(user_id, timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_identity_yuanbot ON identity_mappings(yuanbot_user_id)",
]


class SQLiteStore:
    """SQLite 异步存储

    使用 aiosqlite 实现所有持久化操作，启用 WAL 模式提升并发性能。
    """

    def __init__(self, db_path: str = "data/yuanbot.db"):
        self._db_path = db_path
        self._db: Any = None  # aiosqlite.Connection
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    async def initialize(self) -> None:
        """初始化数据库连接并创建表"""
        if self._initialized:
            return

        try:
            import aiosqlite
        except ImportError:
            raise ImportError(
                "aiosqlite is required for SQLiteStore. Install it with: pip install aiosqlite"
            ) from None

        # 确保目录存在
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

        self._db = await aiosqlite.connect(self._db_path)

        # 启用 WAL 模式
        await self._db.execute("PRAGMA journal_mode=WAL")
        # 启用外键约束
        await self._db.execute("PRAGMA foreign_keys=ON")

        # 创建表
        for sql in _CREATE_TABLES:
            await self._db.execute(sql)

        # 创建索引
        for sql in _CREATE_INDEXES:
            await self._db.execute(sql)

        await self._db.commit()
        self._initialized = True
        logger.info("sqlite_store_initialized", db_path=self._db_path)

    async def close(self) -> None:
        """关闭数据库连接"""
        if self._db:
            await self._db.close()
            self._db = None
        self._initialized = False
        logger.info("sqlite_store_closed")

    # ──────────────────────────────────────────
    # 事实记忆操作
    # ──────────────────────────────────────────

    async def save_fact_memory(
        self,
        *,
        id: str,
        user_id: str,
        category: str,
        key: str,
        value: str,
        confidence: float = 1.0,
        source: str | None = None,
        importance: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """保存或更新事实记忆"""
        now = time.time()
        await self._db.execute(
            """INSERT INTO fact_memories
               (id, user_id, category, key, value, confidence, source,
                importance, first_mentioned_at, last_updated_at, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                value=excluded.value,
                confidence=excluded.confidence,
                importance=excluded.importance,
                last_updated_at=excluded.last_updated_at,
                access_count=access_count + 1,
                metadata=excluded.metadata""",
            (
                id,
                user_id,
                category,
                key,
                value,
                confidence,
                source,
                importance,
                now,
                now,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        await self._db.commit()

    async def get_fact_memories(
        self,
        user_id: str,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """获取用户的事实记忆"""
        if category:
            cursor = await self._db.execute(
                "SELECT * FROM fact_memories WHERE user_id=? AND category=? AND is_deleted=0",
                (user_id, category),
            )
        else:
            cursor = await self._db.execute(
                "SELECT * FROM fact_memories WHERE user_id=? AND is_deleted=0",
                (user_id,),
            )
        rows = await cursor.fetchall()
        return self._rows_to_dicts(rows, cursor)

    async def find_facts_by_keys(
        self,
        user_id: str,
        keys: list[str],
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """通过 key 列匹配多个实体键，筛选事实记忆

        用于冲突检测：先用 DB 级 LIKE 过滤，再在内存中做精确交集检查。
        """
        if not keys:
            return []
        # OR 条件：key 匹配任一实体
        conditions = ["user_id=?", "is_deleted=0"]
        params: list[Any] = [user_id]
        if category:
            conditions.append("category=?")
            params.append(category)
        # 对每个 key 做精确匹配（不使用 LIKE 以利用索引）
        key_conds = ["key=?" for _ in keys]
        conditions.append(f"({' OR '.join(key_conds)})")
        params.extend(keys)
        where = " AND ".join(conditions)
        cursor = await self._db.execute(
            f"SELECT * FROM fact_memories WHERE {where}", params,
        )
        rows = await cursor.fetchall()
        return self._rows_to_dicts(rows, cursor)

    async def delete_fact_memory(self, id: str) -> None:
        """软删除事实记忆"""
        await self._db.execute("UPDATE fact_memories SET is_deleted=1 WHERE id=?", (id,))
        await self._db.commit()

    async def get_fact_memories_by_categories(
        self,
        user_id: str,
        categories: list[str],
    ) -> list[dict[str, Any]]:
        """获取用户指定多个类别的事实记忆（单次查询）"""
        if not categories:
            return []
        placeholders = ", ".join("?" for _ in categories)
        cursor = await self._db.execute(
            f"SELECT * FROM fact_memories WHERE user_id=? AND category IN ({placeholders}) "
            f"AND is_deleted=0",
            [user_id, *categories],
        )
        rows = await cursor.fetchall()
        return self._rows_to_dicts(rows, cursor)

    async def get_memory_counts(self, user_id: str) -> dict[str, int]:
        """获取用户各类记忆数量（单次查询，避免多次 DB 往返）"""
        cursor = await self._db.execute(
            "SELECT "
            "(SELECT COUNT(*) FROM fact_memories "
            "WHERE user_id=? AND (is_deleted=0 OR is_deleted IS NULL)) AS fact, "
            "(SELECT COUNT(*) FROM episodic_metadata WHERE user_id=?) AS episodic",
            (user_id, user_id),
        )
        row = await cursor.fetchone()
        return {"fact": row[0], "episodic": row[1], "semantic": 0}

    # ──────────────────────────────────────────
    # 情景记忆元数据操作
    # ──────────────────────────────────────────

    async def save_episodic_metadata(
        self,
        *,
        id: str,
        user_id: str,
        session_id: str,
        date: str,
        time_of_day: str | None = None,
        topic: str | None = None,
        summary: str | None = None,
        emotional_tone: str | None = None,
        emotional_intensity: float = 0.5,
        key_entities: list[str] | None = None,
        user_state: str | None = None,
        ai_response_style: str | None = None,
        importance: float = 0.5,
    ) -> None:
        """保存情景记忆元数据"""
        now = time.time()
        await self._db.execute(
            """INSERT INTO episodic_metadata
               (id, user_id, session_id, date, time_of_day, topic, summary,
                emotional_tone, emotional_intensity, key_entities,
                user_state, ai_response_style, importance,
                created_at, last_accessed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                id,
                user_id,
                session_id,
                date,
                time_of_day,
                topic,
                summary,
                emotional_tone,
                emotional_intensity,
                json.dumps(key_entities or [], ensure_ascii=False),
                user_state,
                ai_response_style,
                importance,
                now,
                now,
            ),
        )
        await self._db.commit()

    async def get_episodic_metadata(
        self,
        user_id: str,
        date_from: str | None = None,
        date_to: str | None = None,
        topic: str | None = None,
    ) -> list[dict[str, Any]]:
        """获取情景记忆元数据"""
        conditions = ["user_id=?"]
        params: list[Any] = [user_id]

        if date_from:
            conditions.append("date>=?")
            params.append(date_from)
        if date_to:
            conditions.append("date<=?")
            params.append(date_to)
        if topic:
            conditions.append("topic LIKE ?")
            params.append(f"%{topic}%")

        where = " AND ".join(conditions)
        cursor = await self._db.execute(
            f"SELECT * FROM episodic_metadata WHERE {where} ORDER BY created_at DESC",
            params,
        )
        rows = await cursor.fetchall()
        return self._rows_to_dicts(rows, cursor)

    async def update_episodic_access(self, id: str) -> None:
        """更新情景记忆的访问信息"""
        now = time.time()
        await self._db.execute(
            "UPDATE episodic_metadata SET access_count=access_count+1, "
            "last_accessed_at=? WHERE id=?",
            (now, id),
        )
        await self._db.commit()

    async def batch_update_episodic_access(self, ids: list[str]) -> None:
        """批量更新情景记忆的访问信息（单次提交，减少 I/O）"""
        if not ids:
            return
        now = time.time()
        await self._db.executemany(
            "UPDATE episodic_metadata SET access_count=access_count+1, "
            "last_accessed_at=? WHERE id=?",
            [(now, id) for id in ids],
        )
        await self._db.commit()

    async def delete_episodic_metadata(self, id: str) -> None:
        """删除情景记忆元数据"""
        await self._db.execute("DELETE FROM episodic_metadata WHERE id=?", (id,))
        await self._db.commit()

    async def batch_delete_episodic_metadata(self, ids: list[str]) -> None:
        """批量删除情景记忆元数据（单次提交，减少 I/O）"""
        if not ids:
            return
        await self._db.executemany(
            "DELETE FROM episodic_metadata WHERE id=?",
            [(id,) for id in ids],
        )
        await self._db.commit()

    # ──────────────────────────────────────────
    # 用户画像操作
    # ──────────────────────────────────────────

    async def save_user_profile(
        self,
        *,
        user_id: str,
        display_name: str | None = None,
        preferences: dict[str, Any] | None = None,
        relationship_stage: str = "initial",
        trust_score: float = 0.0,
        total_interactions: int = 0,
        first_interaction: float | None = None,
        last_interaction: float | None = None,
        typical_mood_patterns: dict[str, Any] | None = None,
        platform_ids: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """保存或更新用户画像"""
        await self._db.execute(
            """INSERT INTO user_profiles
               (user_id, display_name, preferences, relationship_stage,
                trust_score, total_interactions, first_interaction,
                last_interaction, typical_mood_patterns, platform_ids, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                display_name=excluded.display_name,
                preferences=excluded.preferences,
                relationship_stage=excluded.relationship_stage,
                trust_score=excluded.trust_score,
                total_interactions=excluded.total_interactions,
                last_interaction=excluded.last_interaction,
                typical_mood_patterns=excluded.typical_mood_patterns,
                platform_ids=excluded.platform_ids,
                metadata=excluded.metadata""",
            (
                user_id,
                display_name,
                json.dumps(preferences or {}, ensure_ascii=False),
                relationship_stage,
                trust_score,
                total_interactions,
                first_interaction,
                last_interaction,
                json.dumps(typical_mood_patterns or {}, ensure_ascii=False),
                json.dumps(platform_ids or {}, ensure_ascii=False),
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        await self._db.commit()

    async def get_user_profile(self, user_id: str) -> dict[str, Any] | None:
        """获取用户画像"""
        cursor = await self._db.execute("SELECT * FROM user_profiles WHERE user_id=?", (user_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_dict(row, cursor)

    async def touch_user_profile(self, user_id: str) -> dict[str, Any] | None:
        """原子更新交互计数并返回用户画像

        将 SELECT + UPDATE 合并为单条 SQL，减少 DB 往返。
        仅在画像已存在时更新；不存在时返回 None（由调用方创建新画像）。
        """
        now = time.time()
        cursor = await self._db.execute(
            """UPDATE user_profiles
               SET last_interaction = ?, total_interactions = total_interactions + 1
               WHERE user_id = ?
               RETURNING *""",
            (now, user_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        await self._db.commit()
        return self._row_to_dict(row, cursor)

    # ──────────────────────────────────────────
    # 情感记录操作
    # ──────────────────────────────────────────

    async def save_emotion_record(
        self,
        *,
        id: str,
        user_id: str,
        session_id: str,
        emotion: str,
        intensity: float = 0.5,
        valence: str = "neutral",
        arousal: str = "medium",
        dominance: str = "medium",
        needs_immediate_comfort: bool = False,
        confidence: float = 0.8,
        trigger_text: str,
        context_summary: str | None = None,
        analysis_method: str = "rule_based",
        raw_scores: dict[str, float] | None = None,
    ) -> None:
        """保存情感记录"""
        now = time.time()
        await self._db.execute(
            """INSERT INTO emotion_records
               (id, user_id, session_id, timestamp, emotion, intensity,
                valence, arousal, dominance, needs_immediate_comfort,
                confidence, trigger_text, context_summary,
                analysis_method, raw_scores)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                id,
                user_id,
                session_id,
                now,
                emotion,
                intensity,
                valence,
                arousal,
                dominance,
                1 if needs_immediate_comfort else 0,
                confidence,
                trigger_text,
                context_summary,
                analysis_method,
                json.dumps(raw_scores or {}, ensure_ascii=False),
            ),
        )
        await self._db.commit()

    async def get_emotion_records(
        self,
        user_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """获取情感记录"""
        cursor = await self._db.execute(
            "SELECT * FROM emotion_records WHERE user_id=? ORDER BY timestamp DESC LIMIT ?",
            (user_id, limit),
        )
        rows = await cursor.fetchall()
        return self._rows_to_dicts(rows, cursor)

    # ──────────────────────────────────────────
    # 身份映射操作
    # ──────────────────────────────────────────

    async def save_identity_mapping(
        self,
        *,
        platform: str,
        platform_user_id: str,
        yuanbot_user_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """保存身份映射"""
        now = time.time()
        await self._db.execute(
            """INSERT INTO identity_mappings
               (platform, platform_user_id, yuanbot_user_id, created_at, metadata)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(platform, platform_user_id) DO UPDATE SET
                yuanbot_user_id=excluded.yuanbot_user_id,
                metadata=excluded.metadata""",
            (
                platform,
                platform_user_id,
                yuanbot_user_id,
                now,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        await self._db.commit()

    async def get_yuanbot_user_id(
        self,
        platform: str,
        platform_user_id: str,
    ) -> str | None:
        """根据平台用户 ID 获取 YuanBot 用户 ID"""
        cursor = await self._db.execute(
            "SELECT yuanbot_user_id FROM identity_mappings WHERE platform=? AND platform_user_id=?",
            (platform, platform_user_id),
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def get_platforms_for_user(
        self,
        yuanbot_user_id: str,
    ) -> list[tuple[str, str]]:
        """获取统一用户 ID 关联的所有平台账号"""
        cursor = await self._db.execute(
            "SELECT platform, platform_user_id FROM identity_mappings WHERE yuanbot_user_id=?",
            (yuanbot_user_id,),
        )
        return [(row[0], row[1]) for row in await cursor.fetchall()]

    async def get_all_identity_mappings(
        self,
    ) -> list[dict[str, Any]]:
        """获取所有身份映射（调试/管理用）"""
        cursor = await self._db.execute(
            "SELECT platform, platform_user_id, yuanbot_user_id, created_at FROM identity_mappings"
        )
        rows = await cursor.fetchall()
        return self._rows_to_dicts(rows, cursor)

    # ──────────────────────────────────────────
    # 主动交互配置操作
    # ──────────────────────────────────────────

    async def get_user_proactive_settings(
        self,
        user_id: str,
    ) -> dict[str, Any] | None:
        """获取用户的主动交互配置"""
        cursor = await self._db.execute(
            "SELECT * FROM user_proactive_settings WHERE user_id=?",
            (user_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None

        result = self._row_to_dict(row, cursor)
        # 解析 JSON 字段
        for field_name in ("quiet_hours", "important_dates"):
            if field_name in result and isinstance(result[field_name], str):
                with contextlib.suppress(json.JSONDecodeError, TypeError):
                    result[field_name] = json.loads(result[field_name])
        # 转换布尔字段
        for field_name in ("proactive_greeting_enabled", "event_trigger_enabled"):
            if field_name in result:
                result[field_name] = bool(result[field_name])
        return result

    async def save_user_proactive_settings(
        self,
        user_id: str,
        settings: dict[str, Any],
    ) -> None:
        """保存用户的主动交互配置（upsert）"""
        now = time.time()
        await self._db.execute(
            """INSERT INTO user_proactive_settings
            (user_id, proactive_greeting_enabled, proactive_frequency,
             quiet_hours, max_proactive_per_day, event_trigger_enabled,
             custom_wake_up_time, custom_sleep_time, important_dates, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                proactive_greeting_enabled=excluded.proactive_greeting_enabled,
                proactive_frequency=excluded.proactive_frequency,
                quiet_hours=excluded.quiet_hours,
                max_proactive_per_day=excluded.max_proactive_per_day,
                event_trigger_enabled=excluded.event_trigger_enabled,
                custom_wake_up_time=excluded.custom_wake_up_time,
                custom_sleep_time=excluded.custom_sleep_time,
                important_dates=excluded.important_dates,
                updated_at=excluded.updated_at""",
            (
                user_id,
                int(settings.get("proactive_greeting_enabled", True)),
                settings.get("proactive_frequency", "medium"),
                json.dumps(settings.get("quiet_hours", ["23:00-07:00"]), ensure_ascii=False),
                settings.get("max_proactive_per_day", 5),
                int(settings.get("event_trigger_enabled", True)),
                settings.get("custom_wake_up_time"),
                settings.get("custom_sleep_time"),
                json.dumps(settings.get("important_dates", []), ensure_ascii=False),
                now,
            ),
        )
        await self._db.commit()

    # ──────────────────────────────────────────
    # 辅助方法
    # ──────────────────────────────────────────

    @staticmethod
    def _row_to_dict(row: Any, cursor: Any) -> dict[str, Any]:
        """将数据库行转换为字典"""
        if cursor.description:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row, strict=False))
        return {}

    @staticmethod
    def _rows_to_dicts(rows: list[Any], cursor: Any) -> list[dict[str, Any]]:
        """批量将数据库行转换为字典（列名只计算一次）"""
        if not rows or not cursor.description:
            return []
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row, strict=False)) for row in rows]
