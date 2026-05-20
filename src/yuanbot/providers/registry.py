"""AI 提供商适配器注册表

管理所有 AI 提供商适配器的注册和发现。
"""

from __future__ import annotations

from typing import Any

import structlog

from yuanbot.core.interfaces import AIProviderAdapter

logger = structlog.get_logger(__name__)

# 内置适配器映射
_BUILTIN_ADAPTERS: dict[str, str] = {
    "openai": "yuanbot.adapters.ai.openai_adapter.OpenAIAdapter",
    "openai-adapter": "yuanbot.adapters.ai.openai_adapter.OpenAIAdapter",
    "anthropic": "yuanbot.adapters.ai.anthropic_adapter.AnthropicAdapter",
    "claude-adapter": "yuanbot.adapters.ai.anthropic_adapter.AnthropicAdapter",
    "deepseek": "yuanbot.adapters.ai.deepseek_adapter.DeepSeekAdapter",
    "deepseek-adapter": "yuanbot.adapters.ai.deepseek_adapter.DeepSeekAdapter",
    "ollama": "yuanbot.adapters.ai.ollama_adapter.OllamaAdapter",
    "ollama-adapter": "yuanbot.adapters.ai.ollama_adapter.OllamaAdapter",
}


class ProviderRegistry:
    """AI 提供商适配器注册表

    职责：
    1. 注册和发现 AI 提供商适配器类
    2. 根据配置创建适配器实例
    3. 支持自定义适配器扩展
    """

    def __init__(self) -> None:
        self._adapter_classes: dict[str, type[AIProviderAdapter]] = {}
        self._register_builtin()

    def _register_builtin(self) -> None:
        """注册内置适配器"""
        # 延迟导入，避免循环依赖
        from yuanbot.adapters.ai.anthropic_adapter import AnthropicAdapter
        from yuanbot.adapters.ai.deepseek_adapter import DeepSeekAdapter
        from yuanbot.adapters.ai.ollama_adapter import OllamaAdapter
        from yuanbot.adapters.ai.openai_adapter import OpenAIAdapter

        self._adapter_classes["openai"] = OpenAIAdapter
        self._adapter_classes["openai-adapter"] = OpenAIAdapter
        self._adapter_classes["anthropic"] = AnthropicAdapter
        self._adapter_classes["claude-adapter"] = AnthropicAdapter
        self._adapter_classes["deepseek"] = DeepSeekAdapter
        self._adapter_classes["deepseek-adapter"] = DeepSeekAdapter
        self._adapter_classes["ollama"] = OllamaAdapter
        self._adapter_classes["ollama-adapter"] = OllamaAdapter

    def register(self, adapter_id: str, adapter_class: type[AIProviderAdapter]) -> None:
        """注册自定义适配器"""
        self._adapter_classes[adapter_id] = adapter_class
        logger.info("provider_registered", adapter_id=adapter_id)

    def create_adapter(
        self,
        adapter_id: str,
        config: dict[str, Any],
    ) -> AIProviderAdapter:
        """创建适配器实例

        Args:
            adapter_id: 适配器标识（如 'openai', 'anthropic'）
            config: 适配器配置

        Returns:
            适配器实例

        Raises:
            ValueError: 如果适配器未注册
        """
        adapter_class = self._adapter_classes.get(adapter_id)
        if adapter_class is None:
            raise ValueError(
                f"Unknown AI provider adapter: {adapter_id}. "
                f"Available: {list(self._adapter_classes.keys())}"
            )
        return adapter_class(config)

    def get_registered_ids(self) -> list[str]:
        """获取所有已注册的适配器 ID"""
        return list(self._adapter_classes.keys())

    def is_registered(self, adapter_id: str) -> bool:
        """检查适配器是否已注册"""
        return adapter_id in self._adapter_classes
