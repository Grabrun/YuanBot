"""AI 提供商适配器

各 AI 服务提供商的适配器实现。
"""

from yuanbot.adapters.ai.base import BaseAIProvider
from yuanbot.adapters.ai.openai_adapter import OpenAIAdapter

__all__ = [
    "BaseAIProvider",
    "OpenAIAdapter",
]
