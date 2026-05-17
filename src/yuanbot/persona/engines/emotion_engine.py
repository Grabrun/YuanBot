"""情感分析引擎

独立的情感分析模块，可被编排引擎和记忆系统复用。
当前使用规则引擎，后续可扩展为模型驱动。
"""

from __future__ import annotations

from typing import Any

import structlog

from yuanbot.core.types import EmotionCategory, EmotionState
from yuanbot.memory.emotion_tracker import EmotionTracker

logger = structlog.get_logger(__name__)


class EmotionEngine:
    """情感分析引擎

    封装 EmotionTracker，提供面向决策系统的高级接口。
    支持规则引擎和模型引擎两种模式。
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self._config = config or {}
        self._tracker = EmotionTracker(self._config)
        self._engine_mode = self._config.get("engine_mode", "rule_based")

    @property
    def tracker(self) -> EmotionTracker:
        """获取底层情感追踪器"""
        return self._tracker

    async def analyze(
        self,
        text: str,
        user_id: str,
        session_id: str,
        context_summary: str | None = None,
    ) -> EmotionState:
        """分析文本情感

        Args:
            text: 用户输入文本
            user_id: 用户 ID
            session_id: 会话 ID
            context_summary: 上下文摘要（可选）

        Returns:
            EmotionState: 情感状态
        """
        return await self._tracker.analyze_emotion(
            text=text,
            user_id=user_id,
            session_id=session_id,
            context_summary=context_summary,
        )

    async def get_dominant_emotion(self, user_id: str, session_id: str) -> EmotionCategory:
        """获取当前会话的主导情感"""
        summary = await self._tracker.get_session_emotion_summary(session_id)
        dominant = summary.get("dominant_emotion", "neutral")
        try:
            return EmotionCategory(dominant)
        except ValueError:
            return EmotionCategory.NEUTRAL

    async def needs_comfort(self, emotion: EmotionState) -> bool:
        """判断是否需要安慰"""
        return emotion.needs_immediate_comfort

    async def get_response_strategy(self, emotion: EmotionState) -> str:
        """基于情感状态推荐响应策略

        Returns:
            策略标识: "comfort" | "celebrate" | "calm" | "engage" | "neutral"
        """
        if emotion.emotion in (EmotionCategory.SADNESS, EmotionCategory.FEAR):
            if emotion.intensity > 0.6:
                return "comfort"
            return "gentle_engage"

        if emotion.emotion == EmotionCategory.ANGER:
            if emotion.intensity > 0.7:
                return "calm"
            return "acknowledge"

        if emotion.emotion in (EmotionCategory.JOY, EmotionCategory.ANTICIPATION):
            return "celebrate"

        if emotion.emotion == EmotionCategory.TRUST:
            return "engage"

        return "neutral"
