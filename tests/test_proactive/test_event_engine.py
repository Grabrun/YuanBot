"""测试事件监听引擎"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from yuanbot.proactive.event_engine import (
    EventEngine,
    EventOccurrence,
    EventTrigger,
    EventType,
)


class TestEventTrigger:
    """EventTrigger 数据结构测试"""

    def test_default_values(self):
        trigger = EventTrigger()
        assert trigger.event_type == EventType.CUSTOM
        assert trigger.enabled is True
        assert trigger.priority == 1
        assert trigger.trigger_id  # auto-generated

    def test_custom_values(self):
        trigger = EventTrigger(
            event_type=EventType.USER_SILENCE,
            name="silence_check",
            user_ids=["user1"],
            priority=5,
        )
        assert trigger.event_type == EventType.USER_SILENCE
        assert trigger.name == "silence_check"
        assert trigger.user_ids == ["user1"]
        assert trigger.priority == 5


class TestEventOccurrence:
    """EventOccurrence 数据结构测试"""

    def test_default_values(self):
        event = EventOccurrence()
        assert event.event_type == EventType.CUSTOM
        assert event.user_id == ""
        assert event.event_id  # auto-generated

    def test_with_data(self):
        event = EventOccurrence(
            event_type=EventType.USER_SILENCE,
            user_id="user1",
            data={"silence_hours": 48},
        )
        assert event.event_type == EventType.USER_SILENCE
        assert event.user_id == "user1"
        assert event.data["silence_hours"] == 48


class TestEventEngine:
    """事件引擎测试"""

    def test_register_trigger(self):
        engine = EventEngine()
        trigger = EventTrigger(
            event_type=EventType.USER_SILENCE,
            name="silence_check",
        )
        tid = engine.register_trigger(trigger)
        assert tid == trigger.trigger_id
        assert len(engine.get_triggers()) == 1

    def test_unregister_trigger(self):
        engine = EventEngine()
        trigger = EventTrigger(event_type=EventType.USER_SILENCE, name="test")
        tid = engine.register_trigger(trigger)
        assert engine.unregister_trigger(tid) is True
        assert len(engine.get_triggers()) == 0

    def test_unregister_nonexistent(self):
        engine = EventEngine()
        assert engine.unregister_trigger("nonexistent") is False

    def test_check_silence_event(self):
        engine = EventEngine()
        engine.register_trigger(
            EventTrigger(
                event_type=EventType.USER_SILENCE,
                name="silence",
                user_ids=["user1"],
            )
        )
        event = engine.check_silence_events(
            "user1",
            last_interaction=datetime.now() - timedelta(hours=3),
            threshold_minutes=120,
        )
        assert event is not None
        assert event.event_type == EventType.USER_SILENCE
        assert event.data["silence_minutes"] >= 180

    def test_check_silence_not_triggered(self):
        engine = EventEngine()
        engine.register_trigger(
            EventTrigger(
                event_type=EventType.USER_SILENCE,
                name="silence",
                user_ids=["user1"],
            )
        )
        event = engine.check_silence_events(
            "user1",
            last_interaction=datetime.now() - timedelta(minutes=10),
            threshold_minutes=120,
        )
        assert event is None

    def test_check_silence_no_matching_trigger(self):
        engine = EventEngine()
        # 没有注册触发器
        event = engine.check_silence_events(
            "user1",
            last_interaction=datetime.now() - timedelta(hours=5),
        )
        assert event is None

    def test_check_silence_wrong_user(self):
        engine = EventEngine()
        engine.register_trigger(
            EventTrigger(
                event_type=EventType.USER_SILENCE,
                name="silence",
                user_ids=["user2"],
            )
        )
        event = engine.check_silence_events(
            "user1",
            last_interaction=datetime.now() - timedelta(hours=5),
        )
        assert event is None

    def test_check_emotion_risk(self):
        engine = EventEngine()
        engine.register_trigger(
            EventTrigger(
                event_type=EventType.EMOTION_RISK,
                name="emotion_risk",
                user_ids=["user1"],
            )
        )
        event = engine.check_emotion_risk("user1", "sadness", 0.8)
        assert event is not None
        assert event.event_type == EventType.EMOTION_RISK
        assert event.data["emotion"] == "sadness"

    def test_check_emotion_risk_not_triggered_low_intensity(self):
        engine = EventEngine()
        engine.register_trigger(
            EventTrigger(
                event_type=EventType.EMOTION_RISK,
                name="emotion_risk",
            )
        )
        event = engine.check_emotion_risk("user1", "sadness", 0.3)
        assert event is None

    def test_check_emotion_risk_positive_emotion(self):
        engine = EventEngine()
        engine.register_trigger(
            EventTrigger(
                event_type=EventType.EMOTION_RISK,
                name="emotion_risk",
            )
        )
        event = engine.check_emotion_risk("user1", "joy", 0.9)
        assert event is None  # joy 不是负面情感

    def test_check_special_date(self):
        engine = EventEngine()
        engine.register_trigger(
            EventTrigger(
                event_type=EventType.SPECIAL_DATE,
                name="birthday",
            )
        )
        today = datetime.now().strftime("%m-%d")
        event = engine.check_special_date("user1", {"birthday": today})
        assert event is not None
        assert event.data["date_name"] == "birthday"

    def test_check_special_date_no_match(self):
        engine = EventEngine()
        engine.register_trigger(
            EventTrigger(
                event_type=EventType.SPECIAL_DATE,
                name="birthday",
            )
        )
        event = engine.check_special_date("user1", {"birthday": "01-01"})
        # 如果今天不是 01-01 则不触发
        if datetime.now().strftime("%m-%d") != "01-01":
            assert event is None

    def test_emit_custom_event(self):
        engine = EventEngine()
        engine.register_trigger(
            EventTrigger(
                event_type=EventType.CUSTOM,
                name="custom",
            )
        )
        event = engine.emit_custom_event("user1", "test_event", {"key": "value"})
        assert event is not None
        assert event.event_type == EventType.CUSTOM
        assert event.data["event_name"] == "test_event"

    def test_get_recent_events(self):
        engine = EventEngine()
        engine.register_trigger(
            EventTrigger(
                event_type=EventType.CUSTOM,
                name="custom",
            )
        )
        engine.emit_custom_event("user1", "event1")
        engine.emit_custom_event("user1", "event2")
        engine.emit_custom_event("user2", "event3")

        # 所有事件
        all_events = engine.get_recent_events()
        assert len(all_events) == 3

        # 按用户过滤
        user1_events = engine.get_recent_events("user1")
        assert len(user1_events) == 2

        # limit
        limited = engine.get_recent_events(limit=1)
        assert len(limited) == 1

    def test_disabled_trigger(self):
        engine = EventEngine()
        engine.register_trigger(
            EventTrigger(
                event_type=EventType.USER_SILENCE,
                name="disabled",
                user_ids=["user1"],
                enabled=False,
            )
        )
        event = engine.check_silence_events(
            "user1",
            last_interaction=datetime.now() - timedelta(hours=5),
        )
        assert event is None


class TestEventEngineHandlers:
    """事件处理器注册与触发测试"""

    @pytest.mark.asyncio
    async def test_register_and_emit_handler(self):
        engine = EventEngine()
        handler = AsyncMock()

        engine.register_handler("user_silence", handler)
        await engine.emit_event("user_silence", {"user_id": "user1"})

        handler.assert_called_once_with({"user_id": "user1"})

    @pytest.mark.asyncio
    async def test_multiple_handlers(self):
        engine = EventEngine()
        handler1 = AsyncMock()
        handler2 = AsyncMock()

        engine.register_handler("test_event", handler1)
        engine.register_handler("test_event", handler2)
        await engine.emit_event("test_event", {"data": "value"})

        handler1.assert_called_once()
        handler2.assert_called_once()

    @pytest.mark.asyncio
    async def test_emit_no_handlers(self):
        engine = EventEngine()
        # 无处理器时不应报错
        await engine.emit_event("nonexistent_event", {})

    @pytest.mark.asyncio
    async def test_handler_error_does_not_break_others(self):
        engine = EventEngine()

        async def bad_handler(data: dict) -> None:
            raise ValueError("intentional error")

        good_handler = AsyncMock()

        engine.register_handler("test_event", bad_handler)
        engine.register_handler("test_event", good_handler)
        await engine.emit_event("test_event", {})

        # 好的处理器仍应被调用
        good_handler.assert_called_once()

    def test_unregister_handlers(self):
        engine = EventEngine()
        engine.register_handler("test", AsyncMock())
        engine.register_handler("test", AsyncMock())

        count = engine.unregister_handlers("test")
        assert count == 2

    def test_unregister_handlers_empty(self):
        engine = EventEngine()
        count = engine.unregister_handlers("nonexistent")
        assert count == 0


class TestEventEngineAsync:
    """事件引擎异步功能测试"""

    @pytest.mark.asyncio
    async def test_start_stop(self):
        engine = EventEngine(config={"silence_check_interval_seconds": 1})
        assert engine.is_running is False

        await engine.start()
        assert engine.is_running is True

        await engine.stop()
        assert engine.is_running is False

    @pytest.mark.asyncio
    async def test_start_twice(self):
        engine = EventEngine(config={"silence_check_interval_seconds": 1})
        await engine.start()
        await engine.start()  # 不应报错
        assert engine.is_running is True
        await engine.stop()

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self):
        engine = EventEngine()
        await engine.stop()  # 不应报错

    @pytest.mark.asyncio
    async def test_check_user_silence(self):
        """测试静默检测通过 memory_manager"""
        mock_profile = AsyncMock()
        mock_profile.last_interaction = datetime.now() - timedelta(hours=50)
        mock_profile.relationship_stage = "familiar"

        mock_memory = AsyncMock()
        mock_memory._user_profiles = {"user1": mock_profile}
        mock_memory.get_or_create_user_profile = AsyncMock(return_value=mock_profile)

        engine = EventEngine(
            config={"silence_threshold_hours": 48, "silence_check_interval_seconds": 0},
            memory_manager=mock_memory,
        )

        handler = AsyncMock()
        engine.register_handler(EventType.USER_SILENCE, handler)

        await engine._check_user_silence()

        handler.assert_called_once()
        call_data = handler.call_args[0][0]
        assert call_data["user_id"] == "user1"
        assert call_data["silence_hours"] >= 48

    @pytest.mark.asyncio
    async def test_check_user_silence_no_memory_manager(self):
        """无 memory_manager 时静默检测跳过"""
        engine = EventEngine()
        # 不应报错
        await engine._check_user_silence()

    @pytest.mark.asyncio
    async def test_check_emotion_alerts(self):
        """测试情感告警检测"""
        from yuanbot.core.types import EmotionCategory, EmotionTrend

        mock_trend = EmotionTrend(
            user_id="user1",
            period="daily",
            start_date=datetime.now() - timedelta(days=3),
            end_date=datetime.now(),
            dominant_emotion=EmotionCategory.SADNESS,
            valence_ratio={"negative": 0.7, "positive": 0.2, "neutral": 0.1},
            mood_stability=0.3,
        )

        mock_profile = AsyncMock()
        mock_memory = AsyncMock()
        mock_memory._user_profiles = {"user1": mock_profile}
        mock_memory.get_emotion_trend = AsyncMock(return_value=mock_trend)

        engine = EventEngine(
            config={"emotion_check_interval_seconds": 0, "emotion_alert_days": 3},
            memory_manager=mock_memory,
        )

        handler = AsyncMock()
        engine.register_handler(EventType.EMOTION_RISK, handler)

        await engine._check_emotion_alerts()

        handler.assert_called_once()
        call_data = handler.call_args[0][0]
        assert call_data["user_id"] == "user1"
        assert call_data["negative_ratio"] == 0.7

    @pytest.mark.asyncio
    async def test_check_emotion_alerts_no_alert(self):
        """情绪正常时不触发告警"""
        from yuanbot.core.types import EmotionCategory, EmotionTrend

        mock_trend = EmotionTrend(
            user_id="user1",
            period="daily",
            start_date=datetime.now() - timedelta(days=3),
            end_date=datetime.now(),
            dominant_emotion=EmotionCategory.JOY,
            valence_ratio={"negative": 0.1, "positive": 0.8, "neutral": 0.1},
            mood_stability=0.8,
        )

        mock_profile = AsyncMock()
        mock_memory = AsyncMock()
        mock_memory._user_profiles = {"user1": mock_profile}
        mock_memory.get_emotion_trend = AsyncMock(return_value=mock_trend)

        engine = EventEngine(
            config={"emotion_check_interval_seconds": 0},
            memory_manager=mock_memory,
        )

        handler = AsyncMock()
        engine.register_handler(EventType.EMOTION_RISK, handler)

        await engine._check_emotion_alerts()

        handler.assert_not_called()

    def test_get_last_check_time(self):
        engine = EventEngine()
        assert engine.get_last_check_time("silence") is None
        engine._last_check_times["silence"] = datetime.now()
        assert engine.get_last_check_time("silence") is not None

    def test_constructor_with_config(self):
        engine = EventEngine(
            config={
                "silence_check_interval_seconds": 1800,
                "silence_threshold_hours": 24,
                "emotion_check_interval_seconds": 900,
                "emotion_alert_days": 5,
            }
        )
        assert engine._silence_check_interval == 1800
        assert engine._silence_threshold_hours == 24
        assert engine._emotion_check_interval == 900
        assert engine._emotion_alert_days == 5
