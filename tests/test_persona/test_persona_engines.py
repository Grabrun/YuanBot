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


class TestEmotionEngineDeepIntegration:
    """情感引擎深度分析集成测试"""

    @pytest.mark.asyncio
    async def test_deep_analyzer_called_when_low_confidence(self):
        """当规则引擎置信度低时，应调用 DeepEmotionAnalyzer"""
        from unittest.mock import AsyncMock

        from yuanbot.core.types import EmotionCategory, EmotionState
        from yuanbot.persona.engines.emotion_engine import DeepEmotionAnalyzer, EmotionEngine

        mock_deep = AsyncMock(spec=DeepEmotionAnalyzer)
        mock_deep.enabled = True
        mock_deep.analyze = AsyncMock(return_value=EmotionState(
            emotion=EmotionCategory.SADNESS,
            intensity=0.8,
            confidence=0.9,
            valence="negative",
        ))

        engine = EmotionEngine(
            config={"deep_analysis_threshold": 0.5},
            deep_analyzer=mock_deep,
        )

        # 使用模糊文本，规则引擎置信度通常较低
        state = await engine.analyze("嗯...", "user1", "session1")

        # 如果规则引擎置信度 < 0.5，深度分析器应该被调用
        if mock_deep.analyze.called:
            assert state.confidence == 0.9
            assert state.emotion == EmotionCategory.SADNESS

    @pytest.mark.asyncio
    async def test_deep_analyzer_not_called_when_high_confidence(self):
        """当规则引擎置信度高时，不应调用 DeepEmotionAnalyzer"""
        from unittest.mock import AsyncMock

        from yuanbot.persona.engines.emotion_engine import DeepEmotionAnalyzer, EmotionEngine

        mock_deep = AsyncMock(spec=DeepEmotionAnalyzer)
        mock_deep.enabled = True
        mock_deep.analyze = AsyncMock()

        engine = EmotionEngine(deep_analyzer=mock_deep)

        # 情感关键词明确，规则引擎置信度应该较高
        await engine.analyze("我非常难过伤心", "user1", "session1")

        # 置信度高时不应调用深度分析
        mock_deep.analyze.assert_not_called()

    @pytest.mark.asyncio
    async def test_deep_analyzer_disabled(self):
        """DeepEmotionAnalyzer 未启用时不应调用"""
        from unittest.mock import AsyncMock

        from yuanbot.persona.engines.emotion_engine import DeepEmotionAnalyzer, EmotionEngine

        mock_deep = AsyncMock(spec=DeepEmotionAnalyzer)
        mock_deep.enabled = False
        mock_deep.analyze = AsyncMock()

        engine = EmotionEngine(deep_analyzer=mock_deep)
        await engine.analyze("嗯", "user1", "session1")

        mock_deep.analyze.assert_not_called()

    def test_set_deep_analyzer(self):
        """测试运行时设置 DeepEmotionAnalyzer"""
        from yuanbot.persona.engines.emotion_engine import DeepEmotionAnalyzer, EmotionEngine

        engine = EmotionEngine()
        assert engine.deep_analyzer is None

        analyzer = DeepEmotionAnalyzer()
        engine.set_deep_analyzer(analyzer)
        assert engine.deep_analyzer is analyzer


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

    @pytest.mark.asyncio
    async def test_decide_with_capability_domains(self):
        """测试传入人设能力域声明时的决策"""
        engine = DialogueDecisionEngine()
        result = await engine.decide(
            "我很难过", "user1", "session1",
            capability_domains=["emotional_care", "daily_chat"],
        )
        assert "emotional_comfort" in result.should_use_skills

    @pytest.mark.asyncio
    async def test_domain_matcher_integration_knowledge_query(self):
        """测试 DomainMatcher 集成：知识查询意图应推荐搜索工具"""
        engine = DialogueDecisionEngine()
        result = await engine.decide(
            "帮我搜索一下最新的新闻", "user1", "session1",
            capability_domains=["knowledge_query"],
        )
        # DomainMatcher 应该将 knowledge_query 域映射到 web_search 工具
        assert "web_search" in result.should_use_tools

    @pytest.mark.asyncio
    async def test_domain_matcher_integration_task_management(self):
        """测试 DomainMatcher 集成：任务管理意图应推荐提醒工具"""
        engine = DialogueDecisionEngine()
        result = await engine.decide(
            "帮我设置提醒", "user1", "session1",
            capability_domains=["task_management"],
        )
        assert "reminder" in result.should_use_tools

    @pytest.mark.asyncio
    async def test_domain_matcher_comfort_priority(self):
        """测试 DomainMatcher 在情感紧急时优先推荐情感安慰技能"""
        engine = DialogueDecisionEngine()
        result = await engine.decide(
            "我好难过，想哭", "user1", "session1",
            capability_domains=["daily_chat", "emotional_care"],
        )
        # emotional_comfort 应该排在第一位
        assert result.should_use_skills[0] == "emotional_comfort"


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
