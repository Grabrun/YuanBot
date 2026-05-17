"""YuanBot 编排引擎

核心职责：
1. 接收用户消息，驱动完整的处理流水线
2. 意图识别 + 情感分析
3. 记忆检索 → 上下文组装 → LLM 调用 → 响应生成
4. 主动交互触发判断
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from yuanbot.core.interfaces import AIProviderAdapter, ChannelAdapter, PersonaProfile
from yuanbot.core.types import (
    BotResponse,
    ContentType,
    MemorySearchResult,
    Message,
    MessageContent,
    ProactiveTask,
    UserMessage,
)
from yuanbot.memory.manager import MemoryManager

logger = structlog.get_logger(__name__)


class OrchestratorEngine:
    """编排引擎 - YuanBot 的大脑

    处理流水线：
    UserMessage → 意图识别 → 情感分析 → 记忆检索 → 上下文组装 →
    LLM 推理 → 响应生成 → 记忆更新 → BotResponse
    """

    def __init__(
        self,
        ai_provider: AIProviderAdapter,
        persona: PersonaProfile,
        memory_manager: MemoryManager,
    ):
        self._ai_provider = ai_provider
        self._persona = persona
        self._memory = memory_manager
        self._channels: dict[str, ChannelAdapter] = {}

    # ──────────────────────────────────────────
    # 核心对话处理流水线
    # ──────────────────────────────────────────

    async def process_message(self, message: UserMessage) -> BotResponse:
        """处理用户消息的完整流水线"""
        logger.info(
            "processing_message",
            platform=message.platform,
            user_id=message.yuanbot_user_id,
            content_type=message.content_type,
        )

        # 1. 获取或创建用户画像
        user_profile = await self._memory.get_or_create_user_profile(message.yuanbot_user_id)

        # 2. 添加到工作记忆
        await self._memory.add_working_memory(
            session_id=message.session_id,
            content=f"[用户] {message.text or '[媒体消息]'}",
        )

        # 3. 情感分析（简化版，后续可独立为 EmotionEngine）
        emotion = await self._analyze_emotion(message.text or "")

        # 4. 情景触发式检索相关记忆
        relevant_memories, current_emotion = await self._memory.retrieve_relevant_memories(
            user_id=message.yuanbot_user_id,
            current_input=message.text or "",
        )

        # 5. 组装上下文（System Prompt + 记忆 + 工作记忆）
        system_prompt = await self._build_system_prompt(
            user_profile=user_profile,
            relevant_memories=relevant_memories,
            emotion=emotion,
        )

        # 6. 获取工作记忆作为对话历史
        working_memory = await self._memory.get_working_memory(message.session_id)
        messages = self._build_messages(system_prompt, working_memory)

        # 7. 调用 LLM
        response = await self._ai_provider.chat_completion(
            messages=messages,
            system_prompt=system_prompt,
        )

        # 8. 将 AI 回复加入工作记忆
        await self._memory.add_working_memory(
            session_id=message.session_id,
            content=f"[AI] {response.content}",
        )

        # 9. 生成主动跟进任务
        proactive_tasks = await self._generate_proactive_tasks(
            user_profile=user_profile,
            emotion=emotion,
        )

        # 10. 构建响应
        bot_response = BotResponse(
            content=MessageContent(
                content_type=ContentType.TEXT,
                text=response.content,
            ),
            proactive_followups=proactive_tasks if proactive_tasks else None,
        )

        logger.info(
            "message_processed",
            user_id=message.yuanbot_user_id,
            emotion=emotion,
            memory_count=len(relevant_memories),
        )

        return bot_response

    # ──────────────────────────────────────────
    # 上下文组装
    # ──────────────────────────────────────────

    async def _build_system_prompt(
        self,
        user_profile: Any,
        relevant_memories: list[MemorySearchResult],
        emotion: str,
    ) -> str:
        """组装完整的 System Prompt"""
        parts = []

        # 基础人设提示词
        parts.append(self._persona.get_system_prompt())

        # 用户画像信息
        if user_profile.display_name:
            parts.append(f"\n[用户信息]\n用户名称: {user_profile.display_name}")
        if user_profile.preferences:
            prefs = ", ".join(f"{k}: {v}" for k, v in user_profile.preferences.items())
            parts.append(f"用户偏好: {prefs}")
        parts.append(f"关系阶段: {user_profile.relationship_stage}")

        # 记忆提示（情景触发注入）
        if relevant_memories:
            memory_section = "\n[记忆提示]\n你回忆起以下与用户相关的过往交流：\n"
            for result in relevant_memories:
                node = result.node
                if node.summary:
                    memory_section += f"- {node.summary}"
                elif node.content:
                    memory_section += f"- {node.content[:100]}"
                if node.emotional_tone:
                    memory_section += f"（情感: {node.emotional_tone}）"
                memory_section += "\n"
            parts.append(memory_section)

        # 当前情感状态
        parts.append(f"\n[当前情感分析]\n用户当前情绪: {emotion}")

        # 行为规则
        rules = self._persona.get_behavior_rules()
        if rules:
            parts.append("\n[行为规则]\n" + "\n".join(f"- {r}" for r in rules))

        return "\n".join(parts)

    def _build_messages(
        self,
        system_prompt: str,
        working_memory: list[Any],
    ) -> list[Message]:
        """从工作记忆构建消息列表"""
        messages = [Message(role="system", content=system_prompt)]

        for node in working_memory:
            content = node.content
            if content.startswith("[用户] "):
                messages.append(Message(role="user", content=content[5:]))
            elif content.startswith("[AI] "):
                messages.append(Message(role="assistant", content=content[5:]))
            elif content.startswith("[用户]"):
                messages.append(Message(role="user", content=content[4:].lstrip()))
            elif content.startswith("[AI]"):
                messages.append(Message(role="assistant", content=content[4:].lstrip()))

        return messages

    # ──────────────────────────────────────────
    # 情感分析（简化版）
    # ──────────────────────────────────────────

    async def _analyze_emotion(self, text: str) -> str:
        """情感分析（简化版，基于关键词匹配）

        后续版本将独立为 EmotionEngine，使用专门的情感分析模型。
        """
        positive_words = ["开心", "高兴", "喜欢", "爱", "棒", "好", "哈哈", "嘿嘿", "太好了"]
        negative_words = ["难过", "伤心", "烦", "讨厌", "累", "压力", "焦虑", "不好", "糟糕"]

        text_lower = text.lower()

        pos_count = sum(1 for w in positive_words if w in text_lower)
        neg_count = sum(1 for w in negative_words if w in text_lower)

        if pos_count > neg_count:
            return "positive"
        elif neg_count > pos_count:
            return "negative"
        else:
            return "neutral"

    # ──────────────────────────────────────────
    # 主动交互任务生成
    # ──────────────────────────────────────────

    async def _generate_proactive_tasks(
        self,
        user_profile: Any,
        emotion: str,
    ) -> list[ProactiveTask]:
        """基于用户状态生成主动交互任务"""
        tasks = []

        # 如果用户情绪低落，生成后续关心任务
        if emotion == "negative":
            tasks.append(
                ProactiveTask(
                    task_type="care",
                    scheduled_at=datetime.now(),  # 立即或短时间后
                    content_hint="用户情绪低落，需要后续关心",
                    priority=2,
                )
            )

        return tasks

    # ──────────────────────────────────────────
    # 通道管理
    # ──────────────────────────────────────────

    def register_channel(self, channel: ChannelAdapter) -> None:
        """注册消息通道"""
        self._channels[channel.platform_name] = channel
        logger.info("channel_registered", platform=channel.platform_name)

    def get_channel(self, platform: str) -> ChannelAdapter | None:
        """获取消息通道"""
        return self._channels.get(platform)
