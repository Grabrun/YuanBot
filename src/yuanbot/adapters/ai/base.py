"""AI 提供商适配器基类"""

from __future__ import annotations

import os
import re
from abc import ABC
from typing import Any

import structlog

from yuanbot.core.interfaces import AIProviderAdapter
from yuanbot.core.types import ValidationResult

logger = structlog.get_logger(__name__)

# 需要脱敏的配置键名模式
_SENSITIVE_KEYS = frozenset({"api_key", "api_secret", "secret", "token", "password"})
_SENSITIVE_PATTERN = re.compile(
    r"(?i)(api[_-]?key|api[_-]?secret|secret|token|password|authorization)",
)


def sanitize_log_data(data: dict[str, Any]) -> dict[str, Any]:
    """脱敏日志数据，将敏感字段替换为 ****"""
    sanitized = {}
    for key, value in data.items():
        if isinstance(key, str) and (
            _SENSITIVE_PATTERN.search(key) or key.lower() in _SENSITIVE_KEYS
        ):
            if isinstance(value, str) and len(value) > 0:
                sanitized[key] = "****"
            else:
                sanitized[key] = value
        elif isinstance(value, dict):
            sanitized[key] = sanitize_log_data(value)
        else:
            sanitized[key] = value
    return sanitized


class BaseAIProvider(AIProviderAdapter, ABC):
    """AI 提供商适配器基类

    提供通用的配置加载和环境变量隔离机制。
    命名规范：YUAN_AI_{PROVIDER_ID}_{PARAM}
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self._config = config or {}
        self._load_config_from_env()

    def _load_config_from_env(self) -> None:
        """从环境变量加载配置"""
        prefix = f"YUAN_AI_{self.provider_id.upper()}_"
        for key, value in os.environ.items():
            if key.startswith(prefix):
                param = key[len(prefix) :].lower()
                self._config[param] = value
                logger.debug("config_loaded", provider=self.provider_id, param=param)

    def _get_config(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        return self._config.get(key, default)

    @property
    def max_context_length(self) -> int:
        """默认最大上下文长度"""
        return 128000

    def validate_config(self) -> ValidationResult:
        """验证提供商基础配置

        子类应重写此方法以检查各自特有配置。
        """
        return ValidationResult(valid=True)

    def get_safe_config_summary(self) -> dict[str, Any]:
        """返回脱敏后的配置摘要（用于日志和诊断）"""
        return sanitize_log_data(self._config)
