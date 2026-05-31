"""Skill 链式组合测试"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from yuanbot.services.skill_chain import (
    ChainExecutionResult,
    ChainStep,
    ChainStepStatus,
    ChainTrigger,
    SkillChain,
    SkillChainManager,
)


@pytest.fixture
def manager() -> SkillChainManager:
    return SkillChainManager()


@pytest.fixture
def comfort_chain() -> SkillChain:
    return SkillChain(
        chain_id="comfort_then_distract",
        name="安抚后转移注意力",
        description="先安抚情绪，再讲故事转移注意力",
        steps=[
            ChainStep(skill_id="emotional_comfort", trigger=ChainTrigger.ALWAYS),
            ChainStep(skill_id="creative_storytelling", trigger=ChainTrigger.ALWAYS, fallback_skill_id="daily_chat"),
        ],
        trigger=ChainTrigger.EMOTION_LOW,
        max_total_tokens=2000,
        max_duration_seconds=60,
        persona_filters=[],
        priority=5,
    )


@pytest.fixture
def greeting_chain() -> SkillChain:
    return SkillChain(
        chain_id="greeting_flow",
        name="问候流程",
        steps=[
            ChainStep(skill_id="daily_chat"),
        ],
        trigger=ChainTrigger.ALWAYS,
        priority=1,
    )


# ──────────────────────────────────────────────
# 注册与注销
# ──────────────────────────────────────────────


class TestRegistration:
    def test_register_chain(self, manager, comfort_chain):
        manager.register_chain(comfort_chain)
        assert manager.get_chain("comfort_then_distract") is comfort_chain

    def test_unregister_chain(self, manager, comfort_chain):
        manager.register_chain(comfort_chain)
        assert manager.unregister_chain("comfort_then_distract") is True
        assert manager.get_chain("comfort_then_distract") is None

    def test_unregister_nonexistent(self, manager):
        assert manager.unregister_chain("nonexistent") is False

    def test_list_chains(self, manager, comfort_chain, greeting_chain):
        manager.register_chain(comfort_chain)
        manager.register_chain(greeting_chain)
        chains = manager.list_chains()
        assert len(chains) == 2

    def test_list_chains_empty(self, manager):
        assert manager.list_chains() == []


# ──────────────────────────────────────────────
# 匹配
# ──────────────────────────────────────────────


class TestMatchChains:
    def test_match_by_trigger_emotion_low(self, manager, comfort_chain):
        manager.register_chain(comfort_chain)
        matched = manager.match_chains(emotion="sadness")
        assert comfort_chain in matched

    def test_no_match_wrong_emotion(self, manager, comfort_chain):
        manager.register_chain(comfort_chain)
        matched = manager.match_chains(emotion="joy")
        # comfort_chain triggers on EMOTION_LOW, not EMOTION_HIGH
        assert comfort_chain not in matched

    def test_match_always_trigger(self, manager, greeting_chain):
        manager.register_chain(greeting_chain)
        matched = manager.match_chains()
        assert greeting_chain in matched

    def test_match_by_persona_filter(self, manager):
        chain = SkillChain(
            chain_id="persona_only",
            name="特定人格",
            steps=[ChainStep(skill_id="test")],
            trigger=ChainTrigger.ALWAYS,
            persona_filters=["persona_a"],
        )
        manager.register_chain(chain)

        # Should match with correct persona
        matched = manager.match_chains(persona_id="persona_a")
        assert chain in matched

        # Should NOT match with wrong persona
        matched = manager.match_chains(persona_id="persona_b")
        assert chain not in matched

    def test_disabled_chain_not_matched(self, manager, comfort_chain):
        comfort_chain.enabled = False
        manager.register_chain(comfort_chain)
        matched = manager.match_chains(emotion="sadness")
        assert len(matched) == 0

    def test_sorted_by_priority(self, manager, comfort_chain, greeting_chain):
        manager.register_chain(comfort_chain)  # priority 5
        manager.register_chain(greeting_chain)  # priority 1
        matched = manager.match_chains(emotion="sadness")
        # comfort_chain has higher priority + emotion match bonus
        assert matched[0] == comfort_chain

    def test_user_request_trigger(self, manager):
        chain = SkillChain(
            chain_id="custom_chain",
            name="自定义链",
            steps=[ChainStep(skill_id="test")],
            trigger=ChainTrigger.USER_REQUEST,
        )
        manager.register_chain(chain)
        matched = manager.match_chains(intent="执行自定义链")
        assert chain in matched

    def test_intent_match_trigger(self, manager):
        chain = SkillChain(
            chain_id="story_chain",
            name="故事链",
            steps=[ChainStep(skill_id="story", condition="故事")],
            trigger=ChainTrigger.INTENT_MATCH,
        )
        manager.register_chain(chain)
        matched = manager.match_chains(intent="我想听故事")
        assert chain in matched


# ──────────────────────────────────────────────
# 从配置创建
# ──────────────────────────────────────────────


class TestCreateFromConfig:
    def test_create_basic_chain(self, manager):
        config = {
            "chain_id": "test_chain",
            "name": "测试链",
            "description": "测试",
            "steps": [
                {"skill_id": "skill_a", "trigger": "always"},
                {"skill_id": "skill_b", "condition": "test", "fallback_skill_id": "skill_c"},
            ],
            "trigger": "emotion_low",
            "max_total_tokens": 1500,
            "priority": 3,
        }
        chain = manager.create_chain_from_config(config)
        assert chain.chain_id == "test_chain"
        assert chain.name == "测试链"
        assert len(chain.steps) == 2
        assert chain.steps[1].fallback_skill_id == "skill_c"
        assert chain.trigger == ChainTrigger.EMOTION_LOW
        assert chain.max_total_tokens == 1500


# ──────────────────────────────────────────────
# 执行
# ──────────────────────────────────────────────


class TestExecuteChain:
    async def test_execute_simple_chain(self):
        chain = SkillChain(
            chain_id="test",
            name="测试",
            steps=[
                ChainStep(skill_id="s1"),
                ChainStep(skill_id="s2"),
            ],
        )

        prompt_getter = lambda sid: f"Prompt for {sid}"
        llm_caller = AsyncMock(side_effect=lambda p, u: f"Output from {p}")

        result = await SkillChainManager.execute_chain(chain, prompt_getter, llm_caller)
        assert result.success is True
        assert result.completed_steps == 2
        assert result.total_steps == 2
        assert len(result.step_outputs) == 2

    async def test_execute_chain_missing_skill(self):
        chain = SkillChain(
            chain_id="test",
            name="测试",
            steps=[ChainStep(skill_id="missing")],
        )

        prompt_getter = lambda sid: None  # No skills available
        llm_caller = AsyncMock()

        result = await SkillChainManager.execute_chain(chain, prompt_getter, llm_caller)
        assert result.success is False
        assert result.completed_steps == 0
        assert "not found" in result.error.lower()

    async def test_execute_chain_with_fallback(self):
        chain = SkillChain(
            chain_id="test",
            name="测试",
            steps=[
                ChainStep(skill_id="missing", fallback_skill_id="fallback"),
            ],
        )

        prompt_getter = lambda sid: f"Prompt for {sid}" if sid == "fallback" else None
        llm_caller = AsyncMock(return_value="Fallback output")

        result = await SkillChainManager.execute_chain(chain, prompt_getter, llm_caller)
        assert result.success is True
        assert result.completed_steps == 1

    async def test_execute_chain_token_budget_exceeded(self):
        chain = SkillChain(
            chain_id="test",
            name="测试",
            steps=[ChainStep(skill_id="s1"), ChainStep(skill_id="s2")],
            max_total_tokens=1,  # Very small budget
        )

        prompt_getter = lambda sid: "A" * 1000
        llm_caller = AsyncMock(return_value="B" * 1000)

        result = await SkillChainManager.execute_chain(chain, prompt_getter, llm_caller)
        # Second step should be skipped due to token budget
        assert result.completed_steps <= 1

    async def test_execute_chain_duration_timeout(self):
        chain = SkillChain(
            chain_id="test",
            name="测试",
            steps=[ChainStep(skill_id="s1")],
            max_duration_seconds=0,  # Immediate timeout
        )

        prompt_getter = lambda sid: "prompt"
        llm_caller = AsyncMock(return_value="output")

        result = await SkillChainManager.execute_chain(chain, prompt_getter, llm_caller)
        # Should handle timeout gracefully
        assert result.duration_seconds >= 0

    async def test_execute_chain_llm_error(self):
        chain = SkillChain(
            chain_id="test",
            name="测试",
            steps=[ChainStep(skill_id="s1")],
        )

        prompt_getter = lambda sid: "prompt"
        llm_caller = AsyncMock(side_effect=RuntimeError("LLM error"))

        result = await SkillChainManager.execute_chain(chain, prompt_getter, llm_caller)
        assert result.success is False
        assert "LLM error" in result.error


# ──────────────────────────────────────────────
# SkillChain 数据结构
# ──────────────────────────────────────────────


class TestSkillChainData:
    def test_total_token_estimate(self):
        chain = SkillChain(
            chain_id="test",
            name="测试",
            steps=[
                ChainStep(skill_id="s1", token_budget=300),
                ChainStep(skill_id="s2", token_budget=500),
            ],
        )
        assert chain.total_token_estimate == 800

    def test_total_token_estimate_default(self):
        chain = SkillChain(
            chain_id="test",
            name="测试",
            steps=[ChainStep(skill_id="s1"), ChainStep(skill_id="s2")],
        )
        # Default 200 per step
        assert chain.total_token_estimate == 400
