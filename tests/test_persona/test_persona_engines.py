"""测试人格与行为决策系统引擎"""

from __future__ import annotations

import pytest

from yuanbot.core.types import MemoryNode, MemorySearchResult, MemoryType, UserProfile
from yuanbot.persona.default import DefaultPersona
from yuanbot.persona.engines.context_builder import ContextBuilder
from yuanbot.persona.engines.dialogue_decision import DecisionResult, DialogueDecisionEngine
from yuanbot.persona.engines.emotion_engine import EmotionEngine
from yuanbot.persona.engines.intent_engine import IntentEngine
from yuanbot.persona.engines.token_budget import TokenBudgetManager


class TestIntentEngine:
    """意图识别引擎测试"""

    def test_empty_input(self):
        engine = IntentEngine()
        result = engine.recognize("")
        assert result.primary == "empty"

    def test_greeting(self):
        engine = IntentEngine()
        result = engine.recognize("你好")
        assert result.primary == "greeting"
        assert result.confidence > 0

    def test_emotional_comfort(self):
        engine = IntentEngine()
        result = engine.recognize("我今天很难过，压力好大")
        assert result.primary == "emotional_seeking_comfort"

    def test_seeking_advice(self):
        engine = IntentEngine()
        result = engine.recognize("你觉得我应该怎么办？")
        assert result.primary == "seeking_advice"

    def test_command_pattern(self):
        engine = IntentEngine()
        result = engine.recognize("/set_reminder 10:00 吃药")
        assert result.primary == "set_reminder"
        assert result.confidence >= 0.99

    def test_casual_chat(self):
        engine = IntentEngine()
        result = engine.recognize("无聊，聊聊吧")
        assert result.primary == "casual_chat"

    def test_gratitude(self):
        engine = IntentEngine()
        result = engine.recognize("谢谢你！")
        assert result.primary == "expressing_gratitude"

    def test_unknown_intent(self):
        engine = IntentEngine()
        result = engine.recognize("asdfghjkl")
        assert result.primary == "unknown"

    def test_multiple_intents(self):
        engine = IntentEngine()
        result = engine.recognize("我很开心，谢谢你")
        assert result.primary in ("emotional_sharing_joy", "expressing_gratitude")
        # 应该有次要意图
        assert isinstance(result.secondary, list)


class TestEmotionEngine:
    """情感分析引擎测试"""

    @pytest.mark.asyncio
    async def test_analyze_joy(self):
        engine = EmotionEngine()
        state = await engine.analyze("太好了！我好开心！", "user1", "session1")
        assert state.emotion.value == "joy"

    @pytest.mark.asyncio
    async def test_analyze_sadness(self):
        engine = EmotionEngine()
        state = await engine.analyze("我很难过，心里不舒服", "user1", "session1")
        assert state.emotion.value == "sadness"

    @pytest.mark.asyncio
    async def test_analyze_neutral(self):
        engine = EmotionEngine()
        state = await engine.analyze("今天天气不错", "user1", "session1")
        assert state.emotion.value == "neutral"

    @pytest.mark.asyncio
    async def test_needs_comfort(self):
        engine = EmotionEngine()
        state = await engine.analyze("我非常难过，想哭", "user1", "session1")
        needs = await engine.needs_comfort(state)
        assert needs is True

    @pytest.mark.asyncio
    async def test_response_strategy_comfort(self):
        engine = EmotionEngine()
        state = await engine.analyze("我很难过", "user1", "session1")
        strategy = await engine.get_response_strategy(state)
        assert strategy in ("comfort", "gentle_engage")

    @pytest.mark.asyncio
    async def test_response_strategy_celebrate(self):
        engine = EmotionEngine()
        state = await engine.analyze("太好了！我成功了！", "user1", "session1")
        strategy = await engine.get_response_strategy(state)
        assert strategy == "celebrate"

    @pytest.mark.asyncio
    async def test_get_dominant_emotion(self):
        engine = EmotionEngine()
        await engine.analyze("开心", "user1", "session1")
        dominant = await engine.get_dominant_emotion("user1", "session1")
        assert dominant.value == "joy"


class TestDialogueDecisionEngine:
    """对话决策引擎测试"""

    @pytest.mark.asyncio
    async def test_decide_comfort_scenario(self):
        engine = DialogueDecisionEngine()
        result = await engine.decide("我今天很难过", "user1", "session1")
        assert isinstance(result, DecisionResult)
        assert result.response_strategy in ("comfort", "gentle_engage")
        assert result.intent.primary == "emotional_seeking_comfort"

    @pytest.mark.asyncio
    async def test_decide_celebrate_scenario(self):
        engine = DialogueDecisionEngine()
        result = await engine.decide("太好了！我通过考试了！", "user1", "session1")
        assert result.response_strategy == "celebrate"

    @pytest.mark.asyncio
    async def test_decide_neutral_scenario(self):
        engine = DialogueDecisionEngine()
        result = await engine.decide("今天天气怎么样", "user1", "session1")
        assert isinstance(result, DecisionResult)

    @pytest.mark.asyncio
    async def test_decide_recommends_skills(self):
        engine = DialogueDecisionEngine()
        result = await engine.decide("我很难过", "user1", "session1")
        assert "emotional_comfort" in result.should_use_skills


class TestContextBuilder:
    """上下文组装器测试"""

    def test_build_basic_prompt(self):
        persona = DefaultPersona()
        builder = ContextBuilder(persona)
        prompt = builder.build_system_prompt()
        assert "小缘" in prompt

    def test_build_with_user_profile(self):
        persona = DefaultPersona()
        builder = ContextBuilder(persona)
        profile = UserProfile(
            user_id="user1",
            display_name="小明",
            preferences={"favorite_color": "blue"},
        )
        prompt = builder.build_system_prompt(user_profile=profile)
        assert "小明" in prompt
        assert "blue" in prompt

    def test_build_with_memories(self):
        persona = DefaultPersona()
        builder = ContextBuilder(persona)
        memories = [
            MemorySearchResult(
                node=MemoryNode(
                    memory_type=MemoryType.EPISODIC,
                    content="聊过工作压力",
                    summary="用户提到工作压力很大",
                ),
                score=0.9,
                match_type="semantic",
            )
        ]
        prompt = builder.build_system_prompt(relevant_memories=memories)
        assert "工作压力" in prompt

    def test_build_with_emotion(self):
        persona = DefaultPersona()
        builder = ContextBuilder(persona)
        prompt = builder.build_system_prompt(emotion="positive")
        assert "positive" in prompt

    def test_build_with_strategy(self):
        persona = DefaultPersona()
        builder = ContextBuilder(persona)
        prompt = builder.build_system_prompt(response_strategy="comfort")
        assert "温暖" in prompt or "共情" in prompt


class TestTokenBudgetManager:
    """Token 预算管理器测试"""

    def test_estimate_tokens(self):
        manager = TokenBudgetManager()
        tokens = manager.estimate_tokens("你好世界")
        assert tokens > 0

    def test_available_tokens(self):
        manager = TokenBudgetManager(max_tokens=1000, response_reserve=200)
        assert manager.available_tokens == 800

    def test_allocate_within_budget(self):
        manager = TokenBudgetManager(max_tokens=10000, response_reserve=1000)
        sections = {
            "persona": "你是小缘" * 10,
            "memory": "记忆内容" * 5,
        }
        result = manager.allocate_budget(sections)
        assert "persona" in result

    def test_allocate_truncates_low_priority(self):
        manager = TokenBudgetManager(max_tokens=200, response_reserve=50)
        sections = {
            "high": "重要",
            "low": "不重要的内容" * 100,
        }
        priorities = {"high": "high", "low": "low"}
        result = manager.allocate_budget(sections, priorities)
        assert "high" in result

    def test_budget_status(self):
        manager = TokenBudgetManager()
        status = manager.get_budget_status()
        assert "max_tokens" in status
        assert "available_tokens" in status
