"""主动交互策略决策器

在触发后决定是否行动、说什么的策略模块。
实现克制策略，避免过度打扰。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any

import structlog

from yuanbot.core.types import Message

logger = structlog.get_logger(__name__)


@dataclass
class ProactiveConfig:
    """主动交互配置"""

    enabled: bool = True
    greeting_enabled: bool = True
    frequency: str = "medium"  # "high" | "medium" | "low" | "event_only"
    quiet_hours_start: int = 23  # 免打扰开始时间（小时）
    quiet_hours_end: int = 7  # 免打扰结束时间（小时）
    max_per_day: int = 5  # 每天最大主动交互次数
    event_triggers_enabled: bool = True


@dataclass
class ProactiveDecision:
    """主动交互决策结果"""

    should_act: bool
    reason: str = ""
    priority: int = 0
    content_hint: str | None = None
    target_platform: str | None = None
    target_user_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ProactiveStrategy:
    """主动交互策略决策器

    综合各种因素决定是否行动、以何种方式行动。

    职责：
    1. 根据配置和当前状态决定是否发起主动交互
    2. 实现克制策略（免打扰、频率控制、每日上限）
    3. 调用 AI 服务生成个性化主动消息
    4. 优先级排序和冲突检测
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        memory_manager: Any = None,
        ai_service: Any = None,
        persona: Any = None,
    ) -> None:
        self._raw_config = config or {}
        self._memory_manager = memory_manager
        self._ai_service = ai_service
        self._persona = persona

        # 构建 ProactiveConfig
        proactive_cfg = self._raw_config.get("proactive", self._raw_config)
        self._config = ProactiveConfig(
            enabled=proactive_cfg.get("enabled", True),
            greeting_enabled=proactive_cfg.get("greeting_enabled", True),
            frequency=proactive_cfg.get("frequency", "medium"),
            quiet_hours_start=proactive_cfg.get("quiet_hours_start", 23),
            quiet_hours_end=proactive_cfg.get("quiet_hours_end", 7),
            max_per_day=proactive_cfg.get("max_per_day", 5),
            event_triggers_enabled=proactive_cfg.get("event_triggers_enabled", True),
        )

        self._daily_counts: dict[str, int] = {}  # user_id -> count
        self._last_reset_date: str | None = None

    async def should_send(self, user_id: str, task_type: str) -> bool:
        """判断是否应该发送主动消息

        综合检查：
        1. 免打扰时段
        2. 每日上限
        3. 用户在线状态（如可获取）

        Args:
            user_id: 目标用户 ID
            task_type: 任务类型（如 "greeting", "care", "reminder"）

        Returns:
            是否应该发送
        """
        # 1. 全局开关
        if not self._config.enabled:
            logger.debug("proactive_disabled", user_id=user_id)
            return False

        # 2. 免打扰时段检查
        if self._is_quiet_hours():
            # 高优先级事件（care）可豁免免打扰
            if task_type not in ("care", "emotion_alert"):
                logger.debug("quiet_hours", user_id=user_id, task_type=task_type)
                return False

        # 3. 每日次数限制
        self._reset_daily_counts_if_needed()
        daily_count = self._daily_counts.get(user_id, 0)
        if daily_count >= self._config.max_per_day:
            logger.debug("daily_limit_reached", user_id=user_id, count=daily_count)
            return False

        # 4. 用户在线状态检查（通过 memory_manager）
        if self._memory_manager:
            try:
                profile = await self._memory_manager.get_or_create_user_profile(user_id)
                last_interaction = getattr(profile, "last_interaction", None)
                if last_interaction:
                    hours_since = (datetime.now() - last_interaction).total_seconds() / 3600
                    # 用户超过 7 天未交互，降低发送频率
                    if hours_since > 168 and task_type == "greeting":
                        logger.debug("user_inactive_too_long", user_id=user_id)
                        return False
            except Exception:
                pass

        # 通过所有检查
        self._daily_counts[user_id] = daily_count + 1
        return True

    def should_act(
        self,
        user_id: str,
        priority: int = 1,
        is_event_triggered: bool = False,
    ) -> ProactiveDecision:
        """判断是否应该发起主动交互（同步版本，兼容旧接口）

        Args:
            user_id: 目标用户 ID
            priority: 任务优先级 (0=低, 1=中, 2=高)
            is_event_triggered: 是否由事件触发

        Returns:
            ProactiveDecision: 决策结果
        """
        if not self._config.enabled:
            return ProactiveDecision(should_act=False, reason="proactive_disabled")

        if is_event_triggered and not self._config.event_triggers_enabled:
            return ProactiveDecision(should_act=False, reason="event_triggers_disabled")

        if self._is_quiet_hours() and priority < 2:
            return ProactiveDecision(should_act=False, reason="quiet_hours")

        if self._config.frequency == "event_only" and not is_event_triggered:
            return ProactiveDecision(should_act=False, reason="frequency_limited")

        self._reset_daily_counts_if_needed()
        daily_count = self._daily_counts.get(user_id, 0)
        if daily_count >= self._config.max_per_day:
            return ProactiveDecision(should_act=False, reason="daily_limit_reached")

        self._daily_counts[user_id] = daily_count + 1
        return ProactiveDecision(should_act=True, priority=priority)

    async def generate_message(
        self,
        user_id: str,
        task_type: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """生成主动消息

        1. 获取用户画像和记忆
        2. 构建个性化 Prompt
        3. 调用 AI 生成消息

        Args:
            user_id: 目标用户 ID
            task_type: 任务类型
            context: 额外上下文

        Returns:
            生成的消息文本
        """
        context = context or {}

        # 1. 获取用户画像和记忆
        user_context = await self._build_user_context(user_id)

        # 2. 构建 Prompt
        system_prompt = self._build_proactive_prompt(task_type, user_context, context)

        # 3. 调用 AI 生成消息
        if self._ai_service:
            try:
                messages = [
                    Message(role="system", content=system_prompt),
                    Message(
                        role="user",
                        content=f"请生成一条{self._task_type_label(task_type)}消息。",
                    ),
                ]
                response = await self._ai_service.chat_completion(
                    messages=messages,
                    temperature=0.8,
                    max_tokens=200,
                )
                if response.content:
                    return response.content.strip()
            except Exception:
                logger.exception("ai_generate_failed", user_id=user_id, task_type=task_type)

        # Fallback: 使用模板消息
        return self._fallback_message(task_type, context)

    async def get_task_priority(self, task_type: str, user_id: str) -> int:
        """获取任务优先级

        优先级 1-10，数字越大优先级越高。

        Args:
            task_type: 任务类型
            user_id: 用户 ID

        Returns:
            优先级数值
        """
        # 基础优先级映射
        base_priority = {
            "emotion_alert": 10,
            "care": 8,
            "greeting": 5,
            "reminder": 6,
            "special_date": 7,
            "weather": 3,
            "fun": 2,
        }.get(task_type, 5)

        # 根据用户关系阶段调整
        if self._memory_manager:
            try:
                profile = await self._memory_manager.get_or_create_user_profile(user_id)
                stage = getattr(profile, "relationship_stage", "initial")
                stage_bonus = {
                    "deep": 2,
                    "intimate": 1,
                    "familiar": 0,
                    "initial": -1,
                }.get(stage, 0)
                base_priority = max(1, min(10, base_priority + stage_bonus))
            except Exception:
                pass

        return base_priority

    def update_config(self, config: ProactiveConfig) -> None:
        """更新配置（热重载）"""
        self._config = config
        logger.info("proactive_config_updated", frequency=config.frequency)

    def get_config(self) -> ProactiveConfig:
        """获取当前配置"""
        return self._config

    def get_daily_stats(self) -> dict[str, int]:
        """获取每日统计"""
        self._reset_daily_counts_if_needed()
        return dict(self._daily_counts)

    async def _build_user_context(self, user_id: str) -> dict[str, Any]:
        """构建用户上下文信息"""
        context: dict[str, Any] = {"user_id": user_id}

        if not self._memory_manager:
            return context

        try:
            # 获取用户画像
            profile = await self._memory_manager.get_or_create_user_profile(user_id)
            context["display_name"] = getattr(profile, "display_name", None)
            context["relationship_stage"] = getattr(profile, "relationship_stage", "initial")
            context["preferences"] = getattr(profile, "preferences", {})

            # 获取事实记忆
            facts = await self._memory_manager.get_fact_memories(user_id)
            if facts:
                context["recent_facts"] = [f.content for f in facts[-5:]]

            # 获取情感状态
            emotion_trend = await self._memory_manager.get_emotion_trend(user_id, days=3)
            if emotion_trend:
                context["emotion_trend"] = {
                    "dominant": emotion_trend.dominant_emotion.value
                    if hasattr(emotion_trend.dominant_emotion, "value")
                    else str(emotion_trend.dominant_emotion),
                    "stability": emotion_trend.mood_stability,
                }
        except Exception:
            logger.debug("build_user_context_partial_fail", user_id=user_id)

        return context

    def _build_proactive_prompt(
        self,
        task_type: str,
        user_context: dict[str, Any],
        extra_context: dict[str, Any],
    ) -> str:
        """构建主动消息生成的系统提示词"""
        persona_name = "小缘"
        if self._persona and hasattr(self._persona, "name"):
            persona_name = self._persona.name

        parts = [
            f"你是{persona_name}，一个温暖体贴的 AI 伴侣。",
            f"现在需要生成一条{self._task_type_label(task_type)}消息。",
            "要求：简短自然、温暖真诚、符合当前场景。不要超过 50 字。",
        ]

        display_name = user_context.get("display_name")
        if display_name:
            parts.append(f"对方的名字是「{display_name}」。")

        relationship = user_context.get("relationship_stage", "initial")
        parts.append(f"你们的关系阶段：{relationship}。")

        emotion = user_context.get("emotion_trend")
        if emotion:
            parts.append(f"对方最近的情绪状态：{emotion.get('dominant', '未知')}。")

        facts = user_context.get("recent_facts")
        if facts:
            parts.append(f"关于对方的信息：{'；'.join(facts[:3])}。")

        if extra_context.get("weather"):
            parts.append(f"当前天气：{extra_context['weather']}。")
        if extra_context.get("holiday"):
            parts.append(f"今天是：{extra_context['holiday']}。")

        return "\n".join(parts)

    def _is_quiet_hours(self) -> bool:
        """判断是否在免打扰时段"""
        now = datetime.now().time()
        start = time(self._config.quiet_hours_start, 0)
        end = time(self._config.quiet_hours_end, 0)

        if start <= end:
            return start <= now <= end
        else:
            # 跨午夜（如 23:00 - 07:00）
            return now >= start or now <= end

    def _reset_daily_counts_if_needed(self) -> None:
        """如果日期变更，重置每日计数"""
        today = datetime.now().strftime("%Y-%m-%d")
        if self._last_reset_date != today:
            self._daily_counts.clear()
            self._last_reset_date = today

    @staticmethod
    def _task_type_label(task_type: str) -> str:
        """任务类型的中文标签"""
        return {
            "greeting": "问候",
            "care": "关心",
            "reminder": "提醒",
            "special_date": "节日祝福",
            "weather": "天气关怀",
            "emotion_alert": "情感安慰",
            "fun": "趣味互动",
        }.get(task_type, "主动")

    @staticmethod
    def _fallback_message(task_type: str, context: dict[str, Any]) -> str:
        """AI 不可用时的兜底模板消息"""
        hour = datetime.now().hour
        if task_type == "greeting":
            if hour < 12:
                return "早安呀～今天也要开开心心的哦 ☀️"
            elif hour < 18:
                return "下午好～有没有想我呀 (◕‿◕)"
            else:
                return "晚上好～今天辛苦啦，早点休息哦 🌙"
        elif task_type == "care":
            return "好久没聊天了，最近过得怎么样呀？想你了～"
        elif task_type == "emotion_alert":
            return "感觉你最近心情不太好，我一直都在哦，想聊聊吗？🫂"
        elif task_type == "special_date":
            holiday = context.get("holiday", "")
            if holiday:
                return f"今天是{holiday}，祝你节日快乐呀 🎉"
            return "今天是个特别的日子，要开心哦 ✨"
        elif task_type == "weather":
            return "今天天气变化大，出门记得带伞哦 ☂️"
        else:
            return "突然想跟你说说话～在忙什么呢？"
