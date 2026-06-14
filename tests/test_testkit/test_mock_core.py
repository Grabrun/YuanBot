"""MockCore 单元测试"""
from __future__ import annotations

import pytest

from yuanbot.core.types import (
    ChatChunk,
    ChatResponse,
    MemoryNode,
    MemorySearchResult,
    MemoryType,
    Message,
)
from yuanbot_testkit import MockCore


@pytest.mark.asyncio
async def test_chat_completion_default_response(mock_core: MockCore):
    """未配置响应时，chat_completion 返回默认值"""
    result = await mock_core.chat_completion(
        messages=[Message(role="user", content="Hi")]
    )
    assert isinstance(result, ChatResponse)
    assert result.content is not None


@pytest.mark.asyncio
async def test_chat_completion_configured_response(mock_core: MockCore):
    """配置响应后，chat_completion 返回配置值"""
    expected = ChatResponse(content="你好！")
    mock_core.mock_response("chat_completion", expected)

    result = await mock_core.chat_completion(
        messages=[Message(role="user", content="你好")]
    )
    assert result == expected
    assert result.content == "你好！"


@pytest.mark.asyncio
async def test_chat_completion_records_call(mock_core: MockCore):
    """chat_completion 记录调用历史"""
    messages = [Message(role="user", content="What's up?")]
    await mock_core.chat_completion(messages=messages, temperature=0.5)

    assert len(mock_core.calls) == 1
    call = mock_core.calls[0]
    assert call.method == "chat_completion"
    assert call.kwargs["messages"] == messages
    assert call.kwargs["temperature"] == 0.5


@pytest.mark.asyncio
async def test_stream_chat_completion(mock_core: MockCore):
    """流式 chat completion 正常工作"""
    chunks = []
    async for chunk in mock_core.stream_chat_completion(
        messages=[Message(role="user", content="Hi")]
    ):
        chunks.append(chunk)

    assert len(chunks) == 1
    assert isinstance(chunks[0], ChatChunk)


@pytest.mark.asyncio
async def test_get_embedding_default(mock_core: MockCore):
    """get_embedding 未配置时返回默认零向量"""
    result = await mock_core.get_embedding(text="Hello")
    assert isinstance(result, list)
    assert all(v == 0.0 for v in result)
    assert len(result) == 384


@pytest.mark.asyncio
async def test_get_embedding_configured(mock_core: MockCore):
    """get_embedding 返回配置值"""
    expected = [0.1, 0.2, 0.3]
    mock_core.mock_response("get_embedding", expected)
    result = await mock_core.get_embedding(text="Hello")
    assert result == expected


@pytest.mark.asyncio
async def test_get_embedding_records_call(mock_core: MockCore):
    """get_embedding 记录调用历史"""
    await mock_core.get_embedding(text="test text", model="test-model")
    assert len(mock_core.calls) == 1
    assert mock_core.calls[0].method == "get_embedding"
    assert mock_core.calls[0].kwargs["text"] == "test text"


@pytest.mark.asyncio
async def test_get_memory_default(mock_core: MockCore):
    """get_memory 未配置时返回空列表"""
    result = await mock_core.get_memory(query="test")
    assert result == []


@pytest.mark.asyncio
async def test_get_memory_configured(mock_core: MockCore):
    """get_memory 返回配置值"""
    expected = [
        MemorySearchResult(
            node=MemoryNode(content="test", memory_type=MemoryType.FACT),
            score=0.9,
            match_type="semantic",
        )
    ]
    mock_core.mock_response("get_memory", expected)
    result = await mock_core.get_memory(query="test")
    assert result == expected


@pytest.mark.asyncio
async def test_add_memory(mock_core: MockCore):
    """add_memory 返回 MemoryNode"""
    result = await mock_core.add_memory(content="这是一条测试记忆")
    assert isinstance(result, MemoryNode)
    assert result.content == "这是一条测试记忆"
    assert result.importance_score == 0.5


@pytest.mark.asyncio
async def test_add_memory_records_call(mock_core: MockCore):
    """add_memory 记录调用"""
    await mock_core.add_memory(content="test", memory_type="fact", importance=0.8)
    assert len(mock_core.calls) == 1
    assert mock_core.calls[0].method == "add_memory"
    assert mock_core.calls[0].kwargs["importance"] == 0.8


@pytest.mark.asyncio
async def test_execute_tool(mock_core: MockCore):
    """execute_tool 返回默认 ToolResult"""
    result = await mock_core.execute_tool("test_tool", {"arg": "value"})
    assert result.success
    assert result.tool_id == "test_tool"


@pytest.mark.asyncio
async def test_call_count_filtering(mock_core: MockCore):
    """get_call_count 支持按方法名过滤"""
    await mock_core.chat_completion(messages=[Message(role="user", content="Hi")])
    await mock_core.get_embedding(text="Hi")
    await mock_core.chat_completion(messages=[Message(role="user", content="Hi again")])

    assert mock_core.get_call_count() == 3
    assert mock_core.get_call_count("chat_completion") == 2
    assert mock_core.get_call_count("get_embedding") == 1


@pytest.mark.asyncio
async def test_get_calls_by_method(mock_core: MockCore):
    """get_calls_by_method 按方法名过滤调用记录"""
    await mock_core.chat_completion(messages=[Message(role="user", content="Hi")])
    await mock_core.get_embedding(text="Hi")

    calls = mock_core.get_calls_by_method("chat_completion")
    assert len(calls) == 1
    assert calls[0].method == "chat_completion"


def test_reset_all(mock_core: MockCore):
    """reset_all 清空所有状态"""
    mock_core.mock_response("chat_completion", ChatResponse(content="test"))
    mock_core.reset_all()
    assert len(mock_core.calls) == 0
    assert mock_core._get_response("chat_completion") is None


def test_clear_calls(mock_core: MockCore):
    """clear_calls 只清空调用记录，保留 mock 响应"""
    mock_core.mock_response("chat_completion", ChatResponse(content="test"))
    mock_core._record("chat_completion")
    mock_core.clear_calls()
    assert len(mock_core.calls) == 0
    assert mock_core._get_response("chat_completion") is not None


def test_clear_mock_responses(mock_core: MockCore):
    """clear_mock_responses 只清空 mock 响应，保留调用记录"""
    mock_core.mock_response("chat_completion", ChatResponse(content="test"))
    mock_core._record("chat_completion")
    mock_core.clear_mock_responses()
    assert mock_core._get_response("chat_completion") is None
    assert len(mock_core.calls) == 1


@pytest.mark.asyncio
async def test_mock_responses_bulk(mock_core: MockCore):
    """批量设置 mock 响应"""
    mock_core.mock_responses({
        "chat_completion": ChatResponse(content="test"),
        "get_embedding": [0.5, 0.5],
    })
    result1 = await mock_core.chat_completion(messages=[Message(role="user", content="Hi")])
    result2 = await mock_core.get_embedding(text="Hi")
    assert result1.content == "test"
    assert result2 == [0.5, 0.5]


@pytest.mark.asyncio
async def test_set_default_embedding_size(mock_core: MockCore):
    """set_default_embedding_size 修改默认向量维度"""
    mock_core.set_default_embedding_size(128)
    result = await mock_core.get_embedding(text="Hi")
    assert len(result) == 128
