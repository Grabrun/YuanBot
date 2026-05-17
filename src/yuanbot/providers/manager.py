"""AI 提供商管理器

管理活跃提供商选择、模型列表解析和凭据加载。
支持 v1.4 的模型列表式配置。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from yuanbot.core.interfaces import AIProviderAdapter
from yuanbot.providers.registry import ProviderRegistry

logger = structlog.get_logger(__name__)


@dataclass
class ModelInfo:
    """模型信息"""

    id: str
    type: str  # "chat" | "embedding" | "multimodal"
    max_tokens: int = 128000
    dimension: int | None = None  # 仅 embedding 模型


@dataclass
class ProviderConfig:
    """提供商配置（对应 configs/Providers/*.yaml）"""

    provider_id: str
    adapter: str  # 适配器标识
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)
    models: list[ModelInfo] = field(default_factory=list)
    default_model: str | None = None


class ProviderManager:
    """AI 提供商管理器

    职责：
    1. 管理多个 AI 提供商的配置
    2. 选择活跃提供商和默认模型
    3. 创建和缓存适配器实例
    4. 支持运行时切换提供商
    """

    def __init__(self, registry: ProviderRegistry | None = None):
        self._registry = registry or ProviderRegistry()
        self._providers: dict[str, ProviderConfig] = {}
        self._adapters: dict[str, AIProviderAdapter] = {}  # 缓存的适配器实例
        self._default_provider_id: str | None = None

    def register_provider(self, config: ProviderConfig) -> None:
        """注册提供商配置"""
        self._providers[config.provider_id] = config
        logger.info(
            "provider_configured",
            provider_id=config.provider_id,
            enabled=config.enabled,
            model_count=len(config.models),
        )

    def set_default_provider(self, provider_id: str) -> None:
        """设置默认提供商"""
        if provider_id not in self._providers:
            raise ValueError(f"Provider '{provider_id}' not registered")
        self._default_provider_id = provider_id

    def get_default_provider(self) -> ProviderConfig | None:
        """获取默认提供商配置"""
        if self._default_provider_id:
            return self._providers.get(self._default_provider_id)
        # 返回第一个启用的提供商
        for config in self._providers.values():
            if config.enabled:
                return config
        return None

    def get_provider(self, provider_id: str) -> ProviderConfig | None:
        """获取指定提供商配置"""
        return self._providers.get(provider_id)

    def get_enabled_providers(self) -> list[ProviderConfig]:
        """获取所有启用的提供商"""
        return [p for p in self._providers.values() if p.enabled]

    async def get_adapter(
        self,
        provider_id: str | None = None,
    ) -> AIProviderAdapter:
        """获取提供商的适配器实例

        Args:
            provider_id: 提供商 ID，None 则使用默认

        Returns:
            适配器实例

        Raises:
            ValueError: 如果提供商未找到或未启用
        """
        pid = provider_id or self._default_provider_id
        if not pid:
            # 尝试使用第一个启用的提供商
            for config in self._providers.values():
                if config.enabled:
                    pid = config.provider_id
                    break
            if not pid:
                raise ValueError("No enabled AI provider found")

        # 检查缓存
        if pid in self._adapters:
            return self._adapters[pid]

        config = self._providers.get(pid)
        if not config:
            raise ValueError(f"Provider '{pid}' not found")

        if not config.enabled:
            raise ValueError(f"Provider '{pid}' is disabled")

        # 创建适配器
        adapter = self._registry.create_adapter(config.adapter, config.config)
        self._adapters[pid] = adapter

        logger.info("adapter_created", provider_id=pid)
        return adapter

    def get_default_model(self, provider_id: str | None = None) -> str | None:
        """获取提供商的默认模型"""
        pid = provider_id or self._default_provider_id
        if not pid:
            return None
        config = self._providers.get(pid)
        if not config:
            return None
        return config.default_model

    def get_models(
        self,
        provider_id: str | None = None,
        model_type: str | None = None,
    ) -> list[ModelInfo]:
        """获取提供商的模型列表

        Args:
            provider_id: 提供商 ID
            model_type: 模型类型过滤（"chat" | "embedding"）

        Returns:
            模型信息列表
        """
        pid = provider_id or self._default_provider_id
        if not pid:
            return []
        config = self._providers.get(pid)
        if not config:
            return []
        if model_type:
            return [m for m in config.models if m.type == model_type]
        return config.models

    def get_embedding_model(self, provider_id: str | None = None) -> ModelInfo | None:
        """获取提供商的嵌入模型"""
        models = self.get_models(provider_id, model_type="embedding")
        return models[0] if models else None

    async def close_all(self) -> None:
        """关闭所有适配器"""
        for pid, adapter in self._adapters.items():
            try:
                if hasattr(adapter, "close"):
                    await adapter.close()
            except Exception as e:
                logger.error("adapter_close_error", provider_id=pid, error=str(e))
        self._adapters.clear()
