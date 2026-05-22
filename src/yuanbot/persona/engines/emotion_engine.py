"""情感分析引擎

独立的情感分析模块，可被编排引擎和记忆系统复用。
当前使用规则引擎，后续可扩展为模型驱动。
包含 DeepEmotionAnalyzer，当规则引擎置信度低时调用 LLM 进行深度分析。
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


class DeepEmotionAnalyzer:
    """深度情感分析器

    当规则引擎置信度低于阈值时，调用 LLM 进行链式思考（chain-of-thought）
    深度情感分析，返回结构化的 EmotionState。

    使用方式:
        analyzer = DeepEmotionAnalyzer(ai_service=ai_service)
        if rule_result.confidence < 0.5:
            deep_result = await analyzer.analyze(text, user_id, session_id)
    """

    def __init__(
        self,
        ai_service: Any | None = None,
        config: dict[str, Any] | None = None,
    ):
        self._ai_service = ai_service
        self._config = config or {}
        self._confidence_threshold = self._config.get("confidence_threshold", 0.5)
        self._enabled = self._config.get("enabled", True)

    @property
    def enabled(self) -> bool:
        """是否启用深度分析"""
        return self._enabled and self._ai_service is not None

    @property
    def confidence_threshold(self) -> float:
        """置信度阈值：低于此值时触发深度分析"""
        return self._confidence_threshold

    async def analyze(
        self,
        text: str,
        user_id: str,
        session_id: str,
        context_summary: str | None = None,
        rule_result: EmotionState | None = None,
    ) -> EmotionState:
        """使用 LLM 链式思考进行深度情感分析

        Args:
            text: 用户输入文本
            user_id: 用户 ID
            session_id: 会话 ID
            context_summary: 上下文摘要
            rule_result: 规则引擎的分析结果（作为参考）

        Returns:
            EmotionState: 深度分析后的情感状态
        """
        if not self.enabled:
            # 降级：返回规则结果或中性
            return rule_result or EmotionState(
                emotion=EmotionCategory.NEUTRAL,
                intensity=0.3,
                confidence=0.3,
                analysis_method="fallback",
            )

        try:
            return await self._call_llm_analysis(text, context_summary, rule_result)
        except Exception as e:
            logger.warning(
                "deep_emotion_analysis_failed",
                error=str(e),
                user_id=user_id,
            )
            # 降级：返回规则结果
            return rule_result or EmotionState(
                emotion=EmotionCategory.NEUTRAL,
                intensity=0.3,
                confidence=0.3,
            )

    async def _call_llm_analysis(
        self,
        text: str,
        context_summary: str | None = None,
        rule_result: EmotionState | None = None,
    ) -> EmotionState:
        """调用 LLM 进行链式思考情感分析"""
        from yuanbot.core.types import Message

        prompt = self._build_cot_prompt(text, context_summary, rule_result)

        messages = [Message(role="user", content=prompt)]

        response = await self._ai_service.chat(
            messages=messages,
            temperature=0.1,  # 低温度确保一致性
            max_tokens=500,
        )

        return self._parse_llm_response(response.content or "", rule_result)

    def _build_cot_prompt(
        self,
        text: str,
        context_summary: str | None = None,
        rule_result: EmotionState | None = None,
    ) -> str:
        """构建链式思考提示词"""
        parts = [
            "你是一个专业的情感分析专家。请分析以下文本中的情感，使用链式思考方法。",
            "",
            "## 分析步骤",
            "1. 仔细阅读文本，理解字面意思和隐含情感",
            "2. 识别文本中的情感关键词和表达",
            "3. 考虑语境、语气和修辞手法",
            "4. 判断主要情感和强度",
            "5. 输出结构化结果",
            "",
            "## 待分析文本",
            f"```\n{text}\n```",
        ]

        if context_summary:
            parts.extend(["## 对话上下文", f"```\n{context_summary}\n`", ""])

        if rule_result:
            parts.extend([
                "## 规则引擎初步结果（供参考）",
                f"- 情感: {rule_result.emotion.value}",
                f"- 强度: {rule_result.intensity}",
                f"- 置信度: {rule_result.confidence}",
                "",
                "如果规则引擎结果不准确，请基于你的分析给出修正。",
                "",
            ])

        parts.extend([
            "## 输出格式",
            "请严格按以下 JSON 格式输出（不要输出其他内容）：",
            "```json",
            "{",
            '  "thinking": "你的分析思考过程（2-3句话）",',
            '  "emotion": "joy|sadness|anger|fear|surprise|disgust|trust|anticipation|neutral",',
            '  "intensity": 0.0到1.0之间的浮点数,',
            '  "confidence": 0.0到1.0之间的浮点数,',
            '  "valence": "positive|negative|neutral",',
            '  "arousal": "low|medium|high",',
            '  "needs_comfort": true或false',
            "}",
            "```",
            "",
            "请开始分析：",
        ])

        return "\n".join(parts)

    def _parse_llm_response(
        self,
        response_text: str,
        rule_result: EmotionState | None = None,
    ) -> EmotionState:
        """解析 LLM 响应为 EmotionState"""
        import json
        import re

        # 提取 JSON 块
        json_match = re.search(r"\{[^}]+\}", response_text, re.DOTALL)
        if not json_match:
            logger.warning("deep_emotion_no_json", response=response_text[:200])
            return rule_result or EmotionState(
                emotion=EmotionCategory.NEUTRAL,
                intensity=0.3,
                confidence=0.3,
            )

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            logger.warning("deep_emotion_parse_failed", response=response_text[:200])
            return rule_result or EmotionState(
                emotion=EmotionCategory.NEUTRAL,
                intensity=0.3,
                confidence=0.3,
            )

        # 解析情感类别
        emotion_str = data.get("emotion", "neutral")
        try:
            emotion = EmotionCategory(emotion_str)
        except ValueError:
            logger.warning("deep_emotion_unknown_category", emotion=emotion_str)
            emotion = EmotionCategory.NEUTRAL

        # 构建 EmotionState
        intensity = float(data.get("intensity", 0.5))
        intensity = max(0.0, min(1.0, intensity))

        confidence = float(data.get("confidence", 0.7))
        confidence = max(0.0, min(1.0, confidence))

        valence = data.get("valence", "neutral")
        arousal = data.get("arousal", "medium")
        needs_comfort = bool(data.get("needs_comfort", False))

        # 判断主导度
        high_dominance = {EmotionCategory.ANGER, EmotionCategory.DISGUST, EmotionCategory.JOY}
        low_dominance = {EmotionCategory.FEAR, EmotionCategory.SADNESS}
        if emotion in high_dominance:
            dominance = "high"
        elif emotion in low_dominance:
            dominance = "low"
        else:
            dominance = "medium"

        result = EmotionState(
            emotion=emotion,
            intensity=intensity,
            valence=valence,
            arousal=arousal,
            dominance=dominance,
            needs_immediate_comfort=needs_comfort,
            confidence=confidence,
        )

        thinking = data.get("thinking", "")
        if thinking:
            logger.debug("deep_emotion_analysis", thinking=thinking, emotion=emotion.value)

        return result
