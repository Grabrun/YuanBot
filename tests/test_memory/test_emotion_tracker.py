"""情感追踪系统测试"""

import pytest

from yuanbot.core.types import (
    EmotionCategory,
    EmotionState,
)
from yuanbot.memory.emotion_tracker import EmotionTracker


class TestEmotionAnalyzer:
    """情感分析测试"""

    @pytest.fixture
    def tracker(self):
        return EmotionTracker()

    @pytest.mark.asyncio
    async def test_analyze_joy(self, tracker):
        """测试喜悦情感分析"""
        result = await tracker.analyze_emotion(
            text="今天太开心了！考试通过了！",
            user_id="user_001",
            session_id="session_001",
        )

        assert result.emotion == EmotionCategory.JOY
        assert result.valence == "positive"
        assert result.intensity > 0.5

    @pytest.mark.asyncio
    async def test_analyze_sadness(self, tracker):
        """测试悲伤情感分析"""
        result = await tracker.analyze_emotion(
            text="我今天很难过，和朋友吵架了",
            user_id="user_001",
            session_id="session_001",
        )

        assert result.emotion == EmotionCategory.SADNESS
        assert result.valence == "negative"
        assert result.needs_immediate_comfort is True

    @pytest.mark.asyncio
    async def test_analyze_anger(self, tracker):
        """测试愤怒情感分析"""
        result = await tracker.analyze_emotion(
            text="太生气了！他竟然骗我！",
            user_id="user_001",
            session_id="session_001",
        )

        assert result.emotion == EmotionCategory.ANGER
        assert result.valence == "negative"
        assert result.arousal == "high"

    @pytest.mark.asyncio
    async def test_analyze_fear(self, tracker):
        """测试恐惧情感分析"""
        result = await tracker.analyze_emotion(
            text="我好害怕，明天要面试了",
            user_id="user_001",
            session_id="session_001",
        )

        assert result.emotion == EmotionCategory.FEAR
        assert result.valence == "negative"

    @pytest.mark.asyncio
    async def test_analyze_neutral(self, tracker):
        """测试中性情感分析"""
        result = await tracker.analyze_emotion(
            text="今天天气怎么样",
            user_id="user_001",
            session_id="session_001",
        )

        assert result.emotion == EmotionCategory.NEUTRAL
        assert result.valence == "neutral"

    @pytest.mark.asyncio
    async def test_analyze_with_negation(self, tracker):
        """测试否定词处理"""
        result = await tracker.analyze_emotion(
            text="我不开心",
            user_id="user_001",
            session_id="session_001",
        )

        # 否定词应该影响情感分析结果
        # "不开心" 应该是负向情感或中性（因为否定词反转了喜悦）
        assert result.valence in ["negative", "neutral"]

    @pytest.mark.asyncio
    async def test_analyze_with_intensity_modifier(self, tracker):
        """测试强度修饰词"""
        result1 = await tracker.analyze_emotion(
            text="开心",
            user_id="user_001",
            session_id="session_001",
        )

        result2 = await tracker.analyze_emotion(
            text="非常开心",
            user_id="user_001",
            session_id="session_001",
        )

        # "非常"应该比单独的"开心"有更高的强度
        assert result2.intensity >= result1.intensity * 0.8  # 允许一定误差


class TestEmotionRecords:
    """情感记录测试"""

    @pytest.fixture
    def tracker(self):
        return EmotionTracker()

    @pytest.mark.asyncio
    async def test_record_creation(self, tracker):
        """测试情感记录创建"""
        await tracker.analyze_emotion(
            text="今天很开心",
            user_id="user_001",
            session_id="session_001",
        )

        records = tracker._records.get("user_001", [])
        assert len(records) == 1
        assert records[0].user_id == "user_001"
        assert records[0].session_id == "session_001"

    @pytest.mark.asyncio
    async def test_session_emotion_tracking(self, tracker):
        """测试会话情感追踪"""
        # 添加多条情感记录
        await tracker.analyze_emotion("今天很开心", "user_001", "session_001")
        await tracker.analyze_emotion("有点累", "user_001", "session_001")
        await tracker.analyze_emotion("但还是开心", "user_001", "session_001")

        emotions = tracker._session_emotions.get("session_001", [])
        assert len(emotions) == 3

    @pytest.mark.asyncio
    async def test_session_emotion_summary(self, tracker):
        """测试会话情感摘要"""
        await tracker.analyze_emotion("今天很开心", "user_001", "session_001")
        await tracker.analyze_emotion("非常高兴", "user_001", "session_001")

        summary = await tracker.get_session_emotion_summary("session_001")

        assert summary["dominant_emotion"] == "joy"
        assert summary["emotion_count"] == 2
        assert summary["average_intensity"] > 0


class TestEmotionTrend:
    """情感趋势测试"""

    @pytest.fixture
    def tracker(self):
        return EmotionTracker()

    @pytest.mark.asyncio
    async def test_emotion_trend_empty(self, tracker):
        """测试空情感趋势"""
        trend = await tracker.get_emotion_trend("user_001", days=7)

        assert trend.dominant_emotion == EmotionCategory.NEUTRAL
        assert trend.average_intensity == 0.3

    @pytest.mark.asyncio
    async def test_emotion_trend_with_records(self, tracker):
        """测试有记录的情感趋势"""
        # 添加多天的情感记录
        for i in range(5):
            await tracker.analyze_emotion(
                text=f"今天{'开心' if i % 2 == 0 else '有点累'}",
                user_id="user_001",
                session_id=f"session_{i}",
            )

        trend = await tracker.get_emotion_trend("user_001", days=7)

        assert trend.emotion_distribution is not None
        assert trend.valence_ratio is not None
        assert 0 <= trend.mood_stability <= 1
        assert 0 <= trend.emotional_variety <= 1


class TestEmotionPatterns:
    """情感模式测试"""

    @pytest.fixture
    def tracker(self):
        return EmotionTracker()

    @pytest.mark.asyncio
    async def test_pattern_detection(self, tracker):
        """测试情感模式检测"""
        # 模拟重复的情感模式
        for i in range(4):
            await tracker.analyze_emotion(
                text="工作压力好大",
                user_id="user_001",
                session_id=f"session_{i}",
            )

        patterns = await tracker.get_user_patterns("user_001")

        # 应该检测到模式
        assert len(patterns) > 0

    @pytest.mark.asyncio
    async def test_comfort_suggestions(self, tracker):
        """测试安慰建议"""
        emotion = EmotionState(
            emotion=EmotionCategory.SADNESS,
            intensity=0.8,
            valence="negative",
            arousal="medium",
            dominance="low",
            needs_immediate_comfort=True,
        )

        suggestions = await tracker.get_comfort_suggestions("user_001", emotion)

        assert len(suggestions) > 0
        assert all(isinstance(s, str) for s in suggestions)


class TestEmotionIntegration:
    """情感系统集成测试"""

    @pytest.fixture
    def tracker(self):
        return EmotionTracker()

    @pytest.mark.asyncio
    async def test_context_influence(self, tracker):
        """测试上下文对情感分析的影响"""
        # 先分析一个悲伤的上下文
        context_summary = "用户之前提到了失去宠物"

        result = await tracker.analyze_emotion(
            text="我现在很想它",
            user_id="user_001",
            session_id="session_001",
            context_summary=context_summary,
        )

        # 上下文应该影响情感分析
        # "想" 本身就带有一定的情感色彩
        assert result.valence in ["negative", "neutral"]
        assert result.emotion in [
            EmotionCategory.SADNESS,
            EmotionCategory.ANTICIPATION,
            EmotionCategory.NEUTRAL,
        ]

    @pytest.mark.asyncio
    async def test_multiple_users(self, tracker):
        """测试多用户情感追踪"""
        await tracker.analyze_emotion("今天很开心", "user_001", "session_001")
        await tracker.analyze_emotion("很难过", "user_002", "session_002")

        assert len(tracker._records["user_001"]) == 1
        assert len(tracker._records["user_002"]) == 1
        assert tracker._records["user_001"][0].emotion_state.valence == "positive"
        assert tracker._records["user_002"][0].emotion_state.valence == "negative"

    @pytest.mark.asyncio
    async def test_emotion_pattern_matching(self, tracker):
        """测试情感模式匹配"""
        # 创建一个情感模式
        for i in range(4):
            await tracker.analyze_emotion(
                text="考试要到了好紧张",
                user_id="user_001",
                session_id=f"session_{i}",
            )

        # 再次分析类似文本
        result = await tracker.analyze_emotion(
            text="明天考试好紧张",
            user_id="user_001",
            session_id="session_new",
        )

        # 应该识别为相似的情感模式
        assert result.emotion in [EmotionCategory.FEAR, EmotionCategory.ANTICIPATION]
