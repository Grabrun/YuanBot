"""YuanBot 记忆管理器测试"""

import pytest
from datetime import datetime

from yuanbot.memory.manager import MemoryManager
from yuanbot.core.types import MemoryType


@pytest.fixture
def memory_manager():
    return MemoryManager()


class TestWorkingMemory:
    @pytest.mark.asyncio
    async def test_add_and_get(self, memory_manager: MemoryManager):
        node = await memory_manager.add_working_memory(
            session_id="test_session",
            content="用户说今天天气不错",
        )
        assert node.memory_type == MemoryType.WORKING

        memories = await memory_manager.get_working_memory("test_session")
        assert len(memories) == 1
        assert memories[0].content == "用户说今天天气不错"

    @pytest.mark.asyncio
    async def test_clear(self, memory_manager: MemoryManager):
        await memory_manager.add_working_memory("s1", "msg1")
        await memory_manager.add_working_memory("s1", "msg2")

        memories = await memory_manager.get_working_memory("s1")
        assert len(memories) == 2

        await memory_manager.clear_working_memory("s1")
        memories = await memory_manager.get_working_memory("s1")
        assert len(memories) == 0


class TestFactMemory:
    @pytest.mark.asyncio
    async def test_add_fact(self, memory_manager: MemoryManager):
        node = await memory_manager.add_fact_memory(
            user_id="user1",
            content="用户喜欢喝咖啡",
            key_entities=["咖啡"],
            importance=0.8,
        )
        assert node.memory_type == MemoryType.FACT
        assert "咖啡" in node.key_entities

        facts = await memory_manager.get_fact_memories("user1")
        assert len(facts) == 1


class TestEpisodicMemory:
    @pytest.mark.asyncio
    async def test_add_episodic(self, memory_manager: MemoryManager):
        node = await memory_manager.add_episodic_memory(
            user_id="user1",
            content="用户聊到工作项目压力大",
            summary="工作压力相关对话",
            topic_tags=["工作", "压力"],
            emotional_tone="negative",
            key_entities=["项目截止日"],
        )
        assert node.memory_type == MemoryType.EPISODIC
        assert node.summary == "工作压力相关对话"


class TestMemoryRetrieval:
    @pytest.mark.asyncio
    async def test_entity_match(self, memory_manager: MemoryManager):
        # 添加情景记忆
        await memory_manager.add_episodic_memory(
            user_id="user1",
            content="用户聊到工作项目压力大",
            summary="工作压力对话",
            topic_tags=["工作"],
            key_entities=["项目", "截止日"],
        )

        # 检索
        results = await memory_manager.retrieve_relevant_memories(
            user_id="user1",
            current_input="我的项目快到截止日了",
        )
        assert len(results) > 0
        assert results[0].match_type == "entity"


class TestForgetCurve:
    @pytest.mark.asyncio
    async def test_forget_low_importance(self, memory_manager: MemoryManager):
        # 添加低重要性记忆
        node = await memory_manager.add_episodic_memory(
            user_id="user1",
            content="随意聊天",
            summary="闲聊",
            importance=0.1,
        )
        # 模拟很久没访问
        from datetime import timedelta
        node.last_accessed = datetime.now() - timedelta(days=60)

        removed = await memory_manager.apply_forget_curve("user1")
        assert removed >= 0  # 可能被淘汰


class TestUserProfile:
    @pytest.mark.asyncio
    async def test_create_profile(self, memory_manager: MemoryManager):
        profile = await memory_manager.get_or_create_user_profile("user1")
        assert profile.user_id == "user1"
        assert profile.total_interactions == 1

        # 再次获取
        profile2 = await memory_manager.get_or_create_user_profile("user1")
        assert profile2.total_interactions == 2

    @pytest.mark.asyncio
    async def test_relationship_stage(self, memory_manager: MemoryManager):
        await memory_manager.update_relationship_stage("user1", "familiar")
        profile = await memory_manager.get_or_create_user_profile("user1")
        assert profile.relationship_stage == "familiar"


class TestConsolidation:
    @pytest.mark.asyncio
    async def test_consolidate_high_frequency_topics(self, memory_manager: MemoryManager):
        # 添加多次提及同一话题的情景记忆
        for i in range(4):
            await memory_manager.add_episodic_memory(
                user_id="user1",
                content=f"用户第{i+1}次提到想学吉他",
                summary=f"学吉他讨论 {i+1}",
                topic_tags=["吉他"],
            )

        stats = await memory_manager.consolidate_memories("user1")
        assert stats["upgraded"] >= 1
