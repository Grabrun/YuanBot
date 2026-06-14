"""YuanBot Tools 管理器

扫描 configs/Plugins/tools/ 目录加载 YAML 定义，
根据意图获取可用的 Tool Schema（OpenAI Function Calling 格式）。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog
import yaml

from yuanbot.core.types import ToolResult

logger = structlog.get_logger(__name__)


class ToolManager:
    """Tool 管理器 - 扫描 configs/Plugins/tools/ 加载 YAML 定义"""

    def __init__(self, tools_dir: str = "configs/Plugins/tools"):
        self._tools_dir = Path(tools_dir)
        self._tool_configs: dict[str, dict] = {}  # tool_id -> config
        self._tool_schemas: dict[str, dict] = {}  # tool_id -> Function Calling Schema

    async def load_tools(self) -> None:
        """扫描目录加载所有 *.yaml Tool 配置"""
        if not self._tools_dir.exists():
            logger.warning("tools_dir_not_found", path=str(self._tools_dir))
            return

        for yaml_file in sorted(self._tools_dir.glob("*.yaml")):
            try:
                with open(yaml_file, encoding="utf-8") as f:
                    config = yaml.safe_load(f)
            except (yaml.YAMLError, OSError) as exc:
                logger.error(
                    "tool_load_failed",
                    file=str(yaml_file),
                    error=str(exc),
                )
                continue

            if not isinstance(config, dict):
                logger.warning("tool_invalid_format", file=str(yaml_file))
                continue

            # 检查 enabled 字段（默认为 True）
            if not config.get("enabled", True):
                logger.info("tool_disabled", file=str(yaml_file))
                continue

            tool_id = config.get("tool_id")
            if not tool_id:
                logger.warning("tool_missing_id", file=str(yaml_file))
                continue

            self._tool_configs[tool_id] = config

            # 解析 schema（OpenAI Function Calling 格式）
            schema = config.get("schema")
            if isinstance(schema, dict):
                self._tool_schemas[tool_id] = schema

            logger.info(
                "tool_loaded",
                tool_id=tool_id,
                name=config.get("name", ""),
                category=config.get("category", ""),
            )

    def get_tools_for_intent(self, intent: str) -> list[dict]:
        """根据意图获取可用的 Tool Schema 列表（OpenAI Function Calling 格式）"""
        result = []
        for tool_id, config in self._tool_configs.items():
            tags = config.get("capability_tags", [])
            category = config.get("category", "")

            # 简单匹配：意图包含 category 或 capability_tags 中的标签
            if category and category in intent:
                schema = self._tool_schemas.get(tool_id)
                if schema:
                    result.append(schema)
                continue

            if any(tag in intent for tag in tags):
                schema = self._tool_schemas.get(tool_id)
                if schema:
                    result.append(schema)

        return result

    def get_tool_schema(self, tool_id: str) -> dict | None:
        """获取 Tool 的 Function Calling Schema"""
        return self._tool_schemas.get(tool_id)

    async def execute_tool(self, tool_id: str, params: dict) -> ToolResult:
        """执行工具调用（本地受限执行）"""
        config = self._tool_configs.get(tool_id)
        if not config:
            return ToolResult(
                tool_id=tool_id,
                success=False,
                error=f"Tool '{tool_id}' not found",
            )

        executor_cfg = config.get("executor", {})
        executor_type = executor_cfg.get("type", "local_thread")
        timeout = executor_cfg.get("timeout", 10)

        if executor_type == "local_thread":
            return await self._execute_local(tool_id, params, timeout)

        return ToolResult(
            tool_id=tool_id,
            success=False,
            error=f"Unsupported executor type: {executor_type}",
        )

    async def _execute_local(
        self,
        tool_id: str,
        params: dict,
        timeout: int,
    ) -> ToolResult:
        """在线程池中本地执行工具（模拟受限沙盒）"""
        try:
            loop = asyncio.get_running_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, self._sync_execute, tool_id, params),
                timeout=timeout,
            )
            return result
        except TimeoutError:
            return ToolResult(
                tool_id=tool_id,
                success=False,
                error=f"Tool '{tool_id}' execution timed out after {timeout}s",
            )
        except Exception as exc:
            logger.error("tool_execution_error", tool_id=tool_id, error=str(exc))
            return ToolResult(
                tool_id=tool_id,
                success=False,
                error=str(exc),
            )

    def _sync_execute(self, tool_id: str, params: dict) -> ToolResult:
        """同步执行（在线程池中运行）

        根据 executor.handler 配置动态导入并调用对应的执行器函数。
        handler 格式: "yuanbot.tools.builtin.search_executor"
        """
        config = self._tool_configs.get(tool_id, {})
        executor_cfg = config.get("executor", {})
        handler_path = executor_cfg.get("handler")

        if handler_path:
            try:
                module_path, func_name = handler_path.rsplit(".", 1)
                import importlib

                module = importlib.import_module(module_path)
                handler_func = getattr(module, func_name)

                # handler 可能是同步或异步函数
                import asyncio

                if asyncio.iscoroutinefunction(handler_func):
                    loop = asyncio.new_event_loop()
                    try:
                        result = loop.run_until_complete(handler_func(params))
                    finally:
                        loop.close()
                else:
                    result = handler_func(params)

                return ToolResult(
                    tool_id=tool_id,
                    success=result.get("success", True),
                    output=result,
                    error=result.get("error"),
                )
            except Exception as exc:
                logger.error(
                    "tool_handler_error",
                    tool_id=tool_id,
                    handler=handler_path,
                    error=str(exc),
                )
                return ToolResult(
                    tool_id=tool_id,
                    success=False,
                    error=f"Handler error: {exc}",
                )

        # Fallback: 占位实现
        schema = self._tool_schemas.get(tool_id, {})
        func_name = schema.get("function", {}).get("name", tool_id)

        return ToolResult(
            tool_id=tool_id,
            success=True,
            output={
                "function": func_name,
                "params": params,
                "note": "No handler configured",
            },
        )

    def get_all_tools(self) -> list[dict]:
        """获取所有已注册 Tool 的元数据"""
        result = []
        for tool_id, config in self._tool_configs.items():
            result.append(
                {
                    "tool_id": tool_id,
                    "name": config.get("name", ""),
                    "version": config.get("version", "1.0.0"),
                    "category": config.get("category", ""),
                    "permission_level": config.get("permission_level", "readonly"),
                    "enabled": config.get("enabled", True),
                    "executor_type": config.get("executor", {}).get("type", "local_thread"),
                }
            )
        return result
