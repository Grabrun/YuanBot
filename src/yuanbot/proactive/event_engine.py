"""事件监听引擎

监听外部事件（天气、节日）和内部状态（用户静默、情绪趋势），
自动触发主动交互。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class EventType(StrEnum):
    """事件类型"""

    USER_SILENCE = "user_silence"  # 用户长时间未说话
    EMOTION_RISK = "emotion_risk"  # 情绪风险检测
    SPECIAL_DATE = "special_date"  # 特殊日期（生日、纪念日）
    WEATHER_CHANGE = "weather_change"  # 天气变化
    TIME_OF_DAY = "time_of_day"  # 时段触发（早安、晚安）
    CUSTOM = "custom"  # 自定义事件


@dataclass
class EventTrigger:
    """事件触发器"""

    trigger_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType = EventType.CUSTOM
    name: str = ""
    enabled: bool = True
    conditions: dict[str, Any] = field(default_factory=dict)
    user_ids: list[str] = field(default_factory=list)
    priority: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EventOccurrence:
    """事件发生记录"""

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trigger_id: str = ""
    event_type: EventType = EventType.CUSTOM
    user_id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    data: dict[str, Any] = field(default_factory=dict)


class EventEngine:
    """事件监听引擎

    职责：
    1. 管理事件触发器的注册
    2. 检测事件条件是否满足
    3. 生成事件发生记录
    """

    def __init__(self) -> None:
        self._triggers: dict[str, EventTrigger] = {}
        self._recent_events: list[EventOccurrence] = []

    def register_trigger(self, trigger: EventTrigger) -> str:
        """注册事件触发器"""
        self._triggers[trigger.trigger_id] = trigger
        logger.info(
            "event_trigger_registered",
            trigger_id=trigger.trigger_id,
            event_type=trigger.event_type.value,
            name=trigger.name,
        )
        return trigger.trigger_id

    def unregister_trigger(self, trigger_id: str) -> bool:
        """注销事件触发器"""
        if trigger_id in self._triggers:
            del self._triggers[trigger_id]
            return True
        return False

    def check_silence_events(
        self,
        user_id: str,
        last_interaction: datetime,
        threshold_minutes: int = 120,
    ) -> EventOccurrence | None:
        """检测用户静默事件"""
        now = datetime.now()
        silence_minutes = (now - last_interaction).total_seconds() / 60

        if silence_minutes >= threshold_minutes:
            trigger = self._find_trigger(EventType.USER_SILENCE, user_id)
            if trigger:
                event = EventOccurrence(
                    trigger_id=trigger.trigger_id,
                    event_type=EventType.USER_SILENCE,
                    user_id=user_id,
                    data={
                        "silence_minutes": round(silence_minutes),
                        "threshold": threshold_minutes,
                    },
                )
                self._recent_events.append(event)
                return event
        return None

    def check_emotion_risk(
        self,
        user_id: str,
        emotion: str,
        intensity: float,
        threshold: float = 0.7,
    ) -> EventOccurrence | None:
        """检测情绪风险事件"""
        negative_emotions = {"sadness", "anger", "fear", "disgust"}

        if emotion in negative_emotions and intensity >= threshold:
            trigger = self._find_trigger(EventType.EMOTION_RISK, user_id)
            if trigger:
                event = EventOccurrence(
                    trigger_id=trigger.trigger_id,
                    event_type=EventType.EMOTION_RISK,
                    user_id=user_id,
                    data={
                        "emotion": emotion,
                        "intensity": intensity,
                        "threshold": threshold,
                    },
                )
                self._recent_events.append(event)
                return event
        return None

    def check_special_date(
        self,
        user_id: str,
        dates: dict[str, str],
    ) -> EventOccurrence | None:
        """检测特殊日期事件

        Args:
            user_id: 用户 ID
            dates: {date_name: "MM-DD"} 格式的日期字典
        """
        today = datetime.now().strftime("%m-%d")

        for date_name, date_str in dates.items():
            if date_str == today:
                trigger = self._find_trigger(EventType.SPECIAL_DATE, user_id)
                if trigger:
                    event = EventOccurrence(
                        trigger_id=trigger.trigger_id,
                        event_type=EventType.SPECIAL_DATE,
                        user_id=user_id,
                        data={"date_name": date_name, "date": date_str},
                    )
                    self._recent_events.append(event)
                    return event
        return None

    def emit_custom_event(
        self,
        user_id: str,
        event_name: str,
        data: dict[str, Any] | None = None,
    ) -> EventOccurrence | None:
        """触发自定义事件"""
        trigger = self._find_trigger(EventType.CUSTOM, user_id)
        if trigger:
            event = EventOccurrence(
                trigger_id=trigger.trigger_id,
                event_type=EventType.CUSTOM,
                user_id=user_id,
                data={"event_name": event_name, **(data or {})},
            )
            self._recent_events.append(event)
            return event
        return None

    def get_recent_events(
        self,
        user_id: str | None = None,
        limit: int = 10,
    ) -> list[EventOccurrence]:
        """获取最近的事件"""
        events = self._recent_events
        if user_id:
            events = [e for e in events if e.user_id == user_id]
        return events[-limit:]

    def get_triggers(self) -> list[EventTrigger]:
        """获取所有触发器"""
        return list(self._triggers.values())

    def _find_trigger(
        self,
        event_type: EventType,
        user_id: str,
    ) -> EventTrigger | None:
        """查找匹配的触发器"""
        for trigger in self._triggers.values():
            if (
                trigger.enabled
                and trigger.event_type == event_type
                and (not trigger.user_ids or user_id in trigger.user_ids)
            ):
                return trigger
        return None
