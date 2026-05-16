"""YuanBot 核心模块 - 类型定义与接口规范"""

from yuanbot.core.types import (
    ContentType,
    Message,
    MessageContent,
    ChatResponse,
    ChatChunk,
    ToolDefinition,
    ToolInvocation,
    ToolResult,
    UserMessage,
    BotResponse,
    ProactiveTask,
    ChannelConfig,
    MemoryNode,
    MemoryType,
    UserProfile,
)
from yuanbot.core.interfaces import (
    AIProviderAdapter,
    ChannelAdapter,
    SkillModule,
    ToolModule,
    PersonaProfile,
)

__all__ = [
    # Types
    "ContentType",
    "Message",
    "MessageContent",
    "ChatResponse",
    "ChatChunk",
    "ToolDefinition",
    "ToolInvocation",
    "ToolResult",
    "UserMessage",
    "BotResponse",
    "ProactiveTask",
    "ChannelConfig",
    "MemoryNode",
    "MemoryType",
    "UserProfile",
    # Interfaces
    "AIProviderAdapter",
    "ChannelAdapter",
    "SkillModule",
    "ToolModule",
    "PersonaProfile",
]
