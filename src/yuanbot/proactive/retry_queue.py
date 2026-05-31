"""持久化重试队列

基于 SQLite 的消息发送失败重试队列。
进程重启后队列不丢失，支持延迟重试和最大重试次数。

设计参考: proactive-companion-system.md 第3.5节（失败重试机制）
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class RetryTask:
    """重试任务

    Attributes:
        task_id: 唯一任务 ID
        user_id: 目标用户 ID
        task_type: 任务类型（如 greeting, care, weather 等）
        message: 待发送的消息文本
        channel: 通道标识（如 telegram, webchat 等）
        metadata: 附加元数据
        retry_count: 已重试次数
        max_retries: 最大重试次数
        next_retry_at: 下次重试的时间戳
        created_at: 创建时间戳
        last_error: 最后一次错误信息
        status: 状态 (pending / retrying / completed / failed)
    """

    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    task_type: str = ""
    message: str = ""
    channel: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0
    max_retries: int = 3
    next_retry_at: float = 0.0
    created_at: float = field(default_factory=time.time)
    last_error: str = ""
    status: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "task_type": self.task_type,
            "message": self.message,
            "channel": self.channel,
            "metadata": self.metadata,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "next_retry_at": self.next_retry_at,
            "created_at": self.created_at,
            "last_error": self.last_error,
            "status": self.status,
        }


# 发送函数类型: async (user_id, message, channel, **kwargs) -> bool
SendFunc = Callable[..., Coroutine[Any, Any, bool]]


class PersistentRetryQueue:
    """持久化重试队列

    使用 SQLite 存储待重试的消息发送任务。
    进程重启后队列自动恢复，避免消息丢失。

    使用示例::

        queue = PersistentRetryQueue(db_path="data/proactive_retry.db")
        await queue.initialize()

        # 入队一个重试任务
        task = RetryTask(
            user_id="u_123",
            task_type="greeting",
            message="早安～",
            channel="telegram",
        )
        await queue.enqueue(task)

        # 启动重试消费者
        async def send_func(user_id, message, channel, **kw):
            # 实际发送逻辑
            return True

        await queue.start_consumer(send_func)

        # 停止
        await queue.stop_consumer()
    """

    # 重试延迟策略（秒），按重试次数递增
    DEFAULT_RETRY_DELAYS = (60, 300, 900, 1800, 3600)  # 1m, 5m, 15m, 30m, 1h

    def __init__(
        self,
        db_path: str = "data/proactive_retry.db",
        retry_delays: tuple[int, ...] | None = None,
        consumer_interval: int = 30,
    ) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._retry_delays = retry_delays or self.DEFAULT_RETRY_DELAYS
        self._consumer_interval = consumer_interval
        self._consumer_task: asyncio.Task[None] | None = None
        self._running = False

    async def initialize(self) -> None:
        """初始化数据库表"""
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS retry_queue (
                task_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                task_type TEXT NOT NULL,
                message TEXT NOT NULL,
                channel TEXT NOT NULL DEFAULT '',
                metadata TEXT NOT NULL DEFAULT '{}',
                retry_count INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 3,
                next_retry_at REAL NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                last_error TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending'
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_retry_status_next
            ON retry_queue(status, next_retry_at)
        """)
        self._conn.commit()
        logger.info("retry_queue_initialized", db_path=str(self._db_path))

    async def close(self) -> None:
        """关闭数据库连接"""
        await self.stop_consumer()
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── 队列操作 ──────────────────────────────

    async def enqueue(self, task: RetryTask) -> str:
        """将任务加入重试队列

        Args:
            task: 重试任务

        Returns:
            任务 ID
        """
        if not self._conn:
            await self.initialize()

        # 计算下次重试时间
        if task.next_retry_at <= 0:
            # 首次入队(retry_count=0)应立即到期，重试时才有延迟
            if task.retry_count > 0:
                task.next_retry_at = self._calculate_next_retry(task.retry_count)
            else:
                task.next_retry_at = 0.0  # 立即到期

        self._conn.execute(
            """
            INSERT OR REPLACE INTO retry_queue
            (task_id, user_id, task_type, message, channel, metadata,
             retry_count, max_retries, next_retry_at, created_at, last_error, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.task_id,
                task.user_id,
                task.task_type,
                task.message,
                task.channel,
                json.dumps(task.metadata, ensure_ascii=False),
                task.retry_count,
                task.max_retries,
                task.next_retry_at,
                task.created_at,
                task.last_error,
                task.status,
            ),
        )
        self._conn.commit()

        logger.info(
            "task_enqueued",
            task_id=task.task_id,
            user_id=task.user_id,
            task_type=task.task_type,
            retry_count=task.retry_count,
            next_retry_at=task.next_retry_at,
        )
        return task.task_id

    async def enqueue_simple(
        self,
        user_id: str,
        task_type: str,
        message: str,
        channel: str = "",
        max_retries: int = 3,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """简化入队接口

        Returns:
            任务 ID
        """
        task = RetryTask(
            user_id=user_id,
            task_type=task_type,
            message=message,
            channel=channel,
            max_retries=max_retries,
            metadata=metadata or {},
        )
        return await self.enqueue(task)

    async def get_due_tasks(self, limit: int = 10) -> list[RetryTask]:
        """获取到期的待重试任务

        Args:
            limit: 最大返回数量

        Returns:
            到期任务列表
        """
        if not self._conn:
            return []

        now = time.time()
        rows = self._conn.execute(
            """
            SELECT * FROM retry_queue
            WHERE status IN ('pending', 'retrying') AND next_retry_at <= ?
            ORDER BY next_retry_at ASC
            LIMIT ?
            """,
            (now, limit),
        ).fetchall()

        return [self._row_to_task(row) for row in rows]

    async def mark_retrying(self, task_id: str) -> None:
        """标记任务为正在重试"""
        if not self._conn:
            return
        self._conn.execute(
            "UPDATE retry_queue SET status = 'retrying' WHERE task_id = ?",
            (task_id,),
        )
        self._conn.commit()

    async def mark_success(self, task_id: str) -> None:
        """标记任务发送成功，从队列中移除"""
        if not self._conn:
            return
        self._conn.execute(
            "UPDATE retry_queue SET status = 'completed' WHERE task_id = ?",
            (task_id,),
        )
        self._conn.commit()
        logger.info("task_completed", task_id=task_id)

    async def mark_failed(self, task_id: str, error: str = "") -> None:
        """标记任务重试失败

        如果还有重试次数，更新重试计数和下次重试时间；
        否则标记为最终失败。
        """
        if not self._conn:
            return

        row = self._conn.execute(
            "SELECT * FROM retry_queue WHERE task_id = ?", (task_id,)
        ).fetchone()

        if not row:
            return

        task = self._row_to_task(row)
        task.retry_count += 1
        task.last_error = error

        if task.retry_count >= task.max_retries:
            # 超过最大重试次数，标记为最终失败
            task.status = "failed"
            logger.warning(
                "task_failed_permanently",
                task_id=task_id,
                retry_count=task.retry_count,
                error=error,
            )
        else:
            # 还可以重试，更新下次重试时间
            task.status = "pending"
            task.next_retry_at = self._calculate_next_retry(task.retry_count)
            logger.info(
                "task_retry_scheduled",
                task_id=task_id,
                retry_count=task.retry_count,
                next_retry_at=task.next_retry_at,
            )

        self._conn.execute(
            """
            UPDATE retry_queue
            SET retry_count = ?, last_error = ?, status = ?, next_retry_at = ?
            WHERE task_id = ?
            """,
            (
                task.retry_count,
                task.last_error,
                task.status,
                task.next_retry_at,
                task_id,
            ),
        )
        self._conn.commit()

    async def remove_task(self, task_id: str) -> bool:
        """从队列中移除任务"""
        if not self._conn:
            return False
        cursor = self._conn.execute(
            "DELETE FROM retry_queue WHERE task_id = ?", (task_id,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    async def get_pending_count(self) -> int:
        """获取待处理任务数量"""
        if not self._conn:
            return 0
        row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM retry_queue WHERE status IN ('pending', 'retrying')"
        ).fetchone()
        return row["cnt"] if row else 0

    async def get_failed_count(self) -> int:
        """获取最终失败的任务数量"""
        if not self._conn:
            return 0
        row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM retry_queue WHERE status = 'failed'"
        ).fetchone()
        return row["cnt"] if row else 0

    async def get_queue_stats(self) -> dict[str, int]:
        """获取队列统计信息"""
        if not self._conn:
            return {"pending": 0, "retrying": 0, "completed": 0, "failed": 0, "total": 0}

        stats: dict[str, int] = {}
        for status in ("pending", "retrying", "completed", "failed"):
            row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM retry_queue WHERE status = ?",
                (status,),
            ).fetchone()
            stats[status] = row["cnt"] if row else 0

        stats["total"] = sum(stats.values())
        return stats

    async def cleanup_completed(self, max_age_seconds: int = 86400) -> int:
        """清理已完成或最终失败的任务

        Args:
            max_age_seconds: 最大保留时间（秒），默认 24 小时

        Returns:
            清理的任务数量
        """
        if not self._conn:
            return 0

        cutoff = time.time() - max_age_seconds
        cursor = self._conn.execute(
            """
            DELETE FROM retry_queue
            WHERE status IN ('completed', 'failed') AND created_at < ?
            """,
            (cutoff,),
        )
        self._conn.commit()
        removed = cursor.rowcount
        if removed > 0:
            logger.info("retry_queue_cleanup", removed=removed)
        return removed

    # ── 消费者循环 ────────────────────────────

    async def start_consumer(self, send_func: SendFunc) -> None:
        """启动重试消费者

        定期检查队列中的到期任务并尝试发送。

        Args:
            send_func: 发送函数 async (user_id, message, channel, **kwargs) -> bool
        """
        if self._running:
            logger.warning("consumer_already_running")
            return

        self._running = True
        self._consumer_task = asyncio.create_task(
            self._consumer_loop(send_func)
        )
        logger.info("retry_consumer_started", interval=self._consumer_interval)

    async def stop_consumer(self) -> None:
        """停止重试消费者"""
        self._running = False
        if self._consumer_task and not self._consumer_task.done():
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
        self._consumer_task = None
        logger.info("retry_consumer_stopped")

    @property
    def is_running(self) -> bool:
        """消费者是否正在运行"""
        return self._running

    async def _consumer_loop(self, send_func: SendFunc) -> None:
        """消费者主循环"""
        try:
            while self._running:
                try:
                    due_tasks = await self.get_due_tasks()
                    for task in due_tasks:
                        await self._process_task(task, send_func)
                except Exception:
                    logger.exception("retry_consumer_error")

                await asyncio.sleep(self._consumer_interval)
        except asyncio.CancelledError:
            logger.debug("retry_consumer_cancelled")

    async def _process_task(self, task: RetryTask, send_func: SendFunc) -> None:
        """处理单个重试任务"""
        await self.mark_retrying(task.task_id)

        try:
            success = await send_func(
                task.user_id,
                task.message,
                task.channel,
                **task.metadata,
            )
            if success:
                await self.mark_success(task.task_id)
            else:
                await self.mark_failed(task.task_id, "send_func returned False")
        except Exception as e:
            await self.mark_failed(task.task_id, str(e))

    # ── 内部方法 ──────────────────────────────

    def _calculate_next_retry(self, retry_count: int) -> float:
        """计算下次重试时间

        使用递增延迟策略。
        """
        delay_index = min(retry_count, len(self._retry_delays) - 1)
        delay = self._retry_delays[delay_index]
        return time.time() + delay

    def _row_to_task(self, row: sqlite3.Row) -> RetryTask:
        """将数据库行转换为 RetryTask"""
        metadata = {}
        try:
            metadata = json.loads(row["metadata"])
        except (json.JSONDecodeError, KeyError):
            pass

        return RetryTask(
            task_id=row["task_id"],
            user_id=row["user_id"],
            task_type=row["task_type"],
            message=row["message"],
            channel=row["channel"],
            metadata=metadata,
            retry_count=row["retry_count"],
            max_retries=row["max_retries"],
            next_retry_at=row["next_retry_at"],
            created_at=row["created_at"],
            last_error=row["last_error"],
            status=row["status"],
        )
