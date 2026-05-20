"""对话决策引擎

综合意图、情感、记忆和人设信息，做出行为决策。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from yuanbot.core.types import EmotionState
from yuanbot.persona.engines.emotion_engine import EmotionEngine
from yuanbot.persona.engines.intent_engine import IntentEngine, IntentResult

logger = structlog.get_logger(__name__)


@dataclass
class DecisionResult:
    """决策结果"""

    response_strategy: str  # "comfort" | "celebrate" | "calm" | "engage" | "neutral"
    intent: IntentResult
    emotion_state: EmotionState | None = None
    should_use_skills: list[str] = field(default_factory=list)  # 推荐使用的 Skills
    should_use_tools: list[str] = field(default_factory=list)  # 推荐使用的 Tools
    context_priority: str = "normal"  # "high" | "normal" | "low"
    token_budget_ratio: float = 1.0  # Token 预算比例（0.0 ~ 1.0）
    metadata: dict[str, Any] = field(default_factory=dict)


class DialogueDecisionEngine:
    """对话决策引擎

    中枢模块，综合以下信息做出行为决策：
    1. 意图识别结果
    2. 情感分析结果
    3. 记忆系统提供的上下文
    4. 人设配置的行为规则

    输出决策结果，指导上下文组装和能力调用。
    """

    def __init__(
        self,
        intent_engine: IntentEngine | None = None,
        emotion_engine: EmotionEngine | None = None,
    ):
        self._intent_engine = intent_engine or IntentEngine()
        self._emotion_engine = emotion_engine or EmotionEngine()

    async def decide(
        self,
        text: str,
        user_id: str,
        session_id: str,
        context_summary: str | None = None,
    ) -> DecisionResult:
        """做出对话决策

        Args:
            text: 用户输入文本
            user_id: 用户 ID
            session_id: 会话 ID
            context_summary: 上下文摘要

        Returns:
            DecisionResult: 综合决策结果
        """
        # 1. 意图识别
        intent = self._intent_engine.recognize(text)

        # 2. 情感分析
        emotion = await self._emotion_engine.analyze(
            text=text,
            user_id=user_id,
            session_id=session_id,
            context_summary=context_summary,
        )

        # 3. 确定响应策略
        response_strategy = await self._emotion_engine.get_response_strategy(emotion)

        # 4. 根据意图和情感推荐 Skills/Tools
        recommended_skills = self._recommend_skills(intent, emotion)
        recommended_tools = self._recommend_tools(intent)

        # 5. 确定上下文优先级和 Token 预算
        context_priority, token_ratio = self._determine_resource_allocation(intent, emotion)

        result = DecisionResult(
            response_strategy=response_strategy,
            intent=intent,
            emotion_state=emotion,
            should_use_skills=recommended_skills,
            should_use_tools=recommended_tools,
            context_priority=context_priority,
            token_budget_ratio=token_ratio,
        )

        logger.info(
            "decision_made",
            user_id=user_id,
            intent=intent.primary,
            strategy=response_strategy,
            emotion=emotion.emotion.value,
        )

        return result

    def _recommend_skills(
        self,
        intent: IntentResult,
        emotion: EmotionState,
    ) -> list[str]:
        """根据意图和情感推荐 Skills"""
        skills = []

        # 情感相关 Skills
        if intent.primary == "emotional_seeking_comfort":
            skills.append("emotional_comfort")
        elif intent.primary == "emotional_sharing_joy":
            skills.append("celebration")

        # 意图相关 Skills
        if intent.primary == "seeking_advice":
            skills.append("advisory")
        elif intent.primary == "casual_chat":
            skills.append("daily_chat")

        # 基于情感状态的 Skills
        if emotion.needs_immediate_comfort:
            if "emotional_comfort" not in skills:
                skills.append("emotional_comfort")

        return skills

    def _recommend_tools(self, intent: IntentResult) -> list[str]:
        """根据意图推荐 Tools"""
        tools = []

        if intent.primary == "set_reminder":
            tools.append("reminder")
        elif intent.primary == "search":
            tools.append("web_search")
        elif intent.primary == "request_action":
            if "weather" in str(intent.entities):
                tools.append("weather")

        return tools

    def _determine_resource_allocation(
        self,
        intent: IntentResult,
        emotion: EmotionState,
    ) -> tuple[str, float]:
        """确定资源分配策略

        Returns:
            (context_priority, token_budget_ratio)
        """
        # 高优先级：情感需要安慰、寻求建议
        if intent.primary in ("emotional_seeking_comfort", "seeking_advice"):
            return "high", 1.0

        # 情感强烈时给予更多资源
        if emotion.intensity > 0.7:
            return "high", 1.0

        # 普通对话
        if intent.primary in ("casual_chat", "greeting", "farewell"):
            return "normal", 0.8

        # 低优先级
        return "normal", 0.9
