"""主动陪伴与自动化系统

定时任务、事件驱动和主动交互策略。
"""

from yuanbot.proactive.event_engine import EventEngine, EventOccurrence, EventTrigger, EventType
from yuanbot.proactive.scheduler import ProactiveScheduler, ScheduledTask
from yuanbot.proactive.strategy import ProactiveConfig, ProactiveDecision, ProactiveStrategy

__all__ = [
    "EventEngine",
    "EventOccurrence",
    "EventTrigger",
    "EventType",
    "ProactiveConfig",
    "ProactiveDecision",
    "ProactiveScheduler",
    "ProactiveStrategy",
    "ScheduledTask",
]
