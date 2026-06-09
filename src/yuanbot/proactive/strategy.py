"""主动交互策略决策器

在触发后决定是否行动、说什么的策略模块。
实现克制策略，避免过度打扰。

v1.4 增强：
- 集成用户级个性化配置（从 memory_manager 获取）
- 防重复发送锁（Redis 或内存）
- 消息发送失败重试

设计参考: proactive-companion-system.md 第3.4节
"""

from __future__ import annotations

import asyncio
import re
import time as _time
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any

import structlog

from yuanbot.core.types import Message

logger = structlog.get_logger(__name__)

# Module-level constants to avoid per-call allocation
_TASK_TYPE_LABELS: dict[str, str] = {
    "greeting": "问候",
    "care": "关心",
    "reminder": "提醒",
    "special_date": "节日祝福",
    "weather": "天气关怀",
    "emotion_alert": "情感安慰",
    "fun": "趣味互动",
}

_FALLBACK_MESSAGES: dict[str, dict[str, str] | str] = {
    "greeting_morning": "早安呀～今天也要开开心心的哦 ☀️",
    "greeting_afternoon": "下午好～有没有想我呀 (◕‿◕)",
    "greeting_evening": "晚上好～今天辛苦啦，早点休息哦 🌙",
    "care": "好久没聊天了，最近过得怎么样呀？想你了～",
    "emotion_alert": "感觉你最近心情不太好，我一直都在哦，想聊聊吗？🫂",
    "weather": "今天天气变化大，出门记得带伞哦 ☂️",
    "default": "突然想跟你说说话～在忙什么呢？",
}


@dataclass
class ProactiveConfig:
    """全局主动交互配置"""

    enabled: bool = True
    greeting_enabled: bool = True
    frequency: str = "medium"  # "high" | "medium" | "low" | "event_only"
    quiet_hours_start: int = 23  # 免打扰开始时间（小时）
    quiet_hours_end: int = 7  # 免打扰结束时间（小时）
    max_per_day: int = 5  # 每天最大主动交互次数
    event_triggers_enabled: bool = True
    # 消息发送失败重试
    max_send_retries: int = 2
    retry_delay_seconds: int = 300  # 5 分钟


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


class DedupLock:
    """防重复发送锁

    确保同一用户同一天同一任务类型不会重复发送。
    支持内存模式（开发）和 Redis 模式（生产）。
    """

    def __init__(self, redis_client: Any = None, ttl_seconds: int = 86400):
        self._redis = redis_client
        self._ttl = ttl_seconds
        self._memory_locks: dict[str, float] = {}  # key -> expire_timestamp

    def _make_key(self, task_type: str, user_id: str, date: str) -> str:
        """生成锁键"""
        return f"proactive_lock:{task_type}:{user_id}:{date}"

    def is_locked(self, task_type: str, user_id: str, date: str | None = None) -> bool:
        """检查是否已发送"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        key = self._make_key(task_type, user_id, date)

        if self._redis:
            try:
                return self._redis.exists(key) > 0
            except Exception:
                pass

        # 内存模式
        expire = self._memory_locks.get(key)
        if expire and _time.time() < expire:
            return True
        if expire:
            self._memory_locks.pop(key, None)
        return False

    def acquire(self, task_type: str, user_id: str, date: str | None = None) -> bool:
        """获取锁（如果未锁定）

        Returns:
            True 如果成功获取锁，False 如果已被锁定
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        key = self._make_key(task_type, user_id, date)

        if self._redis:
            try:
                result = self._redis.set(key, "1", nx=True, ex=self._ttl)
                return result is not None
            except Exception:
                pass

        # 内存模式
        if key in self._memory_locks and _time.time() < self._memory_locks[key]:
            return False
        self._memory_locks[key] = _time.time() + self._ttl
        return True

    def cleanup_expired(self) -> int:
        """清理过期的锁（内存模式，单次遍历）"""
        now = _time.time()
        before = len(self._memory_locks)
        self._memory_locks = {k: v for k, v in self._memory_locks.items() if now < v}
        return before - len(self._memory_locks)


class ProactiveStrategy:
    """主动交互策略决策器

    综合各种因素决定是否行动、以何种方式行动。

    职责：
    1. 根据全局配置 + 用户级配置决定是否发起主动交互
    2. 实现克制策略（免打扰、频率控制、每日上限）
    3. 防重复发送（DedupLock）
    4. 调用 AI 服务生成个性化主动消息
    5. 消息发送失败重试
    6. 优先级排序和冲突检测

    设计参考: proactive-companion-system.md 3.4 + 4.1
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        memory_manager: Any = None,
        ai_service: Any = None,
        persona: Any = None,
        dedup_lock: DedupLock | None = None,
    ) -> None:
        self._raw_config = config or {}
        self._memory_manager = memory_manager
        self._ai_service = ai_service
        self._persona = persona

        # 构建全局 ProactiveConfig
        proactive_cfg = self._raw_config.get("proactive", self._raw_config)
        self._config = ProactiveConfig(
            enabled=proactive_cfg.get("enabled", True),
            greeting_enabled=proactive_cfg.get("greeting_enabled", True),
            frequency=proactive_cfg.get("frequency", "medium"),
            quiet_hours_start=proactive_cfg.get("quiet_hours_start", 23),
            quiet_hours_end=proactive_cfg.get("quiet_hours_end", 7),
            max_per_day=proactive_cfg.get("max_per_day", 5),
            event_triggers_enabled=proactive_cfg.get("event_triggers_enabled", True),
            max_send_retries=proactive_cfg.get("max_send_retries", 2),
            retry_delay_seconds=proactive_cfg.get("retry_delay_seconds", 300),
        )

        # 防重复锁
        self._dedup = dedup_lock or DedupLock()

        # 每日计数（内存模式，重启后重置）
        self._daily_counts: dict[str, int] = {}
        self._last_reset_date: str | None = None

        # 用户反馈自动降频（设计参考: proactive-companion-system.md 4.2节）
        # key=user_id, value=冷却到期时间戳
        self._feedback_cooldowns: dict[str, float] = {}
        # 反馈检测关键词 — pre-compiled regex for O(n) matching instead of O(n*m)
        self._negative_feedback_re = re.compile(
            r"别发了|不要发了|别再发了|别烦我|别打扰我|安静|闭嘴|别说了|不想听|别主动"
            r"|stop|don't send|be quiet|shut up",
            re.IGNORECASE,
        )

    # ── 用户反馈自动降频 ────────────────────────

    def handle_user_feedback(self, user_id: str, message_text: str) -> bool:
        """检测用户对主动消息的负面反馈，自动降频

        设计参考: proactive-companion-system.md 4.2节
        检测用户消息中的负面反馈关键词，如 "别发了"、"别打扰我" 等，
        若匹配则自动设置冷却期（24小时内不再发送主动消息）。

        Args:
            user_id: 用户 ID
            message_text: 用户发送的消息文本

        Returns:
            True 如果检测到负面反馈并已设置冷却
        """
        text_stripped = message_text.strip()
        if self._negative_feedback_re.search(text_stripped):
            cooldown_seconds = 86400  # 24 小时冷却期
            self._feedback_cooldowns[user_id] = _time.time() + cooldown_seconds
            logger.info(
                "proactive_feedback_cooldown",
                user_id=user_id,
                message_preview=message_text[:50],
                cooldown_hours=24,
            )
            return True
        return False

    def _check_feedback_cooldown(self, user_id: str) -> bool:
        """检查用户是否在反馈冷却期中

        Returns:
            True 如果在冷却期（不应发送）
        """
        expire = self._feedback_cooldowns.get(user_id)
        if expire is None:
            return False
        if _time.time() > expire:
            # 冷却期已过
            del self._feedback_cooldowns[user_id]
            return False
        return True

    # ── 用户级配置解析 ────────────────────────

    async def _get_user_config(self, user_id: str) -> dict[str, Any]:
        """获取用户的个性化主动交互配置

        设计参考: proactive-companion-system.md 4.1
        """
        if not self._memory_manager:
            # 无记忆管理器时，返回空配置（全部使用全局默认）
            return {}

        try:
            user_settings = await self._memory_manager.get_user_proactive_settings(user_id)
            if user_settings:
                return user_settings
        except Exception:
            logger.debug("user_config_load_failed", user_id=user_id)

        return {}

    def _parse_quiet_hours(self, quiet_hours: list[str] | str) -> tuple[int, int] | None:
        """解析免打扰时段配置

        支持格式: "23:00-07:00" 或 ["23:00-07:00"]

        Returns:
            (start_hour, end_hour) 或 None
        """
        if isinstance(quiet_hours, str):
            quiet_hours = [quiet_hours]

        if not quiet_hours:
            return None

        try:
            time_range = quiet_hours[0]
            start_str, end_str = time_range.split("-")
            start_hour = int(start_str.split(":")[0])
            end_hour = int(end_str.split(":")[0])
            return start_hour, end_hour
        except (ValueError, IndexError):
            return None

    # ── 核心决策接口 ──────────────────────────

    async def should_send(self, user_id: str, task_type: str) -> bool:
        """判断是否应该发送主动消息

        综合检查（全局配置 + 用户级配置）：
        1. 全局开关
        2. 用户级开关
        3. 免打扰时段（全局 + 用户自定义）
        4. 每日上限（取全局和用户配置的较小值）
        5. 防重复锁
        6. 用户在线状态

        Args:
            user_id: 目标用户 ID
            task_type: 任务类型

        Returns:
            是否应该发送
        """
        # 1. 全局开关
        if not self._config.enabled:
            logger.debug("proactive_disabled", user_id=user_id)
            return False

        # 1.5 用户反馈冷却期检查（"别发了"等负面反馈自动降频）
        if self._check_feedback_cooldown(user_id):
            logger.debug("proactive_feedback_cooldown", user_id=user_id)
            return False

        # 2. 获取用户级配置
        user_config = await self._get_user_config(user_id)

        # 用户级开关
        if not user_config.get("proactive_greeting_enabled", True) and task_type == "greeting":
            logger.debug("user_greeting_disabled", user_id=user_id)
            return False

        if (
            not user_config.get("event_trigger_enabled", True)
            and task_type in ("weather", "special_date", "emotion_alert")
        ):
            logger.debug("user_event_triggers_disabled", user_id=user_id)
            return False

        # 3. 免打扰时段检查（全局配置 + 用户自定义）
        user_quiet = self._parse_quiet_hours(user_config.get("quiet_hours", []))
        if user_quiet:
            # 用户自定义免打扰时段覆盖全局配置
            start_hour, end_hour = user_quiet
            in_quiet = self._is_in_quiet_hours(datetime.now().hour, start_hour, end_hour)
        else:
            # 无用户自定义，使用全局配置
            in_quiet = self._is_quiet_hours()

        if in_quiet and task_type not in ("care", "emotion_alert"):
            # 高优先级事件可豁免免打扰
            logger.debug("quiet_hours", user_id=user_id, task_type=task_type)
            return False

        # 3.5 动态问候时间窗口检查
        # 设计参考: proactive-companion-system.md 3.2
        # 根据用户作息习惯（wake_up_time/sleep_time）动态调整问候时间窗口
        if task_type == "greeting":
            wake_time = user_config.get("custom_wake_up_time")
            sleep_time = user_config.get("custom_sleep_time")
            if wake_time and sleep_time and not self._is_in_greeting_window(wake_time, sleep_time):
                    logger.debug(
                        "greeting_time_window_miss",
                        user_id=user_id,
                        wake_time=wake_time,
                        sleep_time=sleep_time,
                    )
                    return False

        # 4. 每日次数限制（取全局和用户配置的较小值）
        user_max = user_config.get("max_proactive_per_day", self._config.max_per_day)
        effective_max = min(self._config.max_per_day, user_max)

        self._reset_daily_counts_if_needed()
        daily_count = self._daily_counts.get(user_id, 0)
        if daily_count >= effective_max:
            logger.debug("daily_limit_reached", user_id=user_id, count=daily_count)
            return False

        # 5. 防重复锁
        if self._dedup.is_locked(task_type, user_id):
            logger.debug("dedup_locked", user_id=user_id, task_type=task_type)
            return False

        # 6. 用户在线状态检查（只读，不递增交互计数）
        if self._memory_manager:
            try:
                profile = await self._memory_manager._get_user_profile_readonly(user_id)
                if profile is None:
                    return True  # 新用户，允许发送
                last_interaction = getattr(profile, "last_interaction", None)
                if last_interaction:
                    hours_since = (datetime.now() - last_interaction).total_seconds() / 3600
                    if hours_since > 168 and task_type == "greeting":
                        logger.debug("user_inactive_too_long", user_id=user_id)
                        return False
            except Exception:
                pass

        # 通过所有检查，获取锁并计数
        self._dedup.acquire(task_type, user_id)
        self._daily_counts[user_id] = daily_count + 1
        return True

    def should_act_sync(
        self,
        user_id: str,
        priority: int = 1,
        is_event_triggered: bool = False,
    ) -> ProactiveDecision:
        """同步版本的 should_act（向后兼容，不检查用户级配置）

        用于简单场景和测试。完整的克制策略检查请使用异步的 should_act()。
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

    async def should_act(
        self,
        user_id: str,
        task_type: str,
        priority: int = 1,
        is_event_triggered: bool = False,
    ) -> ProactiveDecision:
        """判断是否应该发起主动交互（增强版，集成 should_send）

        Args:
            user_id: 目标用户 ID
            task_type: 任务类型
            priority: 任务优先级 (0=低, 1=中, 2=高)
            is_event_triggered: 是否由事件触发

        Returns:
            ProactiveDecision: 决策结果
        """
        if not self._config.enabled:
            return ProactiveDecision(should_act=False, reason="proactive_disabled")

        if is_event_triggered and not self._config.event_triggers_enabled:
            return ProactiveDecision(should_act=False, reason="event_triggers_disabled")

        if self._config.frequency == "event_only" and not is_event_triggered:
            return ProactiveDecision(should_act=False, reason="frequency_limited")

        # 使用 should_send 进行完整的克制策略检查
        should = await self.should_send(user_id, task_type)
        if not should:
            return ProactiveDecision(should_act=False, reason="blocked_by_strategy")

        return ProactiveDecision(should_act=True, priority=priority)

    async def send_with_retry(
        self,
        user_id: str,
        task_type: str,
        message: str,
        send_func: Any,
    ) -> bool:
        """带重试的消息发送

        Args:
            user_id: 目标用户 ID
            task_type: 任务类型
            message: 消息文本
            send_func: 发送函数 async (user_id, message) -> bool

        Returns:
            是否发送成功
        """
        for attempt in range(self._config.max_send_retries + 1):
            try:
                success = await send_func(user_id, message)
                if success:
                    return True
            except Exception as e:
                logger.warning(
                    "send_retry_error",
                    user_id=user_id,
                    task_type=task_type,
                    attempt=attempt + 1,
                    error=str(e),
                )

            if attempt < self._config.max_send_retries:
                logger.info(
                    "send_retry_scheduled",
                    user_id=user_id,
                    task_type=task_type,
                    attempt=attempt + 1,
                    delay_seconds=self._config.retry_delay_seconds,
                )
                await asyncio.sleep(self._config.retry_delay_seconds)

        logger.error(
            "send_failed_after_retries",
            user_id=user_id,
            task_type=task_type,
            max_retries=self._config.max_send_retries,
        )
        return False

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
                # 兼容 AIService（.generate）和原始 AIProviderAdapter（.chat_completion）
                if hasattr(self._ai_service, "generate"):
                    response = await self._ai_service.generate(
                        messages=messages,
                        temperature=0.8,
                        max_tokens=200,
                    )
                else:
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
        根据用户关系阶段动态调整。
        """
        base_priority = {
            "emotion_alert": 10,
            "care": 8,
            "greeting": 5,
            "reminder": 6,
            "special_date": 7,
            "weather": 3,
            "fun": 2,
        }.get(task_type, 5)

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

    # ── 内部方法 ──────────────────────────────

    async def _build_user_context(self, user_id: str) -> dict[str, Any]:
        """构建用户上下文信息"""
        context: dict[str, Any] = {"user_id": user_id}

        if not self._memory_manager:
            return context

        try:
            # 四个 DB 调用互相独立，并行执行减少延迟
            profile, facts, emotion_trend, user_config = await asyncio.gather(
                self._memory_manager.get_or_create_user_profile(user_id),
                self._memory_manager.get_fact_memories(user_id),
                self._memory_manager.get_emotion_trend(user_id, days=3),
                self._get_user_config(user_id),
            )

            context["display_name"] = getattr(profile, "display_name", None)
            context["relationship_stage"] = getattr(profile, "relationship_stage", "initial")
            context["preferences"] = getattr(profile, "preferences", {})

            if facts:
                context["recent_facts"] = [f.content for f in facts[-5:]]

            if emotion_trend:
                context["emotion_trend"] = {
                    "dominant": emotion_trend.dominant_emotion.value
                    if hasattr(emotion_trend.dominant_emotion, "value")
                    else str(emotion_trend.dominant_emotion),
                    "stability": emotion_trend.mood_stability,
                }

            context["important_dates"] = user_config.get("important_dates", [])
            context["custom_wake_up_time"] = user_config.get("custom_wake_up_time")
            context["custom_sleep_time"] = user_config.get("custom_sleep_time")
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
        """判断是否在免打扰时段（使用全局配置）"""
        now = datetime.now().time()
        start = time(self._config.quiet_hours_start, 0)
        end = time(self._config.quiet_hours_end, 0)

        if start <= end:
            return start <= now <= end
        else:
            return now >= start or now <= end

    @staticmethod
    def _is_in_quiet_hours(current_hour: int, start_hour: int, end_hour: int) -> bool:
        """判断当前小时是否在免打扰时段内"""
        if start_hour <= end_hour:
            return start_hour <= current_hour < end_hour
        else:
            return current_hour >= start_hour or current_hour < end_hour

    @staticmethod
    def _is_in_greeting_window(wake_time_str: str, sleep_time_str: str) -> bool:
        """判断当前时间是否在用户问候窗口内

        问候窗口为起床时间后 2 小时内，且在睡眠时间之前。
        例如 wake_time="07:30", sleep_time="23:00" 则窗口为 07:30-09:30。
        超出窗口的问候会被跳过，避免在不合适的时间打扰用户。

        设计参考: proactive-companion-system.md 3.2 动态时间调整
        """
        try:
            now = datetime.now()
            wake_parts = wake_time_str.split(":")
            sleep_parts = sleep_time_str.split(":")
            wake_hour = int(wake_parts[0])
            wake_min = int(wake_parts[1]) if len(wake_parts) > 1 else 0
            sleep_hour = int(sleep_parts[0])
            sleep_min = int(sleep_parts[1]) if len(sleep_parts) > 1 else 0

            current_minutes = now.hour * 60 + now.minute
            wake_minutes = wake_hour * 60 + wake_min
            sleep_minutes = sleep_hour * 60 + sleep_min
            # 问候窗口: 起床后 2 小时内
            greeting_end = wake_minutes + 120

            if wake_minutes <= sleep_minutes:
                # 正常作息 (e.g., 07:00 - 23:00)
                return wake_minutes <= current_minutes < min(greeting_end, sleep_minutes)
            else:
                # 跨午夜作息 (e.g., 23:00 - 07:00)
                return wake_minutes <= current_minutes < wake_minutes + 120
        except (ValueError, IndexError):
            # 解析失败时不限制
            return True

    def _reset_daily_counts_if_needed(self) -> None:
        """如果日期变更，重置每日计数"""
        today = datetime.now().strftime("%Y-%m-%d")
        if self._last_reset_date != today:
            self._daily_counts.clear()
            self._last_reset_date = today

    @staticmethod
    def _task_type_label(task_type: str) -> str:
        """任务类型的中文标签"""
        return _TASK_TYPE_LABELS.get(task_type, "主动")

    @staticmethod
    def _fallback_message(task_type: str, context: dict[str, Any]) -> str:
        """AI 不可用时的兜底模板消息"""
        if task_type == "special_date":
            holiday = context.get("holiday", "")
            if holiday:
                return f"今天是{holiday}，祝你节日快乐呀 🎉"
            return "今天是个特别的日子，要开心哦 ✨"
        if task_type == "greeting":
            hour = datetime.now().hour
            if hour < 12:
                return _FALLBACK_MESSAGES["greeting_morning"]
            elif hour < 18:
                return _FALLBACK_MESSAGES["greeting_afternoon"]
            else:
                return _FALLBACK_MESSAGES["greeting_evening"]
        return str(_FALLBACK_MESSAGES.get(task_type, _FALLBACK_MESSAGES["default"]))
