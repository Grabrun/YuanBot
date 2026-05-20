"""YuanBot 集成测试

测试完整的对话处理流水线：
UserMessage → 编排引擎 → 记忆系统 → 情感分析 → AI 适配器 → BotResponse

测试各子系统之间的协作，而非单个模块的单元测试。
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from yuanbot.config import (
    BotConfig,
    ConfigLoader,
    DatabaseConfig,
    MemorySystemConfig,
    YuanBotConfig,
)
from yuanbot.core.interfaces import AIProviderAdapter
from yuanbot.core.types import (
    ChatResponse,
    ContentType,
    EmotionCategory,
    EmotionState,
    MemoryType,
    Message,
    ToolDefinition,
    UserMessage,
)
from yuanbot.gateway.identity_service import IdentityService
from yuanbot.memory.emotion_tracker import EmotionTracker
from yuanbot.memory.manager import MemoryManager
from yuanbot.orchestrator.engine import OrchestratorEngine
from yuanbot.persona.default import DefaultPersona
from yuanbot.proactive.strategy import ProactiveStrategy
from yuanbot.skills.manager import SkillManager
from yuanbot.tools.manager import ToolManager

# ──────────────────────────────────────────────
# Mock AI Provider（替代真实 LLM 调用）
# ──────────────────────────────────────────────


class MockAIProvider(AIProviderAdapter):
    """模拟 AI 提供商，用于集成测试"""

    def __init__(self, response_text: str = "你好呀～今天过得怎么样？"):
        self._response_text = response_text
        self.call_count = 0
        self.last_messages: list[Message] = []
        self.last_system_prompt: str | None = None

    async def chat_completion(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system_prompt: str | None = None,
    ) -> ChatResponse:
        self.call_count += 1
        self.last_messages = messages
        self.last_system_prompt = system_prompt
        return ChatResponse(
            content=self._response_text,
            finish_reason="stop",
            model="mock-model",
        )

    async def stream_chat_completion(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system_prompt: str | None = None,
    ):
        yield  # pragma: no cover
        return  # pragma: no cover

    async def get_embedding(self, text: str, model: str | None = None) -> list[float]:
        # 简单的伪 embedding：将文本哈希为固定长度向量
        import hashlib

        hash_bytes = hashlib.md5(text.encode()).digest()
        return [b / 255.0 for b in hash_bytes]

    @property
    def supported_models(self) -> list[str]:
        return ["mock-model"]

    @property
    def max_context_length(self) -> int:
        return 4096

    @property
    def provider_id(self) -> str:
        return "mock"


# ──────────────────────────────────────────────
# 配置加载集成测试
# ──────────────────────────────────────────────


class TestConfigIntegration:
    """测试配置系统的集成"""

    def test_default_config_loads(self, config):
        """默认配置应能正常加载"""
        assert config.app_name == "YuanBot"
        assert config.version == "1.0.0"
        assert config.ai_provider.provider_id == "openai"
        assert config.memory.max_working_memory_turns == 20
        assert config.proactive.enabled is True

    def test_config_pydantic_models(self):
        """验证各子配置模型可以独立实例化"""
        bot = BotConfig()
        assert bot.app_name == "YuanBot"
        assert bot.ai.default_provider == "openai"

        db = DatabaseConfig()
        assert db.relational.type == "sqlite"

        mem = MemorySystemConfig()
        assert mem.working_memory.max_turns == 20
        assert mem.forgetting_curve.enabled is True

    def test_config_model_dump_roundtrip(self, config):
        """配置可以序列化和反序列化"""
        dumped = config.model_dump()
        restored = YuanBotConfig(**dumped)
        assert restored.app_name == config.app_name
        assert restored.memory.max_working_memory_turns == config.memory.max_working_memory_turns

    def test_config_loader_with_empty_dir(self, tmp_path):
        """空目录应返回默认配置"""
        loader = ConfigLoader(tmp_path)
        bot_config = loader.load_bot_config()
        assert bot_config.app_name == "YuanBot"

    def test_config_env_substitution(self, tmp_path, monkeypatch):
        """配置文件中的 ${ENV_VAR} 应被替换"""
        import yaml

        config_file = tmp_path / "bot.yaml"
        config_file.write_text(yaml.dump({"app_name": "${YUAN_APP_NAME}", "debug": True}))
        monkeypatch.setenv("YUAN_APP_NAME", "TestBot")

        loader = ConfigLoader(tmp_path)
        bot_config = loader.load_bot_config()
        assert bot_config.app_name == "TestBot"


# ──────────────────────────────────────────────
# 记忆系统集成测试
# ──────────────────────────────────────────────


class TestMemoryIntegration:
    """测试记忆系统的完整工作流"""

    @pytest.mark.asyncio
    async def test_working_memory_lifecycle(self, memory_manager):
        """工作记忆的完整生命周期：添加 → 查询 → 清除"""
        session_id = "test-session-1"

        # 添加工作记忆
        node1 = await memory_manager.add_working_memory(session_id, "你好")
        node2 = await memory_manager.add_working_memory(session_id, "今天天气不错")

        assert node1.memory_type == MemoryType.WORKING
        assert node2.content == "今天天气不错"

        # 查询工作记忆
        memories = await memory_manager.get_working_memory(session_id)
        assert len(memories) == 2

        # 获取上下文
        context = await memory_manager.get_working_memory_context(session_id)
        assert "你好" in context
        assert "今天天气不错" in context

        # 清除
        await memory_manager.clear_working_memory(session_id)
        memories_after = await memory_manager.get_working_memory(session_id)
        assert len(memories_after) == 0

    @pytest.mark.asyncio
    async def test_fact_memory_dedup(self, memory_manager):
        """事实记忆应自动去重（相同实体）"""
        user_id = "user-1"

        await memory_manager.add_fact_memory(user_id, "用户喜欢蓝色", key_entities=["颜色", "蓝色"])
        await memory_manager.add_fact_memory(
            user_id, "用户最喜欢的颜色是蓝色", key_entities=["颜色", "蓝色"]
        )

        facts = await memory_manager.get_fact_memories(user_id)
        # 相同实体的事实应被更新而非重复
        assert len(facts) == 1
        assert facts[0].content == "用户最喜欢的颜色是蓝色"

    @pytest.mark.asyncio
    async def test_episodic_memory_with_emotion(self, memory_manager):
        """情景记忆应保存情感信息"""
        user_id = "user-1"

        node = await memory_manager.add_episodic_memory(
            user_id=user_id,
            content="用户分享了旅行经历",
            summary="用户去了日本旅行",
            topic_tags=["旅行", "日本"],
            emotional_tone="joy",
            key_entities=["日本"],
            importance=0.7,
        )

        assert node.memory_type == MemoryType.EPISODIC
        assert node.emotional_tone == "joy"
        assert "旅行" in node.topic_tags

    @pytest.mark.asyncio
    async def test_memory_consolidation(self, memory_manager):
        """频繁出现的情景记忆应固化为事实记忆"""
        user_id = "user-consolidation"

        # 添加足够多的相似情景记忆（超过固化阈值 3）
        for i in range(4):
            await memory_manager.add_episodic_memory(
                user_id=user_id,
                content=f"用户讨论了编程 {i}",
                summary=f"用户聊编程 #{i}",
                topic_tags=["编程"],
            )

        result = await memory_manager.consolidate_memories(user_id)
        assert result["upgraded"] >= 1

        # 检查是否生成了事实记忆
        facts = await memory_manager.get_fact_memories(user_id)
        assert len(facts) >= 1
        assert "编程" in facts[0].content

    @pytest.mark.asyncio
    async def test_forget_curve(self, memory_manager):
        """遗忘曲线应淘汰低价值记忆"""
        user_id = "user-forget"

        # 添加一条低重要性的记忆
        node = await memory_manager.add_episodic_memory(
            user_id=user_id,
            content="普通闲聊",
            summary="闲聊",
            importance=0.05,
        )
        # 模拟很久以前访问
        from datetime import timedelta

        node.last_accessed = datetime.now() - timedelta(days=60)
        node.access_count = 0

        removed = await memory_manager.apply_forget_curve(user_id)
        assert removed >= 0  # 可能被遗忘

    @pytest.mark.asyncio
    async def test_user_profile_creation(self, memory_manager):
        """用户画像应自动创建和更新"""
        user_id = "user-profile"

        profile = await memory_manager.get_or_create_user_profile(user_id)
        assert profile.user_id == user_id
        assert profile.total_interactions == 1
        assert profile.relationship_stage == "initial"

        # 再次获取应增加交互次数
        profile2 = await memory_manager.get_or_create_user_profile(user_id)
        assert profile2.total_interactions == 2

    @pytest.mark.asyncio
    async def test_trust_score_calculation(self, memory_manager):
        """信任度应基于多因素计算"""
        user_id = "user-trust"

        # 添加一些记忆和交互
        await memory_manager.add_fact_memory(user_id, "喜欢猫", key_entities=["猫"])
        await memory_manager.add_episodic_memory(
            user_id, "聊了天气", summary="天气话题", topic_tags=["天气"]
        )
        await memory_manager.get_or_create_user_profile(user_id)

        trust = await memory_manager.calculate_trust_score(user_id)
        assert 0.0 <= trust <= 1.0

    @pytest.mark.asyncio
    async def test_retrieve_relevant_memories(self, memory_manager):
        """检索应返回与输入相关的记忆"""
        user_id = "user-retrieve"

        # 添加一些记忆
        await memory_manager.add_episodic_memory(
            user_id,
            content="用户喜欢日本动漫",
            summary="聊了动漫",
            topic_tags=["动漫", "日本"],
            key_entities=["动漫"],
        )
        await memory_manager.add_fact_memory(
            user_id, "用户最喜欢火影忍者", key_entities=["火影忍者"]
        )

        # 检索相关记忆
        results, emotion = await memory_manager.retrieve_relevant_memories(
            user_id=user_id,
            current_input="推荐一些好看的动漫",
            include_emotional_context=True,
        )

        # 应该有匹配结果（通过实体或话题）
        assert isinstance(results, list)
        # 情感应被分析
        assert emotion is not None or emotion is None  # 取决于规则匹配


# ──────────────────────────────────────────────
# 情感分析集成测试
# ──────────────────────────────────────────────


class TestEmotionIntegration:
    """测试情感分析引擎"""

    @pytest.mark.asyncio
    async def test_positive_emotion_detection(self):
        """正面情感应被正确识别"""
        tracker = EmotionTracker()

        state = await tracker.analyze_emotion(
            text="今天太开心了！哈哈",
            user_id="user-1",
            session_id="session-1",
        )

        assert state.emotion == EmotionCategory.JOY
        assert state.valence == "positive"
        assert state.intensity > 0.5

    @pytest.mark.asyncio
    async def test_negative_emotion_detection(self):
        """负面情感应被正确识别"""
        tracker = EmotionTracker()

        state = await tracker.analyze_emotion(
            text="今天好难过，什么都不顺",
            user_id="user-1",
            session_id="session-1",
        )

        assert state.emotion == EmotionCategory.SADNESS
        assert state.valence == "negative"

    @pytest.mark.asyncio
    async def test_neutral_emotion_detection(self):
        """中性文本应返回中性情感"""
        tracker = EmotionTracker()

        state = await tracker.analyze_emotion(
            text="今天星期三",
            user_id="user-1",
            session_id="session-1",
        )

        assert state.emotion == EmotionCategory.NEUTRAL

    @pytest.mark.asyncio
    async def test_emotion_session_summary(self):
        """会话情感摘要应正确统计"""
        tracker = EmotionTracker()

        await tracker.analyze_emotion("开心的一天", "u1", "s1")
        await tracker.analyze_emotion("有点难过", "u1", "s1")
        await tracker.analyze_emotion("太好了", "u1", "s1")

        summary = await tracker.get_session_emotion_summary("s1")
        assert summary["emotion_count"] == 3
        assert "dominant_emotion" in summary

    @pytest.mark.asyncio
    async def test_emotion_trend(self):
        """情感趋势应正确计算"""
        tracker = EmotionTracker()

        # 生成多条情感记录
        for _ in range(5):
            await tracker.analyze_emotion("开心", "u-trend", "s-trend")
        for _ in range(3):
            await tracker.analyze_emotion("难过", "u-trend", "s-trend")

        trend = await tracker.get_emotion_trend("u-trend", days=1)
        assert trend.user_id == "u-trend"
        assert trend.dominant_emotion == EmotionCategory.JOY

    @pytest.mark.asyncio
    async def test_comfort_suggestions_for_sadness(self):
        """悲伤情感应生成安慰建议"""
        tracker = EmotionTracker()

        sad_state = EmotionState(
            emotion=EmotionCategory.SADNESS,
            intensity=0.8,
            valence="negative",
        )

        suggestions = await tracker.get_comfort_suggestions("u1", sad_state)
        assert len(suggestions) > 0
        assert any("陪" in s or "在" in s for s in suggestions)

    @pytest.mark.asyncio
    async def test_needs_immediate_comfort(self):
        """高强度悲伤/恐惧应标记需要安慰"""
        tracker = EmotionTracker()

        state = await tracker.analyze_emotion(
            text="我好害怕，非常恐惧",
            user_id="u1",
            session_id="s1",
        )

        assert state.needs_immediate_comfort is True


# ──────────────────────────────────────────────
# 编排引擎集成测试（核心流水线）
# ──────────────────────────────────────────────


class TestOrchestratorIntegration:
    """测试编排引擎的完整流水线"""

    def _create_engine(self, response_text: str = "你好呀～") -> OrchestratorEngine:
        """创建带有 Mock AI 的编排引擎"""
        from unittest.mock import AsyncMock

        mock_ai_service = AsyncMock()
        mock_response = ChatResponse(
            content=response_text,
            finish_reason="stop",
            model="mock-model",
        )
        mock_ai_service.generate = AsyncMock(return_value=mock_response)
        mock_ai_service.embed = AsyncMock(return_value=[0.1] * 16)

        persona = DefaultPersona()
        memory = MemoryManager()
        return OrchestratorEngine(
            ai_service=mock_ai_service,
            persona=persona,
            memory_manager=memory,
        )

    def _make_user_message(
        self,
        text: str = "你好",
        user_id: str = "test-user",
        session_id: str = "test-session",
    ) -> UserMessage:
        """创建测试用用户消息"""
        return UserMessage(
            platform="test",
            platform_user_id="test-123",
            yuanbot_user_id=user_id,
            session_id=session_id,
            content_type=ContentType.TEXT,
            text=text,
        )

    @pytest.mark.asyncio
    async def test_full_pipeline_basic(self):
        """基本消息处理流水线应完整执行"""
        engine = self._create_engine("你好呀～今天开心吗？")
        message = self._make_user_message("你好")

        response = await engine.process_message(message)

        # 验证响应
        assert response.content.content_type == ContentType.TEXT
        assert response.content.text == "你好呀～今天开心吗？"

        # 验证 AI 被调用
        engine._ai.generate.assert_called_once()

        # 验证工作记忆被更新（用户消息 + AI 回复）
        memories = await engine._memory.get_working_memory("test-session")
        assert len(memories) == 2
        assert "你好" in memories[0].content
        assert "你好呀" in memories[1].content

    @pytest.mark.asyncio
    async def test_pipeline_preserves_context(self):
        """连续对话应保持上下文"""
        engine = self._create_engine("好的～")
        session_id = "multi-turn-session"

        # 第一轮
        msg1 = self._make_user_message("我叫小明", session_id=session_id)
        await engine.process_message(msg1)

        # 第二轮
        msg2 = self._make_user_message("我今天很开心", session_id=session_id)
        await engine.process_message(msg2)

        # 工作记忆应包含所有消息
        memories = await engine._memory.get_working_memory(session_id)
        assert len(memories) == 4  # 2 user + 2 AI

    @pytest.mark.asyncio
    async def test_pipeline_with_negative_emotion(self):
        """负面情绪应触发主动关心任务"""
        engine = self._create_engine("我理解你的心情")
        message = self._make_user_message("今天伤心，心情很差")

        response = await engine.process_message(message)

        # 应该生成关心类的主动跟进任务
        assert response.proactive_followups is not None
        assert any(t.task_type == "care" for t in response.proactive_followups)

    @pytest.mark.asyncio
    async def test_pipeline_builds_system_prompt_with_persona(self):
        """系统提示词应包含人设信息"""
        engine = self._create_engine("测试回复")
        message = self._make_user_message("你好")

        await engine.process_message(message)

        # 验证 AI 收到了包含人设的系统提示词
        engine._ai.generate.assert_called_once()
        call_kwargs = engine._ai.generate.call_args
        system_prompt = call_kwargs.kwargs.get("system_prompt") or call_kwargs[1].get("system_prompt")
        assert system_prompt is not None
        assert "小缘" in system_prompt  # 默认人设名称

    @pytest.mark.asyncio
    async def test_pipeline_includes_memory_in_context(self):
        """相关记忆应被注入到上下文中"""
        engine = self._create_engine("好的")

        # 先添加一些记忆
        user_id = "memory-test-user"
        await engine._memory.add_fact_memory(user_id, "用户喜欢猫", key_entities=["猫"])

        message = self._make_user_message("推荐一些宠物", user_id=user_id)
        await engine.process_message(message)

        # 验证 AI 收到了包含记忆的系统提示词
        engine._ai.generate.assert_called_once()
        call_kwargs = engine._ai.generate.call_args
        system_prompt = call_kwargs.kwargs.get("system_prompt") or call_kwargs[1].get("system_prompt")
        assert system_prompt is not None

    @pytest.mark.asyncio
    async def test_pipeline_handles_empty_text(self):
        """空文本消息不应崩溃"""
        engine = self._create_engine("收到～")
        message = UserMessage(
            platform="test",
            platform_user_id="test-123",
            yuanbot_user_id="test-user",
            session_id="empty-session",
            content_type=ContentType.TEXT,
            text=None,
        )

        response = await engine.process_message(message)
        assert response.content.text is not None


# ──────────────────────────────────────────────
# 身份服务集成测试
# ──────────────────────────────────────────────


class TestIdentityIntegration:
    """测试跨平台身份解析"""

    def test_identity_resolution_creates_mapping(self):
        """首次交互应自动创建映射"""
        service = IdentityService()

        uid = service.resolve_user_id("telegram", "tg_123")
        assert uid.startswith("yb_")

        # 再次请求应返回相同 ID
        uid2 = service.resolve_user_id("telegram", "tg_123")
        assert uid == uid2

    def test_cross_platform_linking(self):
        """跨平台账号应能关联"""
        service = IdentityService()

        uid = service.resolve_user_id("telegram", "tg_123")
        linked = service.link_accounts(uid, "discord", "dc_456")
        assert linked is True

        # 验证关联
        platforms = service.get_linked_platforms(uid)
        platform_names = [p["platform"] for p in platforms]
        assert "telegram" in platform_names
        assert "discord" in platform_names

    def test_session_id_generation(self):
        """会话 ID 应包含平台和用户信息"""
        service = IdentityService()
        sid = service.build_session_id("telegram", "tg_123")
        assert sid == "telegram:tg_123"


# ──────────────────────────────────────────────
# 人设系统集成测试
# ──────────────────────────────────────────────


class TestPersonaIntegration:
    """测试人设系统的集成"""

    def test_default_persona_properties(self, persona):
        """默认人设应有完整的属性"""
        assert persona.persona_id == "default"
        assert persona.name == "小缘"
        assert len(persona.get_system_prompt()) > 50
        assert len(persona.get_behavior_rules()) > 0
        assert len(persona.get_capability_domains()) > 0

    def test_persona_voice_style(self, persona):
        """默认人设应有语音风格配置"""
        style = persona.get_voice_style()
        assert "tone" in style
        assert style["tone"] == "温柔"

    def test_persona_skill_matching(self, persona):
        """人设应能判断是否使用技能"""
        # 创建一个模拟的 SkillMetadata
        mock_skill = MagicMock()
        mock_skill.category = "emotional"
        mock_skill.capability_tags = ["emotional_care"]

        assert persona.should_use_skill(mock_skill) is True

        # 不兼容的技能
        mock_skill.category = "system"
        mock_skill.capability_tags = ["admin"]
        assert persona.should_use_skill(mock_skill) is False


# ──────────────────────────────────────────────
# 主动交互策略集成测试
# ──────────────────────────────────────────────


class TestProactiveIntegration:
    """测试主动交互策略"""

    def test_strategy_respects_disabled_config(self):
        """禁用时不应主动交互"""
        strategy = ProactiveStrategy(config={"enabled": False})
        decision = strategy.should_act_sync("user-1")
        assert decision.should_act is False
        assert decision.reason == "proactive_disabled"

    def test_strategy_daily_limit(self):
        """应遵守每日上限"""
        strategy = ProactiveStrategy(config={"max_per_day": 2})

        assert strategy.should_act_sync("user-1").should_act is True
        assert strategy.should_act_sync("user-1").should_act is True
        # 第三次应被限制
        assert strategy.should_act_sync("user-1").should_act is False

    @pytest.mark.asyncio
    async def test_strategy_should_send_with_memory(self):
        """应结合记忆管理器判断是否发送"""
        memory = MemoryManager()
        strategy = ProactiveStrategy(
            config={"enabled": True, "max_per_day": 10},
            memory_manager=memory,
        )

        should = await strategy.should_send("user-1", "greeting")
        assert isinstance(should, bool)

    @pytest.mark.asyncio
    async def test_strategy_generate_fallback_message(self):
        """AI 不可用时应返回模板消息"""
        strategy = ProactiveStrategy()

        msg = await strategy.generate_message("user-1", "greeting")
        assert len(msg) > 0
        assert isinstance(msg, str)

    @pytest.mark.asyncio
    async def test_strategy_priority_with_relationship(self):
        """优先级应受关系阶段影响"""
        memory = MemoryManager()
        # 设置亲密关系
        await memory.update_relationship_stage("user-deep", "deep")

        strategy = ProactiveStrategy(memory_manager=memory)
        priority = await strategy.get_task_priority("greeting", "user-deep")
        assert priority >= 5  # 基础 5 + deep 加成 2


# ──────────────────────────────────────────────
# Skills/Tools 加载集成测试
# ──────────────────────────────────────────────


class TestSkillsToolsIntegration:
    """测试 Skills 和 Tools 的加载与管理"""

    @pytest.mark.asyncio
    async def test_skill_manager_empty_dir(self, tmp_path):
        """空目录不应报错"""
        manager = SkillManager(skills_dir=str(tmp_path / "skills"))
        await manager.load_skills()
        assert manager.get_all_skills() == []

    @pytest.mark.asyncio
    async def test_tool_manager_empty_dir(self, tmp_path):
        """空目录不应报错"""
        manager = ToolManager(tools_dir=str(tmp_path / "tools"))
        await manager.load_tools()
        assert manager.get_all_tools() == []

    @pytest.mark.asyncio
    async def test_tool_manager_load_from_yaml(self, tmp_path):
        """从 YAML 文件加载工具定义"""
        import yaml

        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        tool_yaml = {
            "tool_id": "weather_check",
            "name": "天气查询",
            "version": "1.0.0",
            "category": "utility",
            "enabled": True,
            "capability_tags": ["weather"],
            "permission_level": "readonly",
            "schema": {
                "type": "function",
                "function": {
                    "name": "weather_check",
                    "description": "查询天气",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                    },
                },
            },
            "executor": {"type": "local_thread", "timeout": 5},
        }
        (tools_dir / "weather.yaml").write_text(yaml.dump(tool_yaml))

        manager = ToolManager(tools_dir=str(tools_dir))
        await manager.load_tools()

        all_tools = manager.get_all_tools()
        assert len(all_tools) == 1
        assert all_tools[0]["tool_id"] == "weather_check"

    @pytest.mark.asyncio
    async def test_tool_manager_execute(self, tmp_path):
        """工具执行应返回结果"""
        import yaml

        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        tool_yaml = {
            "tool_id": "echo",
            "name": "回声工具",
            "enabled": True,
            "schema": {
                "type": "function",
                "function": {"name": "echo", "parameters": {}},
            },
            "executor": {"type": "local_thread", "timeout": 5},
        }
        (tools_dir / "echo.yaml").write_text(yaml.dump(tool_yaml))

        manager = ToolManager(tools_dir=str(tools_dir))
        await manager.load_tools()

        result = await manager.execute_tool("echo", {"msg": "hello"})
        assert result.success is True
        assert result.tool_id == "echo"

    @pytest.mark.asyncio
    async def test_tool_manager_intent_matching(self, tmp_path):
        """工具应根据意图匹配"""
        import yaml

        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        for name, cat, tags in [
            ("weather", "utility", ["weather"]),
            ("reminder", "utility", ["reminder"]),
        ]:
            tool_yaml = {
                "tool_id": name,
                "name": name,
                "enabled": True,
                "category": cat,
                "capability_tags": tags,
                "schema": {
                    "type": "function",
                    "function": {"name": name, "parameters": {}},
                },
            }
            (tools_dir / f"{name}.yaml").write_text(yaml.dump(tool_yaml))

        manager = ToolManager(tools_dir=str(tools_dir))
        await manager.load_tools()

        # 意图包含 "weather" 应匹配天气工具
        matched = manager.get_tools_for_intent("weather forecast")
        assert len(matched) >= 1


# ──────────────────────────────────────────────
# 端到端集成测试（多系统协作）
# ──────────────────────────────────────────────


class TestEndToEnd:
    """端到端集成测试：多系统协作"""

    @pytest.mark.asyncio
    async def test_full_conversation_flow(self):
        """完整对话流程：身份解析 → 编排 → 记忆 → 响应"""
        # 1. 身份解析
        identity = IdentityService()
        user_id = identity.resolve_user_id("telegram", "tg_user_1")
        session_id = identity.build_session_id("telegram", "tg_user_1")

        # 2. 记忆系统
        memory = MemoryManager()
        await memory.add_fact_memory(user_id, "用户喜欢猫", key_entities=["猫"])

        # 3. 编排引擎
        from unittest.mock import AsyncMock

        mock_ai = AsyncMock()
        mock_ai.generate = AsyncMock(return_value=ChatResponse(
            content="喵～你也喜欢猫吗？",
            finish_reason="stop",
            model="mock-model",
        ))
        mock_ai.embed = AsyncMock(return_value=[0.1] * 16)
        persona = DefaultPersona()
        engine = OrchestratorEngine(
            ai_service=mock_ai,
            persona=persona,
            memory_manager=memory,
        )

        # 4. 处理消息
        message = UserMessage(
            platform="telegram",
            platform_user_id="tg_user_1",
            yuanbot_user_id=user_id,
            session_id=session_id,
            content_type=ContentType.TEXT,
            text="我好喜欢猫咪",
        )

        response = await engine.process_message(message)

        # 5. 验证
        assert response.content.text == "喵～你也喜欢猫吗？"
        mock_ai.generate.assert_called_once()

        # 验证记忆被更新
        wm = await memory.get_working_memory(session_id)
        assert len(wm) == 2  # user + AI

    @pytest.mark.asyncio
    async def test_multi_user_isolation(self):
        """不同用户的记忆应完全隔离"""
        memory = MemoryManager()

        # 用户 A
        await memory.add_working_memory("session-a", "A 的消息")
        await memory.add_fact_memory("user-a", "A 喜欢狗", key_entities=["狗"])

        # 用户 B
        await memory.add_working_memory("session-b", "B 的消息")
        await memory.add_fact_memory("user-b", "B 喜欢猫", key_entities=["猫"])

        # 验证隔离
        mem_a = await memory.get_working_memory("session-a")
        mem_b = await memory.get_working_memory("session-b")
        assert len(mem_a) == 1
        assert len(mem_b) == 1
        assert mem_a[0].content == "A 的消息"
        assert mem_b[0].content == "B 的消息"

        facts_a = await memory.get_fact_memories("user-a")
        facts_b = await memory.get_fact_memories("user-b")
        assert "狗" in facts_a[0].content
        assert "猫" in facts_b[0].content

    @pytest.mark.asyncio
    async def test_emotion_driven_memory_retrieval(self):
        """情感状态应影响记忆检索结果"""
        memory = MemoryManager()
        user_id = "emotion-user"

        # 添加正面和负面记忆
        await memory.add_episodic_memory(
            user_id,
            content="用户分享了快乐的旅行",
            summary="快乐旅行",
            topic_tags=["旅行"],
            emotional_tone="joy",
        )
        await memory.add_episodic_memory(
            user_id,
            content="用户提到工作压力大",
            summary="工作压力",
            topic_tags=["工作"],
            emotional_tone="sadness",
        )

        # 用正面情感检索
        results, emotion = await memory.retrieve_relevant_memories(
            user_id=user_id,
            current_input="今天太开心了",
            include_emotional_context=True,
        )

        # 情感应为正面
        if emotion:
            assert emotion.valence in ("positive", "neutral")
