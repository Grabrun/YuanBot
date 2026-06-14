"""YuanBot 配置管理测试"""

from __future__ import annotations

from pathlib import Path

import yaml

from yuanbot.config import (
    AIProviderConfig,
    BotConfig,
    ChannelConfigEntry,
    ConfigLoader,
    DatabaseConfig,
    MemorySystemConfig,
    ModelEntry,
    OrchestratorConfig,
    ProviderConfigEntry,
    YuanBotConfig,
    _deep_merge,
    _load_env_overrides,
    _substitute_env_vars,
    load_config,
)


class TestYuanBotConfig:
    """主配置测试"""

    def test_default_config(self):
        config = YuanBotConfig()
        assert config.app_name == "YuanBot"
        assert config.version == "1.0.0"
        assert config.debug is False
        assert config.log_level == "INFO"
        assert config.persona_id == "default"

    def test_ai_provider_defaults(self):
        config = YuanBotConfig()
        assert config.ai_provider.provider_id == "openai"
        assert config.ai_provider.api_key is None
        assert config.ai_provider.default_model == "gpt-5.4"

    def test_memory_config_defaults(self):
        config = YuanBotConfig()
        assert config.memory.vector_db == "qdrant"
        assert config.memory.max_working_memory_turns == 20
        assert config.memory.episodic_memory_max_age_days == 90
        assert config.memory.forget_curve_half_life_days == 14

    def test_proactive_config_defaults(self):
        config = YuanBotConfig()
        assert config.proactive.enabled is True
        assert config.proactive.quiet_hours_start == 23
        assert config.proactive.quiet_hours_end == 8
        assert config.proactive.max_per_day == 5

    def test_custom_config(self):
        config = YuanBotConfig(
            app_name="TestBot",
            debug=True,
            ai_provider=AIProviderConfig(provider_id="anthropic", default_model="claude-sonnet"),
        )
        assert config.app_name == "TestBot"
        assert config.debug is True
        assert config.ai_provider.provider_id == "anthropic"

    def test_channels_default_empty(self):
        config = YuanBotConfig()
        assert config.channels == []


class TestLoadConfig:
    """配置加载测试"""

    def test_load_from_yaml(self, tmp_path):
        yaml_content = {
            "app_name": "TestBot",
            "debug": True,
            "ai_provider": {
                "provider_id": "anthropic",
                "default_model": "claude-sonnet",
            },
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(yaml_content))

        config = load_config(config_file)
        assert config.app_name == "TestBot"
        assert config.debug is True
        assert config.ai_provider.provider_id == "anthropic"

    def test_load_nonexistent_file(self):
        """加载不存在的配置文件应返回默认配置"""
        config = load_config("/nonexistent/path/config.yaml")
        assert config.app_name == "YuanBot"

    def test_load_empty_yaml(self, tmp_path):
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")

        config = load_config(config_file)
        assert config.app_name == "YuanBot"

    def test_env_override_debug(self, monkeypatch):
        monkeypatch.setenv("YUAN_DEBUG", "true")
        overrides = _load_env_overrides()
        assert overrides["debug"] is True

    def test_env_override_debug_false(self, monkeypatch):
        monkeypatch.setenv("YUAN_DEBUG", "false")
        overrides = _load_env_overrides()
        assert overrides["debug"] is False

    def test_env_override_provider(self, monkeypatch):
        monkeypatch.setenv("YUAN_AI_PROVIDER", "anthropic")
        overrides = _load_env_overrides()
        assert overrides["ai_provider"]["provider_id"] == "anthropic"

    def test_env_override_api_key(self, monkeypatch):
        monkeypatch.setenv("YUAN_AI_API_KEY", "sk-test-123")
        overrides = _load_env_overrides()
        assert overrides["ai_provider"]["api_key"] == "sk-test-123"

    def test_env_override_base_url(self, monkeypatch):
        monkeypatch.setenv("YUAN_AI_BASE_URL", "https://custom.api.com/v1")
        overrides = _load_env_overrides()
        assert overrides["ai_provider"]["base_url"] == "https://custom.api.com/v1"

    def test_env_override_model(self, monkeypatch):
        monkeypatch.setenv("YUAN_AI_MODEL", "gpt-5.4-mini")
        overrides = _load_env_overrides()
        assert overrides["ai_provider"]["default_model"] == "gpt-5.4-mini"

    def test_env_override_log_level(self, monkeypatch):
        monkeypatch.setenv("YUAN_LOG_LEVEL", "debug")
        overrides = _load_env_overrides()
        assert overrides["log_level"] == "DEBUG"

    def test_load_from_directory(self, tmp_path):
        """从 configs/ 目录加载配置"""
        configs_dir = tmp_path / "configs"
        configs_dir.mkdir()

        # bot.yaml
        bot_config = {
            "app_name": "DirBot",
            "version": "2.0.0",
            "debug": True,
            "ai": {"default_provider": "openai", "default_model": "gpt-5.4"},
            "persona": {"id": "custom"},
            "proactive": {"enabled": False},
        }
        (configs_dir / "bot.yaml").write_text(yaml.dump(bot_config))

        config = load_config(configs_dir)
        assert config.app_name == "DirBot"
        assert config.version == "2.0.0"
        assert config.debug is True
        assert config.persona_id == "custom"
        assert config.proactive.enabled is False


class TestDeepMerge:
    """深度合并测试"""

    def test_simple_merge(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        base = {"a": {"x": 1, "y": 2}, "b": 3}
        override = {"a": {"y": 10, "z": 20}}
        result = _deep_merge(base, override)
        assert result == {"a": {"x": 1, "y": 10, "z": 20}, "b": 3}

    def test_override_replaces_non_dict(self):
        base = {"a": [1, 2, 3]}
        override = {"a": [4, 5]}
        result = _deep_merge(base, override)
        assert result == {"a": [4, 5]}

    def test_empty_merge(self):
        assert _deep_merge({}, {}) == {}
        assert _deep_merge({"a": 1}, {}) == {"a": 1}
        assert _deep_merge({}, {"a": 1}) == {"a": 1}


# ---------------------------------------------------------------------------
# 新配置模型测试
# ---------------------------------------------------------------------------


class TestBotConfig:
    """BotConfig 根配置测试"""

    def test_defaults(self):
        config = BotConfig()
        assert config.app_name == "YuanBot"
        assert config.version == "1.0.0"
        assert config.debug is False
        assert config.log_level == "INFO"
        assert config.ai.default_provider == "openai"
        assert config.ai.default_model == "gpt-5.4"
        assert config.persona.id == "default"

    def test_proactive_defaults(self):
        config = BotConfig()
        assert config.proactive.enabled is True
        assert config.proactive.quiet_hours.start == 23
        assert config.proactive.quiet_hours.end == 8

    def test_orchestrator_defaults(self):
        config = BotConfig()
        assert config.orchestrator.intent_engine.enabled is True
        assert config.orchestrator.intent_engine.confidence_threshold == 0.7
        assert config.orchestrator.emotion_engine.enabled is True
        assert config.orchestrator.token_budget.max_input_tokens == 8000

    def test_custom_values(self):
        config = BotConfig(
            app_name="TestBot",
            debug=True,
            ai={"default_provider": "claude", "default_model": "claude-sonnet"},
        )
        assert config.app_name == "TestBot"
        assert config.debug is True
        assert config.ai.default_provider == "claude"


class TestDatabaseConfig:
    """DatabaseConfig 测试"""

    def test_defaults(self):
        config = DatabaseConfig()
        assert config.relational.type == "sqlite"
        assert config.relational.sqlite.path == "data/yuanbot.db"
        assert config.vector.type == "milvus_lite"
        assert config.redis.url == "redis://localhost:6379/0"
        assert config.graph.type == "kuzu"

    def test_mysql_config(self):
        config = DatabaseConfig(
            relational={"type": "mysql", "mysql": {"host": "db.example.com", "port": 3307}},
        )
        assert config.relational.type == "mysql"
        assert config.relational.mysql.host == "db.example.com"
        assert config.relational.mysql.port == 3307


class TestMemorySystemConfig:
    """MemorySystemConfig 测试"""

    def test_defaults(self):
        config = MemorySystemConfig()
        assert config.working_memory.max_turns == 20
        assert config.episodic_memory.max_age_days == 90
        assert config.forgetting_curve.half_life_days == 14
        assert config.consolidation.threshold == 3

    def test_custom_values(self):
        config = MemorySystemConfig(
            working_memory={"max_turns": 50},
            forgetting_curve={"half_life_days": 7},
        )
        assert config.working_memory.max_turns == 50
        assert config.forgetting_curve.half_life_days == 7


class TestProviderConfigEntry:
    """ProviderConfigEntry 测试"""

    def test_defaults(self):
        entry = ProviderConfigEntry(provider_id="openai")
        assert entry.provider_id == "openai"
        assert entry.enabled is True
        assert entry.adapter == ""
        assert entry.models == []

    def test_with_models(self):
        entry = ProviderConfigEntry(
            provider_id="openai",
            adapter="openai-adapter",
            config={
                "default": "gpt-5.4",
                "models": [
                    {"id": "gpt-5.4", "type": "chat", "max_tokens": 128000},
                    {"id": "gpt-5.4-mini", "type": "chat", "max_tokens": 128000},
                ],
            },
            models=[
                ModelEntry(id="gpt-5.4", type="chat", max_tokens=128000),
                ModelEntry(id="gpt-5.4-mini", type="chat", max_tokens=128000),
            ],
            default_model="gpt-5.4",
        )
        assert len(entry.models) == 2
        assert entry.models[0].id == "gpt-5.4"
        assert entry.default_model == "gpt-5.4"

    def test_embedding_model(self):
        entry = ProviderConfigEntry(
            provider_id="openai",
            models=[ModelEntry(id="text-embedding-3-small", type="embedding", dimension=1536)],
        )
        assert entry.models[0].type == "embedding"
        assert entry.models[0].dimension == 1536

    def test_from_yaml(self):
        raw = {
            "provider_id": "openai",
            "name": "OpenAI",
            "adapter": "openai-adapter",
            "enabled": True,
            "config": {
                "api_key": "test-key",
                "base_url": "https://api.openai.com/v1",
                "models": [
                    {"id": "gpt-5.4", "type": "chat", "max_tokens": 128000},
                ],
                "default": "gpt-5.4",
            },
        }
        entry = ProviderConfigEntry.from_yaml(raw)
        assert entry.provider_id == "openai"
        assert entry.adapter == "openai-adapter"
        assert entry.default_model == "gpt-5.4"
        assert len(entry.models) == 1
        assert entry.models[0].id == "gpt-5.4"


class TestChannelConfigEntry:
    """ChannelConfigEntry 测试"""

    def test_defaults(self):
        entry = ChannelConfigEntry(platform="telegram")
        assert entry.platform == "telegram"
        assert entry.enabled is True
        assert entry.config == {}

    def test_with_config(self):
        entry = ChannelConfigEntry(
            platform="telegram",
            config={"bot_token": "test-token"},
        )
        assert entry.config["bot_token"] == "test-token"


class TestOrchestratorConfig:
    """OrchestratorConfig 测试"""

    def test_defaults(self):
        config = OrchestratorConfig()
        assert config.intent_engine.enabled is True
        assert config.intent_engine.confidence_threshold == 0.7
        assert config.emotion_engine.enabled is True
        assert config.emotion_engine.decay_rate == 0.1
        assert config.token_budget.max_input_tokens == 8000
        assert config.token_budget.max_output_tokens == 2000
        assert config.token_budget.reserved_for_memory == 2000


class TestEnvVarSubstitution:
    """环境变量替换测试"""

    def test_substitute_existing_var(self, monkeypatch):
        monkeypatch.setenv("MY_SECRET", "hello123")
        result = _substitute_env_vars("${MY_SECRET}")
        assert result == "hello123"

    def test_substitute_missing_var(self):
        result = _substitute_env_vars("${NONEXISTENT_VAR_XYZ}")
        assert result == "${NONEXISTENT_VAR_XYZ}"

    def test_substitute_in_dict(self, monkeypatch):
        monkeypatch.setenv("API_KEY", "sk-test")
        data = {"api": {"key": "${API_KEY}", "url": "https://example.com"}}
        result = _substitute_env_vars(data)
        assert result["api"]["key"] == "sk-test"
        assert result["api"]["url"] == "https://example.com"

    def test_substitute_in_list(self, monkeypatch):
        monkeypatch.setenv("TOKEN", "abc")
        data = ["${TOKEN}", "plain"]
        result = _substitute_env_vars(data)
        assert result == ["abc", "plain"]

    def test_non_string_passthrough(self):
        assert _substitute_env_vars(42) == 42
        assert _substitute_env_vars(True) is True
        assert _substitute_env_vars(None) is None


class TestNewConfigLoader:
    """新 ConfigLoader 测试"""

    def test_load_bot_config(self):
        """从项目 configs/ 目录加载 bot.yaml"""
        loader = ConfigLoader(Path(__file__).parent.parent / "configs")
        config = loader.load_bot_config()
        assert isinstance(config, BotConfig)
        assert config.app_name == "YuanBot"
        assert config.ai.default_provider == "openai"

    def test_load_database_config(self):
        loader = ConfigLoader(Path(__file__).parent.parent / "configs")
        config = loader.load_database_config()
        assert isinstance(config, DatabaseConfig)
        assert config.relational.type == "sqlite"
        assert config.vector.type == "milvus_lite"

    def test_load_memory_config(self):
        loader = ConfigLoader(Path(__file__).parent.parent / "configs")
        config = loader.load_memory_config()
        assert isinstance(config, MemorySystemConfig)
        assert config.working_memory.max_turns == 20
        assert config.forgetting_curve.half_life_days == 14

    def test_load_provider_configs(self):
        loader = ConfigLoader(Path(__file__).parent.parent / "configs")
        providers = loader.load_provider_configs()
        assert "openai" in providers
        assert "anthropic" in providers
        assert "deepseek" in providers
        assert "glm" in providers
        assert "qwen" in providers
        assert isinstance(providers["openai"], ProviderConfigEntry)
        assert providers["openai"].default_model == "gpt-5.4"
        assert len(providers["openai"].models) == 5

    def test_load_channel_configs(self):
        loader = ConfigLoader(Path(__file__).parent.parent / "configs")
        channels = loader.load_channel_configs()
        assert "telegram" in channels
        assert "webchat" in channels
        assert isinstance(channels["telegram"], ChannelConfigEntry)
        assert channels["telegram"].enabled is True

    def test_load_nonexistent_dir(self):
        loader = ConfigLoader("/tmp/nonexistent_configs_xyz")
        assert loader.load_bot_config().app_name == "YuanBot"
        assert loader.load_provider_configs() == {}
        assert loader.load_channel_configs() == {}

    def test_load_single_provider(self):
        loader = ConfigLoader(Path(__file__).parent.parent / "configs")
        entry = loader.load_provider_config("openai")
        assert entry is not None
        assert entry.provider_id == "openai"

    def test_load_single_provider_nonexistent(self):
        loader = ConfigLoader(Path(__file__).parent.parent / "configs")
        entry = loader.load_provider_config("nonexistent")
        assert entry is None

    def test_load_single_channel(self):
        loader = ConfigLoader(Path(__file__).parent.parent / "configs")
        entry = loader.load_channel_config("telegram")
        assert entry is not None
        assert entry.platform == "telegram"

    def test_cache_behavior(self):
        loader = ConfigLoader(Path(__file__).parent.parent / "configs")
        config1 = loader.load_bot_config()
        config2 = loader.load_bot_config()
        assert config1.app_name == config2.app_name
        loader.clear_cache()

    def test_env_substitution_in_yaml(self, tmp_path, monkeypatch):
        """YAML 中的 ${ENV_VAR} 应被替换"""
        monkeypatch.setenv("TEST_API_KEY", "sk-12345")
        configs_dir = tmp_path / "configs"
        configs_dir.mkdir()
        (configs_dir / "bot.yaml").write_text(yaml.dump({"ai": {"default_provider": "openai"}}))
        providers_dir = configs_dir / "Providers"
        providers_dir.mkdir()
        (providers_dir / "openai.yaml").write_text(
            yaml.dump(
                {
                    "provider_id": "openai",
                    "adapter": "openai-adapter",
                    "config": {
                        "api_key": "${TEST_API_KEY}",
                        "base_url": "https://api.openai.com/v1",
                        "models": [{"id": "gpt-5.4", "type": "chat"}],
                        "default": "gpt-5.4",
                    },
                }
            )
        )

        loader = ConfigLoader(configs_dir)
        entry = loader.load_provider_config("openai")
        assert entry is not None
        assert entry.config["api_key"] == "sk-12345"

    def test_apply_env_overrides_nested(self, monkeypatch):
        """支持 YUAN_BOT__AI__DEFAULT_PROVIDER 格式的环境变量"""
        monkeypatch.setenv("YUAN_BOT__AI__DEFAULT_PROVIDER", "claude")
        loader = ConfigLoader()
        config = {"ai": {"default_provider": "openai"}}
        result = loader.apply_env_overrides(config)
        assert result["ai"]["default_provider"] == "claude"

    def test_apply_env_overrides_bool(self, monkeypatch):
        monkeypatch.setenv("YUAN_BOT__DEBUG", "true")
        loader = ConfigLoader()
        config = {"debug": False}
        result = loader.apply_env_overrides(config)
        assert result["debug"] is True


class TestLoadConfigFromDirectory:
    """测试 load_config 从目录加载并转换为 YuanBotConfig"""

    def test_load_from_project_configs(self):
        """从项目 configs/ 目录加载"""
        project_root = Path(__file__).parent.parent
        config = load_config(project_root / "configs")
        assert config.app_name == "YuanBot"
        assert config.ai_provider.provider_id == "openai"
        assert config.persona_id == "default"

    def test_load_from_tmp_directory(self, tmp_path):
        """从临时目录加载"""
        configs_dir = tmp_path / "configs"
        configs_dir.mkdir()

        bot = {
            "app_name": "TmpBot",
            "version": "3.0.0",
            "ai": {"default_provider": "claude", "default_model": "claude-sonnet"},
            "persona": {"id": "test-persona"},
            "proactive": {"enabled": False, "max_per_day": 10},
        }
        (configs_dir / "bot.yaml").write_text(yaml.dump(bot))

        providers_dir = configs_dir / "Providers"
        providers_dir.mkdir()
        (providers_dir / "claude.yaml").write_text(
            yaml.dump(
                {
                    "provider_id": "claude",
                    "adapter": "anthropic-adapter",
                    "config": {
                        "api_key": "test-key",
                        "base_url": "https://api.anthropic.com",
                        "models": [{"id": "claude-sonnet", "type": "chat"}],
                        "default": "claude-sonnet",
                    },
                }
            )
        )

        channels_dir = configs_dir / "Channels"
        channels_dir.mkdir()
        (channels_dir / "telegram.yaml").write_text(
            yaml.dump(
                {
                    "platform": "telegram",
                    "enabled": False,
                    "config": {"bot_token": "test"},
                }
            )
        )

        config = load_config(configs_dir)
        assert config.app_name == "TmpBot"
        assert config.version == "3.0.0"
        assert config.ai_provider.provider_id == "claude"
        assert config.ai_provider.base_url == "https://api.anthropic.com"
        assert config.persona_id == "test-persona"
        assert config.proactive.enabled is False
        assert config.proactive.max_per_day == 10
        assert len(config.channels) == 1
        assert config.channels[0].platform == "telegram"
        assert config.channels[0].enabled is False
