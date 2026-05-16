"""AI 提供商适配器基类"""

from __future__ import annotations

import os
from abc import ABC
from typing import Any

import structlog

from yuanbot.core.interfaces import AIProviderAdapter

logger = structlog.get_logger(__name__)


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
                param = key[len(prefix):].lower()
                self._config[param] = value
                logger.debug("config_loaded", provider=self.provider_id, param=param)

    def _get_config(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        return self._config.get(key, default)

    @property
    def max_context_length(self) -> int:
        """默认最大上下文长度"""
        return 128000
