"""YuanBot 记忆管理器

核心职责：
1. 四层记忆的统一管理（工作/事实/情景/语义）
2. 情景触发式检索
3. 记忆生命周期管理（重要性评分、遗忘曲线）
4. 自主记忆整理（定时固化）
5. 情感状态追踪
"""

from __future__ import annotations

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


class MemoryManager:
    """记忆系统管理器

    实现四层记忆模型的统一管理：
    - 工作记忆：会话级缓存
    - 事实记忆：结构化持久存储
    - 情景记忆：向量 + 结构化元数据
    - 语义记忆：知识图谱

    集成情感追踪系统，实现情感感知的记忆管理。
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self._config = config if config is not None else {}
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
        if session_id not in self._working_memories:
            self._working_memories[session_id] = []

        # 检查是否超过最大轮数限制
        if len(self._working_memories[session_id]) >= self._working_memory_max_turns:
            # 移除最旧的记忆
            self._working_memories[session_id].pop(0)

        self._working_memories[session_id].append(node)
        logger.debug("working_memory_added", session_id=session_id, node_id=node.id)
        return node

    async def get_working_memory(self, session_id: str) -> list[MemoryNode]:
        """获取当前会话的工作记忆"""
        return self._working_memories.get(session_id, [])

    async def get_working_memory_context(self, session_id: str, max_turns: int = 10) -> str:
        """获取工作记忆的文本上下文"""
        memories = self._working_memories.get(session_id, [])
        if not memories:
            return ""

        # 获取最近的对话轮次
        recent_memories = memories[-max_turns:]
        context_parts = []
        for mem in recent_memories:
            context_parts.append(mem.content)

        return "\n".join(context_parts)

    async def clear_working_memory(self, session_id: str) -> None:
        """清除会话的工作记忆"""
        self._working_memories.pop(session_id, None)

    async def archive_working_memory(
        self,
        session_id: str,
        user_id: str,
    ) -> MemoryNode | None:
        """归档工作记忆到情景记忆

        会话结束时调用，将工作记忆总结为情景记忆。
        """
        working_memories = self._working_memories.get(session_id, [])
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
        """添加事实记忆（用户偏好、习惯、重要事实）"""
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
        if user_id not in self._fact_memories:
            self._fact_memories[user_id] = []

        # 检查是否已存在相似的事实（避免重复）
        existing_facts = self._fact_memories[user_id]
        for existing in existing_facts:
            if self._is_similar_fact(existing, node):
                # 更新现有事实
                existing.content = content
                existing.importance_score = max(existing.importance_score, importance)
                existing.last_accessed = datetime.now()
                existing.access_count += 1
                logger.info("fact_memory_updated", user_id=user_id, node_id=existing.id)
                return existing

        self._fact_memories[user_id].append(node)

        # 同步更新用户画像
        await self._update_user_profile_from_fact(user_id, content, key_entities)

        logger.info("fact_memory_added", user_id=user_id, node_id=node.id)
        return node

    async def get_fact_memories(
        self,
        user_id: str,
        category: str | None = None,
    ) -> list[MemoryNode]:
        """获取用户的事实记忆"""
        memories = self._fact_memories.get(user_id, [])
        if category:
            memories = [m for m in memories if m.metadata.get("category") == category]
        return memories

    async def get_user_facts_summary(self, user_id: str) -> dict[str, Any]:
        """获取用户事实记忆的摘要"""
        facts = await self.get_fact_memories(user_id)

        # 按类别组织
        categorized: dict[str, list[str]] = {}
        for fact in facts:
            category = fact.metadata.get("category", "general")
            if category not in categorized:
                categorized[category] = []
            categorized[category].append(fact.content)

        return {
            "total_facts": len(facts),
            "categories": categorized,
            "recent_facts": [f.content for f in facts[-5:]],  # 最近5条
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
        """添加语义记忆（从长期交互中提炼的深层认知）"""
        node = MemoryNode(
            memory_type=MemoryType.SEMANTIC,
            content=content,
            importance_score=importance,
            metadata={"relation_type": relation_type},
        )
        if user_id not in self._semantic_memories:
            self._semantic_memories[user_id] = []
        self._semantic_memories[user_id].append(node)
        logger.info("semantic_memory_added", user_id=user_id, relation_type=relation_type)
        return node

    async def get_semantic_memories(self, user_id: str) -> list[MemoryNode]:
        """获取语义记忆"""
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
                session_id="current",  # 临时会话ID
            )

        # 获取用户所有记忆
        episodic = self._episodic_memories.get(user_id, [])
        fact = self._fact_memories.get(user_id, [])
        semantic = self._semantic_memories.get(user_id, [])

        all_memories = episodic + fact + semantic

        for node in all_memories:
            score = 0.0
            match_type = "unknown"

            # 路径 1: 语义相似度（如果有 embedding）
            if current_embedding and node.embedding:
                sim = self._cosine_similarity(current_embedding, node.embedding)
                if sim > 0.7:
                    score = sim
                    match_type = "semantic"

            # 路径 2: 关键词/实体匹配
            if score == 0:
                entity_score = self._entity_match_score(current_input, node.key_entities)
                if entity_score > 0:
                    score = entity_score
                    match_type = "entity"

            # 路径 3: 话题标签匹配
            if score == 0:
                topic_score = self._topic_match_score(current_input, node.topic_tags)
                if topic_score > 0:
                    score = topic_score * 0.8
                    match_type = "keyword"

            # 路径 4: 情感匹配（如果当前有情感状态）
            if score == 0 and current_emotion and node.emotional_tone:
                emotion_score = self._emotion_match_score(current_emotion, node.emotional_tone)
                if emotion_score > 0:
                    score = emotion_score * 0.6
                    match_type = "emotional"

            if score > 0:
                # 结合重要性评分
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

        # 按分数排序，返回 Top-K
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
                # 计算时间衰减
                days_since_access = (now - node.last_accessed).days
                decay_factor = math.exp(-0.05 * days_since_access)  # 半衰期约 14 天

                # 结合访问频率的强化
                boost = min(node.access_count * 0.1, 0.5)
                effective_score = node.importance_score * (decay_factor + boost)

                if effective_score > self._min_importance_threshold:  # 阈值以下淘汰
                    survived.append(node)
                else:
                    removed += 1
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

        episodic = self._episodic_memories.get(user_id, [])

        # 分析重复出现的话题
        topic_counts: dict[str, list[MemoryNode]] = {}
        for node in episodic:
            for tag in node.topic_tags:
                if tag not in topic_counts:
                    topic_counts[tag] = []
                topic_counts[tag].append(node)

        # 高频话题（出现 >= 3 次）的情景记忆升级为事实记忆
        removed_ids: set[str] = set()
        for topic, nodes in topic_counts.items():
            if len(nodes) >= self._consolidation_threshold:
                # 合并为一条事实记忆
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
                # 标记已合并的情景记忆
                for node in nodes:
                    removed_ids.add(node.id)

        # 移除已合并的情景记忆
        if removed_ids:
            original_count = len(self._episodic_memories.get(user_id, []))
            self._episodic_memories[user_id] = [
                n for n in self._episodic_memories.get(user_id, []) if n.id not in removed_ids
            ]
            stats["removed"] = original_count - len(self._episodic_memories[user_id])

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
        return await self._emotion_tracker.analyze_emotion(text, user_id, session_id)

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

    # ──────────────────────────────────────────
    # 用户画像管理
    # ──────────────────────────────────────────

    async def get_or_create_user_profile(self, user_id: str) -> UserProfile:
        """获取或创建用户画像"""
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
        logger.info("relationship_updated", user_id=user_id, stage=stage)

    async def calculate_trust_score(self, user_id: str) -> float:
        """计算信任度分数"""
        profile = await self.get_or_create_user_profile(user_id)

        # 基于多个因素计算信任度
        factors = []

        # 1. 交互天数
        if profile.first_interaction:
            interaction_days = (datetime.now() - profile.first_interaction).days
            days_score = min(interaction_days / 90, 1.0)  # 90天达到最大
            factors.append(days_score * 0.3)

        # 2. 交互频率
        if profile.total_interactions > 0:
            frequency_score = min(profile.total_interactions / 100, 1.0)  # 100次交互达到最大
            factors.append(frequency_score * 0.2)

        # 3. 情感深度（基于情感记录）
        emotion_records = self._emotion_tracker._records.get(user_id, [])
        if emotion_records:
            # 统计深度情感（悲伤、恐惧、愤怒等）的出现次数
            deep_emotions = sum(
                1
                for r in emotion_records
                if r.emotion_state.emotion.value in ["sadness", "fear", "anger"]
            )
            depth_score = min(deep_emotions / 10, 1.0)  # 10次深度情感达到最大
            factors.append(depth_score * 0.3)

        # 4. 记忆丰富度
        total_memories = (
            len(self._fact_memories.get(user_id, []))
            + len(self._episodic_memories.get(user_id, []))
            + len(self._semantic_memories.get(user_id, []))
        )
        memory_score = min(total_memories / 50, 1.0)  # 50条记忆达到最大
        factors.append(memory_score * 0.2)

        # 计算总分
        trust_score = sum(factors) if factors else 0.0

        # 更新用户画像
        profile.trust_score = trust_score

        # 根据信任度更新关系阶段
        if trust_score >= 0.8:
            await self.update_relationship_stage(user_id, "deep")
        elif trust_score >= 0.6:
            await self.update_relationship_stage(user_id, "intimate")
        elif trust_score >= 0.3:
            await self.update_relationship_stage(user_id, "familiar")
        else:
            await self.update_relationship_stage(user_id, "initial")

        return trust_score

    # ──────────────────────────────────────────
    # 记忆统计与报告
    # ──────────────────────────────────────────

    async def get_memory_stats(self, user_id: str) -> dict[str, Any]:
        """获取记忆统计信息"""
        return {
            "working_memory_sessions": len(self._working_memories),
            "fact_memories": len(self._fact_memories.get(user_id, [])),
            "episodic_memories": len(self._episodic_memories.get(user_id, [])),
            "semantic_memories": len(self._semantic_memories.get(user_id, [])),
            "emotion_records": len(self._emotion_tracker._records.get(user_id, [])),
            "emotion_patterns": len(self._emotion_tracker._patterns.get(user_id, [])),
            "user_profile": self._user_profiles.get(user_id),
        }

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
        # 简单实现：将实体作为偏好记录
        if entities:
            for entity in entities:
                if entity not in profile.preferences:
                    profile.preferences[entity] = content

    async def _generate_session_summary(self, memories: list[MemoryNode]) -> str:
        """生成会话摘要"""
        if not memories:
            return "空会话"

        # 提取关键内容
        key_contents = []
        for mem in memories:
            if mem.content and len(mem.content) > 10:
                key_contents.append(mem.content[:100])

        if not key_contents:
            return "简短对话"

        # 简化实现：取前3条有内容的记忆
        summary_parts = key_contents[:3]
        return "会话摘要：" + "；".join(summary_parts)

    def _extract_entities_from_memories(self, memories: list[MemoryNode]) -> list[str]:
        """从记忆中提取关键实体"""
        entities = set()
        for mem in memories:
            entities.update(mem.key_entities)
        return list(entities)[:10]  # 最多10个实体

    def _extract_topics_from_memories(self, memories: list[MemoryNode]) -> list[str]:
        """从记忆中提取话题标签"""
        topics = set()
        for mem in memories:
            topics.update(mem.topic_tags)
        return list(topics)[:5]  # 最多5个话题

    def _is_similar_fact(self, existing: MemoryNode, new_node: MemoryNode) -> bool:
        """检查是否是相似的事实"""
        # 简化实现：检查关键实体是否重叠
        if not existing.key_entities or not new_node.key_entities:
            return False

        common_entities = set(existing.key_entities) & set(new_node.key_entities)
        return len(common_entities) > 0

    def _emotion_match_score(self, current_emotion: EmotionState, memory_emotion: str) -> float:
        """情感匹配评分"""
        if not memory_emotion:
            return 0.0

        # 情感相同或相似时给予高分
        if current_emotion.emotion.value == memory_emotion:
            return 1.0

        # 情感效价相同给予部分分数
        positive_emotions = {"joy", "trust", "anticipation"}
        negative_emotions = {"sadness", "anger", "fear", "disgust"}

        current_valence = (
            "positive"
            if current_emotion.emotion.value in positive_emotions
            else "negative"
            if current_emotion.emotion.value in negative_emotions
            else "neutral"
        )
        memory_valence = (
            "positive"
            if memory_emotion in positive_emotions
            else "negative"
            if memory_emotion in negative_emotions
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
        matched = sum(1 for e in entities if e.lower() in text.lower())
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
