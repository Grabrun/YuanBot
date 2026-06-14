"""事件队列系统

解耦网关与编排层，实现异步消息处理。
支持 Redis Streams（生产）和内存队列（开发/测试）两种后端。

设计参考: gateway-communication-system.md 第7节
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from collections import defaultdict
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# 消息主题定义（对应设计文档 7.2）
TOPIC_INBOUND = "yuanbot.inbound"  # 网关 → 编排层
TOPIC_OUTBOUND_PREFIX = "yuanbot.outbound"  # 编排层 → 网关（按通道）
TOPIC_PROACTIVE_PUSH = "yuanbot.proactive.push"  # 主动推送


def outbound_topic(channel: str) -> str:
    """获取特定通道的出站主题"""
    return f"{TOPIC_OUTBOUND_PREFIX}.{channel}"


# 事件处理器类型
EventHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


@dataclass
class QueueMessage:
    """队列消息"""

    message_id: str
    topic: str
    payload: dict[str, Any]
    timestamp: float = 0.0
    retry_count: int = 0
    max_retries: int = 3


class MemoryEventQueue:
    """内存事件队列（开发/测试用）

    使用 asyncio.Queue 实现，无需外部依赖。
    不支持持久化，进程重启后消息丢失。
    """

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[QueueMessage]] = defaultdict(asyncio.Queue)
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._running = False
        self._consumer_tasks: dict[str, asyncio.Task[None]] = {}
        self._message_counter = 0

    async def publish(self, topic: str, payload: dict[str, Any]) -> str:
        """发布消息到指定主题

        Args:
            topic: 消息主题
            payload: 消息内容

        Returns:
            消息 ID
        """
        self._message_counter += 1
        msg = QueueMessage(
            message_id=str(uuid.uuid4()),
            topic=topic,
            payload=payload,
            timestamp=time.time(),
        )

        await self._queues[topic].put(msg)

        logger.debug(
            "message_published",
            topic=topic,
            message_id=msg.message_id,
            queue_size=self._queues[topic].qsize(),
        )
        return msg.message_id

    def subscribe(self, topic: str, handler: EventHandler) -> None:
        """订阅主题并注册处理器

        Args:
            topic: 消息主题
            handler: 异步处理器函数
        """
        self._handlers[topic].append(handler)
        logger.info("handler_subscribed", topic=topic, handler=handler.__name__)

    async def start(self) -> None:
        """启动所有主题的消费者"""
        if self._running:
            return
        self._running = True

        for topic in list(self._handlers.keys()):
            task = asyncio.create_task(self._consume_loop(topic))
            self._consumer_tasks[topic] = task
            logger.info("consumer_started", topic=topic)

    async def stop(self) -> None:
        """停止所有消费者"""
        self._running = False
        for topic, task in self._consumer_tasks.items():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            logger.info("consumer_stopped", topic=topic)
        self._consumer_tasks.clear()

    async def _consume_loop(self, topic: str) -> None:
        """主题消费循环"""
        queue = self._queues[topic]
        handlers = self._handlers[topic]

        while self._running:
            try:
                # 等待消息，超时后继续循环（便于检查 _running）
                msg = await asyncio.wait_for(queue.get(), timeout=1.0)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            # 分发给所有处理器
            for handler in handlers:
                try:
                    await handler(msg.payload)
                except Exception:
                    logger.exception(
                        "handler_error",
                        topic=topic,
                        handler=handler.__name__,
                        message_id=msg.message_id,
                    )

                    # 重试逻辑
                    if msg.retry_count < msg.max_retries:
                        msg.retry_count += 1
                        await queue.put(msg)
                        logger.info(
                            "message_retried",
                            message_id=msg.message_id,
                            retry_count=msg.retry_count,
                        )

    def get_queue_size(self, topic: str) -> int:
        """获取指定主题的队列大小"""
        return self._queues[topic].qsize()

    def get_stats(self) -> dict[str, Any]:
        """获取队列统计信息"""
        return {
            "backend": "memory",
            "running": self._running,
            "topics": {
                topic: {
                    "queue_size": queue.qsize(),
                    "handler_count": len(self._handlers.get(topic, [])),
                }
                for topic, queue in self._queues.items()
            },
        }


class RedisEventQueue:
    """Redis 事件队列（生产用）

    使用 Redis Streams 实现，支持：
    - 消息持久化
    - 消费者组
    - 消息确认（ACK）
    - 死信队列

    需要 redis[hiredis] 依赖。
    """

    def __init__(self, redis_url: str, consumer_group: str = "yuanbot"):
        self._redis_url = redis_url
        self._consumer_group = consumer_group
        self._redis: Any = None
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._running = False
        self._consumer_tasks: dict[str, asyncio.Task[None]] = {}
        self._consumer_name: str = ""

    async def start(self) -> None:
        """启动 Redis 连接和消费者"""
        try:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
            # 测试连接
            await self._redis.ping()

            import uuid

            self._consumer_name = f"consumer-{uuid.uuid4().hex[:8]}"

            # 创建消费者组
            for topic in self._handlers:
                with contextlib.suppress(Exception):  # 组已存在
                    await self._redis.xgroup_create(
                        topic, self._consumer_group, id="0", mkstream=True
                    )

                task = asyncio.create_task(self._consume_loop(topic))
                self._consumer_tasks[topic] = task
                logger.info("redis_consumer_started", topic=topic)

            self._running = True
            logger.info("redis_event_queue_started", url=self._redis_url)

        except ImportError:
            logger.error("redis_not_installed", hint="pip install redis[hiredis]")
            raise
        except Exception as e:
            logger.error("redis_connection_failed", error=str(e))
            raise

    async def stop(self) -> None:
        """停止消费者和连接"""
        self._running = False
        for task in self._consumer_tasks.values():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._consumer_tasks.clear()

        if self._redis:
            await self._redis.close()
            self._redis = None
        logger.info("redis_event_queue_stopped")

    async def publish(self, topic: str, payload: dict[str, Any]) -> str:
        """发布消息到 Redis Stream"""
        if not self._redis:
            raise RuntimeError("Redis event queue not started")

        # 将 payload 序列化为 Redis Streams 的 field-value 格式
        data = {"payload": json.dumps(payload, ensure_ascii=False)}
        message_id = await self._redis.xadd(topic, data, maxlen=10000)

        logger.debug("redis_message_published", topic=topic, message_id=message_id)
        return message_id

    def subscribe(self, topic: str, handler: EventHandler) -> None:
        """订阅主题"""
        self._handlers[topic].append(handler)

    async def _consume_loop(self, topic: str) -> None:
        """Redis Stream 消费循环"""
        while self._running:
            try:
                # 读取新消息
                messages = await self._redis.xreadgroup(
                    self._consumer_group,
                    self._consumer_name,
                    {topic: ">"},
                    count=10,
                    block=1000,  # 阻塞 1 秒
                )

                if not messages:
                    continue

                for _stream, entries in messages:
                    for message_id, fields in entries:
                        payload = json.loads(fields.get("payload", "{}"))

                        for handler in self._handlers.get(topic, []):
                            try:
                                await handler(payload)
                            except Exception:
                                logger.exception(
                                    "redis_handler_error",
                                    topic=topic,
                                    handler=handler.__name__,
                                    message_id=message_id,
                                )

                        # 确认消息
                        await self._redis.xack(topic, self._consumer_group, message_id)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("redis_consume_error", topic=topic)
                await asyncio.sleep(1)

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        return {
            "backend": "redis",
            "running": self._running,
            "redis_url": self._redis_url,
            "consumer_group": self._consumer_group,
            "consumer_name": self._consumer_name,
        }


def create_event_queue(config: dict[str, Any] | None = None) -> MemoryEventQueue | RedisEventQueue:
    """根据配置创建事件队列实例

    Args:
        config: 配置字典，包含 backend ("memory" | "redis") 和 redis_url

    Returns:
        事件队列实例
    """
    config = config or {}
    backend = config.get("backend", "memory")

    if backend == "redis":
        redis_url = config.get("redis_url", "redis://localhost:6379/0")
        return RedisEventQueue(
            redis_url=redis_url,
            consumer_group=config.get("consumer_group", "yuanbot"),
        )

    return MemoryEventQueue()
