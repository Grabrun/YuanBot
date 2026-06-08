"""MySQL 异步存储实现

使用 aiomysql 实现与 SQLiteStore 相同接口的 MySQL 存储。
支持连接池提升并发性能。
"""

from __future__ import annotations

import contextlib
import json
import time
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# 建表 SQL（MySQL 语法）
_CREATE_TABLES = [
    """CREATE TABLE IF NOT EXISTS fact_memories (
        id VARCHAR(255) PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        category VARCHAR(255) NOT NULL,
        `key` VARCHAR(255) NOT NULL,
        `value` TEXT NOT NULL,
        confidence DOUBLE DEFAULT 1.0,
        source VARCHAR(255),
        importance DOUBLE DEFAULT 0.5,
        first_mentioned_at DOUBLE,
        last_updated_at DOUBLE,
        access_count INT DEFAULT 0,
        is_deleted TINYINT DEFAULT 0,
        metadata TEXT DEFAULT '{}'
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS episodic_metadata (
        id VARCHAR(255) PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        session_id VARCHAR(255) NOT NULL,
        `date` VARCHAR(32) NOT NULL,
        time_of_day VARCHAR(32),
        topic VARCHAR(255),
        summary TEXT,
        emotional_tone VARCHAR(64),
        emotional_intensity DOUBLE DEFAULT 0.5,
        key_entities TEXT DEFAULT '[]',
        user_state VARCHAR(255),
        ai_response_style VARCHAR(255),
        importance DOUBLE DEFAULT 0.5,
        access_count INT DEFAULT 0,
        created_at DOUBLE,
        last_accessed_at DOUBLE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS user_profiles (
        user_id VARCHAR(255) PRIMARY KEY,
        display_name VARCHAR(255),
        preferences TEXT DEFAULT '{}',
        relationship_stage VARCHAR(64) DEFAULT 'initial',
        trust_score DOUBLE DEFAULT 0.0,
        total_interactions INT DEFAULT 0,
        first_interaction DOUBLE,
        last_interaction DOUBLE,
        typical_mood_patterns TEXT DEFAULT '{}',
        platform_ids TEXT DEFAULT '{}',
        metadata TEXT DEFAULT '{}'
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS emotion_records (
        id VARCHAR(255) PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        session_id VARCHAR(255) NOT NULL,
        timestamp DOUBLE,
        emotion VARCHAR(64) NOT NULL,
        intensity DOUBLE DEFAULT 0.5,
        valence VARCHAR(32) DEFAULT 'neutral',
        arousal VARCHAR(32) DEFAULT 'medium',
        dominance VARCHAR(32) DEFAULT 'medium',
        needs_immediate_comfort TINYINT DEFAULT 0,
        confidence DOUBLE DEFAULT 0.8,
        trigger_text TEXT,
        context_summary TEXT,
        analysis_method VARCHAR(64) DEFAULT 'rule_based',
        raw_scores TEXT DEFAULT '{}'
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS identity_mappings (
        platform VARCHAR(64) NOT NULL,
        platform_user_id VARCHAR(255) NOT NULL,
        yuanbot_user_id VARCHAR(255) NOT NULL,
        created_at DOUBLE,
        metadata TEXT DEFAULT '{}',
        PRIMARY KEY (platform, platform_user_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS user_proactive_settings (
        user_id VARCHAR(255) PRIMARY KEY,
        proactive_greeting_enabled TINYINT DEFAULT 1,
        proactive_frequency VARCHAR(32) DEFAULT 'medium',
        quiet_hours TEXT DEFAULT '["23:00-07:00"]',
        max_proactive_per_day INT DEFAULT 5,
        event_trigger_enabled TINYINT DEFAULT 1,
        custom_wake_up_time VARCHAR(32),
        custom_sleep_time VARCHAR(32),
        important_dates TEXT DEFAULT '[]',
        updated_at DOUBLE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
]

_CREATE_INDEXES = [
    "CREATE INDEX idx_fact_memories_user ON fact_memories(user_id(191))",
    "CREATE INDEX idx_fact_memories_category ON fact_memories(category(191))",
    "CREATE INDEX idx_episodic_user ON episodic_metadata(user_id(191))",
    "CREATE INDEX idx_episodic_date ON episodic_metadata(`date`(32))",
    "CREATE INDEX idx_emotion_user ON emotion_records(user_id(191))",
    "CREATE INDEX idx_identity_yuanbot ON identity_mappings(yuanbot_user_id(191))",
]


class MySQLStore:
    """MySQL 异步存储

    使用 aiomysql 实现所有持久化操作，使用连接池提升并发性能。
    接口与 SQLiteStore 完全一致。
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 3306,
        database: str = "yuanbot",
        user: str = "yuanbot",
        password: str = "",
        pool_size: int = 10,
    ):
        self._host = host
        self._port = port
        self._database = database
        self._user = user
        self._password = password
        self._pool_size = pool_size
        self._pool: Any = None  # aiomysql.Pool
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    async def initialize(self) -> None:
        """初始化数据库连接池并创建表"""
        if self._initialized:
            return

        try:
            import aiomysql
        except ImportError:
            raise ImportError(
                "aiomysql is required for MySQLStore. "
                "Install it with: pip install aiomysql"
            ) from None

        self._pool = await aiomysql.create_pool(
            host=self._host,
            port=self._port,
            db=self._database,
            user=self._user,
            password=self._password,
            minsize=1,
            maxsize=self._pool_size,
            charset="utf8mb4",
            autocommit=False,
        )

        async with self._pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # 创建表
                for sql in _CREATE_TABLES:
                    await cursor.execute(sql)

                # 创建索引（忽略已存在的索引）
                for sql in _CREATE_INDEXES:
                    with contextlib.suppress(Exception):  # 索引可能已存在
                        await cursor.execute(sql)

            await conn.commit()

        self._initialized = True
        logger.info(
            "mysql_store_initialized",
            host=self._host,
            port=self._port,
            database=self._database,
        )

    async def close(self) -> None:
        """关闭数据库连接池"""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None
        self._initialized = False
        logger.info("mysql_store_closed")

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
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """INSERT INTO fact_memories
                       (id, user_id, category, `key`, `value`, confidence, source,
                        importance, first_mentioned_at, last_updated_at, metadata)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON DUPLICATE KEY UPDATE
                        `value`=VALUES(`value`),
                        confidence=VALUES(confidence),
                        importance=VALUES(importance),
                        last_updated_at=VALUES(last_updated_at),
                        access_count=access_count + 1,
                        metadata=VALUES(metadata)""",
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
            await conn.commit()

    async def get_fact_memories(
        self,
        user_id: str,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """获取用户的事实记忆"""
        async with self._pool.acquire() as conn, conn.cursor() as cursor:
            if category:
                await cursor.execute(
                    "SELECT * FROM fact_memories"
                    " WHERE user_id=%s AND category=%s AND is_deleted=0",
                    (user_id, category),
                )
            else:
                await cursor.execute(
                    "SELECT * FROM fact_memories WHERE user_id=%s AND is_deleted=0",
                    (user_id,),
                )
            rows = await cursor.fetchall()
            return self._rows_to_dicts(rows, cursor)

    async def delete_fact_memory(self, id: str) -> None:
        """软删除事实记忆"""
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "UPDATE fact_memories SET is_deleted=1 WHERE id=%s", (id,)
                )
            await conn.commit()

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
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """INSERT INTO episodic_metadata
                       (id, user_id, session_id, `date`, time_of_day, topic, summary,
                        emotional_tone, emotional_intensity, key_entities,
                        user_state, ai_response_style, importance,
                        created_at, last_accessed_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
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
            await conn.commit()

    async def get_episodic_metadata(
        self,
        user_id: str,
        date_from: str | None = None,
        date_to: str | None = None,
        topic: str | None = None,
    ) -> list[dict[str, Any]]:
        """获取情景记忆元数据"""
        conditions = ["user_id=%s"]
        params: list[Any] = [user_id]

        if date_from:
            conditions.append("`date`>=%s")
            params.append(date_from)
        if date_to:
            conditions.append("`date`<=%s")
            params.append(date_to)
        if topic:
            conditions.append("topic LIKE %s")
            params.append(f"%{topic}%")

        where = " AND ".join(conditions)
        async with self._pool.acquire() as conn, conn.cursor() as cursor:
            await cursor.execute(
                f"SELECT * FROM episodic_metadata WHERE {where} ORDER BY created_at DESC",
                params,
            )
            rows = await cursor.fetchall()
            return self._rows_to_dicts(rows, cursor)

    async def update_episodic_access(self, id: str) -> None:
        """更新情景记忆的访问信息"""
        now = time.time()
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "UPDATE episodic_metadata SET access_count=access_count+1, "
                    "last_accessed_at=%s WHERE id=%s",
                    (now, id),
                )
            await conn.commit()

    async def delete_episodic_metadata(self, id: str) -> None:
        """删除情景记忆元数据"""
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "DELETE FROM episodic_metadata WHERE id=%s", (id,)
                )
            await conn.commit()

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
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """INSERT INTO user_profiles
                       (user_id, display_name, preferences, relationship_stage,
                        trust_score, total_interactions, first_interaction,
                        last_interaction, typical_mood_patterns, platform_ids, metadata)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON DUPLICATE KEY UPDATE
                        display_name=VALUES(display_name),
                        preferences=VALUES(preferences),
                        relationship_stage=VALUES(relationship_stage),
                        trust_score=VALUES(trust_score),
                        total_interactions=VALUES(total_interactions),
                        last_interaction=VALUES(last_interaction),
                        typical_mood_patterns=VALUES(typical_mood_patterns),
                        platform_ids=VALUES(platform_ids),
                        metadata=VALUES(metadata)""",
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
            await conn.commit()

    async def get_user_profile(self, user_id: str) -> dict[str, Any] | None:
        """获取用户画像"""
        async with self._pool.acquire() as conn, conn.cursor() as cursor:
            await cursor.execute(
                "SELECT * FROM user_profiles WHERE user_id=%s", (user_id,)
            )
            row = await cursor.fetchone()
            if row is None:
                return None
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
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """INSERT INTO emotion_records
                       (id, user_id, session_id, timestamp, emotion, intensity,
                        valence, arousal, dominance, needs_immediate_comfort,
                        confidence, trigger_text, context_summary,
                        analysis_method, raw_scores)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
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
            await conn.commit()

    async def get_emotion_records(
        self,
        user_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """获取情感记录"""
        async with self._pool.acquire() as conn, conn.cursor() as cursor:
            await cursor.execute(
                "SELECT * FROM emotion_records"
                " WHERE user_id=%s ORDER BY timestamp DESC LIMIT %s",
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
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """INSERT INTO identity_mappings
                       (platform, platform_user_id, yuanbot_user_id, created_at, metadata)
                       VALUES (%s, %s, %s, %s, %s)
                       ON DUPLICATE KEY UPDATE
                        yuanbot_user_id=VALUES(yuanbot_user_id),
                        metadata=VALUES(metadata)""",
                    (
                        platform,
                        platform_user_id,
                        yuanbot_user_id,
                        now,
                        json.dumps(metadata or {}, ensure_ascii=False),
                    ),
                )
            await conn.commit()

    async def get_yuanbot_user_id(
        self,
        platform: str,
        platform_user_id: str,
    ) -> str | None:
        """根据平台用户 ID 获取 YuanBot 用户 ID"""
        async with self._pool.acquire() as conn, conn.cursor() as cursor:
            await cursor.execute(
                "SELECT yuanbot_user_id FROM identity_mappings "
                "WHERE platform=%s AND platform_user_id=%s",
                (platform, platform_user_id),
            )
            row = await cursor.fetchone()
            return row[0] if row else None

    # ──────────────────────────────────────────
    # 主动交互配置操作
    # ──────────────────────────────────────────

    async def get_user_proactive_settings(
        self,
        user_id: str,
    ) -> dict[str, Any] | None:
        """获取用户的主动交互配置"""
        async with self._pool.acquire() as conn, conn.cursor() as cursor:
            await cursor.execute(
                "SELECT * FROM user_proactive_settings WHERE user_id=%s",
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
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """INSERT INTO user_proactive_settings
                    (user_id, proactive_greeting_enabled, proactive_frequency,
                     quiet_hours, max_proactive_per_day, event_trigger_enabled,
                     custom_wake_up_time, custom_sleep_time, important_dates, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        proactive_greeting_enabled=VALUES(proactive_greeting_enabled),
                        proactive_frequency=VALUES(proactive_frequency),
                        quiet_hours=VALUES(quiet_hours),
                        max_proactive_per_day=VALUES(max_proactive_per_day),
                        event_trigger_enabled=VALUES(event_trigger_enabled),
                        custom_wake_up_time=VALUES(custom_wake_up_time),
                        custom_sleep_time=VALUES(custom_sleep_time),
                        important_dates=VALUES(important_dates),
                        updated_at=VALUES(updated_at)""",
                    (
                        user_id,
                        int(settings.get("proactive_greeting_enabled", True)),
                        settings.get("proactive_frequency", "medium"),
                        json.dumps(
                            settings.get("quiet_hours", ["23:00-07:00"]),
                            ensure_ascii=False,
                        ),
                        settings.get("max_proactive_per_day", 5),
                        int(settings.get("event_trigger_enabled", True)),
                        settings.get("custom_wake_up_time"),
                        settings.get("custom_sleep_time"),
                        json.dumps(
                            settings.get("important_dates", []),
                            ensure_ascii=False,
                        ),
                        now,
                    ),
                )
            await conn.commit()

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
        """将多行数据库结果转换为字典列表"""
        if not rows:
            return []
        if cursor.description:
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row, strict=False)) for row in rows]
        return []
