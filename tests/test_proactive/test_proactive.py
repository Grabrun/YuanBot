"""测试主动陪伴与自动化系统"""

from __future__ import annotations

from datetime import datetime, timedelta

from yuanbot.proactive.event_engine import EventEngine, EventTrigger, EventType
from yuanbot.proactive.scheduler import ProactiveScheduler, ScheduledTask
from yuanbot.proactive.strategy import ProactiveConfig, ProactiveDecision, ProactiveStrategy


class TestProactiveScheduler:
    """调度器测试"""

    def test_register_task(self):
        scheduler = ProactiveScheduler()
        task = ScheduledTask(name="morning_greeting", task_type="interval", interval_seconds=3600)
        task_id = scheduler.register_task(task)
        assert task_id == task.task_id
        assert len(scheduler.get_all_tasks()) == 1

    def test_unregister_task(self):
        scheduler = ProactiveScheduler()
        task = ScheduledTask(name="test", task_type="once")
        task_id = scheduler.register_task(task)
        assert scheduler.unregister_task(task_id) is True
        assert len(scheduler.get_all_tasks()) == 0

    def test_unregister_nonexistent(self):
        scheduler = ProactiveScheduler()
        assert scheduler.unregister_task("nonexistent") is False

    def test_get_due_tasks(self):
        scheduler = ProactiveScheduler()
        # 创建一个已经到期的任务
        task = ScheduledTask(
            name="past_task",
            task_type="once",
            next_run=datetime.now() - timedelta(minutes=5),
        )
        scheduler.register_task(task)
        due = scheduler.get_due_tasks()
        assert len(due) == 1
        assert due[0].name == "past_task"

    def test_get_due_tasks_not_due(self):
        scheduler = ProactiveScheduler()
        task = ScheduledTask(
            name="future_task",
            task_type="once",
            next_run=datetime.now() + timedelta(hours=1),
        )
        scheduler.register_task(task)
        due = scheduler.get_due_tasks()
        assert len(due) == 0

    def test_mark_executed_once(self):
        scheduler = ProactiveScheduler()
        task = ScheduledTask(name="once_task", task_type="once")
        scheduler.register_task(task)
        scheduler.mark_executed(task.task_id)
        updated = scheduler.get_task(task.task_id)
        assert updated.enabled is False

    def test_mark_executed_interval(self):
        scheduler = ProactiveScheduler()
        task = ScheduledTask(name="interval_task", task_type="interval", interval_seconds=60)
        scheduler.register_task(task)
        scheduler.mark_executed(task.task_id)
        updated = scheduler.get_task(task.task_id)
        assert updated.enabled is True
        assert updated.next_run is not None

    def test_enable_disable_task(self):
        scheduler = ProactiveScheduler()
        task = ScheduledTask(name="test", task_type="once")
        task_id = scheduler.register_task(task)

        scheduler.disable_task(task_id)
        assert scheduler.get_task(task_id).enabled is False

        scheduler.enable_task(task_id)
        assert scheduler.get_task(task_id).enabled is True

    def test_cron_next_run(self):
        scheduler = ProactiveScheduler()
        task = ScheduledTask(
            name="morning",
            task_type="cron",
            cron_expression="8 0 * * *",
        )
        next_run = scheduler._calculate_next_run(task)
        assert next_run is not None


class TestProactiveStrategy:
    """策略决策器测试"""

    def test_should_act_normal(self):
        config = ProactiveConfig(enabled=True, quiet_hours_start=23, quiet_hours_end=8)
        strategy = ProactiveStrategy(config)
        # 假设当前不在免打扰时段
        decision = strategy.should_act("user1")
        assert isinstance(decision, ProactiveDecision)

    def test_disabled_strategy(self):
        config = ProactiveConfig(enabled=False)
        strategy = ProactiveStrategy(config)
        decision = strategy.should_act("user1")
        assert decision.should_act is False
        assert decision.reason == "proactive_disabled"

    def test_event_triggers_disabled(self):
        config = ProactiveConfig(enabled=True, event_triggers_enabled=False)
        strategy = ProactiveStrategy(config)
        decision = strategy.should_act("user1", is_event_triggered=True)
        assert decision.should_act is False
        assert decision.reason == "event_triggers_disabled"

    def test_daily_limit(self):
        config = ProactiveConfig(enabled=True, max_per_day=1)
        strategy = ProactiveStrategy(config)
        # 第一次应该成功
        strategy.should_act("user1")
        # 第二次应该被限制
        decision2 = strategy.should_act("user1")
        assert decision2.should_act is False
        assert decision2.reason == "daily_limit_reached"

    def test_update_config(self):
        strategy = ProactiveStrategy()
        new_config = ProactiveConfig(enabled=False)
        strategy.update_config(new_config)
        assert strategy.get_config().enabled is False

    def test_get_daily_stats(self):
        strategy = ProactiveStrategy()
        strategy.should_act("user1")
        stats = strategy.get_daily_stats()
        assert "user1" in stats


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

    def test_check_silence_event(self):
        engine = EventEngine()
        engine.register_trigger(EventTrigger(
            event_type=EventType.USER_SILENCE,
            name="silence",
            user_ids=["user1"],
        ))
        event = engine.check_silence_events(
            "user1",
            last_interaction=datetime.now() - timedelta(hours=3),
            threshold_minutes=120,
        )
        assert event is not None
        assert event.event_type == EventType.USER_SILENCE

    def test_check_silence_not_triggered(self):
        engine = EventEngine()
        engine.register_trigger(EventTrigger(
            event_type=EventType.USER_SILENCE,
            name="silence",
            user_ids=["user1"],
        ))
        event = engine.check_silence_events(
            "user1",
            last_interaction=datetime.now() - timedelta(minutes=10),
            threshold_minutes=120,
        )
        assert event is None

    def test_check_emotion_risk(self):
        engine = EventEngine()
        engine.register_trigger(EventTrigger(
            event_type=EventType.EMOTION_RISK,
            name="emotion_risk",
            user_ids=["user1"],
        ))
        event = engine.check_emotion_risk("user1", "sadness", 0.8)
        assert event is not None
        assert event.event_type == EventType.EMOTION_RISK

    def test_check_emotion_risk_not_triggered(self):
        engine = EventEngine()
        engine.register_trigger(EventTrigger(
            event_type=EventType.EMOTION_RISK,
            name="emotion_risk",
        ))
        # 低强度不触发
        event = engine.check_emotion_risk("user1", "sadness", 0.3)
        assert event is None

    def test_check_special_date(self):
        engine = EventEngine()
        engine.register_trigger(EventTrigger(
            event_type=EventType.SPECIAL_DATE,
            name="birthday",
        ))
        today = datetime.now().strftime("%m-%d")
        event = engine.check_special_date("user1", {"birthday": today})
        assert event is not None

    def test_emit_custom_event(self):
        engine = EventEngine()
        engine.register_trigger(EventTrigger(
            event_type=EventType.CUSTOM,
            name="custom",
        ))
        event = engine.emit_custom_event("user1", "test_event", {"key": "value"})
        assert event is not None
        assert event.event_type == EventType.CUSTOM

    def test_get_recent_events(self):
        engine = EventEngine()
        engine.register_trigger(EventTrigger(
            event_type=EventType.CUSTOM,
            name="custom",
        ))
        engine.emit_custom_event("user1", "event1")
        engine.emit_custom_event("user1", "event2")
        events = engine.get_recent_events("user1")
        assert len(events) == 2
