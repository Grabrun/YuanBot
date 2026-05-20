"""上下文组装器

负责将人设、记忆、对话历史等组装为最终的 System Prompt。
"""

from __future__ import annotations

import structlog

from yuanbot.core.interfaces import PersonaProfile
from yuanbot.core.types import EmotionState, MemorySearchResult, UserProfile

logger = structlog.get_logger(__name__)


class ContextBuilder:
    """上下文组装器

    职责：
    1. 组装完整的 System Prompt
    2. 管理各部分的 Token 分配
    3. 根据决策结果调整上下文结构
    """

    def __init__(self, persona: PersonaProfile, max_tokens: int = 128000):
        self._persona = persona
        self._max_tokens = max_tokens

    def build_system_prompt(
        self,
        user_profile: UserProfile | None = None,
        relevant_memories: list[MemorySearchResult] | None = None,
        emotion: EmotionState | str | None = None,
        response_strategy: str = "neutral",
        extra_sections: dict[str, str] | None = None,
    ) -> str:
        """组装完整的 System Prompt

        Args:
            user_profile: 用户画像
            relevant_memories: 检索到的相关记忆
            emotion: 当前情感状态
            response_strategy: 响应策略
            extra_sections: 额外的上下文段落

        Returns:
            完整的 System Prompt 字符串
        """
        sections: list[str] = []

        # 1. 基础人设
        sections.append(self._persona.get_system_prompt())

        # 2. 用户画像
        if user_profile:
            user_section = self._build_user_section(user_profile)
            if user_section:
                sections.append(user_section)

        # 3. 记忆提示
        if relevant_memories:
            memory_section = self._build_memory_section(relevant_memories)
            if memory_section:
                sections.append(memory_section)

        # 4. 情感状态
        if emotion:
            emotion_section = self._build_emotion_section(emotion)
            sections.append(emotion_section)

        # 5. 响应策略指导
        strategy_section = self._build_strategy_section(response_strategy)
        if strategy_section:
            sections.append(strategy_section)

        # 6. 行为规则
        rules = self._persona.get_behavior_rules()
        if rules:
            sections.append("[行为规则]\n" + "\n".join(f"- {r}" for r in rules))

        # 7. 额外段落
        if extra_sections:
            for title, content in extra_sections.items():
                sections.append(f"[{title}]\n{content}")

        return "\n\n".join(sections)

    def _build_user_section(self, profile: UserProfile) -> str:
        """构建用户信息段落"""
        parts = ["[用户信息]"]

        if profile.display_name:
            parts.append(f"用户名称: {profile.display_name}")

        if profile.preferences:
            prefs = ", ".join(f"{k}: {v}" for k, v in profile.preferences.items())
            parts.append(f"用户偏好: {prefs}")

        parts.append(f"关系阶段: {profile.relationship_stage}")

        if profile.trust_score > 0:
            parts.append(f"信任度: {profile.trust_score:.2f}")

        return "\n".join(parts)

    def _build_memory_section(self, memories: list[MemorySearchResult]) -> str:
        """构建记忆提示段落"""
        if not memories:
            return ""

        lines = ["[记忆提示]", "你回忆起以下与用户相关的过往交流："]

        for result in memories:
            node = result.node
            line = "- "
            if node.summary:
                line += node.summary
            elif node.content:
                line += node.content[:100]
            if node.emotional_tone:
                line += f"（情感: {node.emotional_tone}）"
            lines.append(line)

        return "\n".join(lines)

    def _build_emotion_section(self, emotion: EmotionState | str) -> str:
        """构建情感状态段落"""
        if isinstance(emotion, str):
            return f"[当前情感分析]\n用户当前情绪: {emotion}"

        parts = ["[当前情感分析]"]
        parts.append(f"用户当前情绪: {emotion.emotion.value}")
        parts.append(f"情感强度: {emotion.intensity:.2f}")
        parts.append(f"情感效价: {emotion.valence}")

        if emotion.needs_immediate_comfort:
            parts.append("⚠️ 用户需要立即安慰和关怀")

        return "\n".join(parts)

    def _build_strategy_section(self, strategy: str) -> str:
        """构建响应策略段落"""
        strategy_guides = {
            "comfort": "[响应策略] 用户情绪低落，请优先给予温暖的共情和陪伴，不要急着给建议。",
            "celebrate": "[响应策略] 用户心情很好，请真诚地分享快乐，一起庆祝。",
            "calm": "[响应策略] 用户情绪激动，请保持冷静和理解，帮助用户平复情绪。",
            "acknowledge": "[响应策略] 用户有些不满，请先表示理解和认可。",
            "engage": "[响应策略] 用户状态良好，可以自然地深入交流。",
            "gentle_engage": "[响应策略] 用户情绪略有波动，请温柔地引导对话。",
            "neutral": "",
        }
        return strategy_guides.get(strategy, "")
