"""对话决策引擎

综合意图、情感、记忆和人设信息，做出行为决策。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from yuanbot.core.types import EmotionState
from yuanbot.persona.engines.decision_plugin import (
    DecisionPluginManager,
    PluginDecisionResult,
)
from yuanbot.persona.engines.emotion_engine import EmotionEngine
from yuanbot.persona.engines.intent_engine import (
    IntentEngine,
    IntentResult,
    MLIntentClassifier,
    SklearnIntentClassifier,
    create_intent_classifier,
)
from yuanbot.services.domain_matcher import DomainMatcher, DomainMatchResult

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

    v8: 集成 DomainMatcher，基于意图/情感/能力域三维加权评分推荐 Skills/Tools。
    """

    # 能力域 → 默认 Tool 映射
    _DOMAIN_TOOL_MAP: dict[str, list[str]] = {
        "emotional_care": [],
        "daily_chat": [],
        "creative_storytelling": [],
        "task_management": ["reminder"],
        "knowledge_query": ["web_search", "weather"],
        "media_generation": [],
    }

    # 能力域 → 默认 Skill 映射
    _DOMAIN_SKILL_MAP: dict[str, str] = {
        "emotional_care": "emotional_comfort",
        "daily_chat": "daily_chat",
        "creative_storytelling": "creative_storytelling",
        "task_management": "set_reminder",
    }

    def __init__(
        self,
        intent_engine: IntentEngine | MLIntentClassifier | SklearnIntentClassifier | None = None,
        emotion_engine: EmotionEngine | None = None,
        domain_matcher: DomainMatcher | None = None,
        plugin_manager: DecisionPluginManager | None = None,
        ml_model_dir: str | None = None,
        ml_confidence_threshold: float = 0.5,
    ):
        if intent_engine is not None:
            self._intent_engine = intent_engine
        elif ml_model_dir:
            self._intent_engine = create_intent_classifier(
                model_dir=ml_model_dir,
                confidence_threshold=ml_confidence_threshold,
            )
        else:
            self._intent_engine = IntentEngine()
        self._emotion_engine = emotion_engine or EmotionEngine()
        self._domain_matcher = domain_matcher or DomainMatcher()
        self._plugin_manager = plugin_manager

    async def decide(
        self,
        text: str,
        user_id: str,
        session_id: str,
        context_summary: str | None = None,
        capability_domains: list[str] | None = None,
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
        # 1. 意图识别（支持 ML 分类器和规则引擎）
        if hasattr(self._intent_engine, "classify"):
            intent = self._intent_engine.classify(text)
        else:
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

        # 4. 根据意图和情感推荐 Skills/Tools（DomainMatcher 单次调用，结果复用）
        match_result = self._domain_matcher.match(
            intent=intent.primary,
            emotion=emotion.emotion.value if emotion else "",
            capability_domains=capability_domains,
            max_skills=3,
            max_tools=3,
        )
        recommended_skills = self._recommend_skills(intent, emotion, match_result)
        recommended_tools = self._recommend_tools(intent, emotion, match_result)

        # 5. 确定上下文优先级和 Token 预算
        context_priority, token_ratio = self._determine_resource_allocation(intent, emotion)

        # 6. 运行自定义决策插件
        plugin_result = await self._run_plugins(
            text=text,
            user_id=user_id,
            session_id=session_id,
            intent=intent,
            emotion=emotion,
            context_summary=context_summary,
            capability_domains=capability_domains,
        )

        result = DecisionResult(
            response_strategy=plugin_result.response_strategy or response_strategy,
            intent=intent,
            emotion_state=emotion,
            should_use_skills=plugin_result.should_use_skills or recommended_skills,
            should_use_tools=plugin_result.should_use_tools or recommended_tools,
            context_priority=plugin_result.context_priority or context_priority,
            token_budget_ratio=(
                plugin_result.token_budget_ratio
                if plugin_result.token_budget_ratio is not None
                else token_ratio
            ),
            metadata=plugin_result.metadata,
        )

        logger.info(
            "decision_made",
            user_id=user_id,
            intent=intent.primary,
            strategy=response_strategy,
            emotion=emotion.emotion.value,
            plugin_overridden=bool(plugin_result.response_strategy),
        )

        return result

    def _recommend_skills(
        self,
        intent: IntentResult,
        emotion: EmotionState,
        match_result: DomainMatchResult,
    ) -> list[str]:
        """根据意图和情感推荐 Skills

        使用预计算的 DomainMatcher 结果推导 Skills。
        """
        # 从匹配到的能力域推导 Skills
        skills: list[str] = []
        for domain in match_result.matched_domains:
            skill_id = self._DOMAIN_SKILL_MAP.get(domain.value)
            if skill_id and skill_id not in skills:
                skills.append(skill_id)

        # 补充：基于情感状态的紧急 Skills
        if emotion.needs_immediate_comfort and "emotional_comfort" not in skills:
            skills.insert(0, "emotional_comfort")

        return skills

    def _recommend_tools(
        self,
        intent: IntentResult,
        emotion: EmotionState,
        match_result: DomainMatchResult,
    ) -> list[str]:
        """根据意图和情感推荐 Tools

        使用预计算的 DomainMatcher 结果推导 Tools。
        """
        tools: list[str] = []
        for domain in match_result.matched_domains:
            domain_tools = self._DOMAIN_TOOL_MAP.get(domain.value, [])
            for tool_id in domain_tools:
                if tool_id not in tools:
                    tools.append(tool_id)

        # 补充：基于意图的直接 Tools
        intent_tool_map = {
            "set_reminder": "reminder",
            "search": "web_search",
        }
        direct_tool = intent_tool_map.get(intent.primary)
        if direct_tool and direct_tool not in tools:
            tools.insert(0, direct_tool)

        return tools

    async def _run_plugins(
        self,
        text: str,
        user_id: str,
        session_id: str,
        intent: IntentResult,
        emotion: EmotionState | None,
        context_summary: str | None = None,
        capability_domains: list[str] | None = None,
    ) -> PluginDecisionResult:
        """运行决策插件，返回合并后的插件结果"""
        if not self._plugin_manager or not self._plugin_manager.loaded:
            return PluginDecisionResult()
        return await self._plugin_manager.process_all(
            text=text,
            user_id=user_id,
            session_id=session_id,
            intent=intent,
            emotion=emotion,
            context_summary=context_summary,
            capability_domains=capability_domains,
        )

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

    def get_intent_engine_info(self) -> dict[str, Any]:
        """获取意图引擎信息（用于诊断和状态查询）"""
        if hasattr(self._intent_engine, "get_model_info"):
            info = self._intent_engine.get_model_info()
            info["engine_type"] = type(self._intent_engine).__name__
            return info
        return {
            "engine_type": type(self._intent_engine).__name__,
            "ready": True,
            "model_type": "rule_based",
        }
