"""YuanBot 核心数据类型定义"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# 消息相关类型
# ──────────────────────────────────────────────

class ContentType(str, Enum):
    """消息内容类型"""
    TEXT = "text"
    IMAGE = "image"
    VOICE = "voice"
    VIDEO = "video"
    FILE = "file"


class Message(BaseModel):
    """对话消息（用于 LLM 交互）"""
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str | None = None
    name: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None


class ToolCall(BaseModel):
    """工具调用请求"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str = "function"
    function: FunctionCall


class FunctionCall(BaseModel):
    """函数调用详情"""
    name: str
    arguments: str  # JSON 字符串


class MessageContent(BaseModel):
    """消息内容（用于通道适配器）"""
    content_type: ContentType
    text: str | None = None
    media_url: str | None = None
    media_data: bytes | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    """LLM 对话响应"""
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    finish_reason: str | None = None
    usage: TokenUsage | None = None
    model: str | None = None


class ChatChunk(BaseModel):
    """流式对话响应块"""
    delta_content: str | None = None
    delta_tool_calls: list[ToolCall] | None = None
    finish_reason: str | None = None


class TokenUsage(BaseModel):
    """Token 使用统计"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


# ──────────────────────────────────────────────
# 工具相关类型
# ──────────────────────────────────────────────

class ToolDefinition(BaseModel):
    """工具定义"""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema
    permission_level: str = "safe"  # "safe" | "restricted" | "dangerous"


class ToolInvocation(BaseModel):
    """工具调用请求"""
    tool_id: str
    params: dict[str, Any] = Field(default_factory=dict)
    sandbox_level: str = "standard"  # "standard" | "isolated" | "privileged"


class ToolResult(BaseModel):
    """工具执行结果"""
    tool_id: str
    success: bool
    output: Any = None
    error: str | None = None
    execution_time_ms: float = 0


# ──────────────────────────────────────────────
# 用户消息与机器人响应（通道适配器标准化）
# ──────────────────────────────────────────────

class UserMessage(BaseModel):
    """标准化用户消息（通道适配器输出）"""
    platform: str  # "telegram" | "wechat" | "discord" | ...
    platform_user_id: str  # 平台内用户唯一 ID
    yuanbot_user_id: str  # YuanBot 统一用户 ID
    session_id: str
    content_type: ContentType
    text: str | None = None
    media_url: str | None = None
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BotResponse(BaseModel):
    """标准化机器人响应"""
    content: MessageContent
    suggested_tools: list[ToolInvocation] | None = None
    proactive_followups: list[ProactiveTask] | None = None


class ProactiveTask(BaseModel):
    """主动交互任务"""
    task_type: str  # "greeting" | "care" | "reminder" | "event"
    scheduled_at: datetime
    content_hint: str | None = None
    priority: int = 0  # 0=低, 1=中, 2=高


class ChannelConfig(BaseModel):
    """通道配置"""
    platform: str
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


# ──────────────────────────────────────────────
# 记忆系统类型
# ──────────────────────────────────────────────

class MemoryType(str, Enum):
    """记忆类型"""
    WORKING = "working"      # 工作记忆：当前会话上下文
    FACT = "fact"            # 事实记忆：用户偏好、习惯、重要事实
    EPISODIC = "episodic"    # 情景记忆：过往对话摘要
    SEMANTIC = "semantic"    # 语义记忆：深层认知与关系理解


class MemoryNode(BaseModel):
    """记忆节点"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    memory_type: MemoryType
    content: str  # 记忆内容文本
    summary: str | None = None  # 摘要

    # 时间信息
    created_at: datetime = Field(default_factory=datetime.now)
    last_accessed: datetime = Field(default_factory=datetime.now)
    access_count: int = 0

    # 情感与重要性
    emotional_tone: str | None = None  # "positive" | "negative" | "neutral"
    importance_score: float = 0.5  # 0.0 ~ 1.0

    # 关联实体
    key_entities: list[str] = Field(default_factory=list)
    topic_tags: list[str] = Field(default_factory=list)

    # 向量嵌入（语义检索用）
    embedding: list[float] | None = None

    # 元数据
    metadata: dict[str, Any] = Field(default_factory=dict)


class UserProfile(BaseModel):
    """用户画像"""
    user_id: str
    display_name: str | None = None

    # 事实记忆（结构化偏好）
    preferences: dict[str, Any] = Field(default_factory=dict)
    # 例: {"favorite_color": "blue", "dislikes": ["香菜"], "birthday": "1995-06-15"}

    # 关系状态
    relationship_stage: str = "initial"  # "initial" | "familiar" | "intimate" | "deep"
    trust_score: float = 0.0  # 0.0 ~ 1.0

    # 交互统计
    total_interactions: int = 0
    first_interaction: datetime | None = None
    last_interaction: datetime | None = None

    # 情感模式
    typical_mood_patterns: dict[str, Any] = Field(default_factory=dict)
    # 例: {"monday_morning": "low", "friday_evening": "high"}

    # 平台关联
    platform_ids: dict[str, str] = Field(default_factory=dict)
    # 例: {"telegram": "tg_123", "wechat": "wx_456"}

    metadata: dict[str, Any] = Field(default_factory=dict)


# ──────────────────────────────────────────────
# 记忆检索结果
# ──────────────────────────────────────────────

class MemorySearchResult(BaseModel):
    """记忆检索结果"""
    node: MemoryNode
    score: float  # 相关性评分 0.0 ~ 1.0
    match_type: str  # "semantic" | "keyword" | "entity" | "temporal"


# ──────────────────────────────────────────────
# 发送结果
# ──────────────────────────────────────────────

class SendResult(BaseModel):
    """消息发送结果"""
    success: bool
    message_id: str | None = None
    error: str | None = None
