"""YuanBot Tools 管理器测试"""

from __future__ import annotations

from typing import Any

import pytest

from yuanbot.core.interfaces import ToolModule
from yuanbot.core.types import ToolDefinition, ToolResult
from yuanbot.tools.manager import ToolManager


class MockTool(ToolModule):
    def __init__(
        self,
        name: str = "test_tool",
        description: str = "测试工具",
        permission: str = "safe",
        result_output: Any = "ok",
        should_fail: bool = False,
    ):
        self._name = name
        self._description = description
        self._permission = permission
        self._result_output = result_output
        self._should_fail = should_fail

    def get_schema(self) -> ToolDefinition:
        return ToolDefinition(
            name=self._name,
            description=self._description,
            parameters={"type": "object"},
            permission_level=self._permission,
        )

    async def invoke(
        self,
        params: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> ToolResult:
        if self._should_fail:
            raise RuntimeError("Tool failed")
        return ToolResult(
            tool_id=self._name,
            success=True,
            output=self._result_output,
        )

    @property
    def permission_level(self) -> str:
        return self._permission


@pytest.fixture
def manager():
    return ToolManager()


class TestRegisterTool:
    def test_register(self, manager: ToolManager):
        tool = MockTool(name="search")
        manager.register_tool(tool)
        assert manager.get_tool("search") is tool

    def test_definitions_cached(self, manager: ToolManager):
        tool = MockTool(name="search", description="搜索")
        manager.register_tool(tool)
        defs = manager.get_definitions()
        assert len(defs) == 1
        assert defs[0].name == "search"

    def test_register_multiple(self, manager: ToolManager):
        manager.register_tool(MockTool(name="t1"))
        manager.register_tool(MockTool(name="t2"))
        assert len(manager.get_definitions()) == 2


class TestGetTool:
    def test_existing(self, manager: ToolManager):
        tool = MockTool(name="test")
        manager.register_tool(tool)
        assert manager.get_tool("test") is tool

    def test_nonexistent(self, manager: ToolManager):
        assert manager.get_tool("nonexistent") is None


class TestGetDefinitions:
    def test_all(self, manager: ToolManager):
        manager.register_tool(MockTool(name="t1"))
        manager.register_tool(MockTool(name="t2"))
        defs = manager.get_definitions()
        assert len(defs) == 2

    def test_filtered(self, manager: ToolManager):
        manager.register_tool(MockTool(name="t1"))
        manager.register_tool(MockTool(name="t2"))
        manager.register_tool(MockTool(name="t3"))
        defs = manager.get_definitions(names=["t1", "t3"])
        assert len(defs) == 2
        names = {d.name for d in defs}
        assert names == {"t1", "t3"}

    def test_filtered_with_nonexistent(self, manager: ToolManager):
        manager.register_tool(MockTool(name="t1"))
        defs = manager.get_definitions(names=["t1", "nonexistent"])
        assert len(defs) == 1

    def test_empty_manager(self, manager: ToolManager):
        assert manager.get_definitions() == []


class TestInvokeTool:
    @pytest.mark.asyncio
    async def test_invoke_success(self, manager: ToolManager):
        tool = MockTool(name="search", result_output={"results": []})
        manager.register_tool(tool)

        result = await manager.invoke_tool("search", {"q": "test"})
        assert result.success is True
        assert result.output == {"results": []}

    @pytest.mark.asyncio
    async def test_invoke_nonexistent(self, manager: ToolManager):
        result = await manager.invoke_tool("nonexistent", {})
        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_invoke_with_exception(self, manager: ToolManager):
        tool = MockTool(name="fail", should_fail=True)
        manager.register_tool(tool)

        result = await manager.invoke_tool("fail", {})
        assert result.success is False
        assert "Tool failed" in result.error

    @pytest.mark.asyncio
    async def test_invoke_with_context(self, manager: ToolManager):
        tool = MockTool(name="ctx_tool")
        manager.register_tool(tool)

        result = await manager.invoke_tool("ctx_tool", {"key": "val"}, {"user": "u1"})
        assert result.success is True
