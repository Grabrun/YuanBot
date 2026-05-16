"""YuanBot 记忆管理器综合测试"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import pytest

from yuanbot.core.types import MemoryType
from yuanbot.memory.manager import MemoryManager


@pytest.fixture
def mm():
    return MemoryManager()


class TestWorkingMemory:
    """工作记忆测试"""

    @pytest.mark.asyncio
    async def test_add_multiple_sessions(self, mm: MemoryManager):
        await mm.add_working_memory("s1", "msg1")
        await mm.add_working_memory("s2", "msg2")

        assert len(await mm.get_working_memory("s1")) == 1
        assert len(await mm.get_working_memory("s2")) == 1

    @pytest.mark.asyncio
    async def test_get_empty_session(self, mm: MemoryManager):
        result = await mm.get_working_memory("nonexistent")
        assert result == []

    @pytest.mark.asyncio
    async def test_clear_nonexistent(self, mm: MemoryManager):
        """清除不存在的会话不应报错"""
        await mm.clear_working_memory("nonexistent")

    @pytest.mark.asyncio
    async def test_add_with_metadata(self, mm: MemoryManager):
        node = await mm.add_working_memory("s1", "test", metadata={"key": "val"})
        assert node.metadata["key"] == "val"

    @pytest.mark.asyncio
    async def test_preserves_order(self, mm: MemoryManager):
        await mm.add_working_memory("s1", "first")
        await mm.add_working_memory("s1", "second")
        await mm.add_working_memory("s1", "third")

        memories = await mm.get_working_memory("s1")
        assert [m.content for m in memories] == ["first", "second", "third"]


class TestFactMemory:
    """事实记忆测试"""

    @pytest.mark.asyncio
    async def test_add_creates_user_profile(self, mm: MemoryManager):
        await mm.add_fact_memory("u1", "喜欢咖啡", key_entities=["咖啡"])
        profile = await mm.get_or_create_user_profile("u1")
        assert "咖啡" in profile.preferences

    @pytest.mark.asyncio
    async def test_add_multiple_facts(self, mm: MemoryManager):
        await mm.add_fact_memory("u1", "喜欢咖啡", key_entities=["咖啡"])
        await mm.add_fact_memory("u1", "怕狗", key_entities=["狗"])

        facts = await mm.get_fact_memories("u1")
        assert len(facts) == 2

    @pytest.mark.asyncio
    async def test_get_empty_facts(self, mm: MemoryManager):
        assert await mm.get_fact_memories("nonexistent") == []

    @pytest.mark.asyncio
    async def test_importance_score(self, mm: MemoryManager):
        node = await mm.add_fact_memory("u1", "test", importance=0.9)
        assert node.importance_score == 0.9


class TestEpisodicMemory:
    """情景记忆测试"""

    @pytest.mark.asyncio
    async def test_add_with_all_fields(self, mm: MemoryManager):
        node = await mm.add_episodic_memory(
            user_id="u1",
            content="用户聊到旅行计划",
            summary="旅行计划讨论",
            topic_tags=["旅行", "计划"],
            emotional_tone="positive",
            key_entities=["日本", "东京"],
            importance=0.7,
            embedding=[0.1, 0.2, 0.3],
        )
        assert node.summary == "旅行计划讨论"
        assert "旅行" in node.topic_tags
        assert node.embedding is not None
        assert "time_of_day" in node.metadata
        assert "weekday" in node.metadata

    @pytest.mark.asyncio
    async def test_defaults(self, mm: MemoryManager):
        node = await mm.add_episodic_memory(
            user_id="u1",
            content="test",
            summary="test summary",
        )
        assert node.topic_tags == []
        assert node.emotional_tone is None
        assert node.key_entities == []
        assert node.importance_score == 0.5


class TestSemanticMemory:
    """语义记忆测试"""

    @pytest.mark.asyncio
    async def test_add_semantic(self, mm: MemoryManager):
        node = await mm.add_semantic_memory(
            user_id="u1",
            content="用户在压力大时倾向于沉默",
            relation_type="behavioral_pattern",
            importance=0.9,
        )
        assert node.memory_type == MemoryType.SEMANTIC
        assert node.metadata["relation_type"] == "behavioral_pattern"
        assert node.importance_score == 0.9


class TestRetrieveRelevantMemories:
    """记忆检索测试"""

    @pytest.mark.asyncio
    async def test_no_memories(self, mm: MemoryManager):
        results = await mm.retrieve_relevant_memories("u1", "test input")
        assert results == []

    @pytest.mark.asyncio
    async def test_entity_match(self, mm: MemoryManager):
        await mm.add_episodic_memory(
            user_id="u1",
            content="用户喜欢咖啡",
            summary="咖啡偏好",
            key_entities=["咖啡"],
        )

        results = await mm.retrieve_relevant_memories("u1", "今天想喝咖啡")
        assert len(results) > 0
        assert results[0].match_type == "entity"

    @pytest.mark.asyncio
    async def test_topic_match(self, mm: MemoryManager):
        await mm.add_episodic_memory(
            user_id="u1",
            content="聊到工作",
            summary="工作话题",
            topic_tags=["工作"],
        )

        results = await mm.retrieve_relevant_memories("u1", "工作好累")
        assert len(results) > 0
        assert results[0].match_type == "keyword"

    @pytest.mark.asyncio
    async def test_semantic_match(self, mm: MemoryManager):
        await mm.add_episodic_memory(
            user_id="u1",
            content="用户喜欢蓝色",
            summary="颜色偏好",
            embedding=[1.0, 0.0, 0.0],
        )

        results = await mm.retrieve_relevant_memories(
            "u1", "蓝色的天空", current_embedding=[0.9, 0.1, 0.0]
        )
        assert len(results) > 0
        assert results[0].match_type == "semantic"

    @pytest.mark.asyncio
    async def test_max_results(self, mm: MemoryManager):
        for i in range(10):
            await mm.add_episodic_memory(
                user_id="u1",
                content=f"记忆{i}",
                summary=f"摘要{i}",
                key_entities=[f"实体{i}"],
            )

        results = await mm.retrieve_relevant_memories(
            "u1", "实体0 实体1 实体2", max_results=3
        )
        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_no_match_returns_empty(self, mm: MemoryManager):
        await mm.add_episodic_memory(
            user_id="u1",
            content="完全无关的内容",
            summary="无关",
            key_entities=["xyz"],
        )

        results = await mm.retrieve_relevant_memories("u1", "今天天气不错")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_updates_access_info(self, mm: MemoryManager):
        node = await mm.add_episodic_memory(
            user_id="u1",
            content="测试",
            summary="测试",
            key_entities=["测试"],
        )
        assert node.access_count == 0

        await mm.retrieve_relevant_memories("u1", "测试内容")
        assert node.access_count == 1

    @pytest.mark.asyncio
    async def test_search_across_memory_types(self, mm: MemoryManager):
        """应同时搜索情景、事实、语义记忆"""
        await mm.add_episodic_memory(
            user_id="u1", content="情景", summary="情景", key_entities=["搜索词"]
        )
        await mm.add_fact_memory("u1", "事实", key_entities=["搜索词"])
        await mm.add_semantic_memory("u1", "语义", relation_type="test")

        results = await mm.retrieve_relevant_memories("u1", "搜索词")
        assert len(results) >= 2  # 至少匹配情景和事实


class TestCosineSimilarity:
    """余弦相似度测试"""

    def test_identical_vectors(self):
        assert MemoryManager._cosine_similarity([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert MemoryManager._cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        assert MemoryManager._cosine_similarity([1, 0], [-1, 0]) == pytest.approx(-1.0)

    def test_different_lengths(self):
        assert MemoryManager._cosine_similarity([1, 0], [1, 0, 0]) == 0.0

    def test_zero_vector(self):
        assert MemoryManager._cosine_similarity([0, 0], [1, 0]) == 0.0

    def test_both_zero(self):
        assert MemoryManager._cosine_similarity([0, 0], [0, 0]) == 0.0

    def test_partial_similarity(self):
        a = [1, 1, 0]
        b = [1, 0, 0]
        expected = 1 / math.sqrt(2)
        assert MemoryManager._cosine_similarity(a, b) == pytest.approx(expected)


class TestEntityMatchScore:
    """实体匹配评分测试"""

    def test_all_match(self):
        score = MemoryManager._entity_match_score("我喜欢咖啡和茶", ["咖啡", "茶"])
        assert score == 1.0

    def test_partial_match(self):
        score = MemoryManager._entity_match_score("我喜欢咖啡", ["咖啡", "茶"])
        assert score == 0.5

    def test_no_match(self):
        score = MemoryManager._entity_match_score("今天天气好", ["咖啡", "茶"])
        assert score == 0.0

    def test_empty_entities(self):
        assert MemoryManager._entity_match_score("test", []) == 0.0

    def test_case_insensitive(self):
        score = MemoryManager._entity_match_score("HELLO", ["hello"])
        assert score == 1.0


class TestTopicMatchScore:
    """话题匹配评分测试"""

    def test_match(self):
        score = MemoryManager._topic_match_score("工作好累", ["工作", "休息"])
        assert score == 0.5

    def test_no_match(self):
        score = MemoryManager._topic_match_score("天气好", ["工作", "休息"])
        assert score == 0.0

    def test_empty_tags(self):
        assert MemoryManager._topic_match_score("test", []) == 0.0


class TestForgetCurve:
    """遗忘曲线测试"""

    @pytest.mark.asyncio
    async def test_fresh_memories_survive(self, mm: MemoryManager):
        await mm.add_episodic_memory(
            user_id="u1", content="新鲜记忆", summary="新鲜", importance=0.5
        )
        removed = await mm.apply_forget_curve("u1")
        assert removed == 0

    @pytest.mark.asyncio
    async def test_old_low_importance_forgotten(self, mm: MemoryManager):
        node = await mm.add_episodic_memory(
            user_id="u1", content="低价值旧记忆", summary="旧", importance=0.1
        )
        node.last_accessed = datetime.now() - timedelta(days=90)
        removed = await mm.apply_forget_curve("u1")
        assert removed >= 1

    @pytest.mark.asyncio
    async def test_old_high_importance_survives(self, mm: MemoryManager):
        node = await mm.add_episodic_memory(
            user_id="u1", content="高价值旧记忆", summary="重要", importance=0.95
        )
        node.last_accessed = datetime.now() - timedelta(days=30)
        removed = await mm.apply_forget_curve("u1")
        assert removed == 0

    @pytest.mark.asyncio
    async def test_frequently_accessed_survives(self, mm: MemoryManager):
        node = await mm.add_episodic_memory(
            user_id="u1", content="经常想起", summary="频繁", importance=0.3
        )
        node.last_accessed = datetime.now() - timedelta(days=30)
        node.access_count = 10  # 频繁访问
        removed = await mm.apply_forget_curve("u1")
        assert removed == 0

    @pytest.mark.asyncio
    async def test_only_affects_episodic_and_semantic(self, mm: MemoryManager):
        """遗忘曲线不应影响事实记忆"""
        await mm.add_fact_memory("u1", "重要事实", importance=0.1)
        await mm.apply_forget_curve("u1")
        facts = await mm.get_fact_memories("u1")
        assert len(facts) == 1  # 事实记忆不受影响


class TestConsolidation:
    """记忆固化测试"""

    @pytest.mark.asyncio
    async def test_high_frequency_upgrades(self, mm: MemoryManager):
        for i in range(5):
            await mm.add_episodic_memory(
                user_id="u1",
                content=f"讨论吉他 {i}",
                summary=f"吉他 {i}",
                topic_tags=["吉他"],
            )

        stats = await mm.consolidate_memories("u1")
        assert stats["upgraded"] >= 1

        facts = await mm.get_fact_memories("u1")
        assert len(facts) >= 1
        assert "吉他" in facts[0].content

    @pytest.mark.asyncio
    async def test_low_frequency_not_upgraded(self, mm: MemoryManager):
        await mm.add_episodic_memory(
            user_id="u1",
            content="偶尔提到",
            summary="偶尔",
            topic_tags=["偶尔话题"],
        )

        stats = await mm.consolidate_memories("u1")
        assert stats["upgraded"] == 0

    @pytest.mark.asyncio
    async def test_consolidation_removes_episodic(self, mm: MemoryManager):
        """固化后应移除已合并的情景记忆"""
        for i in range(4):
            await mm.add_episodic_memory(
                user_id="u1",
                content=f"讨论编程 {i}",
                summary=f"编程 {i}",
                topic_tags=["编程"],
            )

        stats = await mm.consolidate_memories("u1")
        assert stats["removed"] >= 3  # 至少移除3条

        episodic = mm._episodic_memories.get("u1", [])
        # 不应再有编程相关的情景记忆
        for node in episodic:
            assert "编程" not in node.topic_tags


class TestUserProfileManagement:
    """用户画像管理测试"""

    @pytest.mark.asyncio
    async def test_create_profile(self, mm: MemoryManager):
        profile = await mm.get_or_create_user_profile("u1")
        assert profile.user_id == "u1"
        assert profile.total_interactions == 1
        assert profile.first_interaction is not None

    @pytest.mark.asyncio
    async def test_increment_interactions(self, mm: MemoryManager):
        for _ in range(5):
            await mm.get_or_create_user_profile("u1")
        profile = await mm.get_or_create_user_profile("u1")
        assert profile.total_interactions == 6

    @pytest.mark.asyncio
    async def test_update_last_interaction(self, mm: MemoryManager):
        profile1 = await mm.get_or_create_user_profile("u1")
        old_time = profile1.last_interaction

        import time
        time.sleep(0.01)
        profile2 = await mm.get_or_create_user_profile("u1")
        assert profile2.last_interaction >= old_time

    @pytest.mark.asyncio
    async def test_relationship_stage(self, mm: MemoryManager):
        await mm.update_relationship_stage("u1", "familiar")
        profile = await mm.get_or_create_user_profile("u1")
        assert profile.relationship_stage == "familiar"

    @pytest.mark.asyncio
    async def test_relationship_stage_progression(self, mm: MemoryManager):
        stages = ["initial", "familiar", "intimate", "deep"]
        for stage in stages:
            await mm.update_relationship_stage("u1", stage)
        profile = await mm.get_or_create_user_profile("u1")
        assert profile.relationship_stage == "deep"


class TestGetTimeOfDay:
    """时段测试"""

    def test_returns_valid_value(self):
        result = MemoryManager._get_time_of_day()
        assert result in ["凌晨", "上午", "中午", "下午", "晚上", "深夜"]
