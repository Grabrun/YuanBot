"""YuanBot Tools 管理器

实现工具的动态加载和沙盒隔离执行。
"""

from __future__ import annotations

from typing import Any

import structlog

from yuanbot.core.interfaces import ToolModule
from yuanbot.core.types import ToolDefinition, ToolResult

logger = structlog.get_logger(__name__)


class ToolManager:
    """Tools 动态管理器"""

    def __init__(self):
        self._tools: dict[str, ToolModule] = {}
        self._definitions_cache: dict[str, ToolDefinition] = {}

    def register_tool(self, tool: ToolModule) -> None:
        """注册 Tool 模块"""
        schema = tool.get_schema()
        self._tools[schema.name] = tool
        self._definitions_cache[schema.name] = schema
        logger.info("tool_registered", name=schema.name, level=tool.permission_level)

    def get_tool(self, name: str) -> ToolModule | None:
        """获取 Tool 模块"""
        return self._tools.get(name)

    def get_definitions(
        self,
        names: list[str] | None = None,
    ) -> list[ToolDefinition]:
        """获取工具定义列表

        如果指定 names，只返回指定工具的定义；
        否则返回所有已注册工具的定义。
        """
        if names:
            return [self._definitions_cache[n] for n in names if n in self._definitions_cache]
        return list(self._definitions_cache.values())

    async def invoke_tool(
        self,
        name: str,
        params: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> ToolResult:
        """调用工具"""
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(
                tool_id=name,
                success=False,
                error=f"Tool '{name}' not found",
            )

        try:
            result = await tool.invoke(params, context)
            logger.info("tool_invoked", name=name, success=result.success)
            return result
        except Exception as e:
            logger.error("tool_invocation_error", name=name, error=str(e))
            return ToolResult(
                tool_id=name,
                success=False,
                error=str(e),
            )
