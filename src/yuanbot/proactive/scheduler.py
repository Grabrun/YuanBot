"""主动触发调度器

管理所有定时任务和事件监听器的注册、调度与生命周期。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ScheduledTask:
    """定时任务"""

    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    task_type: str = "cron"  # "cron" | "interval" | "once"
    cron_expression: str | None = None
    interval_seconds: int | None = None
    user_ids: list[str] = field(default_factory=list)
    priority: int = 0  # 0=低, 1=中, 2=高
    enabled: bool = True
    last_run: datetime | None = None
    next_run: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ProactiveScheduler:
    """主动触发调度器

    职责：
    1. 管理定时任务的注册和调度
    2. 计算下次执行时间
    3. 支持 Cron 表达式和间隔时间
    4. 热重载配置
    """

    def __init__(self) -> None:
        self._tasks: dict[str, ScheduledTask] = {}
        self._running = False

    def register_task(self, task: ScheduledTask) -> str:
        """注册定时任务

        Returns:
            任务 ID
        """
        # 计算下次执行时间
        if task.next_run is None:
            task.next_run = self._calculate_next_run(task)

        self._tasks[task.task_id] = task
        logger.info(
            "task_registered",
            task_id=task.task_id,
            name=task.name,
            task_type=task.task_type,
            next_run=task.next_run.isoformat() if task.next_run else None,
        )
        return task.task_id

    def unregister_task(self, task_id: str) -> bool:
        """注销定时任务"""
        if task_id in self._tasks:
            del self._tasks[task_id]
            logger.info("task_unregistered", task_id=task_id)
            return True
        return False

    def get_due_tasks(self) -> list[ScheduledTask]:
        """获取到期的任务"""
        now = datetime.now()
        due = []
        for task in self._tasks.values():
            if (
                task.enabled
                and task.next_run is not None
                and task.next_run <= now
            ):
                due.append(task)
        return due

    def mark_executed(self, task_id: str) -> None:
        """标记任务已执行，更新下次执行时间"""
        task = self._tasks.get(task_id)
        if not task:
            return

        task.last_run = datetime.now()

        # 一次性任务执行后禁用
        if task.task_type == "once":
            task.enabled = False
            task.next_run = None
        else:
            task.next_run = self._calculate_next_run(task)

        logger.debug(
            "task_executed",
            task_id=task_id,
            next_run=task.next_run.isoformat() if task.next_run else None,
        )

    def get_all_tasks(self) -> list[ScheduledTask]:
        """获取所有任务"""
        return list(self._tasks.values())

    def get_task(self, task_id: str) -> ScheduledTask | None:
        """获取指定任务"""
        return self._tasks.get(task_id)

    def enable_task(self, task_id: str) -> bool:
        """启用任务"""
        task = self._tasks.get(task_id)
        if task:
            task.enabled = True
            task.next_run = self._calculate_next_run(task)
            return True
        return False

    def disable_task(self, task_id: str) -> bool:
        """禁用任务"""
        task = self._tasks.get(task_id)
        if task:
            task.enabled = False
            return True
        return False

    def _calculate_next_run(self, task: ScheduledTask) -> datetime | None:
        """计算下次执行时间"""
        now = datetime.now()

        if task.task_type == "interval" and task.interval_seconds:
            if task.last_run:
                return task.last_run + timedelta(seconds=task.interval_seconds)
            return now + timedelta(seconds=task.interval_seconds)

        if task.task_type == "cron" and task.cron_expression:
            return self._parse_cron_next(task.cron_expression, now)

        if task.task_type == "once":
            if task.next_run and task.next_run > now:
                return task.next_run
            return now

        return None

    @staticmethod
    def _parse_cron_next(cron_expr: str, after: datetime) -> datetime:
        """简易 Cron 解析器

        支持格式: "minute hour day month weekday"
        特殊值: * 表示任意

        注意：这是一个简化的实现，仅支持基本的 Cron 语法。
        生产环境建议使用 croniter 库。
        """
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            # 默认每小时
            return after + timedelta(hours=1)

        minute_part, hour_part, _, _, _ = parts

        # 简单实现：如果指定了具体时间，计算下次匹配
        next_run = after + timedelta(minutes=1)
        next_run = next_run.replace(second=0, microsecond=0)

        # 尝试匹配分钟
        if minute_part != "*":
            try:
                target_minute = int(minute_part)
                if next_run.minute > target_minute:
                    next_run += timedelta(hours=1)
                next_run = next_run.replace(minute=target_minute)
            except ValueError:
                pass

        # 尝试匹配小时
        if hour_part != "*":
            try:
                target_hour = int(hour_part)
                if next_run.hour > target_hour:
                    next_run += timedelta(days=1)
                next_run = next_run.replace(hour=target_hour)
            except ValueError:
                pass

        return next_run
