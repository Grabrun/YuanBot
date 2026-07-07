"""YuanBot 核心模块 - 类型定义与接口规范"""

from yuanbot.core.interfaces import (
    AIProviderAdapter,
    ChannelAdapter,
    PersonaProfile,
    SkillModule,
    ToolModule,
)
from yuanbot.core.types import (
    BotResponse,
    ChannelConfig,
    ChatChunk,
    ChatResponse,
    ContentType,
    MemoryNode,
    MemoryType,
    Message,
    MessageContent,
    ProactiveTask,
    ToolDefinition,
    ToolInvocation,
    ToolResult,
    UserMessage,
    UserProfile,
)

__all__ = [
    # Interfaces
    "AIProviderAdapter",
    # Types
    "BotResponse",
    "ChannelAdapter",
    "ChannelConfig",
    "ChatChunk",
    "ChatResponse",
    "ContentType",
    "MemoryNode",
    "MemoryType",
    "Message",
    "MessageContent",
    "PersonaProfile",
    "ProactiveTask",
    "SkillModule",
    "ToolDefinition",
    "ToolInvocation",
    "ToolModule",
    "ToolResult",
    "UserMessage",
    "UserProfile",
]
