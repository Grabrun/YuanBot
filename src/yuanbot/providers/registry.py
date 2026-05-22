"""AI 提供商适配器注册表

管理所有 AI 提供商适配器的注册和发现。
v2.0: 适配器通过名称引用（如 "openai-adapter", "anthropic-adapter"），
ProviderManager 根据配置中的 adapter 字段查找并实例化对应适配器。
"""

from __future__ import annotations

from typing import Any

import structlog

from yuanbot.core.interfaces import AIProviderAdapter

logger = structlog.get_logger(__name__)

# 内置适配器映射
# 支持两种命名风格：短名（openai）和规范名（openai-adapter）
_BUILTIN_ADAPTERS: dict[str, str] = {
    # OpenAI 兼容适配器（可服务所有 OpenAI 兼容 API）
    "openai": "yuanbot.adapters.ai.openai_adapter.OpenAIAdapter",
    "openai-adapter": "yuanbot.adapters.ai.openai_adapter.OpenAIAdapter",
    # Anthropic 适配器
    "anthropic": "yuanbot.adapters.ai.anthropic_adapter.AnthropicAdapter",
    "anthropic-adapter": "yuanbot.adapters.ai.anthropic_adapter.AnthropicAdapter",
    "claude-adapter": "yuanbot.adapters.ai.anthropic_adapter.AnthropicAdapter",
    # 以下为向后兼容的旧名称，实际类仍独立存在
    # 新的 Provider 配置应使用 openai-adapter + 不同 base_url
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

        # OpenAI 兼容适配器（主适配器，可服务多家提供商）
        self._adapter_classes["openai"] = OpenAIAdapter
        self._adapter_classes["openai-adapter"] = OpenAIAdapter

        # Anthropic 适配器
        self._adapter_classes["anthropic"] = AnthropicAdapter
        self._adapter_classes["anthropic-adapter"] = AnthropicAdapter
        self._adapter_classes["claude-adapter"] = AnthropicAdapter

        # 向后兼容：旧的独立适配器类仍然可用
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
        provider_id: str | None = None,
    ) -> AIProviderAdapter:
        """创建适配器实例

        Args:
            adapter_id: 适配器标识（如 'openai-adapter', 'anthropic-adapter'）
            config: 适配器配置（来自 Provider YAML 的 config 字段）
            provider_id: 提供商 ID，传递给适配器以区分不同 Provider

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
        # 将 provider_id 注入配置，使适配器知道自己属于哪个 Provider
        adapter_config = {**config}
        if provider_id:
            adapter_config["provider_id"] = provider_id
        return adapter_class(adapter_config)

    def get_registered_ids(self) -> list[str]:
        """获取所有已注册的适配器 ID"""
        return list(self._adapter_classes.keys())

    def is_registered(self, adapter_id: str) -> bool:
        """检查适配器是否已注册"""
        return adapter_id in self._adapter_classes
