"""主动推送调度器

负责向已连接的通道适配器推送主动消息。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import structlog

from yuanbot.core.types import (
    ContentType,
    MessageContent,
    ProactiveTask,
)

logger = structlog.get_logger(__name__)


class PushDispatcher:
    """主动推送调度器

    职责：
    1. 接收主动交互任务
    2. 通过对应的通道适配器发送消息
    3. 管理推送队列和重试逻辑
    """

    def __init__(self) -> None:
        self._pending_tasks: list[dict[str, Any]] = []
        self._sent_tasks: list[dict[str, Any]] = []
        self._send_callback: Any = None  # Callable[[str, str, MessageContent], Awaitable[bool]]

    def set_send_callback(
        self,
        callback: Any,
    ) -> None:
        """设置发送回调函数

        callback 签名: async (platform, target_id, content) -> bool
        """
        self._send_callback = callback

    async def dispatch(
        self,
        platform: str,
        target_id: str,
        content: MessageContent,
        task: ProactiveTask | None = None,
    ) -> bool:
        """推送消息到指定通道

        Args:
            platform: 目标平台
            target_id: 目标用户/会话 ID
            content: 消息内容
            task: 关联的主动任务（可选）

        Returns:
            True if dispatched successfully.
        """
        task_record = {
            "id": str(uuid.uuid4()),
            "platform": platform,
            "target_id": target_id,
            "content_type": content.content_type.value,
            "text": content.text,
            "task_type": task.task_type if task else "direct",
            "scheduled_at": task.scheduled_at.isoformat() if task else datetime.now().isoformat(),
            "status": "pending",
            "created_at": datetime.now().isoformat(),
        }

        if self._send_callback:
            try:
                success = await self._send_callback(platform, target_id, content)
                task_record["status"] = "sent" if success else "failed"
                self._sent_tasks.append(task_record)
                logger.info(
                    "push_dispatched",
                    platform=platform,
                    target_id=target_id,
                    success=success,
                )
                return success
            except Exception as e:
                task_record["status"] = "error"
                task_record["error"] = str(e)
                self._sent_tasks.append(task_record)
                logger.error("push_dispatch_error", platform=platform, error=str(e))
                return False
        else:
            self._pending_tasks.append(task_record)
            logger.info("push_queued", platform=platform, target_id=target_id)
            return True

    async def dispatch_proactive(
        self,
        task: ProactiveTask,
        platform: str,
        target_id: str,
        generated_text: str,
    ) -> bool:
        """推送主动交互消息"""
        content = MessageContent(
            content_type=ContentType.TEXT,
            text=generated_text,
            metadata={"task_type": task.task_type, "priority": task.priority},
        )
        return await self.dispatch(platform, target_id, content, task)

    def get_pending_tasks(self) -> list[dict[str, Any]]:
        """获取待处理任务"""
        return list(self._pending_tasks)

    def get_sent_tasks(self) -> list[dict[str, Any]]:
        """获取已发送任务"""
        return list(self._sent_tasks)

    def clear_pending(self) -> int:
        """清空待处理队列，返回清除数量"""
        count = len(self._pending_tasks)
        self._pending_tasks.clear()
        return count
