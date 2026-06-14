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
        manager.register_provider(
            ProviderConfig(provider_id="openai", adapter="openai", enabled=True)
        )
        manager.register_provider(
            ProviderConfig(provider_id="anthropic", adapter="anthropic", enabled=False)
        )
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


class TestProviderManagerV2:
    """v2.0 Provider 管理器测试：YAML 加载与适配器复用"""

    def test_load_providers_from_yaml(self, tmp_path):
        """从 YAML 文件加载 Provider 配置"""
        providers_dir = tmp_path / "Providers"
        providers_dir.mkdir()
        (providers_dir / "openai.yaml").write_text(
            """
provider_id: openai
name: OpenAI
adapter: openai-adapter
enabled: true
config:
  api_key: test-key
  base_url: https://api.openai.com/v1
  models:
    - id: gpt-4o
      type: chat
      max_tokens: 128000
    - id: text-embedding-3-small
      type: embedding
      dimension: 1536
  default: gpt-4o
  embedding_model: text-embedding-3-small
"""
        )

        manager = ProviderManager(config_dir=tmp_path)
        manager.load_providers()

        provider = manager.get_provider("openai")
        assert provider is not None
        assert provider.name == "OpenAI"
        assert provider.adapter == "openai-adapter"
        assert provider.enabled is True
        assert provider.default_model == "gpt-4o"
        assert provider.embedding_model == "text-embedding-3-small"
        assert len(provider.models) == 2

    def test_load_providers_disabled(self, tmp_path):
        """禁用的 Provider 也被加载但标记为禁用"""
        providers_dir = tmp_path / "Providers"
        providers_dir.mkdir()
        (providers_dir / "deepseek.yaml").write_text(
            """
provider_id: deepseek
name: DeepSeek
adapter: openai-adapter
enabled: false
config:
  api_key: test-key
  base_url: https://api.deepseek.com/v1
  models:
    - id: deepseek-chat
      type: chat
  default: deepseek-chat
"""
        )

        manager = ProviderManager(config_dir=tmp_path)
        manager.load_providers()

        provider = manager.get_provider("deepseek")
        assert provider is not None
        assert provider.enabled is False

    def test_load_providers_env_substitution(self, tmp_path, monkeypatch):
        """YAML 中的环境变量应被替换"""
        monkeypatch.setenv("TEST_API_KEY", "sk-real-key")
        providers_dir = tmp_path / "Providers"
        providers_dir.mkdir()
        (providers_dir / "openai.yaml").write_text(
            """
provider_id: openai
adapter: openai-adapter
config:
  api_key: "${TEST_API_KEY}"
  base_url: https://api.openai.com/v1
  default: gpt-4o
"""
        )

        manager = ProviderManager(config_dir=tmp_path)
        manager.load_providers()

        provider = manager.get_provider("openai")
        assert provider is not None
        assert provider.config["api_key"] == "sk-real-key"

    @pytest.mark.asyncio
    async def test_adapter_reuse_same_class(self, tmp_path):
        """同一个适配器类可服务不同的 Provider"""
        providers_dir = tmp_path / "Providers"
        providers_dir.mkdir()
        (providers_dir / "openai.yaml").write_text(
            """
provider_id: openai
adapter: openai-adapter
config:
  api_key: key1
  base_url: https://api.openai.com/v1
  default: gpt-4o
"""
        )
        (providers_dir / "deepseek.yaml").write_text(
            """
provider_id: deepseek
adapter: openai-adapter
config:
  api_key: key2
  base_url: https://api.deepseek.com/v1
  default: deepseek-chat
"""
        )

        manager = ProviderManager(config_dir=tmp_path)
        manager.load_providers()

        adapter1 = await manager.get_adapter("openai")
        adapter2 = await manager.get_adapter("deepseek")

        # 两者都是 OpenAIAdapter 实例
        assert type(adapter1) is type(adapter2)
        # 但 provider_id 不同
        assert adapter1.provider_id == "openai"
        assert adapter2.provider_id == "deepseek"

    @pytest.mark.asyncio
    async def test_adapter_model_override(self):
        """适配器支持 model 参数覆盖默认模型"""
        registry = ProviderRegistry()
        adapter = registry.create_adapter(
            "openai-adapter",
            {"api_key": "test-key", "base_url": "https://api.openai.com/v1", "default": "gpt-4o"},
        )
        # 默认模型应为配置中的值
        assert adapter.provider_id == "openai"

    def test_set_embedding_provider(self, tmp_path):
        """可设置嵌入专用提供商"""
        providers_dir = tmp_path / "Providers"
        providers_dir.mkdir()
        (providers_dir / "openai.yaml").write_text(
            """
provider_id: openai
adapter: openai-adapter
config:
  api_key: test
  default: gpt-4o
  models:
    - id: gpt-4o
      type: chat
    - id: text-embedding-3-small
      type: embedding
      dimension: 1536
  embedding_model: text-embedding-3-small
"""
        )

        manager = ProviderManager(config_dir=tmp_path)
        manager.load_providers()
        manager.set_default_provider("openai")
        manager.set_embedding_provider("openai")

        emb_model = manager.get_embedding_model()
        assert emb_model is not None
        assert emb_model.id == "text-embedding-3-small"

    def test_load_multiple_providers(self, tmp_path):
        """加载多个 Provider 配置"""
        providers_dir = tmp_path / "Providers"
        providers_dir.mkdir()

        for pid, url in [
            ("openai", "https://api.openai.com/v1"),
            ("deepseek", "https://api.deepseek.com/v1"),
            ("glm", "https://open.bigmodel.cn/api/paas/v4"),
            ("qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        ]:
            (providers_dir / f"{pid}.yaml").write_text(
                f"""
provider_id: {pid}
adapter: openai-adapter
config:
  api_key: test
  base_url: {url}
  default: test-model
"""
            )

        manager = ProviderManager(config_dir=tmp_path)
        manager.load_providers()

        enabled = manager.get_enabled_providers()
        assert len(enabled) == 4
        provider_ids = [p.provider_id for p in enabled]
        assert "openai" in provider_ids
        assert "deepseek" in provider_ids
        assert "glm" in provider_ids
        assert "qwen" in provider_ids


class TestProviderManagerResolveModel:
    """ProviderManager.resolve_model 测试"""

    def test_resolve_none_returns_default(self):
        """None 返回默认提供商的默认模型"""
        manager = ProviderManager()
        manager.register_provider(
            ProviderConfig(
                provider_id="openai",
                adapter="openai",
                default_model="gpt-4o",
            )
        )
        manager.set_default_provider("openai")
        pid, model = manager.resolve_model(None)
        assert pid == "openai"
        assert model == "gpt-4o"

    def test_resolve_none_falls_back_to_first_chat_model(self):
        """没有 default_model 时使用第一个 chat 模型"""
        manager = ProviderManager()
        manager.register_provider(
            ProviderConfig(
                provider_id="openai",
                adapter="openai",
                models=[
                    ModelInfo(id="gpt-4o-mini", type="chat"),
                    ModelInfo(id="gpt-4o", type="chat"),
                ],
            )
        )
        manager.set_default_provider("openai")
        pid, model = manager.resolve_model(None)
        assert pid == "openai"
        assert model == "gpt-4o-mini"

    def test_resolve_bare_model_uses_default_provider(self):
        """不带前缀的模型名使用默认提供商"""
        manager = ProviderManager()
        manager.register_provider(
            ProviderConfig(
                provider_id="openai",
                adapter="openai",
                default_model="gpt-4o",
            )
        )
        manager.set_default_provider("openai")
        pid, model = manager.resolve_model("gpt-4o-mini")
        assert pid == "openai"
        assert model == "gpt-4o-mini"

    def test_resolve_slash_format(self):
        """provider/model 格式解析提供商和模型"""
        manager = ProviderManager()
        manager.register_provider(
            ProviderConfig(
                provider_id="openai",
                adapter="openai",
                default_model="gpt-4o",
            )
        )
        manager.register_provider(
            ProviderConfig(
                provider_id="deepseek",
                adapter="openai",
                default_model="deepseek-chat",
            )
        )
        pid, model = manager.resolve_model("deepseek/deepseek-chat")
        assert pid == "deepseek"
        assert model == "deepseek-chat"

    def test_resolve_slash_unknown_provider_raises(self):
        """provider/model 格式中 provider 不存在时抛出错误"""
        manager = ProviderManager()
        manager.register_provider(
            ProviderConfig(provider_id="openai", adapter="openai")
        )
        with pytest.raises(ValueError, match="Provider 'unknown' not found"):
            manager.resolve_model("unknown/model")

    def test_resolve_no_default_raises(self):
        """没有默认提供商时抛出错误"""
        manager = ProviderManager()
        with pytest.raises(ValueError, match="No default AI provider"):
            manager.resolve_model(None)

    def test_resolve_bare_model_no_default_provider(self):
        """没有默认提供商但传了裸模型名时抛出错误"""
        manager = ProviderManager()
        with pytest.raises(ValueError, match="Cannot resolve model"):
            manager.resolve_model("gpt-4o")


class TestProviderManagerListProviders:
    """ProviderManager.list_providers 测试"""

    def test_list_empty(self):
        manager = ProviderManager()
        result = manager.list_providers()
        assert result == []

    def test_list_returns_all_info(self):
        manager = ProviderManager()
        manager.register_provider(
            ProviderConfig(
                provider_id="openai",
                adapter="openai-adapter",
                name="OpenAI",
                enabled=True,
                default_model="gpt-4o",
                models=[ModelInfo(id="gpt-4o", type="chat")],
            )
        )
        manager.set_default_provider("openai")

        result = manager.list_providers()
        assert len(result) == 1
        p = result[0]
        assert p["provider_id"] == "openai"
        assert p["name"] == "OpenAI"
        assert p["adapter"] == "openai-adapter"
        assert p["enabled"] is True
        assert p["default_model"] == "gpt-4o"
        assert p["model_count"] == 1
        assert p["is_default"] is True
        assert p["is_embedding"] is False

    def test_list_marks_embedding_provider(self):
        manager = ProviderManager()
        manager.register_provider(
            ProviderConfig(provider_id="openai", adapter="openai")
        )
        manager.register_provider(
            ProviderConfig(provider_id="emb", adapter="openai")
        )
        manager.set_default_provider("openai")
        manager.set_embedding_provider("emb")

        result = manager.list_providers()
        by_id = {p["provider_id"]: p for p in result}
        assert by_id["openai"]["is_default"] is True
        assert by_id["openai"]["is_embedding"] is False
        assert by_id["emb"]["is_default"] is False
        assert by_id["emb"]["is_embedding"] is True


class TestProviderConfigValidation:
    """Provider 配置验证测试"""

    def test_valid_config_passes(self):
        manager = ProviderManager()
        errors = manager.validate_provider_config({
            "provider_id": "openai",
            "adapter": "openai-adapter",
            "config": {
                "base_url": "https://api.openai.com/v1",
                "api_key": "test",
                "models": [{"id": "gpt-4o", "type": "chat"}],
                "default": "gpt-4o",
            },
        })
        assert errors == []

    def test_missing_provider_id(self):
        manager = ProviderManager()
        errors = manager.validate_provider_config({
            "adapter": "openai-adapter",
            "config": {"base_url": "https://api.openai.com/v1", "models": []},
        })
        assert any("provider_id" in e for e in errors)

    def test_missing_adapter(self):
        manager = ProviderManager()
        errors = manager.validate_provider_config({
            "provider_id": "test",
            "config": {"base_url": "https://api.openai.com/v1", "models": []},
        })
        assert any("adapter" in e for e in errors)

    def test_missing_config(self):
        manager = ProviderManager()
        errors = manager.validate_provider_config({
            "provider_id": "test",
            "adapter": "openai-adapter",
        })
        assert any("config" in e for e in errors)

    def test_empty_base_url(self):
        manager = ProviderManager()
        errors = manager.validate_provider_config({
            "provider_id": "test",
            "adapter": "openai-adapter",
            "config": {
                "base_url": "",
                "models": [{"id": "m1", "type": "chat"}],
            },
        })
        assert any("base_url" in e for e in errors)

    def test_invalid_base_url(self):
        manager = ProviderManager()
        errors = manager.validate_provider_config({
            "provider_id": "test",
            "adapter": "openai-adapter",
            "config": {
                "base_url": "ftp://invalid",
                "models": [{"id": "m1", "type": "chat"}],
            },
        })
        assert any("base_url" in e for e in errors)

    def test_empty_models(self):
        manager = ProviderManager()
        errors = manager.validate_provider_config({
            "provider_id": "test",
            "adapter": "openai-adapter",
            "config": {
                "base_url": "https://api.openai.com/v1",
                "models": [],
            },
        })
        assert any("models" in e for e in errors)

    def test_model_missing_id(self):
        manager = ProviderManager()
        errors = manager.validate_provider_config({
            "provider_id": "test",
            "adapter": "openai-adapter",
            "config": {
                "base_url": "https://api.openai.com/v1",
                "models": [{"type": "chat"}],
            },
        })
        assert any("id" in e for e in errors)

    def test_model_invalid_type(self):
        manager = ProviderManager()
        errors = manager.validate_provider_config({
            "provider_id": "test",
            "adapter": "openai-adapter",
            "config": {
                "base_url": "https://api.openai.com/v1",
                "models": [{"id": "m1", "type": "invalid"}],
            },
        })
        assert any("type" in e for e in errors)

    def test_default_not_in_models(self):
        manager = ProviderManager()
        errors = manager.validate_provider_config({
            "provider_id": "test",
            "adapter": "openai-adapter",
            "config": {
                "base_url": "https://api.openai.com/v1",
                "models": [{"id": "m1", "type": "chat"}],
                "default": "nonexistent-model",
            },
        })
        assert any("default" in e for e in errors)


class TestDeepSeekAdapterDeprecation:
    """DeepSeekAdapter 废弃警告测试"""

    def test_deprecation_warning(self):
        """DeepSeekAdapter 应发出废弃警告"""
        import warnings

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            from yuanbot.adapters.ai.deepseek_adapter import DeepSeekAdapter

            DeepSeekAdapter({"api_key": "test"})
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "deprecated" in str(w[0].message).lower()

    def test_delegates_to_openai_adapter(self):
        """DeepSeekAdapter 应委托给 OpenAIAdapter"""
        import warnings

        from yuanbot.adapters.ai.deepseek_adapter import DeepSeekAdapter
        from yuanbot.adapters.ai.openai_adapter import OpenAIAdapter

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            adapter = DeepSeekAdapter({"api_key": "test"})

        assert isinstance(adapter, OpenAIAdapter)

    def test_default_base_url_is_deepseek(self):
        """DeepSeekAdapter 默认 base_url 应指向 DeepSeek"""
        import warnings

        from yuanbot.adapters.ai.deepseek_adapter import DeepSeekAdapter

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            adapter = DeepSeekAdapter({"api_key": "test"})

        assert "deepseek" in adapter._base_url


class TestBaseAIProviderSanitize:
    """日志脱敏测试"""

    def test_sanitize_api_key(self):
        from yuanbot.adapters.ai.base import sanitize_log_data

        data = {"api_key": "sk-1234567890abcdef", "base_url": "https://api.openai.com"}
        result = sanitize_log_data(data)
        assert result["api_key"] == "****"
        assert result["base_url"] == "https://api.openai.com"

    def test_sanitize_nested(self):
        from yuanbot.adapters.ai.base import sanitize_log_data

        data = {"config": {"api_key": "secret", "base_url": "url"}}
        result = sanitize_log_data(data)
        assert result["config"]["api_key"] == "****"
        assert result["config"]["base_url"] == "url"

    def test_sanitize_various_key_names(self):
        from yuanbot.adapters.ai.base import sanitize_log_data

        for key in ["api_key", "api-key", "API_KEY", "token", "password", "secret"]:
            result = sanitize_log_data({key: "sensitive"})
            assert result[key] == "****", f"Failed for key: {key}"

    def test_non_sensitive_keys_preserved(self):
        from yuanbot.adapters.ai.base import sanitize_log_data

        data = {"base_url": "url", "model": "gpt-4o", "timeout": 60}
        result = sanitize_log_data(data)
        assert result == data
