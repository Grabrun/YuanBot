"""主动陪伴与自动化系统

定时任务、事件驱动和主动交互策略。
"""

from yuanbot.proactive.event_engine import EventEngine
from yuanbot.proactive.scheduler import ProactiveScheduler
from yuanbot.proactive.strategy import ProactiveStrategy

__all__ = [
    "ProactiveScheduler",
    "ProactiveStrategy",
    "EventEngine",
]
