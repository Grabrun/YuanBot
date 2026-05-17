"""主动交互策略决策器

在触发后决定是否行动、说什么的策略模块。
实现克制策略，避免过度打扰。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ProactiveConfig:
    """主动交互配置"""

    enabled: bool = True
    greeting_enabled: bool = True
    frequency: str = "medium"  # "high" | "medium" | "low" | "event_only"
    quiet_hours_start: int = 23  # 免打扰开始时间（小时）
    quiet_hours_end: int = 8  # 免打扰结束时间（小时）
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

    职责：
    1. 根据配置和当前状态决定是否发起主动交互
    2. 实现克制策略（免打扰、频率控制）
    3. 优先级排序和冲突检测
    """

    def __init__(self, config: ProactiveConfig | None = None):
        self._config = config or ProactiveConfig()
        self._daily_counts: dict[str, int] = {}  # user_id -> count
        self._last_reset_date: str | None = None

    def should_act(
        self,
        user_id: str,
        priority: int = 1,
        is_event_triggered: bool = False,
    ) -> ProactiveDecision:
        """判断是否应该发起主动交互

        Args:
            user_id: 目标用户 ID
            priority: 任务优先级 (0=低, 1=中, 2=高)
            is_event_triggered: 是否由事件触发

        Returns:
            ProactiveDecision: 决策结果
        """
        # 1. 全局开关
        if not self._config.enabled:
            return ProactiveDecision(should_act=False, reason="proactive_disabled")

        # 2. 事件触发开关
        if is_event_triggered and not self._config.event_triggers_enabled:
            return ProactiveDecision(should_act=False, reason="event_triggers_disabled")

        # 3. 免打扰时段检查（高优先级事件可豁免）
        if self._is_quiet_hours() and priority < 2:
            return ProactiveDecision(should_act=False, reason="quiet_hours")

        # 4. 频率控制
        if self._is_frequency_limited():
            return ProactiveDecision(should_act=False, reason="frequency_limited")

        # 5. 每日次数限制
        self._reset_daily_counts_if_needed()
        daily_count = self._daily_counts.get(user_id, 0)
        if daily_count >= self._config.max_per_day:
            return ProactiveDecision(should_act=False, reason="daily_limit_reached")

        # 通过所有检查，允许行动
        self._daily_counts[user_id] = daily_count + 1

        return ProactiveDecision(
            should_act=True,
            priority=priority,
        )

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

    def _is_quiet_hours(self) -> bool:
        """判断是否在免打扰时段"""
        now = datetime.now().time()
        start = time(self._config.quiet_hours_start, 0)
        end = time(self._config.quiet_hours_end, 0)

        if start <= end:
            return start <= now <= end
        else:
            # 跨午夜（如 23:00 - 08:00）
            return now >= start or now <= end

    def _is_frequency_limited(self) -> bool:
        """频率控制

        high: 不限制
        medium: 每 30 分钟最多 1 次
        low: 每 2 小时最多 1 次
        event_only: 仅事件触发
        """
        # 简化实现：基于频率配置
        # 生产环境应记录上次交互时间
        return self._config.frequency == "event_only"

    def _reset_daily_counts_if_needed(self) -> None:
        """如果日期变更，重置每日计数"""
        today = datetime.now().strftime("%Y-%m-%d")
        if self._last_reset_date != today:
            self._daily_counts.clear()
            self._last_reset_date = today
