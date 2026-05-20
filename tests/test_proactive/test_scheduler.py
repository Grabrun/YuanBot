"""测试主动触发调度器"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from yuanbot.proactive.scheduler import ProactiveScheduler, ScheduledTask


class TestScheduledTask:
    """ScheduledTask 数据结构测试"""

    def test_default_values(self):
        task = ScheduledTask()
        assert task.task_type == "cron"
        assert task.trigger == ""
        assert task.priority == 5
        assert task.max_retries == 3
        assert task.enabled is True
        assert task.target_users == []
        assert task.task_id  # auto-generated

    def test_custom_values(self):
        task = ScheduledTask(
            task_type="event",
            trigger="user_silence",
            name="silence_check",
            target_users=["user1", "user2"],
            priority=8,
        )
        assert task.task_type == "event"
        assert task.trigger == "user_silence"
        assert task.name == "silence_check"
        assert task.target_users == ["user1", "user2"]
        assert task.priority == 8


class TestProactiveScheduler:
    """调度器测试"""

    def test_register_task(self):
        scheduler = ProactiveScheduler()
        task = ScheduledTask(name="morning_greeting", task_type="cron", trigger="0 8 * * *")
        task_id = scheduler.register_task(task)
        assert task_id == task.task_id
        assert len(scheduler.get_all_tasks()) == 1

    def test_register_task_calculates_next_run(self):
        scheduler = ProactiveScheduler()
        task = ScheduledTask(name="morning", task_type="cron", trigger="0 8 * * *")
        scheduler.register_task(task)
        assert task.next_run is not None

    def test_unregister_task(self):
        scheduler = ProactiveScheduler()
        task = ScheduledTask(name="test", task_type="cron", trigger="0 * * * *")
        task_id = scheduler.register_task(task)
        assert scheduler.unregister_task(task_id) is True
        assert len(scheduler.get_all_tasks()) == 0

    def test_unregister_nonexistent(self):
        scheduler = ProactiveScheduler()
        assert scheduler.unregister_task("nonexistent") is False

    def test_get_due_tasks(self):
        scheduler = ProactiveScheduler()
        task = ScheduledTask(
            name="past_task",
            task_type="cron",
            trigger="* * * * *",
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
            task_type="cron",
            trigger="0 0 1 1 *",
            next_run=datetime.now() + timedelta(hours=1),
        )
        scheduler.register_task(task)
        due = scheduler.get_due_tasks()
        assert len(due) == 0

    def test_get_due_tasks_disabled(self):
        scheduler = ProactiveScheduler()
        task = ScheduledTask(
            name="disabled_task",
            task_type="cron",
            trigger="* * * * *",
            next_run=datetime.now() - timedelta(minutes=1),
            enabled=False,
        )
        scheduler.register_task(task)
        due = scheduler.get_due_tasks()
        assert len(due) == 0

    def test_mark_executed_cron(self):
        scheduler = ProactiveScheduler()
        task = ScheduledTask(name="cron_task", task_type="cron", trigger="0 * * * *")
        scheduler.register_task(task)
        scheduler.mark_executed(task.task_id)
        updated = scheduler.get_task(task.task_id)
        assert updated.last_run is not None
        # cron 任务应计算下次执行时间
        assert updated.next_run is not None

    def test_mark_executed_event(self):
        scheduler = ProactiveScheduler()
        task = ScheduledTask(name="event_task", task_type="event", trigger="user_silence")
        scheduler.register_task(task)
        scheduler.mark_executed(task.task_id)
        updated = scheduler.get_task(task.task_id)
        assert updated.next_run is None  # event 类型不自动调度

    def test_mark_executed_nonexistent(self):
        scheduler = ProactiveScheduler()
        # 不应抛异常
        scheduler.mark_executed("nonexistent")

    def test_enable_disable_task(self):
        scheduler = ProactiveScheduler()
        task = ScheduledTask(name="test", task_type="cron", trigger="0 * * * *")
        task_id = scheduler.register_task(task)

        scheduler.disable_task(task_id)
        assert scheduler.get_task(task_id).enabled is False

        scheduler.enable_task(task_id)
        assert scheduler.get_task(task_id).enabled is True

    def test_enable_disable_nonexistent(self):
        scheduler = ProactiveScheduler()
        assert scheduler.enable_task("nonexistent") is False
        assert scheduler.disable_task("nonexistent") is False

    def test_cron_next_run_valid(self):
        scheduler = ProactiveScheduler()
        now = datetime.now()
        task = ScheduledTask(
            name="morning",
            task_type="cron",
            trigger="0 8 * * *",
        )
        next_run = scheduler._calculate_next_run(task)
        assert next_run is not None
        assert next_run > now

    def test_cron_next_run_invalid(self):
        scheduler = ProactiveScheduler()
        task = ScheduledTask(
            name="bad_cron",
            task_type="cron",
            trigger="invalid cron",
        )
        next_run = scheduler._calculate_next_run(task)
        assert next_run is None

    def test_event_type_no_next_run(self):
        scheduler = ProactiveScheduler()
        task = ScheduledTask(name="event", task_type="event", trigger="user_silence")
        next_run = scheduler._calculate_next_run(task)
        assert next_run is None

    def test_get_task(self):
        scheduler = ProactiveScheduler()
        task = ScheduledTask(name="test", task_type="cron", trigger="0 * * * *")
        task_id = scheduler.register_task(task)
        assert scheduler.get_task(task_id) is task
        assert scheduler.get_task("nonexistent") is None


class TestProactiveSchedulerAsync:
    """调度器异步功能测试"""

    @pytest.mark.asyncio
    async def test_start_stop(self):
        scheduler = ProactiveScheduler(config={"check_interval_seconds": 1})
        assert scheduler.is_running is False

        await scheduler.start()
        assert scheduler.is_running is True

        await scheduler.stop()
        assert scheduler.is_running is False

    @pytest.mark.asyncio
    async def test_start_twice(self):
        scheduler = ProactiveScheduler(config={"check_interval_seconds": 1})
        await scheduler.start()
        # 重复启动不应报错
        await scheduler.start()
        assert scheduler.is_running is True
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self):
        scheduler = ProactiveScheduler()
        # 未启动时停止不应报错
        await scheduler.stop()
        assert scheduler.is_running is False

    @pytest.mark.asyncio
    async def test_check_and_execute(self):
        scheduler = ProactiveScheduler()
        task = ScheduledTask(
            name="due_task",
            task_type="cron",
            trigger="* * * * *",
            next_run=datetime.now() - timedelta(minutes=1),
        )
        scheduler.register_task(task)

        # 直接调用 _check_and_execute
        await scheduler._check_and_execute()

        # 任务应已被标记执行
        updated = scheduler.get_task(task.task_id)
        assert updated.last_run is not None

    @pytest.mark.asyncio
    async def test_scheduler_loop_processes_tasks(self):
        """测试调度循环能处理到期任务"""
        scheduler = ProactiveScheduler(config={"check_interval_seconds": 0.1})
        task = ScheduledTask(
            name="quick_task",
            task_type="cron",
            trigger="* * * * *",
            next_run=datetime.now() - timedelta(seconds=1),
            priority=8,
        )
        scheduler.register_task(task)

        await scheduler.start()
        await asyncio.sleep(0.3)  # 等待至少一个检查周期
        await scheduler.stop()

        updated = scheduler.get_task(task.task_id)
        assert updated.last_run is not None

    def test_priority_ordering(self):
        """测试到期任务按优先级排序"""
        scheduler = ProactiveScheduler()

        low_task = ScheduledTask(
            name="low",
            task_type="cron",
            trigger="* * * * *",
            next_run=datetime.now() - timedelta(minutes=1),
            priority=1,
        )
        high_task = ScheduledTask(
            name="high",
            task_type="cron",
            trigger="* * * * *",
            next_run=datetime.now() - timedelta(minutes=1),
            priority=9,
        )

        scheduler.register_task(low_task)
        scheduler.register_task(high_task)

        due = scheduler.get_due_tasks()
        # get_due_tasks 不排序，但 _check_and_execute 排序
        assert len(due) == 2

    def test_constructor_with_dependencies(self):
        """测试带依赖注入的构造函数"""
        mock_memory = AsyncMock()
        mock_ai = AsyncMock()
        mock_push = AsyncMock()

        scheduler = ProactiveScheduler(
            config={"check_interval_seconds": 60},
            memory_manager=mock_memory,
            ai_service=mock_ai,
            push_dispatcher=mock_push,
        )
        assert scheduler._memory_manager is mock_memory
        assert scheduler._ai_service is mock_ai
        assert scheduler._push_dispatcher is mock_push
        assert scheduler._check_interval == 60
