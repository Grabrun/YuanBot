"""测试基础架构与部署系统"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from yuanbot.infrastructure.cache_store import CacheStore, InMemoryCacheStore
from yuanbot.infrastructure.config_loader import ConfigLoader
from yuanbot.infrastructure.database import DatabaseConfig, DatabaseManager, DatabaseType
from yuanbot.infrastructure.sqlite_store import SQLiteStore
from yuanbot.infrastructure.vector_store import InMemoryVectorStore, VectorStore


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
    async def test_initialize_and_close(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = DatabaseConfig(
                db_type=DatabaseType.SQLITE,
                sqlite_path=str(Path(tmpdir) / "test.db"),
            )
            manager = DatabaseManager(config)
            await manager.initialize()
            assert manager.is_initialized is True
            assert manager.sqlite.is_initialized is True
            assert manager.vector.is_initialized is True
            assert manager.cache.is_initialized is True
            await manager.close()
            assert manager.is_initialized is False

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

    @pytest.mark.asyncio
    async def test_double_initialize(self):
        """重复初始化不应报错"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = DatabaseConfig(
                sqlite_path=str(Path(tmpdir) / "test.db"),
            )
            manager = DatabaseManager(config)
            await manager.initialize()
            await manager.initialize()  # 第二次
            assert manager.is_initialized is True
            await manager.close()

    @pytest.mark.asyncio
    async def test_component_access(self):
        manager = DatabaseManager()
        assert manager.sqlite is not None
        assert manager.vector is not None
        assert manager.cache is not None
        assert manager.config is not None


class TestSQLiteStore:
    """SQLite 存储测试"""

    @pytest.mark.asyncio
    async def test_initialize_and_close(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(str(Path(tmpdir) / "test.db"))
            await store.initialize()
            assert store.is_initialized is True
            await store.close()
            assert store.is_initialized is False

    @pytest.mark.asyncio
    async def test_fact_memory_crud(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(str(Path(tmpdir) / "test.db"))
            await store.initialize()

            # 保存
            await store.save_fact_memory(
                id="fact1",
                user_id="user1",
                category="preference",
                key="coffee",
                value="用户喜欢喝咖啡",
                importance=0.8,
            )

            # 读取
            facts = await store.get_fact_memories("user1")
            assert len(facts) == 1
            assert facts[0]["value"] == "用户喜欢喝咖啡"
            assert facts[0]["category"] == "preference"

            # 按类别读取
            facts_filtered = await store.get_fact_memories("user1", category="preference")
            assert len(facts_filtered) == 1

            facts_other = await store.get_fact_memories("user1", category="other")
            assert len(facts_other) == 0

            # 更新（upsert）
            await store.save_fact_memory(
                id="fact1",
                user_id="user1",
                category="preference",
                key="coffee",
                value="用户非常喜欢喝拿铁",
                importance=0.9,
            )
            facts = await store.get_fact_memories("user1")
            assert len(facts) == 1
            assert facts[0]["value"] == "用户非常喜欢喝拿铁"

            # 删除
            await store.delete_fact_memory("fact1")
            facts = await store.get_fact_memories("user1")
            assert len(facts) == 0

            await store.close()

    @pytest.mark.asyncio
    async def test_episodic_metadata_crud(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(str(Path(tmpdir) / "test.db"))
            await store.initialize()

            await store.save_episodic_metadata(
                id="ep1",
                user_id="user1",
                session_id="sess1",
                date="2024-01-15",
                time_of_day="下午",
                topic="工作, 压力",
                summary="用户讨论工作压力",
                emotional_tone="negative",
                key_entities=["项目", "截止日"],
                importance=0.7,
            )

            episodes = await store.get_episodic_metadata("user1")
            assert len(episodes) == 1
            assert episodes[0]["summary"] == "用户讨论工作压力"

            # 按日期范围查询
            episodes = await store.get_episodic_metadata(
                "user1", date_from="2024-01-01", date_to="2024-12-31"
            )
            assert len(episodes) == 1

            # 按话题查询
            episodes = await store.get_episodic_metadata("user1", topic="工作")
            assert len(episodes) == 1

            # 更新访问计数
            await store.update_episodic_access("ep1")

            # 删除
            await store.delete_episodic_metadata("ep1")
            episodes = await store.get_episodic_metadata("user1")
            assert len(episodes) == 0

            await store.close()

    @pytest.mark.asyncio
    async def test_user_profile_crud(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(str(Path(tmpdir) / "test.db"))
            await store.initialize()

            import time

            now = time.time()

            await store.save_user_profile(
                user_id="user1",
                display_name="小明",
                preferences={"color": "blue"},
                relationship_stage="familiar",
                trust_score=0.5,
                total_interactions=10,
                first_interaction=now,
                last_interaction=now,
            )

            profile = await store.get_user_profile("user1")
            assert profile is not None
            assert profile["display_name"] == "小明"
            assert profile["relationship_stage"] == "familiar"

            # 更新
            await store.save_user_profile(
                user_id="user1",
                display_name="小明",
                preferences={"color": "blue", "food": "火锅"},
                relationship_stage="intimate",
                trust_score=0.7,
                total_interactions=20,
                first_interaction=now,
                last_interaction=now,
            )
            profile = await store.get_user_profile("user1")
            assert profile["relationship_stage"] == "intimate"
            assert profile["total_interactions"] == 20

            # 不存在的用户
            profile = await store.get_user_profile("nonexistent")
            assert profile is None

            await store.close()

    @pytest.mark.asyncio
    async def test_emotion_record(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(str(Path(tmpdir) / "test.db"))
            await store.initialize()

            await store.save_emotion_record(
                id="emo1",
                user_id="user1",
                session_id="sess1",
                emotion="joy",
                intensity=0.8,
                valence="positive",
                trigger_text="今天天气真好！",
            )

            records = await store.get_emotion_records("user1")
            assert len(records) == 1
            assert records[0]["emotion"] == "joy"

            await store.close()

    @pytest.mark.asyncio
    async def test_identity_mapping(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(str(Path(tmpdir) / "test.db"))
            await store.initialize()

            await store.save_identity_mapping(
                platform="telegram",
                platform_user_id="tg_123",
                yuanbot_user_id="yb_user1",
            )

            uid = await store.get_yuanbot_user_id("telegram", "tg_123")
            assert uid == "yb_user1"

            uid = await store.get_yuanbot_user_id("telegram", "tg_999")
            assert uid is None

            # 更新映射
            await store.save_identity_mapping(
                platform="telegram",
                platform_user_id="tg_123",
                yuanbot_user_id="yb_user2",
            )
            uid = await store.get_yuanbot_user_id("telegram", "tg_123")
            assert uid == "yb_user2"

            await store.close()


class TestVectorStore:
    """向量存储测试"""

    @pytest.mark.asyncio
    async def test_memory_backend(self):
        store = VectorStore(use_milvus=False)
        await store.initialize()
        assert store.is_initialized is True

        await store.add_vector("v1", [1.0, 0.0, 0.0], {"type": "test"})
        await store.add_vector("v2", [0.0, 1.0, 0.0], {"type": "test"})
        await store.add_vector("v3", [0.9, 0.1, 0.0], {"type": "test"})

        results = await store.search_similar([1.0, 0.0, 0.0], top_k=2, threshold=0.5)
        assert len(results) >= 1
        assert results[0]["id"] == "v1"

        await store.delete_vector("v1")
        results = await store.search_similar([1.0, 0.0, 0.0], top_k=2, threshold=0.5)
        ids = [r["id"] for r in results]
        assert "v1" not in ids

        await store.close()

    @pytest.mark.asyncio
    async def test_in_memory_vector_store(self):
        store = InMemoryVectorStore()
        store.add_vector("a", [1.0, 0.0])
        store.add_vector("b", [0.0, 1.0])

        results = store.search_similar([1.0, 0.0], top_k=5, threshold=0.5)
        assert len(results) >= 1
        assert results[0]["id"] == "a"

        store.delete_vector("a")
        results = store.search_similar([1.0, 0.0], top_k=5, threshold=0.5)
        assert all(r["id"] != "a" for r in results)

    @pytest.mark.asyncio
    async def test_empty_search(self):
        store = VectorStore(use_milvus=False)
        await store.initialize()

        results = await store.search_similar([1.0, 0.0], top_k=5, threshold=0.5)
        assert results == []

        await store.close()


class TestCacheStore:
    """缓存存储测试"""

    @pytest.mark.asyncio
    async def test_memory_backend(self):
        store = CacheStore(redis_url=None)
        await store.initialize()
        assert store.backend == "memory"

        await store.set("key1", "value1")
        val = await store.get("key1")
        assert val == "value1"

        assert await store.exists("key1") is True
        assert await store.exists("key2") is False

        await store.delete("key1")
        assert await store.exists("key1") is False

        await store.close()

    @pytest.mark.asyncio
    async def test_ttl(self):
        import asyncio

        store = InMemoryCacheStore()
        store.set("key1", "value1", ttl=1)
        assert store.get("key1") == "value1"

        await asyncio.sleep(1.1)
        assert store.get("key1") is None

    @pytest.mark.asyncio
    async def test_json_value(self):
        store = CacheStore(redis_url=None)
        await store.initialize()

        data = {"memories": [{"id": "1", "content": "test"}]}
        await store.set("data", data)
        val = await store.get("data")
        assert val == data

        await store.close()

    @pytest.mark.asyncio
    async def test_working_memory_operations(self):
        store = CacheStore(redis_url=None)
        await store.initialize()

        memories = [{"id": "1", "content": "hello"}, {"id": "2", "content": "world"}]
        await store.set_working_memory("sess1", memories)

        result = await store.get_working_memory("sess1")
        assert len(result) == 2
        assert result[0]["content"] == "hello"

        await store.clear_working_memory("sess1")
        result = await store.get_working_memory("sess1")
        assert result == []

        await store.close()

    @pytest.mark.asyncio
    async def test_interaction_lock(self):
        store = CacheStore(redis_url=None)
        await store.initialize()

        acquired = await store.acquire_interaction_lock("user1", "greeting", ttl=60)
        assert acquired is True

        # 再次获取应失败
        acquired = await store.acquire_interaction_lock("user1", "greeting", ttl=60)
        assert acquired is False

        # 释放后可以再次获取
        await store.release_interaction_lock("user1", "greeting")
        acquired = await store.acquire_interaction_lock("user1", "greeting", ttl=60)
        assert acquired is True

        await store.close()

    @pytest.mark.asyncio
    async def test_in_memory_cache_keys(self):
        store = InMemoryCacheStore()
        store.set("working:s1", "data1")
        store.set("working:s2", "data2")
        store.set("lock:u1", "locked")

        all_keys = store.keys("*")
        assert len(all_keys) == 3

        working_keys = store.keys("working:*")
        assert len(working_keys) == 2
