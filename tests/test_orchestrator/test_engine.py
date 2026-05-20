"""YuanBot 编排引擎测试"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from yuanbot.core.interfaces import AIProviderAdapter, PersonaProfile, SkillMetadata
from yuanbot.core.types import (
    BotResponse,
    ChatChunk,
    ChatResponse,
    ContentType,
    Message,
    TokenUsage,
    UserMessage,
)
from yuanbot.memory.manager import MemoryManager
from yuanbot.orchestrator.engine import OrchestratorEngine


class MockPersona(PersonaProfile):
    """测试用 Persona"""

    @property
    def persona_id(self) -> str:
        return "test"

    @property
    def name(self) -> str:
        return "测试人设"

    def get_system_prompt(self) -> str:
        return "你是测试助手"

    def get_behavior_rules(self) -> list[str]:
        return ["保持友好", "回答简洁"]

    def get_voice_style(self) -> dict[str, Any]:
        return {"tone": "友好"}

    def get_capability_domains(self) -> list[str]:
        return ["test"]

    def should_use_skill(self, skill_metadata: SkillMetadata) -> bool:
        return True


class MockAIProvider(AIProviderAdapter):
    """测试用 AI 提供商"""

    def __init__(self, response_content: str = "测试回复"):
        self._response_content = response_content

    async def chat_completion(
        self,
        messages: list[Message],
        tools: list[...] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system_prompt: str | None = None,
    ) -> ChatResponse:
        return ChatResponse(
            content=self._response_content,
            finish_reason="stop",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )

    async def stream_chat_completion(self, *args, **kwargs):
        yield ChatChunk(delta_content=self._response_content)

    async def get_embedding(self, text: str, model: str | None = None) -> list[float]:
        return [0.1, 0.2, 0.3]

    @property
    def supported_models(self) -> list[str]:
        return ["test-model"]

    @property
    def max_context_length(self) -> int:
        return 1000

    @property
    def provider_id(self) -> str:
        return "test"


def _make_user_message(text: str = "你好") -> UserMessage:
    return UserMessage(
        platform="test",
        platform_user_id="test_user",
        yuanbot_user_id="yb_test_user",
        session_id="test:test_user",
        content_type=ContentType.TEXT,
        text=text,
    )


@pytest.fixture
def engine():
    from unittest.mock import AsyncMock

    mock_ai = AsyncMock()
    mock_ai.generate = AsyncMock(return_value=ChatResponse(
        content="你好呀~",
        finish_reason="stop",
        model="mock-model",
    ))
    mock_ai.embed = AsyncMock(return_value=[0.1] * 16)
    persona = MockPersona()
    memory = MemoryManager()
    return OrchestratorEngine(ai_service=mock_ai, persona=persona, memory_manager=memory)


class TestProcessMessage:
    """消息处理流水线测试"""

    @pytest.mark.asyncio
    async def test_basic_message(self, engine: OrchestratorEngine):
        msg = _make_user_message("你好")
        response = await engine.process_message(msg)

        assert isinstance(response, BotResponse)
        assert response.content.content_type == ContentType.TEXT
        assert response.content.text == "你好呀~"

    @pytest.mark.asyncio
    async def test_empty_text(self, engine: OrchestratorEngine):
        msg = _make_user_message("")
        msg.text = None
        msg.media_url = "https://example.com/img.png"
        response = await engine.process_message(msg)
        assert response.content is not None

    @pytest.mark.asyncio
    async def test_working_memory_updated(self, engine: OrchestratorEngine):
        msg = _make_user_message("测试消息")
        await engine.process_message(msg)

        memories = await engine._memory.get_working_memory(msg.session_id)
        assert len(memories) == 2  # 用户消息 + AI回复
        assert any("[用户]" in m.content for m in memories)
        assert any("[AI]" in m.content for m in memories)

    @pytest.mark.asyncio
    async def test_user_profile_created(self, engine: OrchestratorEngine):
        msg = _make_user_message("你好")
        await engine.process_message(msg)

        profile = await engine._memory.get_or_create_user_profile(msg.yuanbot_user_id)
        assert profile.total_interactions >= 1


class TestAnalyzeEmotion:
    """情感分析测试（通过 DialogueDecisionEngine）"""

    @pytest.mark.asyncio
    async def test_positive_emotion(self):
        from yuanbot.persona.engines.dialogue_decision import DialogueDecisionEngine

        engine = DialogueDecisionEngine()
        result = await engine.decide("今天好开心呀！太好了", "u1", "s1")
        assert result.emotion_state is not None
        assert result.emotion_state.valence == "positive"

    @pytest.mark.asyncio
    async def test_negative_emotion(self):
        from yuanbot.persona.engines.dialogue_decision import DialogueDecisionEngine

        engine = DialogueDecisionEngine()
        result = await engine.decide("好难过，压力好大", "u1", "s1")
        assert result.emotion_state is not None
        assert result.emotion_state.valence == "negative"

    @pytest.mark.asyncio
    async def test_neutral_emotion(self):
        from yuanbot.persona.engines.dialogue_decision import DialogueDecisionEngine

        engine = DialogueDecisionEngine()
        result = await engine.decide("今天天气怎么样", "u1", "s1")
        assert result.emotion_state is not None
        assert result.emotion_state.valence == "neutral"

    @pytest.mark.asyncio
    async def test_empty_text(self):
        from yuanbot.persona.engines.dialogue_decision import DialogueDecisionEngine

        engine = DialogueDecisionEngine()
        result = await engine.decide("", "u1", "s1")
        assert result.emotion_state is not None
        assert result.emotion_state.emotion.value == "neutral"



class TestBuildSystemPrompt:
    """系统提示词组装测试（通过 ContextBuilder）"""

    def test_includes_persona(self):
        from yuanbot.persona.default import DefaultPersona
        from yuanbot.persona.engines.context_builder import ContextBuilder
        from yuanbot.core.types import UserProfile

        persona = DefaultPersona()
        builder = ContextBuilder(persona)
        profile = UserProfile(user_id="u1")
        prompt = builder.build_system_prompt(user_profile=profile)
        assert "小缘" in prompt

    def test_includes_user_info(self):
        from yuanbot.persona.default import DefaultPersona
        from yuanbot.persona.engines.context_builder import ContextBuilder
        from yuanbot.core.types import UserProfile

        persona = DefaultPersona()
        builder = ContextBuilder(persona)
        profile = UserProfile(
            user_id="u1",
            display_name="小明",
            preferences={"color": "蓝色"},
            relationship_stage="familiar",
        )
        prompt = builder.build_system_prompt(user_profile=profile)
        assert "小明" in prompt
        assert "蓝色" in prompt
        assert "familiar" in prompt

    def test_includes_behavior_rules(self):
        from yuanbot.persona.default import DefaultPersona
        from yuanbot.persona.engines.context_builder import ContextBuilder
        from yuanbot.core.types import UserProfile

        persona = DefaultPersona()
        builder = ContextBuilder(persona)
        profile = UserProfile(user_id="u1")
        prompt = builder.build_system_prompt(user_profile=profile)
        assert "共情" in prompt

    def test_includes_emotion(self):
        from yuanbot.persona.default import DefaultPersona
        from yuanbot.persona.engines.context_builder import ContextBuilder
        from yuanbot.core.types import UserProfile, EmotionState, EmotionCategory

        persona = DefaultPersona()
        builder = ContextBuilder(persona)
        profile = UserProfile(user_id="u1")
        emotion = EmotionState(emotion=EmotionCategory.SADNESS, intensity=0.8, valence="negative")
        prompt = builder.build_system_prompt(user_profile=profile, emotion=emotion)
        assert "sadness" in prompt


class TestBuildMessages:
    """消息构建测试"""

    def test_user_messages(self):
        from yuanbot.core.types import MemoryNode, MemoryType

        nodes = [
            MemoryNode(memory_type=MemoryType.WORKING, content="[用户] 你好"),
        ]
        messages = OrchestratorEngine._build_messages(nodes)
        assert len(messages) == 1
        assert messages[0].role == "user"
        assert messages[0].content == "你好"

    def test_assistant_messages(self):
        from yuanbot.core.types import MemoryNode, MemoryType

        nodes = [
            MemoryNode(memory_type=MemoryType.WORKING, content="[AI] 你好呀"),
        ]
        messages = OrchestratorEngine._build_messages(nodes)
        assert len(messages) == 1
        assert messages[0].role == "assistant"
        assert messages[0].content == "你好呀"

    def test_mixed_messages(self):
        from yuanbot.core.types import MemoryNode, MemoryType

        nodes = [
            MemoryNode(memory_type=MemoryType.WORKING, content="[用户] 你好"),
            MemoryNode(memory_type=MemoryType.WORKING, content="[AI] 你好呀~"),
            MemoryNode(memory_type=MemoryType.WORKING, content="[用户] 今天天气怎么样"),
        ]
        messages = OrchestratorEngine._build_messages(nodes)
        assert len(messages) == 3
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"
        assert messages[2].role == "user"


class TestProactiveTasks:
    """主动交互任务测试"""

    @pytest.mark.asyncio
    async def test_negative_emotion_triggers_care(self, engine: OrchestratorEngine):
        from yuanbot.core.types import UserProfile, EmotionState, EmotionCategory

        profile = UserProfile(user_id="u1")
        emotion = EmotionState(emotion=EmotionCategory.SADNESS, intensity=0.8, valence="negative", needs_immediate_comfort=True)
        tasks = await engine._generate_proactive_tasks(profile, emotion)
        assert len(tasks) == 1
        assert tasks[0].task_type == "care"
        assert tasks[0].priority == 2

    @pytest.mark.asyncio
    async def test_positive_emotion_no_task(self, engine: OrchestratorEngine):
        from yuanbot.core.types import UserProfile, EmotionState, EmotionCategory

        profile = UserProfile(user_id="u1")
        emotion = EmotionState(emotion=EmotionCategory.JOY, intensity=0.8, valence="positive")
        tasks = await engine._generate_proactive_tasks(profile, emotion)
        assert len(tasks) == 0

    @pytest.mark.asyncio
    async def test_neutral_emotion_no_task(self, engine: OrchestratorEngine):
        from yuanbot.core.types import UserProfile, EmotionState, EmotionCategory

        profile = UserProfile(user_id="u1")
        emotion = EmotionState(emotion=EmotionCategory.NEUTRAL, intensity=0.3, valence="neutral")
        tasks = await engine._generate_proactive_tasks(profile, emotion)
        assert len(tasks) == 0


class TestChannelManagement:
    """通道管理测试"""

    def test_register_channel(self, engine: OrchestratorEngine):
        channel = MagicMock()
        channel.platform_name = "test"
        engine.register_channel(channel)
        assert engine.get_channel("test") is channel

    def test_get_nonexistent_channel(self, engine: OrchestratorEngine):
        assert engine.get_channel("nonexistent") is None
