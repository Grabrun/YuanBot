"""YuanBot 记忆系统

四层记忆模型：工作记忆 → 事实记忆 → 情景记忆 → 语义记忆
参考 Mem0 的混合存储架构，针对伴侣场景深度适配。

集成情感追踪系统，实现情感感知的记忆管理。
"""

from yuanbot.core.types import (
    EmotionCategory,
    EmotionIntensity,
    EmotionPattern,
    EmotionRecord,
    EmotionState,
    EmotionTrend,
    MemoryNode,
    MemorySearchResult,
    MemoryType,
    UserProfile,
)
from yuanbot.memory.emotion_tracker import EmotionTracker
from yuanbot.memory.manager import MemoryManager

__all__ = [
    # 记忆类型
    "MemoryType",
    "MemoryNode",
    "MemorySearchResult",
    "UserProfile",
    "MemoryManager",
    # 情感类型
    "EmotionCategory",
    "EmotionIntensity",
    "EmotionState",
    "EmotionRecord",
    "EmotionTrend",
    "EmotionPattern",
    "EmotionTracker",
]
