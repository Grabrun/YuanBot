"""YuanBot 编排引擎

核心职责：
1. 接收用户消息，驱动完整的处理流水线
2. 复用 EmotionEngine 进行情感分析（不再内嵌简化版）
3. 复用 DialogueDecisionEngine 做出行为决策
4. 复用 ContextBuilder 组装上下文
5. 通过 AIService 调用 LLM
6. 通过 CapabilityOrchestrator 管理工具执行循环
7. 记忆更新与主动交互触发

设计参考: persona-decision-system.md 第6节决策流水线
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from yuanbot.core.interfaces import ChannelAdapter, PersonaProfile
from yuanbot.core.types import (
    BotResponse,
    ContentType,
    Message,
    MessageContent,
    ProactiveTask,
    UserMessage,
)
from yuanbot.memory.manager import MemoryManager
from yuanbot.persona.engines.context_builder import ContextBuilder
from yuanbot.persona.engines.dialogue_decision import DialogueDecisionEngine
from yuanbot.services.ai_service import AIService
from yuanbot.services.capability_orchestrator import CapabilityOrchestrator

logger = structlog.get_logger(__name__)


class OrchestratorEngine:
    """编排引擎 - YuanBot 的大脑

    完整处理流水线（设计文档 6. 决策流水线）：
    UserMessage
      → 意图识别 + 情感分析 (DialogueDecisionEngine)
      → 记忆检索
      → 能力加载 (CapabilityOrchestrator)
      → 上下文组装 (ContextBuilder)
      → LLM 推理 (AIService)
      → 工具执行循环 (CapabilityOrchestrator)
      → 响应生成
      → 记忆更新
      → BotResponse
    """

    def __init__(
        self,
        ai_service: AIService,
        persona: PersonaProfile,
        memory_manager: MemoryManager,
        decision_engine: DialogueDecisionEngine | None = None,
        context_builder: ContextBuilder | None = None,
        capability_orchestrator: CapabilityOrchestrator | None = None,
    ):
        self._ai = ai_service
        self._persona = persona
        self._memory = memory_manager
        self._decision = decision_engine or DialogueDecisionEngine()
        self._context_builder = context_builder or ContextBuilder(persona)
        self._capability = capability_orchestrator
        self._channels: dict[str, ChannelAdapter] = {}

    # ──────────────────────────────────────────
    # 核心对话处理流水线
    # ──────────────────────────────────────────

    async def process_message(self, message: UserMessage) -> BotResponse:
        """处理用户消息的完整流水线

        按设计文档决策流水线实现：
        1. 意图识别 + 情感分析
        2. 记忆检索
        3. 决策
        4. 能力加载
        5. 上下文组装
        6. LLM 推理 + 工具循环
        7. 响应生成
        8. 记忆更新
        """
        logger.info(
            "processing_message",
            platform=message.platform,
            user_id=message.yuanbot_user_id,
            content_type=message.content_type,
        )

        # 1. 获取或创建用户画像
        user_profile = await self._memory.get_or_create_user_profile(
            message.yuanbot_user_id
        )

        # 2. 添加用户消息到工作记忆
        await self._memory.add_working_memory(
            session_id=message.session_id,
            content=f"[用户] {message.text or '[媒体消息]'}",
        )

        # 3. 情景触发式检索相关记忆
        relevant_memories, _ = await self._memory.retrieve_relevant_memories(
            user_id=message.yuanbot_user_id,
            current_input=message.text or "",
        )

        # 4. 对话决策（复用 DialogueDecisionEngine，含意图+情感分析）
        decision = await self._decision.decide(
            text=message.text or "",
            user_id=message.yuanbot_user_id,
            session_id=message.session_id,
        )

        logger.info(
            "decision_made",
            intent=decision.intent.primary,
            strategy=decision.response_strategy,
            emotion=decision.emotion_state.emotion.value if decision.emotion_state else "unknown",
            skills=decision.should_use_skills,
            tools=decision.should_use_tools,
        )

        # 5. 能力加载（如果 CapabilityOrchestrator 可用）
        skill_prompts: list[str] = []
        tool_definitions = []
        tool_ids = []
        if self._capability and (decision.should_use_skills or decision.should_use_tools):
            capabilities = await self._capability.load_capabilities(
                skill_ids=decision.should_use_skills,
                tool_ids=decision.should_use_tools,
                capability_domains=self._persona.get_capability_domains(),
            )
            skill_prompts = capabilities.skill_prompts
            tool_definitions = capabilities.tool_definitions
            tool_ids = capabilities.tool_ids

        # 6. 组装上下文（复用 ContextBuilder）
        system_prompt = self._context_builder.build_system_prompt(
            user_profile=user_profile,
            relevant_memories=relevant_memories,
            emotion=decision.emotion_state,
            response_strategy=decision.response_strategy,
            extra_sections={
                f"技能提示[{i}]": prompt
                for i, prompt in enumerate(skill_prompts)
            },
        )

        # 7. 获取工作记忆作为对话历史
        working_memory = await self._memory.get_working_memory(message.session_id)
        messages = self._build_messages(working_memory)

        # 8. 调用 LLM（通过 AIService，支持工具执行循环）
        if tool_definitions and self._capability:
            # 有工具定义，使用工具执行循环
            loop_result = await self._capability.execute_tool_loop(
                messages=messages,
                tool_definitions=tool_definitions,
                tool_ids=tool_ids,
                system_prompt=system_prompt,
            )
            response_text = loop_result.final_response

            # 将工具执行结果记录到工作记忆
            if loop_result.tool_calls_made > 0:
                await self._memory.add_working_memory(
                    session_id=message.session_id,
                    content=f"[系统] 执行了 {loop_result.tool_calls_made} 个工具调用",
                )
        else:
            # 无工具，直接调用 LLM
            response = await self._ai.generate(
                messages=messages,
                system_prompt=system_prompt,
            )
            response_text = response.content or ""

        # 9. 将 AI 回复加入工作记忆
        await self._memory.add_working_memory(
            session_id=message.session_id,
            content=f"[AI] {response_text}",
        )

        # 10. 更新情感记录
        if decision.emotion_state:
            await self._memory.record_emotion(
                user_id=message.yuanbot_user_id,
                session_id=message.session_id,
                emotion_state=decision.emotion_state,
            )

        # 11. 生成主动跟进任务
        proactive_tasks = await self._generate_proactive_tasks(
            user_profile=user_profile,
            emotion_state=decision.emotion_state,
        )

        # 12. 构建响应
        bot_response = BotResponse(
            content=MessageContent(
                content_type=ContentType.TEXT,
                text=response_text,
            ),
            proactive_followups=proactive_tasks if proactive_tasks else None,
        )

        logger.info(
            "message_processed",
            user_id=message.yuanbot_user_id,
            strategy=decision.response_strategy,
            memory_count=len(relevant_memories),
            response_length=len(response_text),
        )

        return bot_response

    # ──────────────────────────────────────────
    # 消息构建
    # ──────────────────────────────────────────

    @staticmethod
    def _build_messages(working_memory: list[Any]) -> list[Message]:
        """从工作记忆构建消息列表"""
        messages = []
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
            # 跳过 [系统] 消息，不发送给 LLM
        return messages

    # ──────────────────────────────────────────
    # 主动交互任务生成
    # ──────────────────────────────────────────

    async def _generate_proactive_tasks(
        self,
        user_profile: Any,
        emotion_state: Any | None,
    ) -> list[ProactiveTask]:
        """基于用户状态生成主动交互任务"""
        tasks = []

        if emotion_state and emotion_state.needs_immediate_comfort:
            tasks.append(
                ProactiveTask(
                    task_type="care",
                    scheduled_at=datetime.now(),
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
