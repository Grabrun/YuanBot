"""主动触发调度器

管理所有定时任务和事件监听器的注册、调度与生命周期。
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog
from croniter import croniter

logger = structlog.get_logger(__name__)


@dataclass
class ScheduledTask:
    """定时任务数据结构"""

    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_type: str = "cron"  # "cron" 或 "event"
    trigger: str = ""  # Cron 表达式或事件类型
    name: str = ""
    target_users: list[str] = field(default_factory=list)
    priority: int = 5  # 1-10
    max_retries: int = 3
    enabled: bool = True
    last_run: datetime | None = None
    next_run: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ProactiveScheduler:
    """主动触发调度器

    管理所有定时任务和事件监听器的注册、调度与生命周期。

    职责：
    1. 管理定时任务的注册和调度
    2. 每 30 秒检查一次到期任务
    3. 支持 Cron 表达式（通过 croniter）
    4. 与策略决策器协作，提交到期任务
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        memory_manager: Any = None,
        ai_service: Any = None,
        push_dispatcher: Any = None,
    ) -> None:
        self._config = config or {}
        self._memory_manager = memory_manager
        self._ai_service = ai_service
        self._push_dispatcher = push_dispatcher
        self._tasks: dict[str, ScheduledTask] = {}
        self._running = False
        self._loop_task: asyncio.Task[None] | None = None
        self._check_interval: int = self._config.get("check_interval_seconds", 30)

    async def start(self) -> None:
        """启动调度器，开始调度循环"""
        if self._running:
            logger.warning("scheduler_already_running")
            return
        self._running = True

        # 注册默认的记忆整理定时任务
        self._register_default_memory_tasks()

        self._loop_task = asyncio.create_task(self._run_loop())
        logger.info("scheduler_started", check_interval=self._check_interval)

    def _register_default_memory_tasks(self) -> None:
        """注册默认的记忆整理定时任务

        设计要求: 空闲时自动整理记忆
        - 记忆固化: 每天凌晨 3:00 执行
        - 遗忘曲线: 每天凌晨 4:00 执行
        """
        consolidation_config = {}
        if self._config:
            consolidation_config = self._config.get("memory_consolidation", {})

        # 记忆固化任务
        consolidation_schedule = consolidation_config.get("consolidation_cron", "0 3 * * *")
        consolidation_task = ScheduledTask(
            task_type="cron",
            trigger=consolidation_schedule,
            name="memory_consolidation",
            priority=3,
            metadata={"action": "consolidate_memories"},
        )
        self.register_task(consolidation_task)

        # 遗忘曲线任务
        forget_curve_schedule = consolidation_config.get("forget_curve_cron", "0 4 * * *")
        forget_task = ScheduledTask(
            task_type="cron",
            trigger=forget_curve_schedule,
            name="forget_curve",
            priority=2,
            metadata={"action": "apply_forget_curve"},
        )
        self.register_task(forget_task)

        logger.info(
            "memory_tasks_registered",
            consolidation_cron=consolidation_schedule,
            forget_curve_cron=forget_curve_schedule,
        )

    async def stop(self) -> None:
        """停止调度器"""
        self._running = False
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._loop_task
        self._loop_task = None
        logger.info("scheduler_stopped")

    @property
    def is_running(self) -> bool:
        """调度器是否正在运行"""
        return self._running

    def register_task(self, task: ScheduledTask) -> str:
        """注册定时任务

        Returns:
            任务 ID
        """
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
        return [
            task
            for task in self._tasks.values()
            if task.enabled and task.next_run is not None and task.next_run <= now
        ]

    def mark_executed(self, task_id: str) -> None:
        """标记任务已执行，更新下次执行时间"""
        task = self._tasks.get(task_id)
        if not task:
            return

        task.last_run = datetime.now()

        # event 类型的任务不自动调度下次
        if task.task_type == "event":
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

    async def _run_loop(self) -> None:
        """调度主循环：每 30 秒检查一次到期任务"""
        try:
            while self._running:
                await self._check_and_execute()
                await asyncio.sleep(self._check_interval)
        except asyncio.CancelledError:
            logger.debug("scheduler_loop_cancelled")

    async def _check_and_execute(self) -> None:
        """检查到期任务并执行"""
        due_tasks = self.get_due_tasks()
        if not due_tasks:
            return

        # 按优先级排序（高优先级先执行）
        due_tasks.sort(key=lambda t: t.priority, reverse=True)

        for task in due_tasks:
            logger.info(
                "task_due",
                task_id=task.task_id,
                name=task.name,
                priority=task.priority,
            )

            # 执行内置的记忆整理任务
            action = task.metadata.get("action", "")
            if action in ("consolidate_memories", "apply_forget_curve") and self._memory_manager:
                await self._execute_memory_task(action)

            # 标记已执行（更新下次执行时间）
            self.mark_executed(task.task_id)

    async def _execute_memory_task(self, action: str) -> None:
        """执行记忆整理任务

        遍历所有用户，执行对应的记忆维护操作。
        """
        try:
            # 获取所有用户 ID
            user_ids: list[str] = []
            if hasattr(self._memory_manager, "_user_profiles"):
                user_ids = list(self._memory_manager._user_profiles.keys())
            if hasattr(self._memory_manager, "_fact_memories"):
                user_ids = list(set(user_ids) | set(self._memory_manager._fact_memories.keys()))
            if hasattr(self._memory_manager, "_episodic_memories"):
                user_ids = list(set(user_ids) | set(self._memory_manager._episodic_memories.keys()))

            for user_id in user_ids:
                if action == "consolidate_memories":
                    stats = await self._memory_manager.consolidate_memories(user_id)
                    logger.info("memory_consolidation_executed", user_id=user_id, **stats)
                elif action == "apply_forget_curve":
                    removed = await self._memory_manager.apply_forget_curve(user_id)
                    logger.info("forget_curve_executed", user_id=user_id, removed=removed)

            if not user_ids:
                logger.debug("no_users_for_memory_task", action=action)
        except Exception:
            logger.exception("memory_task_failed", action=action)

    def _calculate_next_run(self, task: ScheduledTask) -> datetime | None:
        """计算下次执行时间"""
        now = datetime.now()

        if task.task_type == "cron" and task.trigger:
            return self._parse_cron_next(task.trigger, now)

        if task.task_type == "event":
            return None

        return None

    @staticmethod
    def _parse_cron_next(cron_expr: str, after: datetime) -> datetime | None:
        """使用 croniter 解析 Cron 表达式，计算下次执行时间

        Args:
            cron_expr: 标准 5 字段 Cron 表达式
            after: 起始时间

        Returns:
            下次执行时间，解析失败返回 None
        """
        try:
            cron = croniter(cron_expr, after)
            return cron.get_next(datetime)
        except (ValueError, KeyError):
            logger.warning("invalid_cron_expression", expression=cron_expr)
            return None
