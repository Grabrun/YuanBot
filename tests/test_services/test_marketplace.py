"""社区扩展市场客户端测试"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from yuanbot.services.marketplace import ExtensionEntry, MarketplaceClient


class TestExtensionEntry:
    """测试 ExtensionEntry 数据类"""

    def test_from_dict(self):
        data = {
            "id": "test-ext",
            "name": "Test Extension",
            "description": "A test extension",
            "version": "1.0.0",
            "author": "Test Author",
            "type": "skill",
            "downloads": 100,
            "stars": 10,
        }
        entry = ExtensionEntry.from_dict(data)

        assert entry.id == "test-ext"
        assert entry.name == "Test Extension"
        assert entry.version == "1.0.0"
        assert entry.type == "skill"
        assert entry.downloads == 100

    def test_to_dict(self):
        entry = ExtensionEntry(
            id="test",
            name="Test",
            version="2.0.0",
            type="tool",
        )
        d = entry.to_dict()

        assert d["id"] == "test"
        assert d["name"] == "Test"
        assert d["version"] == "2.0.0"
        assert d["type"] == "tool"

    def test_from_dict_defaults(self):
        entry = ExtensionEntry.from_dict({})
        assert entry.id == ""
        assert entry.version == "0.0.0"
        assert entry.downloads == 0


class TestMarketplaceClient:
    """测试市场客户端"""

    @pytest.mark.anyio
    async def test_search_empty_registry(self, tmp_path: Path):
        """注册表不可用时，搜索返回空结果"""
        client = MarketplaceClient(
            registry_url="http://localhost:1/nonexistent",
            cache_dir=tmp_path / "cache",
        )
        result = await client.search(query="test")

        assert result["extensions"] == []
        assert result["total"] == 0

    @pytest.mark.anyio
    async def test_list_empty_registry(self, tmp_path: Path):
        client = MarketplaceClient(
            registry_url="http://localhost:1/nonexistent",
            cache_dir=tmp_path / "cache",
        )
        result = await client.list_extensions()

        assert result["extensions"] == []
        assert result["total"] == 0

    @pytest.mark.anyio
    async def test_get_extension_not_found(self, tmp_path: Path):
        client = MarketplaceClient(
            registry_url="http://localhost:1/nonexistent",
            cache_dir=tmp_path / "cache",
        )
        entry = await client.get_extension("nonexistent")
        assert entry is None

    @pytest.mark.anyio
    async def test_search_with_cached_index(self, tmp_path: Path):
        """使用缓存索引进行搜索"""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir(parents=True)

        # 写入缓存索引
        index_data = [
            {
                "id": "weather-tool",
                "name": "天气查询",
                "description": "查询天气信息",
                "version": "1.0.0",
                "type": "tool",
                "keywords": ["weather", "天气"],
                "downloads": 500,
            },
            {
                "id": "emotional-skill",
                "name": "情感安慰",
                "description": "提供情感支持和安慰",
                "version": "1.2.0",
                "type": "skill",
                "keywords": ["emotional", "comfort"],
                "downloads": 300,
            },
            {
                "id": "search-tool",
                "name": "网络搜索",
                "description": "搜索互联网信息",
                "version": "2.0.0",
                "type": "tool",
                "keywords": ["search", "web"],
                "downloads": 800,
            },
        ]
        (cache_dir / "index.json").write_text(
            json.dumps(index_data, ensure_ascii=False),
            encoding="utf-8",
        )

        client = MarketplaceClient(
            registry_url="http://localhost:1/nonexistent",
            cache_dir=cache_dir,
        )

        # 搜索关键词
        result = await client.search(query="天气")
        assert result["total"] == 1
        assert result["extensions"][0]["id"] == "weather-tool"

        # 搜索类型
        result = await client.search(ext_type="tool")
        assert result["total"] == 2

        # 搜索无匹配
        result = await client.search(query="不存在的扩展")
        assert result["total"] == 0

    @pytest.mark.anyio
    async def test_list_with_cached_index(self, tmp_path: Path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir(parents=True)

        index_data = [
            {"id": "a", "name": "A", "type": "skill", "downloads": 10},
            {"id": "b", "name": "B", "type": "tool", "downloads": 30},
            {"id": "c", "name": "C", "type": "skill", "downloads": 20},
        ]
        (cache_dir / "index.json").write_text(json.dumps(index_data))

        client = MarketplaceClient(cache_dir=cache_dir)

        # 默认按下载量排序
        result = await client.list_extensions()
        assert result["total"] == 3
        assert result["extensions"][0]["id"] == "b"  # 最多下载

        # 按类型过滤
        result = await client.list_extensions(ext_type="skill")
        assert result["total"] == 2

        # 分页
        result = await client.list_extensions(limit=1, offset=1)
        assert len(result["extensions"]) == 1

    @pytest.mark.anyio
    async def test_get_extension_from_cache(self, tmp_path: Path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir(parents=True)

        index_data = [
            {
                "id": "my-ext",
                "name": "My Extension",
                "description": "Test",
                "version": "1.0.0",
                "type": "skill",
            },
        ]
        (cache_dir / "index.json").write_text(json.dumps(index_data))

        client = MarketplaceClient(cache_dir=cache_dir)

        entry = await client.get_extension("my-ext")
        assert entry is not None
        assert entry.name == "My Extension"

        assert await client.get_extension("nonexistent") is None

    @pytest.mark.anyio
    async def test_search_case_insensitive(self, tmp_path: Path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir(parents=True)

        index_data = [
            {
                "id": "test",
                "name": "Weather Tool",
                "description": "天气查询工具",
                "type": "tool",
                "keywords": ["Weather"],
            },
        ]
        (cache_dir / "index.json").write_text(json.dumps(index_data))

        client = MarketplaceClient(cache_dir=cache_dir)

        # 大小写不敏感
        result = await client.search(query="weather")
        assert result["total"] == 1

        result = await client.search(query="Weather")
        assert result["total"] == 1

        # 中文搜索
        result = await client.search(query="天气")
        assert result["total"] == 1

    @pytest.mark.anyio
    async def test_get_categories(self, tmp_path: Path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir(parents=True)

        index_data = [
            {"id": "a", "name": "A", "type": "skill"},
            {"id": "b", "name": "B", "type": "tool"},
            {"id": "c", "name": "C", "type": "skill"},
            {"id": "d", "name": "D", "type": "channel"},
        ]
        (cache_dir / "index.json").write_text(json.dumps(index_data))

        client = MarketplaceClient(cache_dir=cache_dir)

        categories = await client.get_categories()
        assert categories["skill"] == 2
        assert categories["tool"] == 1
        assert categories["channel"] == 1

    @pytest.mark.anyio
    async def test_download_extension_no_url(self, tmp_path: Path):
        """没有下载链接时返回 None"""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir(parents=True)

        index_data = [
            {"id": "test", "name": "Test", "type": "skill", "download_url": ""},
        ]
        (cache_dir / "index.json").write_text(json.dumps(index_data))

        client = MarketplaceClient(cache_dir=cache_dir)

        result = await client.download_extension("test", tmp_path / "ext")
        assert result is None

    @pytest.mark.anyio
    async def test_download_extension_not_found(self, tmp_path: Path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "index.json").write_text("[]")

        client = MarketplaceClient(cache_dir=cache_dir)

        result = await client.download_extension("nonexistent", tmp_path / "ext")
        assert result is None
