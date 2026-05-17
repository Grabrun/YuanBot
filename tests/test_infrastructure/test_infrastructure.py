"""测试基础架构与部署系统"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from yuanbot.infrastructure.config_loader import ConfigLoader
from yuanbot.infrastructure.database import DatabaseConfig, DatabaseManager, DatabaseType


class TestConfigLoader:
    """配置加载器测试"""

    def test_load_nonexistent_file(self):
        loader = ConfigLoader("/tmp/nonexistent_yuanbot_configs")
        config = loader.load_bot_config()
        assert config == {}

    def test_load_bot_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bot_config = {"app_name": "TestBot", "version": "1.0.0"}
            with open(Path(tmpdir) / "bot.yaml", "w") as f:
                yaml.dump(bot_config, f)

            loader = ConfigLoader(tmpdir)
            config = loader.load_bot_config()
            assert config["app_name"] == "TestBot"

    def test_load_channel_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            channels_dir = Path(tmpdir) / "Channels"
            channels_dir.mkdir()
            tg_config = {"adapter": "telegram", "enabled": True}
            with open(channels_dir / "telegram.yaml", "w") as f:
                yaml.dump(tg_config, f)

            loader = ConfigLoader(tmpdir)
            config = loader.load_channel_config("telegram")
            assert config["adapter"] == "telegram"

    def test_load_all_channel_configs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            channels_dir = Path(tmpdir) / "Channels"
            channels_dir.mkdir()
            for name in ("telegram", "discord"):
                with open(channels_dir / f"{name}.yaml", "w") as f:
                    yaml.dump({"platform": name}, f)

            loader = ConfigLoader(tmpdir)
            configs = loader.load_all_channel_configs()
            assert "telegram" in configs
            assert "discord" in configs

    def test_load_provider_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            providers_dir = Path(tmpdir) / "Providers"
            providers_dir.mkdir()
            provider_config = {"provider_id": "openai", "adapter": "openai-adapter"}
            with open(providers_dir / "openai.yaml", "w") as f:
                yaml.dump(provider_config, f)

            loader = ConfigLoader(tmpdir)
            config = loader.load_provider_config("openai")
            assert config["provider_id"] == "openai"

    def test_apply_env_overrides(self):
        loader = ConfigLoader()
        config = {"debug": False, "ai_provider": {"provider_id": "openai"}}

        # 设置环境变量
        os.environ["YUAN_BOT_DEBUG"] = "true"
        try:
            result = loader.apply_env_overrides(config)
            assert result["debug"] is True
        finally:
            del os.environ["YUAN_BOT_DEBUG"]

    def test_clear_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(Path(tmpdir) / "bot.yaml", "w") as f:
                yaml.dump({"version": "1"}, f)

            loader = ConfigLoader(tmpdir)
            loader.load_bot_config()
            assert len(loader._cache) > 0

            loader.clear_cache()
            assert len(loader._cache) == 0


class TestDatabaseManager:
    """数据库管理器测试"""

    @pytest.mark.asyncio
    async def test_default_config(self):
        manager = DatabaseManager()
        assert manager.db_type == DatabaseType.SQLITE
        assert manager.is_initialized is False

    @pytest.mark.asyncio
    async def test_initialize_sqlite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = DatabaseConfig(
                db_type=DatabaseType.SQLITE,
                sqlite_path=str(Path(tmpdir) / "test.db"),
            )
            manager = DatabaseManager(config)
            await manager.initialize()
            assert manager.is_initialized is True
            await manager.close()

    @pytest.mark.asyncio
    async def test_connection_info(self):
        manager = DatabaseManager()
        info = manager.get_connection_info()
        assert info["db_type"] == "sqlite"
        assert info["initialized"] is False

    @pytest.mark.asyncio
    async def test_mysql_config(self):
        config = DatabaseConfig(
            db_type=DatabaseType.MYSQL,
            host="localhost",
            port=3306,
            database="yuanbot",
        )
        manager = DatabaseManager(config)
        assert manager.db_type == DatabaseType.MYSQL
