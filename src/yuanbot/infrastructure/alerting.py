"""告警系统

当连续多次 AI 提供商调用失败、磁盘空间不足、数据库连接丢失时，
通过日志和 webhook 发出告警。

设计参考: infrastructure-deployment-system.md 第8.4节
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class AlertSeverity(StrEnum):
    """告警严重程度"""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertCategory(StrEnum):
    """告警类别"""

    AI_PROVIDER = "ai_provider"
    DISK_SPACE = "disk_space"
    DATABASE = "database"
    SYSTEM = "system"


@dataclass
class AlertRule:
    """告警规则定义

    Attributes:
        name: 规则名称
        category: 告警类别
        severity: 严重程度
        threshold: 触发阈值（如连续失败次数）
        cooldown_seconds: 同一规则的告警冷却时间（秒）
        check_interval_seconds: 检查间隔（秒）
        enabled: 是否启用
    """

    name: str
    category: AlertCategory
    severity: AlertSeverity = AlertSeverity.WARNING
    threshold: int = 3
    cooldown_seconds: int = 3600  # 1 小时
    check_interval_seconds: int = 60
    enabled: bool = True


@dataclass
class Alert:
    """告警实例

    Attributes:
        rule_name: 触发的规则名称
        category: 告警类别
        severity: 严重程度
        message: 告警消息
        details: 附加详情
        timestamp: 触发时间戳
        resolved: 是否已恢复
        resolved_timestamp: 恢复时间戳
    """

    rule_name: str
    category: AlertCategory
    severity: AlertSeverity
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    resolved: bool = False
    resolved_timestamp: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "rule_name": self.rule_name,
            "category": self.category.value,
            "severity": self.severity.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
            "resolved": self.resolved,
            "resolved_timestamp": self.resolved_timestamp,
        }


@dataclass
class AlertState:
    """规则的运行时状态"""

    consecutive_failures: int = 0
    last_failure_time: float = 0.0
    last_alert_time: float = 0.0
    total_failures: int = 0
    total_alerts: int = 0
    is_alerting: bool = False


class WebhookDelivery:
    """Webhook 告警投递器

    通过 HTTP POST 将告警推送到外部 webhook 端点。
    支持配置多个端点，任一成功即为投递成功。
    """

    def __init__(self, webhook_urls: list[str] | None = None, timeout: int = 10) -> None:
        self._urls = webhook_urls or []
        self._timeout = timeout

    @property
    def has_targets(self) -> bool:
        """是否有配置的 webhook 端点"""
        return bool(self._urls)

    def add_url(self, url: str) -> None:
        """添加 webhook 端点"""
        if url not in self._urls:
            self._urls.append(url)

    def remove_url(self, url: str) -> None:
        """移除 webhook 端点"""
        if url in self._urls:
            self._urls.remove(url)

    async def deliver(self, alert: Alert) -> bool:
        """投递告警到所有 webhook 端点

        Args:
            alert: 告警实例

        Returns:
            是否至少有一个端点投递成功
        """
        if not self._urls:
            return False

        payload = {
            "type": "yuanbot_alert",
            "alert": alert.to_dict(),
        }

        success_count = 0
        for url in self._urls:
            try:
                import httpx

                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code < 400:
                        success_count += 1
                    else:
                        logger.warning(
                            "webhook_delivery_failed",
                            url=url,
                            status_code=resp.status_code,
                        )
            except ImportError:
                logger.warning("webhook_delivery_skipped", reason="httpx not installed")
                break
            except Exception as e:
                logger.warning("webhook_delivery_error", url=url, error=str(e))

        return success_count > 0


class AlertManager:
    """告警管理器

    核心告警引擎，负责：
    1. 注册和管理告警规则
    2. 接收外部事件（AI 调用失败、磁盘空间不足、DB 连接丢失）
    3. 根据规则判断是否触发告警
    4. 通过日志和 webhook 投递告警
    5. 管理告警冷却和恢复

    使用示例::

        manager = AlertManager()
        manager.add_rule(AlertRule(
            name="ai_consecutive_failures",
            category=AlertCategory.AI_PROVIDER,
            threshold=3,
            cooldown_seconds=600,
        ))

        # 记录 AI 调用失败
        manager.record_ai_failure("openai", "Connection timeout")

        # 记录 AI 调用成功（重置计数）
        manager.record_ai_success("openai")
    """

    def __init__(
        self,
        webhook_urls: list[str] | None = None,
        webhook_timeout: int = 10,
    ) -> None:
        self._rules: dict[str, AlertRule] = {}
        self._states: dict[str, AlertState] = {}
        self._alert_history: list[Alert] = []
        self._history_max_size = 200
        self._webhook = WebhookDelivery(webhook_urls, webhook_timeout)

        # AI 提供商失败跟踪（按 provider_id 分组）
        self._ai_failure_counts: dict[str, int] = {}

        # 注册默认规则
        self._register_default_rules()

    def _register_default_rules(self) -> None:
        """注册默认告警规则"""
        self.add_rule(
            AlertRule(
                name="ai_consecutive_failures",
                category=AlertCategory.AI_PROVIDER,
                severity=AlertSeverity.CRITICAL,
                threshold=3,
                cooldown_seconds=600,  # 10 分钟
            )
        )
        self.add_rule(
            AlertRule(
                name="ai_high_failure_rate",
                category=AlertCategory.AI_PROVIDER,
                severity=AlertSeverity.WARNING,
                threshold=10,  # 10 分钟内累计失败次数
                cooldown_seconds=900,  # 15 分钟
            )
        )
        self.add_rule(
            AlertRule(
                name="disk_space_low",
                category=AlertCategory.DISK_SPACE,
                severity=AlertSeverity.CRITICAL,
                threshold=90,  # 使用率百分比
                cooldown_seconds=3600,  # 1 小时
            )
        )
        self.add_rule(
            AlertRule(
                name="disk_space_warning",
                category=AlertCategory.DISK_SPACE,
                severity=AlertSeverity.WARNING,
                threshold=80,
                cooldown_seconds=3600,
            )
        )
        self.add_rule(
            AlertRule(
                name="database_connection_lost",
                category=AlertCategory.DATABASE,
                severity=AlertSeverity.CRITICAL,
                threshold=1,  # 1 次失败即告警
                cooldown_seconds=300,  # 5 分钟
            )
        )

    # ── 规则管理 ──────────────────────────────

    def add_rule(self, rule: AlertRule) -> None:
        """添加或更新告警规则"""
        self._rules[rule.name] = rule
        if rule.name not in self._states:
            self._states[rule.name] = AlertState()
        logger.debug("alert_rule_added", name=rule.name, category=rule.category.value)

    def remove_rule(self, name: str) -> bool:
        """移除告警规则"""
        if name in self._rules:
            del self._rules[name]
            self._states.pop(name, None)
            return True
        return False

    def get_rule(self, name: str) -> AlertRule | None:
        """获取告警规则"""
        return self._rules.get(name)

    def list_rules(self) -> list[AlertRule]:
        """列出所有告警规则"""
        return list(self._rules.values())

    # ── 事件记录 ──────────────────────────────

    def record_ai_failure(self, provider_id: str, error: str = "") -> Alert | None:
        """记录 AI 提供商调用失败

        Args:
            provider_id: 提供商 ID（如 "openai", "deepseek"）
            error: 错误信息

        Returns:
            如果触发告警，返回 Alert 实例；否则返回 None
        """
        self._ai_failure_counts[provider_id] = self._ai_failure_counts.get(provider_id, 0) + 1

        # 更新连续失败计数（按 provider_id 分组）
        state = self._get_or_create_state("ai_consecutive_failures")
        state.consecutive_failures += 1
        state.total_failures += 1
        state.last_failure_time = time.time()

        # 检查连续失败规则
        rule = self._rules.get("ai_consecutive_failures")
        if rule and rule.enabled and state.consecutive_failures >= rule.threshold:
            return self._fire_alert(
                rule_name="ai_consecutive_failures",
                message=(f"AI 提供商 '{provider_id}' 连续调用失败 {state.consecutive_failures} 次"),
                details={
                    "provider_id": provider_id,
                    "consecutive_failures": state.consecutive_failures,
                    "error": error,
                },
            )

        # 检查累计失败规则
        high_rate_state = self._get_or_create_state("ai_high_failure_rate")
        high_rate_state.total_failures += 1
        high_rate_state.last_failure_time = time.time()

        high_rate_rule = self._rules.get("ai_high_failure_rate")
        if (
            high_rate_rule
            and high_rate_rule.enabled
            and high_rate_state.total_failures >= high_rate_rule.threshold
        ):
            return self._fire_alert(
                rule_name="ai_high_failure_rate",
                message=(
                    f"AI 提供商调用累计失败 {high_rate_state.total_failures} 次（10 分钟窗口）"
                ),
                details={
                    "provider_id": provider_id,
                    "total_failures": high_rate_state.total_failures,
                    "failure_counts": dict(self._ai_failure_counts),
                    "error": error,
                },
            )

        return None

    def record_ai_success(self, provider_id: str) -> None:
        """记录 AI 提供商调用成功，重置连续失败计数

        Args:
            provider_id: 提供商 ID
        """
        self._ai_failure_counts.pop(provider_id, None)

        state = self._get_or_create_state("ai_consecutive_failures")
        if state.consecutive_failures > 0:
            # 如果之前处于告警状态，记录恢复
            if state.is_alerting:
                self._resolve_alert("ai_consecutive_failures")
            state.consecutive_failures = 0

    def record_disk_usage(self, usage_percent: float, path: str = "/") -> Alert | None:
        """记录磁盘使用率，检查是否超过阈值

        Args:
            usage_percent: 磁盘使用率百分比（0-100）
            path: 磁盘路径

        Returns:
            如果触发告警，返回 Alert 实例；否则返回 None
        """
        # 先检查 critical 阈值
        critical_rule = self._rules.get("disk_space_low")
        if critical_rule and critical_rule.enabled and usage_percent >= critical_rule.threshold:
            state = self._get_or_create_state("disk_space_low")
            state.consecutive_failures = 1
            return self._fire_alert(
                rule_name="disk_space_low",
                message=f"磁盘空间严重不足: 使用率 {usage_percent:.1f}%（路径: {path}）",
                details={"usage_percent": usage_percent, "path": path},
            )

        # 再检查 warning 阈值
        warning_rule = self._rules.get("disk_space_warning")
        if warning_rule and warning_rule.enabled and usage_percent >= warning_rule.threshold:
            state = self._get_or_create_state("disk_space_warning")
            state.consecutive_failures = 1
            return self._fire_alert(
                rule_name="disk_space_warning",
                message=f"磁盘空间不足: 使用率 {usage_percent:.1f}%（路径: {path}）",
                details={"usage_percent": usage_percent, "path": path},
            )

        # 使用率正常，恢复告警
        self._resolve_alert("disk_space_low")
        self._resolve_alert("disk_space_warning")
        return None

    def record_database_error(self, db_type: str, error: str = "") -> Alert | None:
        """记录数据库连接错误

        Args:
            db_type: 数据库类型（如 "sqlite", "mysql", "redis", "milvus"）
            error: 错误信息

        Returns:
            如果触发告警，返回 Alert 实例；否则返回 None
        """
        state = self._get_or_create_state("database_connection_lost")
        state.consecutive_failures += 1
        state.total_failures += 1
        state.last_failure_time = time.time()

        rule = self._rules.get("database_connection_lost")
        if rule and rule.enabled and state.consecutive_failures >= rule.threshold:
            return self._fire_alert(
                rule_name="database_connection_lost",
                message=f"数据库连接异常: {db_type} 连接失败 {state.consecutive_failures} 次",
                details={"db_type": db_type, "error": error},
            )

        return None

    def record_database_success(self, db_type: str) -> None:
        """记录数据库连接成功，恢复告警

        Args:
            db_type: 数据库类型
        """
        state = self._get_or_create_state("database_connection_lost")
        if state.is_alerting:
            self._resolve_alert("database_connection_lost")
        state.consecutive_failures = 0

    # ── 自动检查 ──────────────────────────────

    def check_disk_space(self, path: str = "/") -> Alert | None:
        """自动检查磁盘空间

        Args:
            path: 要检查的路径

        Returns:
            如果触发告警，返回 Alert 实例；否则返回 None
        """
        try:
            import shutil

            usage = shutil.disk_usage(path)
            usage_percent = (usage.used / usage.total) * 100
            return self.record_disk_usage(usage_percent, path)
        except Exception as e:
            logger.warning("disk_check_failed", path=path, error=str(e))
            return None

    # ── 查询接口 ──────────────────────────────

    def get_active_alerts(self) -> list[Alert]:
        """获取所有活跃（未恢复）的告警"""
        return [a for a in self._alert_history if not a.resolved]

    def get_alert_history(self, limit: int = 50) -> list[Alert]:
        """获取告警历史

        Args:
            limit: 返回的最大数量

        Returns:
            按时间倒序排列的告警列表
        """
        return list(reversed(self._alert_history[-limit:]))

    def get_state(self, rule_name: str) -> AlertState | None:
        """获取规则的运行时状态"""
        return self._states.get(rule_name)

    def get_all_states(self) -> dict[str, AlertState]:
        """获取所有规则的运行时状态"""
        return dict(self._states)

    def get_ai_failure_counts(self) -> dict[str, int]:
        """获取各 AI 提供商的失败计数"""
        return dict(self._ai_failure_counts)

    def reset_state(self, rule_name: str) -> None:
        """重置指定规则的状态"""
        if rule_name in self._states:
            self._states[rule_name] = AlertState()

    def reset_all_states(self) -> None:
        """重置所有规则的状态"""
        for name in self._states:
            self._states[name] = AlertState()
        self._ai_failure_counts.clear()

    # ── Webhook 配置 ──────────────────────────

    @property
    def webhook(self) -> WebhookDelivery:
        """获取 webhook 投递器"""
        return self._webhook

    def add_webhook_url(self, url: str) -> None:
        """添加 webhook 端点"""
        self._webhook.add_url(url)

    def remove_webhook_url(self, url: str) -> None:
        """移除 webhook 端点"""
        self._webhook.remove_url(url)

    # ── 内部方法 ──────────────────────────────

    def _get_or_create_state(self, rule_name: str) -> AlertState:
        """获取或创建规则状态"""
        if rule_name not in self._states:
            self._states[rule_name] = AlertState()
        return self._states[rule_name]

    def _fire_alert(
        self,
        rule_name: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> Alert | None:
        """触发告警

        检查冷却时间，避免重复告警。
        """
        rule = self._rules.get(rule_name)
        if not rule:
            return None

        state = self._get_or_create_state(rule_name)
        now = time.time()

        # 冷却检查
        if now - state.last_alert_time < rule.cooldown_seconds:
            logger.debug("alert_in_cooldown", rule_name=rule_name)
            return None

        # 创建告警
        alert = Alert(
            rule_name=rule_name,
            category=rule.category,
            severity=rule.severity,
            message=message,
            details=details or {},
            timestamp=now,
        )

        # 更新状态
        state.last_alert_time = now
        state.total_alerts += 1
        state.is_alerting = True

        # 记录到历史
        self._alert_history.append(alert)
        if len(self._alert_history) > self._history_max_size:
            self._alert_history = self._alert_history[-self._history_max_size :]

        # 日志投递
        log_method = {
            AlertSeverity.INFO: logger.info,
            AlertSeverity.WARNING: logger.warning,
            AlertSeverity.CRITICAL: logger.error,
        }.get(rule.severity, logger.warning)
        log_method(
            "alert_fired",
            rule_name=rule_name,
            category=rule.category.value,
            severity=rule.severity.value,
            message=message,
            details=details,
        )

        # Webhook 投递（异步）
        if self._webhook.has_targets:
            asyncio.create_task(self._deliver_webhook(alert))

        return alert

    def _resolve_alert(self, rule_name: str) -> None:
        """恢复告警"""
        state = self._get_or_create_state(rule_name)
        if state.is_alerting:
            state.is_alerting = False
            state.consecutive_failures = 0

            # 在历史中标记最新一条同类告警为已恢复
            for alert in reversed(self._alert_history):
                if alert.rule_name == rule_name and not alert.resolved:
                    alert.resolved = True
                    alert.resolved_timestamp = time.time()
                    break

            logger.info("alert_resolved", rule_name=rule_name)

    async def _deliver_webhook(self, alert: Alert) -> None:
        """投递 webhook（内部方法）"""
        try:
            success = await self._webhook.deliver(alert)
            if success:
                logger.debug("webhook_delivered", rule_name=alert.rule_name)
            else:
                logger.warning("webhook_delivery_all_failed", rule_name=alert.rule_name)
        except Exception as e:
            logger.warning("webhook_delivery_exception", error=str(e))

    # ── 定期检查循环 ──────────────────────────

    async def start_periodic_checks(
        self,
        disk_check_path: str = "/",
        disk_check_interval: int = 300,
    ) -> None:
        """启动定期检查循环

        定期检查磁盘空间等指标。

        Args:
            disk_check_path: 磁盘检查路径
            disk_check_interval: 检查间隔（秒），默认 5 分钟
        """
        self._periodic_running = True
        logger.info("alert_periodic_checks_started", interval=disk_check_interval)

        while getattr(self, "_periodic_running", False):
            try:
                self.check_disk_space(disk_check_path)
            except Exception:
                logger.exception("periodic_disk_check_failed")

            await asyncio.sleep(disk_check_interval)

    def stop_periodic_checks(self) -> None:
        """停止定期检查循环"""
        self._periodic_running = False
        logger.info("alert_periodic_checks_stopped")
