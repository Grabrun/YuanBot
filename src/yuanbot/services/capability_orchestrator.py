"""能力调用编排器

独立模块，管理 Skills 的动态注入和 Tools 的执行循环。
连接人格决策系统与能力扩展系统。

设计参考: persona-decision-system.md 第3.8节 + capability-tool-system.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from yuanbot.core.types import (
    Message,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from yuanbot.gateway.jwt_auth import JWTAuthManager, TokenPayload
from yuanbot.services.ai_service import AIService
from yuanbot.services.domain_matcher import DomainMatcher, DomainMatchResult
from yuanbot.skills.manager import SkillManager
from yuanbot.tools.manager import ToolManager

logger = structlog.get_logger(__name__)

# 最大工具调用循环次数，防止无限循环
_MAX_TOOL_CALL_ROUNDS = 5


@dataclass
class LoadedCapabilities:
    """已加载的能力集合"""

    skill_prompts: list[str] = field(default_factory=list)  # 注入的 Skill 提示词
    tool_definitions: list[ToolDefinition] = field(default_factory=list)  # Tool Schema
    tool_ids: list[str] = field(default_factory=list)  # 对应的 Tool ID 列表


@dataclass
class ToolExecutionLoopResult:
    """工具执行循环结果"""

    final_response: str  # 最终回复文本
    tool_calls_made: int  # 执行的工具调用次数
    tool_results: list[ToolResult] = field(default_factory=list)  # 工具执行结果


class CapabilityOrchestrator:
    """能力调用编排器

    职责：
    1. 根据决策结果加载 Skill 提示词和 Tool Schema
    2. 管理 Tool 执行循环（LLM → tool_calls → 执行 → 重新推理）
    3. 安全策略检查（权限验证，JWT scope 集成）
    4. 将工具结果反馈给对话历史
    5. 能力域匹配（DomainMatcher 集成）

    设计参考:
    - persona-decision-system.md 3.8 能力调用编排器
    - capability-tool-system.md 5.3 Tools 调用流程
    - capability-tool-system.md 7.3 权限级别
    """

    def __init__(
        self,
        skill_manager: SkillManager,
        tool_manager: ToolManager,
        ai_service: AIService,
        domain_matcher: DomainMatcher | None = None,
        jwt_auth_manager: JWTAuthManager | None = None,
    ):
        self._skills = skill_manager
        self._tools = tool_manager
        self._ai = ai_service
        self._domain_matcher = domain_matcher or DomainMatcher()
        self._jwt_auth = jwt_auth_manager

    def match_domains(
        self,
        intent: str = "",
        emotion: str = "",
        capability_domains: list[str] | None = None,
    ) -> DomainMatchResult:
        """执行能力域匹配

        委托给 DomainMatcher，返回匹配结果用于指导 Skill/Tool 加载。

        Args:
            intent: 用户意图
            emotion: 情感标签
            capability_domains: 人设能力域声明

        Returns:
            DomainMatchResult: 匹配结果
        """
        return self._domain_matcher.match(
            intent=intent,
            emotion=emotion,
            capability_domains=capability_domains,
        )

    async def load_capabilities(
        self,
        skill_ids: list[str],
        tool_ids: list[str],
        capability_domains: list[str] | None = None,
    ) -> LoadedCapabilities:
        """加载能力集

        根据决策引擎选定的 Skill ID 和 Tool ID，
        加载完整的 Skill 提示词和 Tool Schema。

        Args:
            skill_ids: 决策引擎推荐的 Skill ID 列表
            tool_ids: 决策引擎推荐的 Tool ID 列表
            capability_domains: 人设的能力域声明（用于补充匹配）

        Returns:
            LoadedCapabilities: 已加载的能力集合
        """
        loaded = LoadedCapabilities()

        # 加载 Skill 提示词
        for skill_id in skill_ids:
            prompt = self._skills.get_skill_prompt(skill_id)
            if prompt:
                loaded.skill_prompts.append(prompt)
                logger.debug("skill_loaded", skill_id=skill_id)

        # 加载 Tool Schema
        for tool_id in tool_ids:
            schema = self._tools.get_tool_schema(tool_id)
            if schema:
                tool_def = self._schema_to_tool_definition(schema)
                loaded.tool_definitions.append(tool_def)
                loaded.tool_ids.append(tool_id)
                logger.debug("tool_loaded", tool_id=tool_id)

        logger.info(
            "capabilities_loaded",
            skill_count=len(loaded.skill_prompts),
            tool_count=len(loaded.tool_definitions),
        )
        return loaded

    async def execute_tool_loop(
        self,
        messages: list[Message],
        tool_definitions: list[ToolDefinition],
        tool_ids: list[str],
        system_prompt: str | None = None,
        max_rounds: int = _MAX_TOOL_CALL_ROUNDS,
        token_payload: TokenPayload | None = None,
    ) -> ToolExecutionLoopResult:
        """执行工具调用循环

        流程：
        1. 调用 LLM（携带 Tool 定义）
        2. 如果 LLM 返回 tool_calls，执行工具
        3. 将工具结果追加到对话历史
        4. 重复 1-3 直到无 tool_calls 或达到最大轮次
        5. 返回最终回复

        Args:
            messages: 对话消息列表
            tool_definitions: 可用的工具定义
            tool_ids: 对应的工具 ID 列表
            system_prompt: 系统提示词
            max_rounds: 最大循环次数
            token_payload: JWT token 载荷（用于权限验证）

        Returns:
            ToolExecutionLoopResult: 执行结果
        """
        result = ToolExecutionLoopResult(final_response="", tool_calls_made=0)
        current_messages = list(messages)
        tool_id_map = {
            td.name: tid for td, tid in zip(tool_definitions, tool_ids)
        }

        for round_num in range(max_rounds):
            # 调用 LLM
            response = await self._ai.generate(
                messages=current_messages,
                tools=tool_definitions if tool_definitions else None,
                system_prompt=system_prompt,
            )

            # 如果没有工具调用，返回最终回复
            if not response.tool_calls:
                result.final_response = response.content or ""
                logger.info(
                    "tool_loop_completed",
                    rounds=round_num + 1,
                    tool_calls=result.tool_calls_made,
                )
                return result

            # 有工具调用，逐个执行
            # 先将 assistant 的回复（含 tool_calls）加入历史
            current_messages.append(
                Message(
                    role="assistant",
                    content=response.content,
                    tool_calls=response.tool_calls,
                )
            )

            for tool_call in response.tool_calls:
                tool_name = tool_call.function.name
                tool_id = tool_id_map.get(tool_name, tool_name)

                # 安全策略检查
                if not self._check_permission(tool_id, token_payload):
                    tool_result = ToolResult(
                        tool_id=tool_id,
                        success=False,
                        error=f"Permission denied for tool '{tool_name}'",
                    )
                else:
                    # 执行工具
                    tool_result = await self._tools.execute_tool(
                        tool_id=tool_id,
                        params=self._parse_tool_arguments(tool_call),
                    )

                result.tool_results.append(tool_result)
                result.tool_calls_made += 1

                # 将工具结果追加到对话历史
                current_messages.append(
                    Message(
                        role="tool",
                        content=self._format_tool_result(tool_result),
                        tool_call_id=tool_call.id,
                    )
                )

                logger.debug(
                    "tool_executed",
                    tool_name=tool_name,
                    success=tool_result.success,
                )

        # 达到最大轮次
        logger.warning("tool_loop_max_rounds_reached", max_rounds=max_rounds)
        result.final_response = current_messages[-1].content or ""
        return result

    def _check_permission(
        self,
        tool_id: str,
        token_payload: TokenPayload | None = None,
    ) -> bool:
        """检查工具调用权限

        权限级别:
        - readonly: 默认允许
        - user_data: 需要 user_data 或 system scope
        - system: 需要 system scope

        集成 JWT scope 验证（当 jwt_auth_manager 可用时）。

        设计参考: capability-tool-system.md 7.3 权限级别
        """
        # 获取工具配置
        all_tools = self._tools.get_all_tools()
        for tool_info in all_tools:
            if tool_info["tool_id"] == tool_id:
                level = tool_info.get("permission_level", "readonly")

                # JWT scope 验证
                if self._jwt_auth and token_payload:
                    from yuanbot.gateway.jwt_auth import InsufficientScopeError

                    try:
                        self._jwt_auth.require_scope(token_payload, level)
                        return True
                    except InsufficientScopeError:
                        logger.warning(
                            "tool_jwt_scope_denied",
                            tool_id=tool_id,
                            required_scope=level,
                            user_scopes=token_payload.scopes,
                        )
                        return False
                    except ValueError:
                        # 无效的 scope 级别，回退到简单检查
                        pass

                # 回退：简单权限检查
                if level == "system":
                    logger.warning("tool_permission_denied", tool_id=tool_id)
                    return False
                return True
        # 未知工具默认允许（向后兼容）
        return True

    @staticmethod
    def _parse_tool_arguments(tool_call: ToolCall) -> dict[str, Any]:
        """解析工具调用参数"""
        import json

        try:
            return json.loads(tool_call.function.arguments)
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "tool_args_parse_failed",
                arguments=tool_call.function.arguments,
            )
            return {}

    @staticmethod
    def _format_tool_result(result: ToolResult) -> str:
        """格式化工具执行结果为 LLM 可理解的文本"""
        import json

        if result.success:
            if isinstance(result.output, str):
                return result.output
            try:
                return json.dumps(result.output, ensure_ascii=False)
            except (TypeError, ValueError):
                return str(result.output)
        else:
            return f"工具执行失败: {result.error}"

    @staticmethod
    def _schema_to_tool_definition(schema: dict[str, Any]) -> ToolDefinition:
        """将 YAML 中的 schema 转换为 ToolDefinition"""
        func = schema.get("function", schema)
        return ToolDefinition(
            name=func.get("name", "unknown"),
            description=func.get("description", ""),
            parameters=func.get("parameters", {"type": "object", "properties": {}}),
        )
