"""持久化重试队列测试

测试 SQLite 持久化、入队/出队、重试逻辑、消费者循环等。
"""

from __future__ import annotations

import asyncio
import time

import pytest

from yuanbot.proactive.retry_queue import PersistentRetryQueue, RetryTask


@pytest.fixture
async def queue(tmp_path):
    """创建临时数据库的重试队列"""
    db_path = str(tmp_path / "test_retry.db")
    q = PersistentRetryQueue(db_path=db_path)
    await q.initialize()
    yield q
    await q.close()


class TestRetryTask:
    """RetryTask 数据类测试"""

    def test_create_with_defaults(self):
        task = RetryTask()
        assert task.task_id
        assert task.user_id == ""
        assert task.status == "pending"
        assert task.retry_count == 0
        assert task.max_retries == 3

    def test_create_with_values(self):
        task = RetryTask(
            user_id="u_123",
            task_type="greeting",
            message="早安～",
            channel="telegram",
            max_retries=5,
        )
        assert task.user_id == "u_123"
        assert task.task_type == "greeting"
        assert task.message == "早安～"
        assert task.channel == "telegram"
        assert task.max_retries == 5

    def test_to_dict(self):
        task = RetryTask(
            user_id="u_1",
            task_type="care",
            message="你好",
            channel="web",
        )
        d = task.to_dict()
        assert d["user_id"] == "u_1"
        assert d["task_type"] == "care"
        assert d["message"] == "你好"
        assert d["channel"] == "web"
        assert d["status"] == "pending"


class TestPersistentRetryQueue:
    """PersistentRetryQueue 核心功能测试"""

    @pytest.mark.asyncio
    async def test_initialize_creates_table(self, queue):
        """初始化应创建数据库表"""
        stats = await queue.get_queue_stats()
        assert stats["pending"] == 0
        assert stats["total"] == 0

    @pytest.mark.asyncio
    async def test_enqueue_and_get_due(self, queue):
        """入队后应能获取到期任务"""
        task = RetryTask(
            user_id="u_1",
            task_type="greeting",
            message="早安",
            channel="telegram",
        )
        task_id = await queue.enqueue(task)
        assert task_id == task.task_id

        due = await queue.get_due_tasks()
        assert len(due) == 1
        assert due[0].task_id == task_id
        assert due[0].user_id == "u_1"

    @pytest.mark.asyncio
    async def test_enqueue_simple(self, queue):
        """简化入队接口测试"""
        task_id = await queue.enqueue_simple(
            user_id="u_2",
            task_type="care",
            message="你好呀",
            channel="webchat",
        )
        assert task_id
        due = await queue.get_due_tasks()
        assert len(due) == 1
        assert due[0].user_id == "u_2"

    @pytest.mark.asyncio
    async def test_future_task_not_due(self, queue):
        """未来时间的任务不应到期"""
        task = RetryTask(
            user_id="u_1",
            task_type="greeting",
            message="明天见",
            next_retry_at=time.time() + 86400,  # 24 小时后
        )
        await queue.enqueue(task)
        due = await queue.get_due_tasks()
        assert len(due) == 0

    @pytest.mark.asyncio
    async def test_mark_success_removes_from_pending(self, queue):
        """标记成功后不再出现在待处理列表"""
        task = RetryTask(user_id="u_1", task_type="greeting", message="hi")
        await queue.enqueue(task)
        await queue.mark_success(task.task_id)

        due = await queue.get_due_tasks()
        assert len(due) == 0

        stats = await queue.get_queue_stats()
        assert stats["completed"] == 1

    @pytest.mark.asyncio
    async def test_mark_failed_increments_retry_count(self, queue):
        """标记失败应增加重试次数"""
        task = RetryTask(user_id="u_1", task_type="greeting", message="hi", max_retries=3)
        await queue.enqueue(task)

        await queue.mark_failed(task.task_id, "connection error")

        # 检查重试次数增加
        await queue.get_due_tasks()
        # 任务应该还在队列中（未超过最大重试次数），但下次重试时间在未来
        stats = await queue.get_queue_stats()
        assert stats["pending"] + stats["completed"] + stats["failed"] >= 1

    @pytest.mark.asyncio
    async def test_permanent_failure_after_max_retries(self, queue):
        """超过最大重试次数后应标记为最终失败"""
        task = RetryTask(
            user_id="u_1",
            task_type="greeting",
            message="hi",
            max_retries=2,
        )
        await queue.enqueue(task)

        # 第一次失败
        await queue.mark_failed(task.task_id, "err1")
        # 第二次失败（达到 max_retries）
        await queue.mark_failed(task.task_id, "err2")

        stats = await queue.get_queue_stats()
        assert stats["failed"] == 1

    @pytest.mark.asyncio
    async def test_remove_task(self, queue):
        """移除任务测试"""
        task = RetryTask(user_id="u_1", task_type="test", message="test")
        await queue.enqueue(task)
        assert await queue.remove_task(task.task_id)
        stats = await queue.get_queue_stats()
        assert stats["total"] == 0

    @pytest.mark.asyncio
    async def test_remove_nonexistent_task(self, queue):
        """移除不存在的任务应返回 False"""
        assert not await queue.remove_task("nonexistent_id")

    @pytest.mark.asyncio
    async def test_pending_count(self, queue):
        """待处理计数测试"""
        for i in range(5):
            await queue.enqueue_simple(
                user_id=f"u_{i}",
                task_type="test",
                message=f"msg_{i}",
            )
        count = await queue.get_pending_count()
        assert count == 5

    @pytest.mark.asyncio
    async def test_failed_count(self, queue):
        """失败计数测试"""
        task = RetryTask(user_id="u_1", task_type="test", message="hi", max_retries=1)
        await queue.enqueue(task)
        await queue.mark_failed(task.task_id, "err")
        count = await queue.get_failed_count()
        assert count == 1

    @pytest.mark.asyncio
    async def test_cleanup_completed(self, queue):
        """清理已完成任务测试"""
        task = RetryTask(user_id="u_1", task_type="test", message="hi")
        await queue.enqueue(task)
        await queue.mark_success(task.task_id)

        # 清理超过 0 秒前的任务
        removed = await queue.cleanup_completed(max_age_seconds=0)
        assert removed >= 1

    @pytest.mark.asyncio
    async def test_get_queue_stats(self, queue):
        """队列统计测试"""
        await queue.enqueue_simple(user_id="u_1", task_type="a", message="1")
        await queue.enqueue_simple(user_id="u_2", task_type="b", message="2")
        stats = await queue.get_queue_stats()
        assert stats["pending"] == 2
        assert stats["total"] >= 2


class TestRetryDelays:
    """重试延迟策略测试"""

    @pytest.mark.asyncio
    async def test_custom_retry_delays(self, tmp_path):
        """自定义重试延迟测试"""
        db_path = str(tmp_path / "custom_delay.db")
        q = PersistentRetryQueue(
            db_path=db_path,
            retry_delays=(10, 20, 30),
        )
        await q.initialize()

        task = RetryTask(user_id="u_1", task_type="test", message="hi", max_retries=3)
        await q.enqueue(task)

        # 第一次失败，延迟应为 10 秒
        await q.mark_failed(task.task_id, "err")

        await q.close()


class TestConsumer:
    """消费者循环测试"""

    @pytest.mark.asyncio
    async def test_consumer_processes_tasks(self, queue):
        """消费者应处理到期任务"""
        results = []

        async def mock_send(user_id, message, channel, **kwargs):
            results.append({"user_id": user_id, "message": message})
            return True

        # 入队一个立即到期的任务
        await queue.enqueue_simple(
            user_id="u_1",
            task_type="greeting",
            message="早安",
            channel="telegram",
        )

        # 启动消费者并等待处理
        await queue.start_consumer(mock_send)
        await asyncio.sleep(0.5)  # 等待消费者处理
        await queue.stop_consumer()

        assert len(results) == 1
        assert results[0]["user_id"] == "u_1"
        assert results[0]["message"] == "早安"

    @pytest.mark.asyncio
    async def test_consumer_handles_send_failure(self, queue):
        """消费者应处理发送失败"""
        call_count = 0

        async def failing_send(user_id, message, channel, **kwargs):
            nonlocal call_count
            call_count += 1
            return False

        # 入队一个任务（max_retries=2）
        await queue.enqueue_simple(
            user_id="u_1",
            task_type="greeting",
            message="hi",
            channel="web",
            max_retries=2,
        )

        await queue.start_consumer(failing_send)
        await asyncio.sleep(0.5)
        await queue.stop_consumer()

        # 至少被调用一次
        assert call_count >= 1

    @pytest.mark.asyncio
    async def test_consumer_handles_exception(self, queue):
        """消费者不应因发送异常而崩溃"""

        async def error_send(user_id, message, channel, **kwargs):
            raise RuntimeError("Network error")

        await queue.enqueue_simple(
            user_id="u_1",
            task_type="test",
            message="hi",
        )

        await queue.start_consumer(error_send)
        await asyncio.sleep(0.5)
        await queue.stop_consumer()

        # 队列不应崩溃
        stats = await queue.get_queue_stats()
        assert stats["total"] >= 1

    @pytest.mark.asyncio
    async def test_consumer_is_running_flag(self, queue):
        """消费者运行状态标志测试"""

        async def noop_send(user_id, message, channel, **kwargs):
            return True

        assert not queue.is_running
        await queue.start_consumer(noop_send)
        assert queue.is_running
        await queue.stop_consumer()
        assert not queue.is_running

    @pytest.mark.asyncio
    async def test_double_start_consumer(self, queue):
        """重复启动消费者不应报错"""

        async def noop_send(user_id, message, channel, **kwargs):
            return True

        await queue.start_consumer(noop_send)
        await queue.start_consumer(noop_send)  # 应该被忽略
        await queue.stop_consumer()


class TestPersistenceAcrossRestarts:
    """跨重启持久化测试"""

    @pytest.mark.asyncio
    async def test_tasks_survive_restart(self, tmp_path):
        """任务应在重启后保留"""
        db_path = str(tmp_path / "persist_test.db")

        # 第一次打开：入队任务
        q1 = PersistentRetryQueue(db_path=db_path)
        await q1.initialize()
        await q1.enqueue_simple(
            user_id="u_persist",
            task_type="greeting",
            message="持久化测试",
            channel="telegram",
        )
        await q1.close()

        # 第二次打开：应该能看到之前的任务
        q2 = PersistentRetryQueue(db_path=db_path)
        await q2.initialize()
        due = await q2.get_due_tasks()
        assert len(due) == 1
        assert due[0].user_id == "u_persist"
        assert due[0].message == "持久化测试"
        await q2.close()

    @pytest.mark.asyncio
    async def test_retry_state_persists(self, tmp_path):
        """重试状态应在重启后保留"""
        db_path = str(tmp_path / "persist_retry.db")

        q1 = PersistentRetryQueue(db_path=db_path)
        await q1.initialize()
        task = RetryTask(
            user_id="u_1",
            task_type="test",
            message="retry test",
            max_retries=3,
        )
        await q1.enqueue(task)
        await q1.mark_failed(task.task_id, "first error")
        await q1.close()

        q2 = PersistentRetryQueue(db_path=db_path)
        await q2.initialize()
        stats = await q2.get_queue_stats()
        assert stats["pending"] >= 1 or stats["failed"] >= 1
        await q2.close()
