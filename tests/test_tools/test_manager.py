"""YuanBot Tools 管理器测试

测试 YAML 加载、Schema 获取、工具执行等功能。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from yuanbot.skills.manager import SkillManager
from yuanbot.tools.manager import ToolManager


@pytest.fixture
def tools_dir(tmp_path: Path) -> Path:
    """创建临时 Tools 配置目录"""
    d = tmp_path / "tools"
    d.mkdir()
    return d


@pytest.fixture
def manager(tools_dir: Path) -> ToolManager:
    return ToolManager(tools_dir=str(tools_dir))


def _write_tool(tools_dir: Path, tool_id: str, **overrides: object) -> Path:
    """辅助：写入一个 tool YAML 文件"""
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
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },
        ),
        "executor": overrides.get("executor", {"type": "local_thread", "timeout": 10}),
    }
    path = tools_dir / f"{tool_id}.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True)
    return path


# ──────────────────────────────────────────────
# 加载测试
# ──────────────────────────────────────────────


class TestLoadTools:
    async def test_load_single(self, manager: ToolManager, tools_dir: Path):
        _write_tool(tools_dir, "weather")
        await manager.load_tools()
        tools = manager.get_all_tools()
        assert len(tools) == 1
        assert tools[0]["tool_id"] == "weather"

    async def test_load_multiple(self, manager: ToolManager, tools_dir: Path):
        _write_tool(tools_dir, "t1")
        _write_tool(tools_dir, "t2")
        _write_tool(tools_dir, "t3")
        await manager.load_tools()
        assert len(manager.get_all_tools()) == 3

    async def test_load_skips_disabled(self, manager: ToolManager, tools_dir: Path):
        _write_tool(tools_dir, "enabled_tool", enabled=True)
        _write_tool(tools_dir, "disabled_tool", enabled=False)
        await manager.load_tools()
        tools = manager.get_all_tools()
        assert len(tools) == 1
        assert tools[0]["tool_id"] == "enabled_tool"

    async def test_load_missing_dir(self, tmp_path: Path):
        manager = ToolManager(tools_dir=str(tmp_path / "nonexistent"))
        await manager.load_tools()
        assert manager.get_all_tools() == []

    async def test_load_invalid_yaml(self, manager: ToolManager, tools_dir: Path):
        bad_file = tools_dir / "bad.yaml"
        bad_file.write_text(": : invalid yaml [{", encoding="utf-8")
        _write_tool(tools_dir, "good")
        await manager.load_tools()
        tools = manager.get_all_tools()
        assert len(tools) == 1
        assert tools[0]["tool_id"] == "good"

    async def test_load_missing_tool_id(self, manager: ToolManager, tools_dir: Path):
        path = tools_dir / "no_id.yaml"
        config = {"name": "No ID", "category": "test", "enabled": True}
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(config, f)
        await manager.load_tools()
        assert manager.get_all_tools() == []

    async def test_load_non_dict_yaml(self, manager: ToolManager, tools_dir: Path):
        path = tools_dir / "list.yaml"
        path.write_text("- item1\n- item2\n", encoding="utf-8")
        await manager.load_tools()
        assert manager.get_all_tools() == []

    async def test_load_schema(self, manager: ToolManager, tools_dir: Path):
        schema = {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "获取天气",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string", "description": "城市名"}},
                    "required": ["city"],
                },
            },
        }
        _write_tool(tools_dir, "weather", schema=schema)
        await manager.load_tools()

        loaded_schema = manager.get_tool_schema("weather")
        assert loaded_schema is not None
        assert loaded_schema["function"]["name"] == "get_weather"
        assert "city" in loaded_schema["function"]["parameters"]["properties"]

    async def test_load_preserves_metadata(self, manager: ToolManager, tools_dir: Path):
        _write_tool(
            tools_dir,
            "meta_test",
            name="Meta Tool",
            category="utility",
            permission_level="restricted",
        )
        await manager.load_tools()
        tools = manager.get_all_tools()
        assert tools[0]["name"] == "Meta Tool"
        assert tools[0]["category"] == "utility"
        assert tools[0]["permission_level"] == "restricted"


# ──────────────────────────────────────────────
# 意图匹配测试
# ──────────────────────────────────────────────


class TestGetToolsForIntent:
    async def test_match_by_category(self, manager: ToolManager, tools_dir: Path):
        _write_tool(tools_dir, "weather", category="daily_chat")
        _write_tool(tools_dir, "code", category="programming")
        await manager.load_tools()

        matched = manager.get_tools_for_intent("daily_chat天气查询")
        schemas = [s["function"]["name"] for s in matched]
        assert "weather" in schemas

    async def test_match_by_capability_tags(self, manager: ToolManager, tools_dir: Path):
        _write_tool(tools_dir, "weather", capability_tags=["天气", "weather"])
        _write_tool(tools_dir, "code", capability_tags=["编程"])
        await manager.load_tools()

        matched = manager.get_tools_for_intent("天气怎么样")
        schemas = [s["function"]["name"] for s in matched]
        assert "weather" in schemas

    async def test_no_match(self, manager: ToolManager, tools_dir: Path):
        _write_tool(tools_dir, "weather", category="weather", capability_tags=["天气"])
        await manager.load_tools()

        matched = manager.get_tools_for_intent("programming")
        assert len(matched) == 0

    async def test_empty_intent(self, manager: ToolManager, tools_dir: Path):
        _write_tool(tools_dir, "t1")
        await manager.load_tools()
        matched = manager.get_tools_for_intent("")
        assert len(matched) == 0

    async def test_returns_openai_format(self, manager: ToolManager, tools_dir: Path):
        _write_tool(tools_dir, "weather", category="daily_chat")
        await manager.load_tools()

        matched = manager.get_tools_for_intent("daily_chat查询")
        assert len(matched) > 0
        schema = matched[0]
        assert schema["type"] == "function"
        assert "function" in schema
        assert "name" in schema["function"]
        assert "description" in schema["function"]


# ──────────────────────────────────────────────
# Schema 获取测试
# ──────────────────────────────────────────────


class TestGetToolSchema:
    async def test_existing(self, manager: ToolManager, tools_dir: Path):
        schema = {
            "type": "function",
            "function": {"name": "test", "description": "Test"},
        }
        _write_tool(tools_dir, "test", schema=schema)
        await manager.load_tools()
        assert manager.get_tool_schema("test") == schema

    async def test_nonexistent(self, manager: ToolManager, tools_dir: Path):
        await manager.load_tools()
        assert manager.get_tool_schema("nonexistent") is None


# ──────────────────────────────────────────────
# 执行测试
# ──────────────────────────────────────────────


class TestExecuteTool:
    async def test_execute_existing(self, manager: ToolManager, tools_dir: Path):
        _write_tool(tools_dir, "weather")
        await manager.load_tools()

        result = await manager.execute_tool("weather", {"city": "北京"})
        assert result.success is True
        assert result.tool_id == "weather"

    async def test_execute_nonexistent(self, manager: ToolManager, tools_dir: Path):
        await manager.load_tools()

        result = await manager.execute_tool("nonexistent", {})
        assert result.success is False
        assert "not found" in result.error.lower()

    async def test_execute_passes_params(self, manager: ToolManager, tools_dir: Path):
        _write_tool(tools_dir, "test")
        await manager.load_tools()

        result = await manager.execute_tool("test", {"key": "value"})
        assert result.success is True
        assert result.output["params"] == {"key": "value"}

    async def test_execute_unsupported_executor(self, manager: ToolManager, tools_dir: Path):
        _write_tool(tools_dir, "remote", executor={"type": "remote_http", "timeout": 5})
        await manager.load_tools()

        result = await manager.execute_tool("remote", {})
        assert result.success is False
        assert "unsupported" in result.error.lower()


# ──────────────────────────────────────────────
# 元数据获取测试
# ──────────────────────────────────────────────


class TestGetAllTools:
    async def test_empty(self, manager: ToolManager):
        assert manager.get_all_tools() == []

    async def test_returns_all_fields(self, manager: ToolManager, tools_dir: Path):
        _write_tool(tools_dir, "full", name="Full Tool", category="test")
        await manager.load_tools()
        tools = manager.get_all_tools()
        assert len(tools) == 1
        tool = tools[0]
        assert tool["tool_id"] == "full"
        assert tool["name"] == "Full Tool"
        assert tool["category"] == "test"
        assert "version" in tool
        assert "permission_level" in tool
        assert "enabled" in tool
        assert "executor_type" in tool


# ──────────────────────────────────────────────
# 集成测试：使用真实配置文件
# ──────────────────────────────────────────────


class TestWithRealConfigs:
    """使用项目中实际的配置文件进行测试"""

    async def test_load_real_skills(self):
        """测试加载 configs/Plugins/skills/ 中的实际配置"""
        manager = SkillManager(skills_dir="configs/Plugins/skills")
        await manager.load_skills()
        skills = manager.get_all_skills()

        # 至少应该有 3 个 skill
        skill_ids = {s["skill_id"] for s in skills}
        assert "emotional_comfort" in skill_ids
        assert "daily_chat" in skill_ids
        assert "creative_storytelling" in skill_ids

    async def test_real_skill_prompts(self):
        """测试实际 skill 的 prompt_template 不为空"""
        manager = SkillManager(skills_dir="configs/Plugins/skills")
        await manager.load_skills()

        for skill in manager.get_all_skills():
            prompt = manager.get_skill_prompt(skill["skill_id"])
            assert prompt is not None
            assert len(prompt) > 0

    async def test_load_real_tools(self):
        """测试加载 configs/Plugins/tools/ 中的实际配置"""
        manager = ToolManager(tools_dir="configs/Plugins/tools")
        await manager.load_tools()
        tools = manager.get_all_tools()

        tool_ids = {t["tool_id"] for t in tools}
        assert "get_weather" in tool_ids
        assert "set_reminder" in tool_ids

    async def test_real_tool_schemas(self):
        """测试实际 tool 的 schema 符合 OpenAI Function Calling 格式"""
        manager = ToolManager(tools_dir="configs/Plugins/tools")
        await manager.load_tools()

        schema = manager.get_tool_schema("get_weather")
        assert schema is not None
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "get_weather"
        assert "city" in schema["function"]["parameters"]["properties"]

        schema = manager.get_tool_schema("set_reminder")
        assert schema is not None
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "set_reminder"
        params = schema["function"]["parameters"]["properties"]
        assert "content" in params
        assert "time" in params

    async def test_real_skill_matching(self):
        """测试实际 skill 的匹配逻辑"""
        manager = SkillManager(skills_dir="configs/Plugins/skills")
        await manager.load_skills()

        # 情感相关意图应该匹配到 emotional_comfort
        matched = manager.get_skills_for_context(
            intent="", emotion="sadness", capability_domains=["emotional_care"]
        )
        assert "emotional_comfort" in matched

        # 创意相关应该匹配到 creative_storytelling
        matched = manager.get_skills_for_context(
            intent="想听故事", emotion="", capability_domains=["creative_storytelling"]
        )
        assert "creative_storytelling" in matched
