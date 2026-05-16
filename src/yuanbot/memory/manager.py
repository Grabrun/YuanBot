"""YuanBot 记忆管理器

核心职责：
1. 四层记忆的统一管理（工作/事实/情景/语义）
2. 情景触发式检索
3. 记忆生命周期管理（重要性评分、遗忘曲线）
4. 自主记忆整理（定时固化）
"""

from __future__ import annotations

import asyncio
import math
import uuid
from datetime import datetime, timedelta
from typing import Any

import structlog

from yuanbot.core.types import (
    MemoryNode,
    MemorySearchResult,
    MemoryType,
    UserProfile,
)

logger = structlog.get_logger(__name__)


class MemoryManager:
    """记忆系统管理器
    
    实现四层记忆模型的统一管理：
    - 工作记忆：会话级 Redis 缓存
    - 事实记忆：PostgreSQL + 知识图谱
    - 情景记忆：向量数据库 + PostgreSQL
    - 语义记忆：知识图谱 + 向量数据库
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self._config = config or {}
        self._working_memories: dict[str, list[MemoryNode]] = {}  # session_id -> nodes
        self._fact_memories: dict[str, list[MemoryNode]] = {}     # user_id -> nodes
        self._episodic_memories: dict[str, list[MemoryNode]] = {} # user_id -> nodes
        self._semantic_memories: dict[str, list[MemoryNode]] = {} # user_id -> nodes
        self._user_profiles: dict[str, UserProfile] = {}

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
        self._working_memories[session_id].append(node)
        logger.debug("working_memory_added", session_id=session_id, node_id=node.id)
        return node

    async def get_working_memory(self, session_id: str) -> list[MemoryNode]:
        """获取当前会话的工作记忆"""
        return self._working_memories.get(session_id, [])

    async def clear_working_memory(self, session_id: str) -> None:
        """清除会话的工作记忆"""
        self._working_memories.pop(session_id, None)

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
    ) -> MemoryNode:
        """添加事实记忆（用户偏好、习惯、重要事实）"""
        node = MemoryNode(
            memory_type=MemoryType.FACT,
            content=content,
            key_entities=key_entities or [],
            importance_score=importance,
            metadata=metadata or {},
        )
        if user_id not in self._fact_memories:
            self._fact_memories[user_id] = []
        self._fact_memories[user_id].append(node)

        # 同步更新用户画像
        await self._update_user_profile_from_fact(user_id, content, key_entities)

        logger.info("fact_memory_added", user_id=user_id, node_id=node.id)
        return node

    async def get_fact_memories(self, user_id: str) -> list[MemoryNode]:
        """获取用户的事实记忆"""
        return self._fact_memories.get(user_id, [])

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
            },
        )
        if user_id not in self._episodic_memories:
            self._episodic_memories[user_id] = []
        self._episodic_memories[user_id].append(node)
        logger.info("episodic_memory_added", user_id=user_id, summary=summary[:50])
        return node

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

    # ──────────────────────────────────────────
    # 情景触发式检索（核心机制）
    # ──────────────────────────────────────────

    async def retrieve_relevant_memories(
        self,
        user_id: str,
        current_input: str,
        current_embedding: list[float] | None = None,
        max_results: int = 5,
    ) -> list[MemorySearchResult]:
        """情景触发式检索
        
        三步流程：
        1. 语义相似度检索（向量匹配）
        2. 关键词/实体匹配
        3. 按重要性和相关性排序，返回 Top-K
        """
        results: list[MemorySearchResult] = []

        # 获取用户所有情景记忆
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

            if score > 0:
                # 结合重要性评分
                final_score = score * 0.7 + node.importance_score * 0.3
                results.append(MemorySearchResult(
                    node=node,
                    score=final_score,
                    match_type=match_type,
                ))

                # 更新访问信息
                node.last_accessed = datetime.now()
                node.access_count += 1

        # 按分数排序，返回 Top-K
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:max_results]

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

                if effective_score > 0.1:  # 阈值以下淘汰
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
        for topic, nodes in topic_counts.items():
            if len(nodes) >= 3:
                # 合并为一条事实记忆
                combined_content = f"用户多次提及{topic}（共{len(nodes)}次）"
                await self.add_fact_memory(
                    user_id=user_id,
                    content=combined_content,
                    key_entities=[topic],
                    importance=0.8,
                    metadata={"source": "consolidation", "source_count": len(nodes)},
                )
                stats["upgraded"] += 1

        logger.info("memory_consolidation", user_id=user_id, **stats)
        return stats

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
