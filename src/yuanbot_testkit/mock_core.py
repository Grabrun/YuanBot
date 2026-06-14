"""MockCore — 用于扩展测试的模拟核心

提供可配置的 mock 实现，模拟 AI 对话、向量嵌入和记忆检索。
记录所有调用历史，便于编写断言。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from yuanbot.core.types import (
    ChatChunk,
    ChatResponse,
    MemoryNode,
    MemorySearchResult,
    MemoryType,
    Message,
    ToolDefinition,
    ToolResult,
)


@dataclass
class CallRecord:
    """单次调用记录"""

    method: str
    args: dict[str, Any]
    kwargs: dict[str, Any]
    result: Any = None


class MockCore:
    """模拟 YuanBot 核心服务

    在测试中替代真实的核心模块（AIService、MemoryManager 等），
    让扩展/Adapter/Skill 的测试无需连接真实 LLM 或数据库即可运行。

    用法::

        core = MockCore()
        core.mock_response("chat_completion", ChatResponse(content="你好！"))
        result = await core.chat_completion(messages=[Message(role="user", content="Hi")])
        assert result.content == "你好！"
        assert core.calls[0].method == "chat_completion"
    """

    def __init__(self) -> None:
        self._mock_responses: dict[str, Any] = {}
        self._calls: list[CallRecord] = []
        self._default_embedding_size: int = 384

    # ── 配置接口 ──────────────────────────────

    def mock_response(self, method: str, response: Any) -> None:
        """设置指定方法的返回 mock 值

        Args:
            method: 方法名（如 "chat_completion", "get_embedding"）
            response: 该方法的返回值
        """
        self._mock_responses[method] = response

    def mock_responses(self, responses: dict[str, Any]) -> None:
        """批量设置 mock 返回值"""
        self._mock_responses.update(responses)

    def set_default_embedding_size(self, size: int) -> None:
        """设置默认嵌入向量维度"""
        self._default_embedding_size = size

    @property
    def calls(self) -> list[CallRecord]:
        """所有历史调用记录，用于断言"""
        return list(self._calls)

    def clear_calls(self) -> None:
        """清空调用记录"""
        self._calls.clear()

    def clear_mock_responses(self) -> None:
        """清空已配置的 mock 响应"""
        self._mock_responses.clear()

    def reset_all(self) -> None:
        """重置所有状态（调用记录和 mock 响应）"""
        self._calls.clear()
        self._mock_responses.clear()

    def get_call_count(self, method: str | None = None) -> int:
        """获取调用次数

        Args:
            method: 如果指定，只统计该方法的调用次数

        Returns:
            调用次数
        """
        if method:
            return sum(1 for c in self._calls if c.method == method)
        return len(self._calls)

    def get_calls_by_method(self, method: str) -> list[CallRecord]:
        """获取指定方法的所有调用记录"""
        return [c for c in self._calls if c.method == method]

    def _record(
        self, method: str, args: dict[str, Any] | None = None, **kwargs: Any
    ) -> None:
        """记录一次调用"""
        self._calls.append(
            CallRecord(method=method, args=args or {}, kwargs=kwargs)
        )

    def _get_response(self, method: str, default: Any = None) -> Any:
        """获取已配置的 mock 响应，没有则返回默认值"""
        return self._mock_responses.get(method, default)

    # ── AI 对话接口 ───────────────────────────

    async def chat_completion(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system_prompt: str | None = None,
        model: str | None = None,
    ) -> ChatResponse:
        """模拟 AI 对话完成

        Args:
            messages: 对话消息列表
            tools: 可用工具定义
            temperature: 温度参数
            max_tokens: 最大输出 Token 数
            system_prompt: 系统提示词
            model: 模型标识
        """
        self._record(
            "chat_completion",
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            model=model,
        )
        response = self._get_response("chat_completion")
        if response is not None:
            return response
        # 默认返回简单响应
        return ChatResponse(
            content="这是 MockCore 的默认响应",
            finish_reason="stop",
            model=model or "mock-model",
        )

    async def stream_chat_completion(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system_prompt: str | None = None,
        model: str | None = None,
    ) -> AsyncIterator[ChatChunk]:
        """模拟流式对话完成

        如果配置了 mock 响应且为 AsyncIterator，则使用该迭代器；
        否则 yield 一个默认的 ChatChunk。
        """
        self._record(
            "stream_chat_completion",
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            model=model,
        )
        response = self._get_response("stream_chat_completion")
        if response is not None:
            async for chunk in response:
                yield chunk
        else:
            yield ChatChunk(delta_content="默认流式响应")

    # ── 向量嵌入接口 ──────────────────────────

    async def get_embedding(
        self,
        text: str,
        model: str | None = None,
    ) -> list[float]:
        """模拟文本向量嵌入

        Args:
            text: 待嵌入文本
            model: 嵌入模型标识
        """
        self._record("get_embedding", text=text, model=model)
        response = self._get_response("get_embedding")
        if response is not None:
            return response
        return [0.0] * self._default_embedding_size

    # ── 记忆接口 ──────────────────────────────

    async def get_memory(
        self,
        query: str,
        user_id: str | None = None,
        limit: int = 10,
    ) -> list[MemorySearchResult]:
        """模拟记忆检索

        Args:
            query: 检索查询
            user_id: 用户 ID（可选）
            limit: 返回结果数量上限
        """
        self._record("get_memory", query=query, user_id=user_id, limit=limit)
        response = self._get_response("get_memory")
        if response is not None:
            return response
        return []

    async def add_memory(
        self,
        content: str,
        memory_type: str = "working",
        user_id: str | None = None,
        importance: float = 0.5,
    ) -> MemoryNode:
        """模拟记忆存储

        Args:
            content: 记忆内容
            memory_type: 记忆类型
            user_id: 用户 ID
            importance: 重要度 0.0~1.0
        """
        self._record(
            "add_memory",
            content=content,
            memory_type=memory_type,
            user_id=user_id,
            importance=importance,
        )
        response = self._get_response("add_memory")
        if response is not None:
            return response
        from datetime import datetime

        try:
            mt = MemoryType(memory_type)
        except ValueError:
            mt = MemoryType.WORKING
        return MemoryNode(
            content=content,
            memory_type=mt,
            importance_score=importance,
            topic_tags=[],
            key_entities=[],
            created_at=datetime.now(),
            last_accessed=datetime.now(),
        )

    # ── 工具调用接口 ──────────────────────────

    async def execute_tool(
        self,
        tool_name: str,
        params: dict[str, Any],
    ) -> ToolResult:
        """模拟工具执行

        Args:
            tool_name: 工具名称
            params: 工具参数
        """
        self._record("execute_tool", tool_name=tool_name, params=params)
        response = self._get_response("execute_tool")
        if response is not None:
            return response
        return ToolResult(
            tool_id=tool_name,
            success=True,
            output=f"MockTool {tool_name} executed",
        )
