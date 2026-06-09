"""事件监听引擎

监听外部和内部事件，在条件满足时触发主动交互。
支持用户静默检测、情感告警等事件。
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# 模块级常量，避免每次调用时分配
_MAX_RECENT_EVENTS = 200  # 限制最近事件列表大小，防止内存泄漏
_NEGATIVE_EMOTIONS: frozenset[str] = frozenset({"sadness", "anger", "fear", "disgust"})

# 事件处理器类型: async (event_data: dict) -> None
EventHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


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

    监听外部和内部事件，在条件满足时触发主动交互。

    职责：
    1. 管理事件触发器的注册
    2. 注册和调用事件处理器
    3. 定期检查用户静默状态和情感趋势
    4. 发布事件并通知所有注册的处理器
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        memory_manager: Any = None,
        weather_tool: Any = None,
    ) -> None:
        self._config = config or {}
        self._memory_manager = memory_manager
        self._weather_tool = weather_tool  # 可选：天气查询工具
        self._triggers: dict[str, EventTrigger] = {}
        self._triggers_by_type: dict[EventType, list[EventTrigger]] = {}  # 预索引
        self._event_handlers: dict[str, list[EventHandler]] = {}
        self._recent_events: list[EventOccurrence] = []
        self._last_check_times: dict[str, datetime] = {}
        self._last_weather: dict[str, dict[str, Any]] = {}  # user_id -> weather_cache
        self._running = False
        self._loop_task: asyncio.Task[None] | None = None

        # 配置参数
        self._silence_check_interval: int = self._config.get("silence_check_interval_seconds", 3600)
        self._silence_threshold_hours: int = self._config.get("silence_threshold_hours", 48)
        self._emotion_check_interval: int = self._config.get("emotion_check_interval_seconds", 3600)
        self._emotion_alert_days: int = self._config.get("emotion_alert_days", 3)
        self._weather_check_interval: int = self._config.get("weather_check_interval_seconds", 3600)
        self._weather_temp_drop_threshold: float = self._config.get(
            "weather_temp_drop_threshold", 5.0
        )
        self._weather_rain_threshold: float = self._config.get("weather_rain_threshold", 70.0)

    async def start(self) -> None:
        """启动事件监听"""
        if self._running:
            logger.warning("event_engine_already_running")
            return
        self._running = True
        self._loop_task = asyncio.create_task(self._run_loop())
        logger.info("event_engine_started")

    async def stop(self) -> None:
        """停止事件监听"""
        self._running = False
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._loop_task
        self._loop_task = None
        logger.info("event_engine_stopped")

    @property
    def is_running(self) -> bool:
        """事件引擎是否正在运行"""
        return self._running

    def register_handler(self, event_type: str, handler: EventHandler) -> None:
        """注册事件处理器

        Args:
            event_type: 事件类型（EventType 值或自定义字符串）
            handler: 异步处理器函数
        """
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)
        logger.info("event_handler_registered", event_type=event_type)

    def unregister_handlers(self, event_type: str) -> int:
        """注销某事件类型的所有处理器

        Returns:
            移除的处理器数量
        """
        handlers = self._event_handlers.pop(event_type, [])
        return len(handlers)

    async def emit_event(self, event_type: str, data: dict[str, Any]) -> None:
        """发布事件，通知所有注册的处理器

        Args:
            event_type: 事件类型
            data: 事件数据
        """
        handlers = self._event_handlers.get(event_type, [])
        if not handlers:
            logger.debug("no_handlers_for_event", event_type=event_type)
            return

        logger.info(
            "event_emitted",
            event_type=event_type,
            handler_count=len(handlers),
        )

        for handler in handlers:
            try:
                await handler(data)
            except Exception:
                logger.exception(
                    "event_handler_error",
                    event_type=event_type,
                    handler=handler.__name__,
                )

    def register_trigger(self, trigger: EventTrigger) -> str:
        """注册事件触发器"""
        self._triggers[trigger.trigger_id] = trigger
        # 维护预索引
        self._triggers_by_type.setdefault(trigger.event_type, []).append(trigger)
        logger.info(
            "event_trigger_registered",
            trigger_id=trigger.trigger_id,
            event_type=trigger.event_type.value,
            name=trigger.name,
        )
        return trigger.trigger_id

    def unregister_trigger(self, trigger_id: str) -> bool:
        """注销事件触发器"""
        trigger = self._triggers.pop(trigger_id, None)
        if trigger is not None:
            # 从预索引中移除
            by_type = self._triggers_by_type.get(trigger.event_type)
            if by_type is not None:
                self._triggers_by_type[trigger.event_type] = [
                    t for t in by_type if t.trigger_id != trigger_id
                ]
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
                if len(self._recent_events) > _MAX_RECENT_EVENTS:
                    self._recent_events = self._recent_events[-_MAX_RECENT_EVENTS:]
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
        if emotion in _NEGATIVE_EMOTIONS and intensity >= threshold:
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
                if len(self._recent_events) > _MAX_RECENT_EVENTS:
                    self._recent_events = self._recent_events[-_MAX_RECENT_EVENTS:]
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
                    if len(self._recent_events) > _MAX_RECENT_EVENTS:
                        self._recent_events = self._recent_events[-_MAX_RECENT_EVENTS:]
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
            if len(self._recent_events) > _MAX_RECENT_EVENTS:
                self._recent_events = self._recent_events[-_MAX_RECENT_EVENTS:]
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

    def get_last_check_time(self, check_type: str) -> datetime | None:
        """获取上次检查时间"""
        return self._last_check_times.get(check_type)

    async def _run_loop(self) -> None:
        """事件监听主循环"""
        try:
            while self._running:
                # 四项检查互相独立，并行执行减少循环延迟
                await asyncio.gather(
                    self._check_user_silence(),
                    self._check_emotion_alerts(),
                    self._check_weather_changes(),
                    self._check_special_dates(),
                )
                # 使用较短的间隔便于测试
                min_interval = min(
                    self._silence_check_interval,
                    self._emotion_check_interval,
                    self._weather_check_interval,
                )
                await asyncio.sleep(min_interval)
        except asyncio.CancelledError:
            logger.debug("event_engine_loop_cancelled")

    async def _check_user_silence(self) -> None:
        """检查用户静默状态

        如果用户超过配置的时间（默认 48 小时）未交互，
        触发静默关心事件。
        """
        now = datetime.now()
        last_check = self._last_check_times.get("silence")
        if last_check and (now - last_check).total_seconds() < self._silence_check_interval:
            return

        self._last_check_times["silence"] = now

        if not self._memory_manager:
            return

        # 从 memory_manager 获取所有用户画像
        profiles = getattr(self._memory_manager, "_user_profiles", {})
        threshold = timedelta(hours=self._silence_threshold_hours)

        for user_id, profile in profiles.items():
            last_interaction = getattr(profile, "last_interaction", None)
            if last_interaction and (now - last_interaction) > threshold:
                silence_hours = (now - last_interaction).total_seconds() / 3600
                logger.info(
                    "user_silence_detected",
                    user_id=user_id,
                    silence_hours=round(silence_hours, 1),
                )
                await self.emit_event(
                    EventType.USER_SILENCE,
                    {
                        "user_id": user_id,
                        "silence_hours": round(silence_hours, 1),
                    },
                )

    async def _check_emotion_alerts(self) -> None:
        """检查情感告警

        如果用户连续多天（默认 3 天）情绪低落，
        触发情感关心事件。
        """
        now = datetime.now()
        last_check = self._last_check_times.get("emotion")
        if last_check and (now - last_check).total_seconds() < self._emotion_check_interval:
            return

        self._last_check_times["emotion"] = now

        if not self._memory_manager:
            return

        profiles = getattr(self._memory_manager, "_user_profiles", {})
        user_ids = list(profiles.keys())

        # Batch fetch emotion trends for all users in parallel
        trends = await asyncio.gather(
            *(
                self._memory_manager.get_emotion_trend(uid, days=self._emotion_alert_days)
                for uid in user_ids
            ),
            return_exceptions=True,
        )

        for user_id, trend in zip(user_ids, trends):
            if isinstance(trend, Exception):
                logger.debug("emotion_check_skip", user_id=user_id)
                continue
            try:
                if trend and hasattr(trend, "valence_ratio"):
                    negative_ratio = trend.valence_ratio.get("negative", 0.0)
                    if negative_ratio >= 0.6:
                        logger.info(
                            "emotion_alert_detected",
                            user_id=user_id,
                            negative_ratio=negative_ratio,
                        )
                        await self.emit_event(
                            EventType.EMOTION_RISK,
                            {
                                "user_id": user_id,
                                "negative_ratio": negative_ratio,
                                "dominant_emotion": trend.dominant_emotion.value
                                if hasattr(trend.dominant_emotion, "value")
                                else str(trend.dominant_emotion),
                            },
                        )
            except Exception:
                logger.debug("emotion_check_skip", user_id=user_id)

    def _find_trigger(
        self,
        event_type: EventType,
        user_id: str,
    ) -> EventTrigger | None:
        """查找匹配的触发器（使用预索引，O(1) 事件类型过滤）"""
        for trigger in self._triggers_by_type.get(event_type, ()):
            if trigger.enabled and (not trigger.user_ids or user_id in trigger.user_ids):
                return trigger
        return None

    async def _check_weather_changes(self) -> None:
        """检查天气变化事件

        设计参考: proactive-companion-system.md 3.3

        每小时查询活跃用户的天气，检测异常变化（降温>5°C、降雨概率>70%）。
        """
        now = datetime.now()
        last_check = self._last_check_times.get("weather")
        if last_check and (now - last_check).total_seconds() < self._weather_check_interval:
            return

        self._last_check_times["weather"] = now

        if not self._memory_manager or not self._weather_tool:
            return

        profiles = getattr(self._memory_manager, "_user_profiles", {})

        # Pre-filter users with locations
        user_locations: list[tuple[str, str, Any]] = []
        for user_id, profile in profiles.items():
            location = getattr(profile, "preferences", {}).get("location")
            if location:
                user_locations.append((user_id, location, profile))

        # Batch fetch weather for all users in parallel
        async def _fetch_weather(location: str) -> dict[str, Any] | None:
            try:
                if hasattr(self._weather_tool, "invoke"):
                    result = await self._weather_tool.invoke({"city": location})
                    return result.output if result.success else None
                elif callable(self._weather_tool):
                    return await self._weather_tool(location)
            except Exception:
                return None
            return None

        weather_results = await asyncio.gather(
            *(_fetch_weather(loc) for _, loc, _ in user_locations),
            return_exceptions=True,
        )

        # Process results sequentially for state tracking and event emission
        for (user_id, location, _), weather in zip(user_locations, weather_results):
            try:
                if isinstance(weather, Exception) or weather is None:
                    continue

                current_weather = weather
                prev_weather = self._last_weather.get(user_id)
                self._last_weather[user_id] = current_weather

                if prev_weather:
                    # 检测温度骤降
                    prev_temp = prev_weather.get("temperature", 0)
                    curr_temp = current_weather.get("temperature", 0)
                    if prev_temp - curr_temp >= self._weather_temp_drop_threshold:
                        logger.info(
                            "weather_temp_drop_detected",
                            user_id=user_id,
                            drop=prev_temp - curr_temp,
                        )
                        await self.emit_event(
                            EventType.WEATHER_CHANGE,
                            {
                                "user_id": user_id,
                                "change_type": "temp_drop",
                                "prev_temp": prev_temp,
                                "curr_temp": curr_temp,
                                "location": location,
                            },
                        )

                    # 检测降雨
                    rain_prob = current_weather.get("rain_probability", 0)
                    if rain_prob >= self._weather_rain_threshold:
                        logger.info(
                            "weather_rain_detected",
                            user_id=user_id,
                            rain_prob=rain_prob,
                        )
                        await self.emit_event(
                            EventType.WEATHER_CHANGE,
                            {
                                "user_id": user_id,
                                "change_type": "rain",
                                "rain_probability": rain_prob,
                                "location": location,
                            },
                        )

            except Exception:
                logger.debug("weather_check_skip", user_id=user_id)

    async def _check_special_dates(self) -> None:
        """检查特殊日期事件

        检查用户配置的重要日期（生日、纪念日等），
        如果今天匹配则触发特殊日期事件。

        设计参考: proactive-companion-system.md 3.2
        """
        now = datetime.now()
        last_check = self._last_check_times.get("special_date")
        if last_check and last_check.date() == now.date():
            return  # 每天只检查一次

        self._last_check_times["special_date"] = now

        if not self._memory_manager:
            return

        today_str = now.strftime("%m-%d")
        profiles = getattr(self._memory_manager, "_user_profiles", {})
        user_ids = list(profiles.keys())

        # Batch fetch proactive settings for all users in parallel
        if hasattr(self._memory_manager, "get_user_proactive_settings"):
            settings_list = await asyncio.gather(
                *(self._memory_manager.get_user_proactive_settings(uid) for uid in user_ids),
                return_exceptions=True,
            )
        else:
            settings_list = [{}] * len(user_ids)

        for user_id, user_config in zip(user_ids, settings_list):
            try:
                if isinstance(user_config, Exception):
                    continue
                important_dates = user_config.get("important_dates", [])

                for date_entry in important_dates:
                    if isinstance(date_entry, dict):
                        date_str = date_entry.get("date", "")
                        desc = date_entry.get("description", "特殊日期")
                    elif isinstance(date_entry, str):
                        # 支持 "MM-DD:description" 格式
                        parts = date_entry.split(":", 1)
                        date_str = parts[0]
                        desc = parts[1] if len(parts) > 1 else "特殊日期"
                    else:
                        continue

                    if date_str == today_str:
                        event = self.check_special_date(
                            user_id, {desc: date_str}
                        )
                        if event:
                            await self.emit_event(
                                EventType.SPECIAL_DATE,
                                {**event.data, "user_id": user_id},
                            )
            except Exception:
                logger.debug("special_date_check_skip", user_id=user_id)
