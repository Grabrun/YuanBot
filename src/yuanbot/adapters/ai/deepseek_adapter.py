"""DeepSeek AI 提供商适配器 (v2.0 - 已废弃)

.. deprecated::
    DeepSeekAdapter 已废弃。DeepSeek API 完全兼容 OpenAI 格式，
    请改用 OpenAIAdapter + 不同的 base_url 配置。

    迁移方式：
    - Provider YAML 中使用 adapter: openai-adapter
    - config.base_url: https://api.deepseek.com/v1

    此模块保留仅为向后兼容，内部委托给 OpenAIAdapter。
"""

from __future__ import annotations

import warnings
from typing import Any

from yuanbot.adapters.ai.openai_adapter import OpenAIAdapter


class DeepSeekAdapter(OpenAIAdapter):
    """DeepSeek 适配器 (已废弃，委托给 OpenAIAdapter)

    .. deprecated::
        请使用 openai-adapter + base_url: https://api.deepseek.com/v1
    """

    def __init__(self, config: dict[str, Any] | None = None):
        warnings.warn(
            "DeepSeekAdapter is deprecated. "
            "Use OpenAIAdapter with base_url='https://api.deepseek.com/v1' instead. "
            "In Provider YAML, set adapter: openai-adapter.",
            DeprecationWarning,
            stacklevel=2,
        )
        # 确保 base_url 指向 DeepSeek
        if config and "base_url" not in config:
            config = {**config, "base_url": "https://api.deepseek.com/v1"}
        super().__init__(config)

    @property
    def provider_id(self) -> str:
        return self._get_config("provider_id", "deepseek")
