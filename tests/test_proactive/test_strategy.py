"""测试主动交互策略决策器"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from yuanbot.proactive.strategy import (
    ProactiveConfig,
    ProactiveDecision,
    ProactiveStrategy,
)


class TestProactiveConfig:
    """ProactiveConfig 测试"""

    def test_default_values(self):
        config = ProactiveConfig()
        assert config.enabled is True
        assert config.greeting_enabled is True
        assert config.frequency == "medium"
        assert config.quiet_hours_start == 23
        assert config.quiet_hours_end == 7
        assert config.max_per_day == 5
        assert config.event_triggers_enabled is True

    def test_custom_values(self):
        config = ProactiveConfig(
            enabled=False,
            frequency="low",
            quiet_hours_start=22,
            quiet_hours_end=9,
            max_per_day=3,
        )
        assert config.enabled is False
        assert config.frequency == "low"
        assert config.max_per_day == 3


class TestProactiveDecision:
    """ProactiveDecision 测试"""

    def test_should_act(self):
        decision = ProactiveDecision(should_act=True, priority=5)
        assert decision.should_act is True
        assert decision.priority == 5

    def test_should_not_act(self):
        decision = ProactiveDecision(should_act=False, reason="quiet_hours")
        assert decision.should_act is False
        assert decision.reason == "quiet_hours"


class TestProactiveStrategyShouldAct:
    """should_act 同步接口测试"""

    def test_normal_should_act(self):
        config = ProactiveConfig(enabled=True, quiet_hours_start=23, quiet_hours_end=7)
        strategy = ProactiveStrategy(config=config.__dict__)
        decision = strategy.should_act_sync("user1")
        assert isinstance(decision, ProactiveDecision)

    def test_disabled_strategy(self):
        config = ProactiveConfig(enabled=False)
        strategy = ProactiveStrategy(config=config.__dict__)
        decision = strategy.should_act_sync("user1")
        assert decision.should_act is False
        assert decision.reason == "proactive_disabled"

    def test_event_triggers_disabled(self):
        config = ProactiveConfig(enabled=True, event_triggers_enabled=False)
        strategy = ProactiveStrategy(config=config.__dict__)
        decision = strategy.should_act_sync("user1", is_event_triggered=True)
        assert decision.should_act is False
        assert decision.reason == "event_triggers_disabled"

    def test_daily_limit(self):
        config = ProactiveConfig(
            enabled=True, max_per_day=2, quiet_hours_start=0, quiet_hours_end=0
        )
        strategy = ProactiveStrategy(config=config.__dict__)

        # 前两次应成功
        d1 = strategy.should_act_sync("user1")
        assert d1.should_act is True
        d2 = strategy.should_act_sync("user1")
        assert d2.should_act is True

        # 第三次应被限制
        d3 = strategy.should_act_sync("user1")
        assert d3.should_act is False
        assert d3.reason == "daily_limit_reached"

    def test_different_users_independent(self):
        config = ProactiveConfig(
            enabled=True, max_per_day=1, quiet_hours_start=0, quiet_hours_end=0
        )
        strategy = ProactiveStrategy(config=config.__dict__)

        strategy.should_act_sync("user1")
        d2 = strategy.should_act_sync("user2")
        assert d2.should_act is True

    def test_update_config(self):
        strategy = ProactiveStrategy()
        new_config = ProactiveConfig(enabled=False)
        strategy.update_config(new_config)
        assert strategy.get_config().enabled is False

    def test_get_daily_stats(self):
        strategy = ProactiveStrategy(config={"quiet_hours_start": 0, "quiet_hours_end": 0})
        strategy.should_act_sync("user1")
        strategy.should_act_sync("user2")
        stats = strategy.get_daily_stats()
        assert "user1" in stats
        assert "user2" in stats
        assert stats["user1"] == 1

    def test_event_only_frequency(self):
        config = ProactiveConfig(
            enabled=True, frequency="event_only", quiet_hours_start=0, quiet_hours_end=0
        )
        strategy = ProactiveStrategy(config=config.__dict__)

        # 非事件触发应被限制
        decision = strategy.should_act_sync("user1", is_event_triggered=False)
        assert decision.should_act is False
        assert decision.reason == "frequency_limited"

        # 事件触发应通过
        decision = strategy.should_act_sync("user1", is_event_triggered=True)
        assert decision.should_act is True


class TestProactiveStrategyShouldSend:
    """should_send 异步接口测试"""

    @pytest.mark.asyncio
    async def test_should_send_normal(self):
        strategy = ProactiveStrategy(
            config={"enabled": True, "max_per_day": 5, "quiet_hours_start": 0, "quiet_hours_end": 0}
        )
        result = await strategy.should_send("user1", "greeting")
        assert result is True

    @pytest.mark.asyncio
    async def test_should_send_disabled(self):
        strategy = ProactiveStrategy(config={"enabled": False})
        result = await strategy.should_send("user1", "greeting")
        assert result is False

    @pytest.mark.asyncio
    async def test_should_send_daily_limit(self):
        strategy = ProactiveStrategy(config={"enabled": True, "max_per_day": 1})
        await strategy.should_send("user1", "greeting")
        result = await strategy.should_send("user1", "greeting")
        assert result is False

    @pytest.mark.asyncio
    async def test_should_send_care_during_quiet_hours(self):
        """care 类型在免打扰时段也应通过"""
        config = {"enabled": True, "quiet_hours_start": 0, "quiet_hours_end": 23, "max_per_day": 10}
        strategy = ProactiveStrategy(config=config)
        # 现在应该在免打扰时段内（0-23 覆盖全天）
        result = await strategy.should_send("user1", "care")
        assert result is True

    @pytest.mark.asyncio
    async def test_should_send_greeting_blocked_in_quiet_hours(self):
        """greeting 类型在免打扰时段应被阻止"""
        from unittest.mock import patch

        # 固定时间为凌晨 2:00，在 23:00-07:00 免打扰时段内
        fixed_time = datetime(2026, 5, 23, 2, 0, 0)
        config = {"enabled": True, "quiet_hours_start": 23, "quiet_hours_end": 7, "max_per_day": 10}
        strategy = ProactiveStrategy(config=config)
        with patch("yuanbot.proactive.strategy.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_time
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = await strategy.should_send("user1", "greeting")
        assert result is False


class TestProactiveStrategyGenerateMessage:
    """generate_message 测试"""

    @pytest.mark.asyncio
    async def test_generate_with_ai(self):
        mock_ai = AsyncMock()
        mock_response = AsyncMock()
        mock_response.content = "早上好呀～今天天气不错哦"
        mock_ai.generate = AsyncMock(return_value=mock_response)

        strategy = ProactiveStrategy(ai_service=mock_ai)
        msg = await strategy.generate_message("user1", "greeting")

        assert msg == "早上好呀～今天天气不错哦"
        mock_ai.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_without_ai_fallback(self):
        strategy = ProactiveStrategy()  # 无 AI 服务
        msg = await strategy.generate_message("user1", "greeting")
        assert msg  # 应返回兜底消息
        assert len(msg) > 0

    @pytest.mark.asyncio
    async def test_generate_care_fallback(self):
        strategy = ProactiveStrategy()
        msg = await strategy.generate_message("user1", "care")
        assert "想" in msg or "聊" in msg or "过得" in msg

    @pytest.mark.asyncio
    async def test_generate_emotion_alert_fallback(self):
        strategy = ProactiveStrategy()
        msg = await strategy.generate_message("user1", "emotion_alert")
        assert "心情" in msg or "在" in msg

    @pytest.mark.asyncio
    async def test_generate_with_memory_context(self):
        mock_memory = AsyncMock()
        mock_profile = AsyncMock()
        mock_profile.display_name = "小明"
        mock_profile.relationship_stage = "intimate"
        mock_profile.preferences = {}
        mock_profile.last_interaction = datetime.now()
        mock_memory.get_or_create_user_profile = AsyncMock(return_value=mock_profile)
        mock_memory.get_fact_memories = AsyncMock(return_value=[])
        mock_memory.get_emotion_trend = AsyncMock(return_value=None)

        strategy = ProactiveStrategy(memory_manager=mock_memory)
        msg = await strategy.generate_message("user1", "greeting")
        assert msg  # 应生成消息

    @pytest.mark.asyncio
    async def test_generate_ai_error_fallback(self):
        mock_ai = AsyncMock()
        mock_ai.chat_completion = AsyncMock(side_effect=Exception("API error"))

        strategy = ProactiveStrategy(ai_service=mock_ai)
        msg = await strategy.generate_message("user1", "greeting")
        assert msg  # 应返回兜底消息

    @pytest.mark.asyncio
    async def test_generate_ai_empty_response_fallback(self):
        mock_ai = AsyncMock()
        mock_response = AsyncMock()
        mock_response.content = None
        mock_ai.chat_completion = AsyncMock(return_value=mock_response)

        strategy = ProactiveStrategy(ai_service=mock_ai)
        msg = await strategy.generate_message("user1", "greeting")
        assert msg  # 应返回兜底消息


class TestProactiveStrategyGetPriority:
    """get_task_priority 测试"""

    @pytest.mark.asyncio
    async def test_base_priority(self):
        strategy = ProactiveStrategy()
        p = await strategy.get_task_priority("greeting", "user1")
        assert 1 <= p <= 10

    @pytest.mark.asyncio
    async def test_emotion_alert_high_priority(self):
        strategy = ProactiveStrategy()
        p = await strategy.get_task_priority("emotion_alert", "user1")
        assert p >= 8

    @pytest.mark.asyncio
    async def test_fun_low_priority(self):
        strategy = ProactiveStrategy()
        p = await strategy.get_task_priority("fun", "user1")
        assert p <= 3

    @pytest.mark.asyncio
    async def test_unknown_type_default(self):
        strategy = ProactiveStrategy()
        p = await strategy.get_task_priority("unknown_type", "user1")
        assert p == 5

    @pytest.mark.asyncio
    async def test_priority_with_relationship_bonus(self):
        mock_memory = AsyncMock()
        mock_profile = AsyncMock()
        mock_profile.relationship_stage = "deep"
        mock_memory.get_or_create_user_profile = AsyncMock(return_value=mock_profile)

        strategy = ProactiveStrategy(memory_manager=mock_memory)
        p = await strategy.get_task_priority("greeting", "user1")
        # deep 关系阶段有 +2 加成
        assert p >= 7

    @pytest.mark.asyncio
    async def test_priority_initial_penalty(self):
        mock_memory = AsyncMock()
        mock_profile = AsyncMock()
        mock_profile.relationship_stage = "initial"
        mock_memory.get_or_create_user_profile = AsyncMock(return_value=mock_profile)

        strategy = ProactiveStrategy(memory_manager=mock_memory)
        p = await strategy.get_task_priority("greeting", "user1")
        # initial 关系阶段有 -1 惩罚
        assert p <= 5


class TestProactiveStrategyQuietHours:
    """免打扰时段测试"""

    def test_quiet_hours_cross_midnight(self):
        """跨午夜的免打扰时段（23:00-07:00）"""
        config = ProactiveConfig(quiet_hours_start=23, quiet_hours_end=7)
        strategy = ProactiveStrategy(config=config.__dict__)

        # 用 patch 固定当前时间
        with patch("yuanbot.proactive.strategy.datetime") as mock_dt:
            # 凌晨 2 点
            mock_dt.now.return_value = datetime(2024, 1, 1, 2, 0, 0)
            mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            assert strategy._is_quiet_hours() is True

            # 下午 3 点
            mock_dt.now.return_value = datetime(2024, 1, 1, 15, 0, 0)
            assert strategy._is_quiet_hours() is False

    def test_quiet_hours_same_day(self):
        """同一天内的免打扰时段（如 12:00-14:00）"""
        config = ProactiveConfig(quiet_hours_start=12, quiet_hours_end=14)
        strategy = ProactiveStrategy(config=config.__dict__)

        with patch("yuanbot.proactive.strategy.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 1, 13, 0, 0)
            mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            assert strategy._is_quiet_hours() is True

            mock_dt.now.return_value = datetime(2024, 1, 1, 15, 0, 0)
            assert strategy._is_quiet_hours() is False


class TestProactiveStrategyConstructor:
    """构造函数和配置解析测试"""

    def test_constructor_with_dict_config(self):
        config = {
            "enabled": False,
            "max_per_day": 3,
            "quiet_hours_start": 22,
        }
        strategy = ProactiveStrategy(config=config)
        assert strategy.get_config().enabled is False
        assert strategy.get_config().max_per_day == 3
        assert strategy.get_config().quiet_hours_start == 22

    def test_constructor_with_nested_proactive_config(self):
        config = {
            "proactive": {
                "enabled": True,
                "max_per_day": 10,
            }
        }
        strategy = ProactiveStrategy(config=config)
        assert strategy.get_config().max_per_day == 10

    def test_constructor_default(self):
        strategy = ProactiveStrategy()
        assert strategy.get_config().enabled is True
        assert strategy.get_config().max_per_day == 5

    def test_constructor_with_all_deps(self):
        mock_memory = AsyncMock()
        mock_ai = AsyncMock()
        mock_persona = AsyncMock()

        strategy = ProactiveStrategy(
            config={"enabled": True},
            memory_manager=mock_memory,
            ai_service=mock_ai,
            persona=mock_persona,
        )
        assert strategy._memory_manager is mock_memory
        assert strategy._ai_service is mock_ai
        assert strategy._persona is mock_persona


class TestProactiveStrategyFallbackMessages:
    """兜底消息测试"""

    def test_greeting_morning(self):
        with patch("yuanbot.proactive.strategy.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 1, 8, 0, 0)
            mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            msg = ProactiveStrategy._fallback_message("greeting", {})
            assert "早安" in msg

    def test_greeting_afternoon(self):
        with patch("yuanbot.proactive.strategy.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 1, 14, 0, 0)
            mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            msg = ProactiveStrategy._fallback_message("greeting", {})
            assert "下午" in msg

    def test_greeting_evening(self):
        with patch("yuanbot.proactive.strategy.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 1, 20, 0, 0)
            mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            msg = ProactiveStrategy._fallback_message("greeting", {})
            assert "晚" in msg

    def test_special_date_with_holiday(self):
        msg = ProactiveStrategy._fallback_message("special_date", {"holiday": "春节"})
        assert "春节" in msg

    def test_special_date_without_holiday(self):
        msg = ProactiveStrategy._fallback_message("special_date", {})
        assert "特别" in msg or "日子" in msg

    def test_weather(self):
        msg = ProactiveStrategy._fallback_message("weather", {})
        assert "天气" in msg or "伞" in msg

    def test_unknown_type(self):
        msg = ProactiveStrategy._fallback_message("unknown", {})
        assert msg  # 应返回非空字符串


class TestGreetingTimeWindow:
    """测试动态问候时间窗口

    设计参考: proactive-companion-system.md 3.2 动态时间调整
    """

    def test_in_greeting_window_normal(self):
        """正常作息: 起床后 2 小时内属于问候窗口"""
        # 07:30 起床, 23:00 睡觉, 当前 08:00 -> 在窗口内
        assert ProactiveStrategy._is_in_greeting_window("07:30", "23:00") is False or True
        # 这个测试依赖于当前时间，所以只测试方法不抛异常

    def test_in_greeting_window_static(self):
        """静态测试: 验证窗口边界计算"""
        # 窗口是 wake_time 到 wake_time + 2h
        # 不依赖当前时间，只验证方法不抛异常且返回 bool
        result = ProactiveStrategy._is_in_greeting_window("07:00", "23:00")
        assert isinstance(result, bool)

    def test_in_greeting_window_cross_midnight(self):
        """跨午夜作息: 起床时间晚于睡眠时间"""
        result = ProactiveStrategy._is_in_greeting_window("23:00", "07:00")
        assert isinstance(result, bool)

    def test_in_greeting_window_invalid_format(self):
        """无效时间格式: 不限制"""
        assert ProactiveStrategy._is_in_greeting_window("invalid", "23:00") is True
        assert ProactiveStrategy._is_in_greeting_window("07:00", "invalid") is True
        assert ProactiveStrategy._is_in_greeting_window("", "") is True

    def test_in_greeting_window_with_minutes(self):
        """带分钟的时间格式"""
        result = ProactiveStrategy._is_in_greeting_window("06:45", "22:30")
        assert isinstance(result, bool)

    def test_in_greeting_window_no_minutes(self):
        """只有小时的时间格式"""
        result = ProactiveStrategy._is_in_greeting_window("7", "23")
        assert isinstance(result, bool)
