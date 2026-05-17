"""测试 AI 提供商适配系统"""

from __future__ import annotations

import pytest

from yuanbot.providers.manager import ModelInfo, ProviderConfig, ProviderManager
from yuanbot.providers.registry import ProviderRegistry


class TestProviderRegistry:
    """提供商注册表测试"""

    def test_builtin_adapters_registered(self):
        registry = ProviderRegistry()
        assert registry.is_registered("openai")
        assert registry.is_registered("anthropic")
        assert registry.is_registered("openai-adapter")
        assert registry.is_registered("claude-adapter")

    def test_get_registered_ids(self):
        registry = ProviderRegistry()
        ids = registry.get_registered_ids()
        assert "openai" in ids
        assert "anthropic" in ids

    def test_create_openai_adapter(self):
        registry = ProviderRegistry()
        adapter = registry.create_adapter("openai", {"api_key": "test-key"})
        assert adapter.provider_id == "openai"

    def test_create_anthropic_adapter(self):
        registry = ProviderRegistry()
        adapter = registry.create_adapter("anthropic", {"api_key": "test-key"})
        assert adapter.provider_id == "anthropic"

    def test_create_unknown_adapter_raises(self):
        registry = ProviderRegistry()
        with pytest.raises(ValueError, match="Unknown AI provider adapter"):
            registry.create_adapter("nonexistent", {})

    def test_register_custom_adapter(self):
        registry = ProviderRegistry()

        class CustomAdapter:
            pass

        registry.register("custom", CustomAdapter)
        assert registry.is_registered("custom")


class TestProviderManager:
    """提供商管理器测试"""

    def test_register_provider(self):
        manager = ProviderManager()
        config = ProviderConfig(
            provider_id="openai",
            adapter="openai",
            models=[
                ModelInfo(id="gpt-4o", type="chat", max_tokens=128000),
            ],
            default_model="gpt-4o",
        )
        manager.register_provider(config)
        assert manager.get_provider("openai") is not None

    def test_set_default_provider(self):
        manager = ProviderManager()
        config = ProviderConfig(
            provider_id="openai",
            adapter="openai",
            default_model="gpt-4o",
        )
        manager.register_provider(config)
        manager.set_default_provider("openai")
        default = manager.get_default_provider()
        assert default is not None
        assert default.provider_id == "openai"

    def test_set_default_provider_not_found(self):
        manager = ProviderManager()
        with pytest.raises(ValueError, match="not registered"):
            manager.set_default_provider("nonexistent")

    def test_get_default_model(self):
        manager = ProviderManager()
        config = ProviderConfig(
            provider_id="openai",
            adapter="openai",
            default_model="gpt-4o",
        )
        manager.register_provider(config)
        model = manager.get_default_model("openai")
        assert model == "gpt-4o"

    def test_get_models_by_type(self):
        manager = ProviderManager()
        config = ProviderConfig(
            provider_id="openai",
            adapter="openai",
            models=[
                ModelInfo(id="gpt-4o", type="chat"),
                ModelInfo(id="text-embedding-3-small", type="embedding", dimension=1536),
            ],
            default_model="gpt-4o",
        )
        manager.register_provider(config)
        chat_models = manager.get_models("openai", model_type="chat")
        assert len(chat_models) == 1
        assert chat_models[0].id == "gpt-4o"

    def test_get_embedding_model(self):
        manager = ProviderManager()
        config = ProviderConfig(
            provider_id="openai",
            adapter="openai",
            models=[
                ModelInfo(id="gpt-4o", type="chat"),
                ModelInfo(id="text-embedding-3-small", type="embedding", dimension=1536),
            ],
            default_model="gpt-4o",
        )
        manager.register_provider(config)
        emb = manager.get_embedding_model("openai")
        assert emb is not None
        assert emb.id == "text-embedding-3-small"

    def test_get_enabled_providers(self):
        manager = ProviderManager()
        manager.register_provider(ProviderConfig(
            provider_id="openai", adapter="openai", enabled=True
        ))
        manager.register_provider(ProviderConfig(
            provider_id="anthropic", adapter="anthropic", enabled=False
        ))
        enabled = manager.get_enabled_providers()
        assert len(enabled) == 1
        assert enabled[0].provider_id == "openai"

    @pytest.mark.asyncio
    async def test_get_adapter(self):
        manager = ProviderManager()
        config = ProviderConfig(
            provider_id="openai",
            adapter="openai",
            config={"api_key": "test-key"},
            default_model="gpt-4o",
        )
        manager.register_provider(config)
        adapter = await manager.get_adapter("openai")
        assert adapter.provider_id == "openai"

    @pytest.mark.asyncio
    async def test_get_adapter_not_found(self):
        manager = ProviderManager()
        with pytest.raises(ValueError, match="No enabled AI provider"):
            await manager.get_adapter()

    @pytest.mark.asyncio
    async def test_get_adapter_disabled(self):
        manager = ProviderManager()
        config = ProviderConfig(
            provider_id="openai",
            adapter="openai",
            enabled=False,
        )
        manager.register_provider(config)
        with pytest.raises(ValueError, match="disabled"):
            await manager.get_adapter("openai")
