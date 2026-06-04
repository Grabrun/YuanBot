"""YuanBot 记忆管理器

核心职责：
1. 四层记忆的统一管理（工作/事实/情景/语义）
2. 情景触发式检索
3. 记忆生命周期管理（重要性评分、遗忘曲线）
4. 自主记忆整理（定时固化）
5. 情感状态追踪

持久化策略：
- 工作记忆 → 缓存存储（Redis/内存）
- 事实记忆 → SQLite
- 情景记忆 → SQLite（元数据）+ 向量存储（embedding）
- 语义记忆 → SQLite（暂用事实记忆表扩展）
- 用户画像 → SQLite
- 情感记录 → SQLite
"""

from __future__ import annotations

import asyncio
import json
import math
from datetime import datetime
from typing import Any

import structlog

from yuanbot.core.types import (
    EmotionState,
    MemoryNode,
    MemorySearchResult,
    MemoryType,
    UserProfile,
)
from yuanbot.memory.emotion_tracker import EmotionTracker

logger = structlog.get_logger(__name__)

# Module-level constants to avoid per-call allocation
_DATE_FORMATS: list[str] = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m-%d",
    "%m/%d",
    "%Y年%m月%d日",
    "%m月%d日",
]
_DATE_KEYWORDS: tuple[str, ...] = (
    "birthday", "anniversary", "interview_date",
    "生日", "纪念日", "面试",
)


class MemoryManager:
    """记忆系统管理器

    实现四层记忆模型的统一管理：
    - 工作记忆：会话级缓存
    - 事实记忆：结构化持久存储
    - 情景记忆：向量 + 结构化元数据
    - 语义记忆：知识图谱

    集成情感追踪系统，实现情感感知的记忆管理。

    支持两种运行模式：
    1. 纯内存模式（默认，向后兼容）：所有数据存储在内存字典中
    2. 持久化模式：传入 DatabaseManager，数据持久化到 SQLite/向量存储/缓存
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        db_manager: Any | None = None,
    ):
        self._config = config if config is not None else {}
        self._db = db_manager  # DatabaseManager | None

        # 自动启用 Redis 缓存: 当配置中包含 redis_url 且未传入 db_manager 时
        self._redis_url: str | None = None
        if self._db is None:
            self._redis_url = self._config.get("redis_url")
        self._auto_cache: Any = None  # 延迟初始化，调用 initialize() 时创建

        # 内存存储（纯内存模式或作为缓存层）
        self._working_memories: dict[str, list[MemoryNode]] = {}  # session_id -> nodes
        self._fact_memories: dict[str, list[MemoryNode]] = {}  # user_id -> nodes
        self._episodic_memories: dict[str, list[MemoryNode]] = {}  # user_id -> nodes
        self._semantic_memories: dict[str, list[MemoryNode]] = {}  # user_id -> nodes
        self._user_profiles: dict[str, UserProfile] = {}

        # 情感追踪系统
        self._emotion_tracker = EmotionTracker(self._config)

        # 记忆生命周期配置
        self._working_memory_max_turns = self._config.get("working_memory_max_turns", 20)
        self._forget_curve_half_life_days = self._config.get("forget_curve_half_life_days", 14)
        self._consolidation_threshold = self._config.get("consolidation_threshold", 3)
        self._min_importance_threshold = self._config.get("min_importance_threshold", 0.1)

    async def initialize(self) -> None:
        """初始化记忆管理器（启动自动缓存等）"""
        if self._redis_url and self._auto_cache is None:
            from yuanbot.infrastructure.cache_store import CacheStore

            cache = CacheStore(redis_url=self._redis_url)
            try:
                await cache.initialize()
                self._auto_cache = cache
                logger.info("memory_manager_initialized", cache_backend=cache.backend)
            except Exception as e:
                logger.warning("memory_manager_cache_init_failed", error=str(e))
                # Redis 不可用时，缓存已自动降级为内存模式
                if cache.backend == "memory":
                    self._auto_cache = cache
                else:
                    self._auto_cache = None

    async def close(self) -> None:
        """关闭记忆管理器，释放资源"""
        if self._auto_cache is not None:
            await self._auto_cache.close()
            self._auto_cache = None

    @property
    def has_persistence(self) -> bool:
        """是否启用了完整持久化存储（SQLite + 向量存储 + 缓存）"""
        return self._db is not None and self._db.is_initialized

    @property
    def has_cache(self) -> bool:
        """是否启用了缓存存储（包括自动 Redis 缓存）"""
        return self._cache is not None

    @property
    def _cache(self) -> Any:
        """获取缓存存储（优先使用 db_manager 的，回退到 auto_cache）"""
        if self._db is not None and self._db.is_initialized:
            return self._db.cache
        if self._auto_cache is not None and self._auto_cache.is_initialized:
            return self._auto_cache
        return None

    # ──────────────────────────────────────────
    # 工作记忆（第一层：会话级）
    # ──────────────────────────────────────────

    async def add_working_memory(
        self,
        session_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryNode:
        """添加工作记忆（当前会话上下文）"""
        node = MemoryNode(
            memory_type=MemoryType.WORKING,
            content=content,
            metadata=metadata or {},
        )

        if self.has_cache and self._cache is not None:
            # 持久化模式：写入缓存
            memories = await self._cache.get_working_memory(session_id)
            # 转换为可序列化格式
            mem_dict = {
                "id": node.id,
                "content": node.content,
                "metadata": node.metadata,
                "created_at": node.created_at.isoformat(),
                "last_accessed": node.last_accessed.isoformat(),
                "access_count": node.access_count,
                "importance_score": node.importance_score,
            }
            memories.append(mem_dict)

            # 检查是否超过最大轮数限制
            if len(memories) > self._working_memory_max_turns:
                memories = memories[-self._working_memory_max_turns :]

            await self._cache.set_working_memory(session_id, memories)
        else:
            # 纯内存模式
            if session_id not in self._working_memories:
                self._working_memories[session_id] = []

            if len(self._working_memories[session_id]) >= self._working_memory_max_turns:
                self._working_memories[session_id].pop(0)

            self._working_memories[session_id].append(node)

        logger.debug("working_memory_added", session_id=session_id, node_id=node.id)
        return node

    async def get_working_memory(self, session_id: str) -> list[MemoryNode]:
        """获取当前会话的工作记忆"""
        if self.has_cache and self._cache is not None:
            memories = await self._cache.get_working_memory(session_id)
            return [self._dict_to_memory_node(m, MemoryType.WORKING) for m in memories]
        return self._working_memories.get(session_id, [])

    async def get_working_memory_context(self, session_id: str, max_turns: int = 10) -> str:
        """获取工作记忆的文本上下文"""
        memories = await self.get_working_memory(session_id)
        if not memories:
            return ""

        recent_memories = memories[-max_turns:]
        context_parts = [mem.content for mem in recent_memories]
        return "\n".join(context_parts)

    async def clear_working_memory(self, session_id: str) -> None:
        """清除会话的工作记忆"""
        if self.has_cache and self._cache is not None:
            await self._cache.clear_working_memory(session_id)
        else:
            self._working_memories.pop(session_id, None)

    async def archive_working_memory(
        self,
        session_id: str,
        user_id: str,
    ) -> MemoryNode | None:
        """归档工作记忆到情景记忆

        会话结束时调用，将工作记忆总结为情景记忆。
        """
        working_memories = await self.get_working_memory(session_id)
        if not working_memories:
            return None

        # 生成会话摘要
        summary = await self._generate_session_summary(working_memories)

        # 提取关键实体和话题
        key_entities = self._extract_entities_from_memories(working_memories)
        topic_tags = self._extract_topics_from_memories(working_memories)

        # 分析整体情感基调
        emotion_summary = await self._emotion_tracker.get_session_emotion_summary(session_id)
        emotional_tone = emotion_summary.get("dominant_emotion", "neutral")

        # 创建情景记忆
        episodic_node = await self.add_episodic_memory(
            user_id=user_id,
            content=summary,
            summary=summary[:200],
            topic_tags=topic_tags,
            emotional_tone=emotional_tone,
            key_entities=key_entities,
            importance=0.6,
        )

        # 清除工作记忆
        await self.clear_working_memory(session_id)

        logger.info(
            "working_memory_archived",
            session_id=session_id,
            user_id=user_id,
            episodic_id=episodic_node.id,
        )

        return episodic_node

    # ──────────────────────────────────────────
    # 事实记忆（第二层：持久化）
    # ──────────────────────────────────────────

    async def add_fact_memory(
        self,
        user_id: str,
        content: str,
        key_entities: list[str] | None = None,
        importance: float = 0.7,
        metadata: dict[str, Any] | None = None,
        category: str = "general",
        confidence: float = 1.0,
    ) -> MemoryNode:
        """添加事实记忆（用户偏好、习惯、重要事实）

        冲突解决策略（设计参考: memory-emotion-system.md 第3.2节）：
        - 用户明确陈述 (confidence=1.0) 优先于推断 (0.6-0.8)
        - 同 confidence 时取较新内容，保留较高 importance
        - 冲突记录存入 metadata.conflict_history 供审计
        """
        node = MemoryNode(
            memory_type=MemoryType.FACT,
            content=content,
            key_entities=key_entities or [],
            importance_score=importance,
            metadata={
                **(metadata or {}),
                "category": category,
                "confidence": confidence,
                "source": metadata.get("source", "explicit_statement")
                if metadata
                else "explicit_statement",
            },
        )

        # 检查是否已存在相似的事实（冲突解决）
        # 快速跳过：无 key_entities 时不可能匹配，跳过全量扫描
        if key_entities:
            existing_facts = await self.get_fact_memories(user_id)
            for existing in existing_facts:
                if self._is_similar_fact(existing, node):
                    return await self._resolve_fact_conflict(
                        user_id, existing, node, content, importance, confidence,
                    )

        if self.has_persistence:
            await self._persist_fact_memory(user_id, node)
        else:
            if user_id not in self._fact_memories:
                self._fact_memories[user_id] = []
            self._fact_memories[user_id].append(node)

        # 同步更新用户画像
        await self._update_user_profile_from_fact(user_id, content, key_entities)

        logger.info("fact_memory_added", user_id=user_id, node_id=node.id)
        return node

    async def _resolve_fact_conflict(
        self,
        user_id: str,
        existing: MemoryNode,
        new_node: MemoryNode,
        new_content: str,
        new_importance: float,
        new_confidence: float,
    ) -> MemoryNode:
        """解决同一 key 的事实记忆冲突

        策略：
        1. 新 confidence > 旧 confidence → 用新内容覆盖
        2. 新 confidence == 旧 confidence → 更新内容，保留较高 importance
        3. 新 confidence < 旧 confidence → 保留旧内容，记录冲突历史
        """
        old_confidence = existing.metadata.get("confidence", 1.0)
        conflict_entry = {
            "old_content": existing.content,
            "new_content": new_content,
            "old_confidence": old_confidence,
            "new_confidence": new_confidence,
            "resolution": "pending",
            "timestamp": datetime.now().isoformat(),
        }

        if new_confidence > old_confidence:
            # 新信息置信度更高，覆盖
            existing.content = new_content
            existing.importance_score = max(existing.importance_score, new_importance)
            existing.metadata["confidence"] = new_confidence
            conflict_entry["resolution"] = "new_wins"
            logger.info(
                "fact_conflict_new_wins",
                user_id=user_id,
                old_conf=old_confidence,
                new_conf=new_confidence,
            )
        elif new_confidence == old_confidence:
            # 同置信度，更新内容，保留较高重要性
            existing.content = new_content
            existing.importance_score = max(existing.importance_score, new_importance)
            conflict_entry["resolution"] = "updated_same_confidence"
            logger.info(
                "fact_conflict_updated",
                user_id=user_id,
                confidence=new_confidence,
            )
        else:
            # 旧信息置信度更高，保留旧内容
            conflict_entry["resolution"] = "existing_wins"
            logger.info(
                "fact_conflict_existing_wins",
                user_id=user_id,
                old_conf=old_confidence,
                new_conf=new_confidence,
            )

        # 记录冲突历史（保留最近 5 条）
        if "conflict_history" not in existing.metadata:
            existing.metadata["conflict_history"] = []
        history: list = existing.metadata["conflict_history"]
        history.append(conflict_entry)
        existing.metadata["conflict_history"] = history[-5:]

        existing.last_accessed = datetime.now()
        existing.access_count += 1

        if self.has_persistence:
            await self._persist_fact_memory(user_id, existing)

        return existing

    async def detect_important_dates(self, user_id: str) -> list[dict[str, Any]]:
        """检测用户的重要日期（生日、纪念日等）

        扫描 category='important_date' 或 key 包含日期模式的事实记忆，
        返回即将来临的重要日期列表，供主动陪伴系统触发祝福。

        设计参考: memory-emotion-system.md 3.2节

        Returns:
            列表，每项包含 {"key", "value", "category", "days_until", "description"}
        """
        facts = await self.get_fact_memories(user_id)
        important_dates: list[dict[str, Any]] = []

        today = datetime.now().date()

        for fact in facts:
            is_date = False
            category = fact.metadata.get("category", "")

            # 1. category 为 important_date 或 personal_info
            if category in ("important_date", "personal_info"):
                is_date = True

            # 2. key 包含日期相关关键词
            date_keywords = ("birthday", "anniversary", "interview_date",
                             "生日", "纪念日", "面试")
            all_entities = " ".join(fact.key_entities) if fact.key_entities else ""
            if any(kw in all_entities for kw in date_keywords):
                is_date = True

            if not is_date:
                continue

            # 尝试解析日期值
            value = fact.content
            try:
                # 尝试多种日期格式
                parsed_date = self._parse_date_value(value)
                if parsed_date is None:
                    continue

                # 计算距今天数（忽略年份，只比较月-日）
                this_year = parsed_date.replace(year=today.year)
                if this_year < today:
                    this_year = this_year.replace(year=today.year + 1)
                days_until = (this_year - today).days

                important_dates.append({
                    "key": fact.key_entities[0] if fact.key_entities else "unknown",
                    "value": value,
                    "category": category,
                    "days_until": days_until,
                    "date": this_year.isoformat(),
                    "description": (
                        f"{fact.key_entities[0] if fact.key_entities else '重要日期'}:"
                        f" {value}"
                    ),
                })
            except Exception:
                continue

        # 按距今天数排序
        important_dates.sort(key=lambda x: x["days_until"])
        return important_dates

    @staticmethod
    def _parse_date_value(value: str) -> datetime | None:
        """尝试解析多种日期格式"""
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(value.strip(), fmt)
            except ValueError:
                continue
        return None

    async def get_fact_memories(
        self,
        user_id: str,
        category: str | None = None,
    ) -> list[MemoryNode]:
        """获取用户的事实记忆"""
        if self.has_persistence:
            rows = await self._db.sqlite.get_fact_memories(user_id, category)
            return [self._row_to_fact_memory_node(row) for row in rows]
        memories = self._fact_memories.get(user_id, [])
        if category:
            memories = [m for m in memories if m.metadata.get("category") == category]
        return memories

    async def get_user_facts_summary(self, user_id: str) -> dict[str, Any]:
        """获取用户事实记忆的摘要"""
        facts = await self.get_fact_memories(user_id)

        categorized: dict[str, list[str]] = {}
        for fact in facts:
            cat = fact.metadata.get("category", "general")
            if cat not in categorized:
                categorized[cat] = []
            categorized[cat].append(fact.content)

        return {
            "total_facts": len(facts),
            "categories": categorized,
            "recent_facts": [f.content for f in facts[-5:]],
        }

    # ──────────────────────────────────────────
    # 情景记忆（第三层：对话摘要）
    # ──────────────────────────────────────────

    async def add_episodic_memory(
        self,
        user_id: str,
        content: str,
        summary: str,
        topic_tags: list[str] | None = None,
        emotional_tone: str | None = None,
        key_entities: list[str] | None = None,
        importance: float = 0.5,
        embedding: list[float] | None = None,
    ) -> MemoryNode:
        """添加情景记忆（对话摘要节点）"""
        node = MemoryNode(
            memory_type=MemoryType.EPISODIC,
            content=content,
            summary=summary,
            topic_tags=topic_tags or [],
            emotional_tone=emotional_tone,
            key_entities=key_entities or [],
            importance_score=importance,
            embedding=embedding,
            metadata={
                "time_of_day": self._get_time_of_day(),
                "weekday": datetime.now().strftime("%A"),
                "date": datetime.now().strftime("%Y-%m-%d"),
            },
        )

        if self.has_persistence:
            # 保存元数据到 SQLite
            await self._db.sqlite.save_episodic_metadata(
                id=node.id,
                user_id=user_id,
                session_id=node.metadata.get("session_id", "unknown"),
                date=node.metadata["date"],
                time_of_day=node.metadata.get("time_of_day"),
                topic=", ".join(node.topic_tags) if node.topic_tags else None,
                summary=node.summary,
                emotional_tone=node.emotional_tone,
                key_entities=node.key_entities,
                importance=node.importance_score,
            )

            # 保存向量到向量存储
            if embedding:
                await self._db.vector.add_vector(
                    id=node.id,
                    vector=embedding,
                    metadata={"user_id": user_id, "type": "episodic"},
                )

            # 同时缓存在内存中以保持兼容性
            if user_id not in self._episodic_memories:
                self._episodic_memories[user_id] = []
            self._episodic_memories[user_id].append(node)
        else:
            if user_id not in self._episodic_memories:
                self._episodic_memories[user_id] = []
            self._episodic_memories[user_id].append(node)

        logger.info("episodic_memory_added", user_id=user_id, summary=summary[:50])
        return node

    async def get_episodic_memories(
        self,
        user_id: str,
        date_range: tuple[datetime, datetime] | None = None,
        topic: str | None = None,
    ) -> list[MemoryNode]:
        """获取情景记忆"""
        if self.has_persistence:
            date_from = date_range[0].strftime("%Y-%m-%d") if date_range else None
            date_to = date_range[1].strftime("%Y-%m-%d") if date_range else None
            rows = await self._db.sqlite.get_episodic_metadata(
                user_id, date_from=date_from, date_to=date_to, topic=topic
            )
            return [self._row_to_episodic_memory_node(row) for row in rows]

        memories = self._episodic_memories.get(user_id, [])

        if date_range:
            start_date, end_date = date_range
            memories = [m for m in memories if start_date <= m.created_at <= end_date]

        if topic:
            memories = [
                m
                for m in memories
                if topic.lower() in (m.summary or "").lower()
                or any(topic.lower() in t.lower() for t in m.topic_tags)
            ]

        return memories

    # ──────────────────────────────────────────
    # 语义记忆（第四层：深层认知）
    # ──────────────────────────────────────────

    async def add_semantic_memory(
        self,
        user_id: str,
        content: str,
        relation_type: str,
        importance: float = 0.8,
    ) -> MemoryNode:
        """添加语义记忆（从长期交互中提炼的深层认知）

        同时写入 SQLite 和知识图谱。
        """
        node = MemoryNode(
            memory_type=MemoryType.SEMANTIC,
            content=content,
            importance_score=importance,
            metadata={"relation_type": relation_type},
        )

        if self.has_persistence:
            # 语义记忆暂存入事实记忆表，category 为 "semantic"
            await self._db.sqlite.save_fact_memory(
                id=node.id,
                user_id=user_id,
                category="semantic",
                key=relation_type,
                value=content,
                importance=importance,
                source="semantic_extraction",
                metadata={"relation_type": relation_type},
            )

            # 写入知识图谱
            if self._db.graph:
                try:
                    await self._db.graph.add_node(
                        node_id=node.id,
                        node_type="SemanticMemory",
                        properties={
                            "content": content,
                            "relation_type": relation_type,
                            "importance": str(importance),
                        },
                    )
                    await self._db.graph.add_edge(
                        source_id=user_id,
                        target_id=node.id,
                        edge_type="HAS_MEMORY",
                    )
                except Exception as e:
                    logger.debug("graph_semantic_memory_failed", error=str(e))

        if user_id not in self._semantic_memories:
            self._semantic_memories[user_id] = []
        self._semantic_memories[user_id].append(node)

        logger.info("semantic_memory_added", user_id=user_id, relation_type=relation_type)
        return node

    async def get_semantic_memories(self, user_id: str) -> list[MemoryNode]:
        """获取语义记忆"""
        if self.has_persistence:
            rows = await self._db.sqlite.get_fact_memories(user_id, category="semantic")
            return [
                MemoryNode(
                    id=row["id"],
                    memory_type=MemoryType.SEMANTIC,
                    content=row["value"],
                    importance_score=row.get("importance", 0.8),
                    metadata={"relation_type": row.get("key", "unknown")},
                )
                for row in rows
            ]
        return self._semantic_memories.get(user_id, [])

    # ──────────────────────────────────────────
    # 情感感知的记忆检索（核心机制）
    # ──────────────────────────────────────────

    async def retrieve_relevant_memories(
        self,
        user_id: str,
        current_input: str,
        current_embedding: list[float] | None = None,
        max_results: int = 5,
        include_emotional_context: bool = True,
    ) -> tuple[list[MemorySearchResult], EmotionState | None]:
        """情感感知的情景触发式检索

        三步流程：
        1. 情感分析
        2. 语义相似度 + 关键词/实体匹配
        3. 按重要性、相关性和情感相关性排序
        """
        results: list[MemorySearchResult] = []

        # 1. 分析当前情感
        current_emotion = None
        if include_emotional_context:
            current_emotion = await self._emotion_tracker.analyze_emotion(
                text=current_input,
                user_id=user_id,
                session_id="current",
            )

        # 获取用户所有记忆（并发查询减少延迟）
        episodic, fact, semantic = await asyncio.gather(
            self.get_episodic_memories(user_id),
            self.get_fact_memories(user_id),
            self.get_semantic_memories(user_id),
        )

        all_memories = episodic + fact + semantic

        # 如果有向量存储且有 embedding，先进行向量检索
        vector_results: dict[str, float] = {}
        if self.has_persistence and current_embedding:
            try:
                similar = await self._db.vector.search_similar(
                    query_vector=current_embedding,
                    top_k=max_results * 2,
                    threshold=0.5,
                )
                for item in similar:
                    vector_results[item["id"]] = item["score"]
            except Exception as e:
                logger.debug("vector_search_fallback", error=str(e))

        ids_to_update: list[str] = []
        # Pre-compute lowered text once (used in entity/topic matching for every memory)
        current_input_lower = current_input.lower()

        for node in all_memories:
            score = 0.0
            match_type = "unknown"

            # 路径 1: 语义相似度（向量检索结果或本地计算）
            if node.id in vector_results:
                score = vector_results[node.id]
                match_type = "semantic"
            elif current_embedding and node.embedding:
                sim = self._cosine_similarity(current_embedding, node.embedding)
                if sim > 0.7:
                    score = sim
                    match_type = "semantic"

            # 路径 2: 关键词/实体匹配
            if score == 0:
                entity_score = self._entity_match_score(current_input_lower, node.key_entities)
                if entity_score > 0:
                    score = entity_score
                    match_type = "entity"

            # 路径 3: 话题标签匹配
            if score == 0:
                topic_score = self._topic_match_score(current_input_lower, node.topic_tags)
                if topic_score > 0:
                    score = topic_score * 0.8
                    match_type = "keyword"

            # 路径 4: 情感匹配
            if score == 0 and current_emotion and node.emotional_tone:
                emotion_score = self._emotion_match_score(current_emotion, node.emotional_tone)
                if emotion_score > 0:
                    score = emotion_score * 0.6
                    match_type = "emotional"

            if score > 0:
                final_score = score * 0.7 + node.importance_score * 0.3
                results.append(
                    MemorySearchResult(
                        node=node,
                        score=final_score,
                        match_type=match_type,
                    )
                )

                # 更新访问信息
                node.last_accessed = datetime.now()
                node.access_count += 1

                # 持久化访问计数更新（批量）
                if self.has_persistence and node.memory_type == MemoryType.EPISODIC:
                    ids_to_update.append(node.id)

        # 批量更新访问计数（单次 DB 提交）
        if ids_to_update:
            try:
                await self._db.sqlite.batch_update_episodic_access(ids_to_update)
            except Exception:
                pass

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:max_results], current_emotion

    # ──────────────────────────────────────────
    # 记忆生命周期管理
    # ──────────────────────────────────────────

    async def apply_forget_curve(self, user_id: str) -> int:
        """应用遗忘曲线，降权或淘汰低价值记忆

        返回被淘汰的记忆数量
        """
        removed = 0
        now = datetime.now()

        for memory_type_key in ["episodic", "semantic"]:
            memories = getattr(self, f"_{memory_type_key}_memories").get(user_id, [])
            survived = []

            for node in memories:
                days_since_access = (now - node.last_accessed).days
                decay_factor = math.exp(-0.05 * days_since_access)

                boost = min(node.access_count * 0.1, 0.5)
                effective_score = node.importance_score * (decay_factor + boost)

                if effective_score > self._min_importance_threshold:
                    survived.append(node)
                else:
                    removed += 1
                    # 持久化删除
                    if self.has_persistence and memory_type_key == "episodic":
                        try:
                            await self._db.sqlite.delete_episodic_metadata(node.id)
                            await self._db.vector.delete_vector(node.id)
                        except Exception:
                            pass
                    logger.info(
                        "memory_forgotten",
                        node_id=node.id,
                        memory_type=memory_type_key,
                        effective_score=effective_score,
                    )

            getattr(self, f"_{memory_type_key}_memories")[user_id] = survived

        return removed

    async def consolidate_memories(self, user_id: str) -> dict[str, int]:
        """记忆固化：将频繁出现的情景记忆升级为事实记忆

        由定时任务（深夜低负载时段）触发。
        返回升级统计。
        """
        stats = {"upgraded": 0, "merged": 0, "removed": 0}

        episodic = await self.get_episodic_memories(user_id)

        topic_counts: dict[str, list[MemoryNode]] = {}
        for node in episodic:
            for tag in node.topic_tags:
                if tag not in topic_counts:
                    topic_counts[tag] = []
                topic_counts[tag].append(node)

        removed_ids: set[str] = set()
        for topic, nodes in topic_counts.items():
            if len(nodes) >= self._consolidation_threshold:
                combined_content = f"用户多次提及{topic}（共{len(nodes)}次）"
                await self.add_fact_memory(
                    user_id=user_id,
                    content=combined_content,
                    key_entities=[topic],
                    importance=0.8,
                    metadata={"source": "consolidation", "source_count": len(nodes)},
                    category="habit",
                )
                stats["upgraded"] += 1
                for node in nodes:
                    removed_ids.add(node.id)

        if removed_ids:
            original_count = len(self._episodic_memories.get(user_id, []))
            self._episodic_memories[user_id] = [
                n for n in self._episodic_memories.get(user_id, []) if n.id not in removed_ids
            ]
            stats["removed"] = original_count - len(self._episodic_memories[user_id])

            # 持久化删除
            if self.has_persistence:
                for rid in removed_ids:
                    try:
                        await self._db.sqlite.delete_episodic_metadata(rid)
                        await self._db.vector.delete_vector(rid)
                    except Exception:
                        pass

        logger.info("memory_consolidation", user_id=user_id, **stats)
        return stats

    # ──────────────────────────────────────────
    # 情感系统集成
    # ──────────────────────────────────────────

    async def analyze_emotion(
        self,
        text: str,
        user_id: str,
        session_id: str,
    ) -> EmotionState:
        """分析情感（代理到情感追踪器）"""
        emotion_state = await self._emotion_tracker.analyze_emotion(text, user_id, session_id)

        # 持久化情感记录
        if self.has_persistence:
            try:
                record = self._emotion_tracker._records[user_id][-1]
                await self._db.sqlite.save_emotion_record(
                    id=record.id,
                    user_id=user_id,
                    session_id=session_id,
                    emotion=emotion_state.emotion.value,
                    intensity=emotion_state.intensity,
                    valence=emotion_state.valence,
                    arousal=emotion_state.arousal,
                    dominance=emotion_state.dominance,
                    needs_immediate_comfort=emotion_state.needs_immediate_comfort,
                    confidence=emotion_state.confidence,
                    trigger_text=record.trigger_text,
                    context_summary=record.context_summary,
                    analysis_method=record.analysis_method,
                    raw_scores=record.raw_scores,
                )
            except Exception as e:
                logger.debug("emotion_record_persist_failed", error=str(e))

        return emotion_state

    async def get_emotion_trend(self, user_id: str, days: int = 7):
        """获取情感趋势"""
        return await self._emotion_tracker.get_emotion_trend(user_id, days=days)

    async def get_comfort_suggestions(
        self,
        user_id: str,
        current_emotion: EmotionState,
    ) -> list[str]:
        """获取安慰建议"""
        return await self._emotion_tracker.get_comfort_suggestions(user_id, current_emotion)

    async def record_emotion(
        self,
        user_id: str,
        session_id: str,
        emotion_state: EmotionState,
    ) -> None:
        """记录情感状态到情感追踪器

        由编排引擎在每次对话后调用，确保情感趋势数据的完整性。
        """
        # 情感追踪器在 analyze_emotion 时已经自动记录，
        # 此方法提供一个显式接口供编排引擎调用
        logger.debug(
            "emotion_recorded",
            user_id=user_id,
            session_id=session_id,
            emotion=emotion_state.emotion.value,
            intensity=emotion_state.intensity,
        )

    async def get_user_proactive_settings(
        self,
        user_id: str,
    ) -> dict[str, Any]:
        """获取用户的主动交互个性化配置

        设计参考: proactive-companion-system.md 4.1
        """
        default_settings = {
            "proactive_greeting_enabled": True,
            "proactive_frequency": "medium",
            "quiet_hours": ["23:00-07:00"],
            "max_proactive_per_day": 5,
            "event_trigger_enabled": True,
            "custom_wake_up_time": None,
            "custom_sleep_time": None,
            "important_dates": [],
        }

        if self.has_persistence:
            try:
                row = await self._db.sqlite.get_user_proactive_settings(user_id)
                if row:
                    default_settings.update(row)
            except Exception:
                pass  # 表可能不存在

        return default_settings

    async def update_user_proactive_settings(
        self,
        user_id: str,
        settings: dict[str, Any],
    ) -> None:
        """更新用户的主动交互个性化配置"""
        if self.has_persistence:
            try:
                await self._db.sqlite.save_user_proactive_settings(user_id, settings)
            except Exception as e:
                logger.warning("proactive_settings_save_failed", error=str(e))

    # ──────────────────────────────────────────
    # 用户画像管理
    # ──────────────────────────────────────────

    async def get_or_create_user_profile(self, user_id: str) -> UserProfile:
        """获取或创建用户画像"""
        if self.has_persistence:
            # 原子更新交互计数并获取画像（单次 DB 往返）
            row = await self._db.sqlite.touch_user_profile(user_id)
            if row:
                return self._row_to_user_profile(row)

            # 创建新画像
            profile = UserProfile(
                user_id=user_id,
                first_interaction=datetime.now(),
            )
            profile.last_interaction = datetime.now()
            profile.total_interactions = 1
            await self._persist_user_profile(profile)
            return profile

        # 纯内存模式
        if user_id not in self._user_profiles:
            self._user_profiles[user_id] = UserProfile(
                user_id=user_id,
                first_interaction=datetime.now(),
            )
        profile = self._user_profiles[user_id]
        profile.last_interaction = datetime.now()
        profile.total_interactions += 1
        return profile

    async def update_relationship_stage(
        self,
        user_id: str,
        stage: str,
    ) -> None:
        """更新关系阶段"""
        profile = await self.get_or_create_user_profile(user_id)
        profile.relationship_stage = stage

        if self.has_persistence:
            await self._persist_user_profile(profile)

        logger.info("relationship_updated", user_id=user_id, stage=stage)

    async def calculate_trust_score(
        self,
        user_id: str,
        profile: UserProfile | None = None,
    ) -> float:
        """计算信任度分数

        Args:
            user_id: 用户 ID
            profile: 可选的已加载用户画像，避免重复 DB 读取
        """
        if profile is None:
            profile = await self.get_or_create_user_profile(user_id)

        # 并行获取三类记忆数量（减少串行等待）
        fact_task = self.get_fact_memories(user_id)
        episodic_task = self.get_episodic_memories(user_id)
        semantic_task = self.get_semantic_memories(user_id)
        fact_memories, episodic_memories, semantic_memories = await asyncio.gather(
            fact_task, episodic_task, semantic_task
        )

        factors = []

        # 1. 交互天数
        if profile.first_interaction:
            interaction_days = (datetime.now() - profile.first_interaction).days
            days_score = min(interaction_days / 90, 1.0)
            factors.append(days_score * 0.3)

        # 2. 交互频率
        if profile.total_interactions > 0:
            frequency_score = min(profile.total_interactions / 100, 1.0)
            factors.append(frequency_score * 0.2)

        # 3. 情感深度
        emotion_records = self._emotion_tracker._records.get(user_id, [])
        if emotion_records:
            deep_emotions = sum(
                1
                for r in emotion_records
                if r.emotion_state.emotion.value in ["sadness", "fear", "anger"]
            )
            depth_score = min(deep_emotions / 10, 1.0)
            factors.append(depth_score * 0.3)

        # 4. 记忆丰富度
        total_memories = len(fact_memories) + len(episodic_memories) + len(semantic_memories)
        memory_score = min(total_memories / 50, 1.0)
        factors.append(memory_score * 0.2)

        trust_score = sum(factors) if factors else 0.0
        profile.trust_score = trust_score

        # 直接更新关系阶段（复用已加载的 profile，避免重复 DB 读取）
        if trust_score >= 0.8:
            new_stage = "deep"
        elif trust_score >= 0.6:
            new_stage = "intimate"
        elif trust_score >= 0.3:
            new_stage = "familiar"
        else:
            new_stage = "initial"

        if profile.relationship_stage != new_stage:
            profile.relationship_stage = new_stage
            if self.has_persistence:
                await self._persist_user_profile(profile)
            logger.info("relationship_updated", user_id=user_id, stage=new_stage)

        return trust_score

    # ──────────────────────────────────────────
    # 记忆统计与报告
    # ──────────────────────────────────────────

    async def get_memory_stats(self, user_id: str) -> dict[str, Any]:
        """获取记忆统计信息"""
        return {
            "working_memory_sessions": len(self._working_memories),
            "fact_memories": len(await self.get_fact_memories(user_id)),
            "episodic_memories": len(await self.get_episodic_memories(user_id)),
            "semantic_memories": len(await self.get_semantic_memories(user_id)),
            "emotion_records": len(self._emotion_tracker._records.get(user_id, [])),
            "emotion_patterns": len(self._emotion_tracker._patterns.get(user_id, [])),
            "user_profile": await self.get_or_create_user_profile(user_id)
            if self.has_persistence
            else self._user_profiles.get(user_id),
        }

    # ──────────────────────────────────────────
    # 持久化辅助方法
    # ──────────────────────────────────────────

    async def _persist_fact_memory(self, user_id: str, node: MemoryNode) -> None:
        """持久化事实记忆到 SQLite"""
        await self._db.sqlite.save_fact_memory(
            id=node.id,
            user_id=user_id,
            category=node.metadata.get("category", "general"),
            key=node.key_entities[0] if node.key_entities else "general",
            value=node.content,
            confidence=node.metadata.get("confidence", 1.0),
            source=node.metadata.get("source", "explicit_statement"),
            importance=node.importance_score,
            metadata=node.metadata,
        )

    async def _persist_user_profile(self, profile: UserProfile) -> None:
        """持久化用户画像到 SQLite"""
        fi = profile.first_interaction
        li = profile.last_interaction
        await self._db.sqlite.save_user_profile(
            user_id=profile.user_id,
            display_name=profile.display_name,
            preferences=profile.preferences,
            relationship_stage=profile.relationship_stage,
            trust_score=profile.trust_score,
            total_interactions=profile.total_interactions,
            first_interaction=fi.timestamp() if fi else None,
            last_interaction=li.timestamp() if li else None,
            typical_mood_patterns=profile.typical_mood_patterns,
            platform_ids=profile.platform_ids,
            metadata=profile.metadata,
        )

    @staticmethod
    def _row_to_fact_memory_node(row: dict[str, Any]) -> MemoryNode:
        """将数据库行转换为事实记忆节点"""
        metadata = {}
        raw_meta = row.get("metadata", "{}")
        if isinstance(raw_meta, str):
            try:
                metadata = json.loads(raw_meta)
            except (json.JSONDecodeError, TypeError):
                metadata = {}
        elif isinstance(raw_meta, dict):
            metadata = raw_meta

        metadata["category"] = row.get("category", "general")
        metadata["confidence"] = row.get("confidence", 1.0)
        metadata["source"] = row.get("source", "explicit_statement")

        return MemoryNode(
            id=row["id"],
            memory_type=MemoryType.FACT,
            content=row["value"],
            key_entities=[],  # fact_memories 表无 key_entities 字段，存于 metadata
            importance_score=row.get("importance", 0.5),
            access_count=row.get("access_count", 0),
            metadata=metadata,
        )

    @staticmethod
    def _row_to_episodic_memory_node(row: dict[str, Any]) -> MemoryNode:
        """将数据库行转换为情景记忆节点"""
        key_entities = []
        raw_entities = row.get("key_entities", "[]")
        if isinstance(raw_entities, str):
            try:
                key_entities = json.loads(raw_entities)
            except (json.JSONDecodeError, TypeError):
                key_entities = []
        elif isinstance(raw_entities, list):
            key_entities = raw_entities

        topic_tags = []
        topic = row.get("topic", "")
        if topic:
            topic_tags = [t.strip() for t in topic.split(",") if t.strip()]

        created_at_ts = row.get("created_at")
        created_at = datetime.fromtimestamp(created_at_ts) if created_at_ts else datetime.now()

        last_accessed_ts = row.get("last_accessed_at")
        last_accessed = datetime.fromtimestamp(last_accessed_ts) if last_accessed_ts else created_at

        metadata = {
            "date": row.get("date", ""),
            "time_of_day": row.get("time_of_day", ""),
        }

        return MemoryNode(
            id=row["id"],
            memory_type=MemoryType.EPISODIC,
            content=row.get("summary", ""),
            summary=row.get("summary", ""),
            topic_tags=topic_tags,
            emotional_tone=row.get("emotional_tone"),
            key_entities=key_entities,
            importance_score=row.get("importance", 0.5),
            access_count=row.get("access_count", 0),
            created_at=created_at,
            last_accessed=last_accessed,
            metadata=metadata,
        )

    @staticmethod
    def _row_to_user_profile(row: dict[str, Any]) -> UserProfile:
        """将数据库行转换为用户画像"""
        preferences = {}
        raw_prefs = row.get("preferences", "{}")
        if isinstance(raw_prefs, str):
            try:
                preferences = json.loads(raw_prefs)
            except (json.JSONDecodeError, TypeError):
                preferences = {}
        elif isinstance(raw_prefs, dict):
            preferences = raw_prefs

        mood_patterns = {}
        raw_mood = row.get("typical_mood_patterns", "{}")
        if isinstance(raw_mood, str):
            try:
                mood_patterns = json.loads(raw_mood)
            except (json.JSONDecodeError, TypeError):
                mood_patterns = {}
        elif isinstance(raw_mood, dict):
            mood_patterns = raw_mood

        platform_ids = {}
        raw_pids = row.get("platform_ids", "{}")
        if isinstance(raw_pids, str):
            try:
                platform_ids = json.loads(raw_pids)
            except (json.JSONDecodeError, TypeError):
                platform_ids = {}
        elif isinstance(raw_pids, dict):
            platform_ids = raw_pids

        metadata = {}
        raw_meta = row.get("metadata", "{}")
        if isinstance(raw_meta, str):
            try:
                metadata = json.loads(raw_meta)
            except (json.JSONDecodeError, TypeError):
                metadata = {}
        elif isinstance(raw_meta, dict):
            metadata = raw_meta

        fi_ts = row.get("first_interaction")
        li_ts = row.get("last_interaction")

        return UserProfile(
            user_id=row["user_id"],
            display_name=row.get("display_name"),
            preferences=preferences,
            relationship_stage=row.get("relationship_stage", "initial"),
            trust_score=row.get("trust_score", 0.0),
            total_interactions=row.get("total_interactions", 0),
            first_interaction=datetime.fromtimestamp(fi_ts) if fi_ts else None,
            last_interaction=datetime.fromtimestamp(li_ts) if li_ts else None,
            typical_mood_patterns=mood_patterns,
            platform_ids=platform_ids,
            metadata=metadata,
        )

    @staticmethod
    def _dict_to_memory_node(
        data: dict[str, Any],
        memory_type: MemoryType,
    ) -> MemoryNode:
        """将字典转换为 MemoryNode（用于缓存反序列化）"""
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        else:
            created_at = datetime.now()

        last_accessed = data.get("last_accessed")
        if isinstance(last_accessed, str):
            last_accessed = datetime.fromisoformat(last_accessed)
        else:
            last_accessed = datetime.now()

        return MemoryNode(
            id=data.get("id", ""),
            memory_type=memory_type,
            content=data.get("content", ""),
            created_at=created_at,
            last_accessed=last_accessed,
            access_count=data.get("access_count", 0),
            importance_score=data.get("importance_score", 0.5),
            metadata=data.get("metadata", {}),
        )

    # ──────────────────────────────────────────
    # 内部辅助方法
    # ──────────────────────────────────────────

    async def _update_user_profile_from_fact(
        self,
        user_id: str,
        content: str,
        entities: list[str] | None,
    ) -> None:
        """从事实记忆中更新用户画像"""
        profile = await self.get_or_create_user_profile(user_id)
        if entities:
            for entity in entities:
                if entity not in profile.preferences:
                    profile.preferences[entity] = content

        if self.has_persistence:
            await self._persist_user_profile(profile)

    async def _generate_session_summary(self, memories: list[MemoryNode]) -> str:
        """生成会话摘要"""
        if not memories:
            return "空会话"

        key_contents = [
            mem.content[:100]
            for mem in memories
            if mem.content and len(mem.content) > 10
        ]

        if not key_contents:
            return "简短对话"

        summary_parts = key_contents[:3]
        return "会话摘要：" + "；".join(summary_parts)

    def _extract_entities_from_memories(self, memories: list[MemoryNode]) -> list[str]:
        """从记忆中提取关键实体"""
        entities = set()
        for mem in memories:
            entities.update(mem.key_entities)
        return list(entities)[:10]

    def _extract_topics_from_memories(self, memories: list[MemoryNode]) -> list[str]:
        """从记忆中提取话题标签"""
        topics = set()
        for mem in memories:
            topics.update(mem.topic_tags)
        return list(topics)[:5]

    def _is_similar_fact(self, existing: MemoryNode, new_node: MemoryNode) -> bool:
        """检查是否是相似的事实"""
        if not existing.key_entities or not new_node.key_entities:
            return False
        common_entities = set(existing.key_entities) & set(new_node.key_entities)
        return len(common_entities) > 0

    # Emotion valence sets (shared across instances, avoid re-creation per call)
    _POSITIVE_EMOTIONS = frozenset({"joy", "trust", "anticipation"})
    _NEGATIVE_EMOTIONS = frozenset({"sadness", "anger", "fear", "disgust"})

    def _emotion_match_score(self, current_emotion: EmotionState, memory_emotion: str) -> float:
        """情感匹配评分"""
        if not memory_emotion:
            return 0.0

        if current_emotion.emotion.value == memory_emotion:
            return 1.0

        current_valence = (
            "positive"
            if current_emotion.emotion.value in self._POSITIVE_EMOTIONS
            else "negative"
            if current_emotion.emotion.value in self._NEGATIVE_EMOTIONS
            else "neutral"
        )
        memory_valence = (
            "positive"
            if memory_emotion in self._POSITIVE_EMOTIONS
            else "negative"
            if memory_emotion in self._NEGATIVE_EMOTIONS
            else "neutral"
        )

        if current_valence == memory_valence:
            return 0.5

        return 0.0

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """计算余弦相似度"""
        if len(a) != len(b):
            return 0.0
        dot_product = sum(x * y for x, y in zip(a, b, strict=False))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot_product / (norm_a * norm_b)

    @staticmethod
    def _entity_match_score(text: str, entities: list[str]) -> float:
        """实体匹配评分"""
        if not entities:
            return 0.0
        text_lower = text.lower()
        matched = sum(1 for e in entities if e.lower() in text_lower)
        return matched / len(entities)

    @staticmethod
    def _topic_match_score(text: str, tags: list[str]) -> float:
        """话题标签匹配评分"""
        if not tags:
            return 0.0
        text_lower = text.lower()
        matched = sum(1 for t in tags if t.lower() in text_lower)
        return matched / len(tags)

    @staticmethod
    def _get_time_of_day() -> str:
        """获取当前时段"""
        hour = datetime.now().hour
        if hour < 6:
            return "凌晨"
        elif hour < 12:
            return "上午"
        elif hour < 14:
            return "中午"
        elif hour < 18:
            return "下午"
        elif hour < 22:
            return "晚上"
        else:
            return "深夜"
