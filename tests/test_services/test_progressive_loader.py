"""三层渐进式动态加载器测试"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from yuanbot.services.domain_matcher import CapabilityDomain, DomainMatcher
from yuanbot.services.progressive_loader import LRUCache, ProgressiveLoader, MetadataIndex
from yuanbot.skills.manager import SkillManager
from yuanbot.tools.manager import ToolManager


def _write_skill(path: Path, skill_id: str, **overrides: object) -> None:
    config = {
        "skill_id": skill_id,
        "name": overrides.get("name", f"Skill {skill_id}"),
        "version": "1.0.0",
        "category": overrides.get("category", "emotional_care"),
        "capability_tags": overrides.get("capability_tags", ["comfort"]),
        "token_cost_estimate": overrides.get("token_cost_estimate", 200),
        "enabled": overrides.get("enabled", True),
        "prompt_template": overrides.get("prompt_template", f"Prompt for {skill_id}"),
    }
    with open(path / f"{skill_id}.yaml", "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True)


def _write_tool(path: Path, tool_id: str, **overrides: object) -> None:
    config = {
        "tool_id": tool_id,
        "name": overrides.get("name", f"Tool {tool_id}"),
        "version": "1.0.0",
        "category": overrides.get("category", "daily_chat"),
        "capability_tags": overrides.get("capability_tags", []),
        "permission_level": overrides.get("permission_level", "readonly"),
        "enabled": overrides.get("enabled", True),
        "schema": overrides.get(
            "schema",
            {
                "type": "function",
                "function": {
                    "name": tool_id,
                    "description": f"Description of {tool_id}",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ),
        "executor": {"type": "local_thread", "timeout": 10},
    }
    with open(path / f"{tool_id}.yaml", "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True)


@pytest.fixture
async def loader(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    tools_dir = tmp_path / "tools"
    skills_dir.mkdir()
    tools_dir.mkdir()

    _write_skill(skills_dir, "emotional_comfort", category="emotional_care", 
                 capability_tags=["comfort", "sadness"], token_cost_estimate=250)
    _write_skill(skills_dir, "daily_chat", category="daily_chat",
                 capability_tags=["chat", "casual"], token_cost_estimate=150)
    _write_skill(skills_dir, "creative_storytelling", category="creative_storytelling",
                 capability_tags=["story", "creative"], token_cost_estimate=400)

    _write_tool(tools_dir, "get_weather", category="daily_chat",
                capability_tags=["天气", "weather"])
    _write_tool(tools_dir, "set_reminder", category="task_management",
                capability_tags=["提醒", "reminder"])
    _write_tool(tools_dir, "search", category="knowledge_query",
                capability_tags=["搜索", "search"])

    skill_mgr = SkillManager(skills_dir=str(skills_dir))
    tool_mgr = ToolManager(tools_dir=str(tools_dir))
    await skill_mgr.load_skills()
    await tool_mgr.load_tools()

    return ProgressiveLoader(
        skill_manager=skill_mgr,
        tool_manager=tool_mgr,
    )


# ──────────────────────────────────────────────
# LRU Cache
# ──────────────────────────────────────────────


class TestLRUCache:
    def test_put_and_get(self):
        cache = LRUCache(max_size=3)
        cache.put("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_cache_miss(self):
        cache = LRUCache()
        assert cache.get("missing") is None

    def test_eviction(self):
        cache = LRUCache(max_size=2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)  # evicts "a"
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("c") == 3

    def test_lru_order(self):
        cache = LRUCache(max_size=2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.get("a")  # move "a" to end
        cache.put("c", 3)  # evicts "b" (least recently used)
        assert cache.get("a") == 1
        assert cache.get("b") is None

    def test_update_existing(self):
        cache = LRUCache(max_size=2)
        cache.put("a", 1)
        cache.put("a", 2)  # update
        assert cache.get("a") == 2
        assert cache.size == 1

    def test_hit_miss_counters(self):
        cache = LRUCache()
        cache.put("a", 1)
        cache.get("a")  # hit
        cache.get("b")  # miss
        assert cache.hits == 1
        assert cache.misses == 1

    def test_size(self):
        cache = LRUCache()
        assert cache.size == 0
        cache.put("a", 1)
        assert cache.size == 1


# ──────────────────────────────────────────────
# 阶段一：构建索引
# ──────────────────────────────────────────────


class TestBuildIndex:
    async def test_build_index(self, loader):
        await loader.build_index()
        summary = loader.get_index_summary()
        assert summary["total_entries"] == 6  # 3 skills + 3 tools
        assert summary["skills"] == 3
        assert summary["tools"] == 3

    async def test_index_excludes_disabled(self, tmp_path):
        skills_dir = tmp_path / "skills"
        tools_dir = tmp_path / "tools"
        skills_dir.mkdir()
        tools_dir.mkdir()

        _write_skill(skills_dir, "enabled_skill", enabled=True)
        _write_skill(skills_dir, "disabled_skill", enabled=False)
        _write_tool(tools_dir, "enabled_tool", enabled=True)
        _write_tool(tools_dir, "disabled_tool", enabled=False)

        skill_mgr = SkillManager(skills_dir=str(skills_dir))
        tool_mgr = ToolManager(tools_dir=str(tools_dir))
        await skill_mgr.load_skills()
        await tool_mgr.load_tools()

        loader = ProgressiveLoader(skill_manager=skill_mgr, tool_manager=tool_mgr)
        await loader.build_index()

        summary = loader.get_index_summary()
        assert summary["total_entries"] == 2  # 1 skill + 1 tool

    async def test_index_categories(self, loader):
        await loader.build_index()
        summary = loader.get_index_summary()
        categories = summary["categories"]
        assert "emotional_care" in categories
        assert "daily_chat" in categories
        assert "creative_storytelling" in categories


# ──────────────────────────────────────────────
# 阶段二：加载匹配的能力
# ──────────────────────────────────────────────


class TestLoadForContext:
    async def test_load_by_domain(self, loader):
        await loader.build_index()
        result = await loader.load_for_context(
            capability_domains=["emotional_care"],
        )
        assert "emotional_comfort" in result.skill_ids
        assert result.tokens_estimate > 0

    async def test_load_by_intent(self, loader):
        await loader.build_index()
        result = await loader.load_for_context(
            intent="我想听故事",
        )
        assert "creative_storytelling" in result.skill_ids

    async def test_load_by_emotion(self, loader):
        await loader.build_index()
        result = await loader.load_for_context(
            emotion="sadness",
        )
        assert "emotional_comfort" in result.skill_ids

    async def test_max_skills_limit(self, loader):
        await loader.build_index()
        result = await loader.load_for_context(
            capability_domains=["emotional_care", "daily_chat", "creative_storytelling"],
            max_skills=1,
        )
        assert len(result.skill_ids) <= 1

    async def test_max_tools_limit(self, loader):
        await loader.build_index()
        result = await loader.load_for_context(
            capability_domains=["daily_chat", "knowledge_query", "task_management"],
            max_tools=1,
        )
        assert len(result.tool_ids) <= 1

    async def test_empty_context(self, loader):
        await loader.build_index()
        result = await loader.load_for_context()
        # No intent/emotion/domains → no matches
        assert len(result.skill_ids) == 0
        assert len(result.tool_ids) == 0

    async def test_token_estimate(self, loader):
        await loader.build_index()
        result = await loader.load_for_context(
            capability_domains=["emotional_care"],
        )
        assert result.tokens_estimate > 0

    async def test_load_time_tracked(self, loader):
        await loader.build_index()
        result = await loader.load_for_context(
            capability_domains=["emotional_care"],
        )
        assert result.load_time_ms >= 0

    async def test_match_result_included(self, loader):
        await loader.build_index()
        result = await loader.load_for_context(
            capability_domains=["emotional_care"],
        )
        assert result.match_result is not None
        assert CapabilityDomain.EMOTIONAL_CARE in result.match_result.matched_domains


# ──────────────────────────────────────────────
# 阶段三：资源获取
# ──────────────────────────────────────────────


class TestGetResource:
    async def test_cache_miss(self, loader):
        await loader.build_index()
        result = await loader.get_resource("skill", "test", "resource_key")
        assert result is None  # Phase 3 returns None for uncached resources

    async def test_stats_updated(self, loader):
        await loader.build_index()
        await loader.get_resource("skill", "test", "key1")
        await loader.get_resource("skill", "test", "key2")
        summary = loader.get_index_summary()
        assert summary["stats"]["stage3_cache_misses"] == 2


# ──────────────────────────────────────────────
# 索引摘要
# ──────────────────────────────────────────────


class TestIndexSummary:
    async def test_summary_structure(self, loader):
        await loader.build_index()
        summary = loader.get_index_summary()
        assert "total_entries" in summary
        assert "skills" in summary
        assert "tools" in summary
        assert "categories" in summary
        assert "stats" in summary

    async def test_summary_stats(self, loader):
        await loader.build_index()
        stats = loader.get_index_summary()["stats"]
        assert stats["stage1_index_count"] == 6
        assert stats["stage2_skills_loaded"] == 0
        assert stats["stage2_tools_loaded"] == 0
