"""YuanBot 配置管理测试"""

from __future__ import annotations

import yaml

from yuanbot.config import (
    AIProviderConfig,
    YuanBotConfig,
    _deep_merge,
    _load_env_overrides,
    load_config,
)


class TestYuanBotConfig:
    """主配置测试"""

    def test_default_config(self):
        config = YuanBotConfig()
        assert config.app_name == "YuanBot"
        assert config.version == "0.1.0"
        assert config.debug is False
        assert config.log_level == "INFO"
        assert config.persona_id == "default"

    def test_ai_provider_defaults(self):
        config = YuanBotConfig()
        assert config.ai_provider.provider_id == "openai"
        assert config.ai_provider.api_key is None
        assert config.ai_provider.default_model == "gpt-4o"

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
        monkeypatch.setenv("YUAN_AI_MODEL", "gpt-4o-mini")
        overrides = _load_env_overrides()
        assert overrides["ai_provider"]["default_model"] == "gpt-4o-mini"

    def test_env_override_log_level(self, monkeypatch):
        monkeypatch.setenv("YUAN_LOG_LEVEL", "debug")
        overrides = _load_env_overrides()
        assert overrides["log_level"] == "DEBUG"


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
