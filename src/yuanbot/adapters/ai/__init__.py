"""YuanBot AI 提供商适配器"""

from yuanbot.adapters.ai.base import BaseAIProvider
from yuanbot.adapters.ai.openai_adapter import OpenAIAdapter

__all__ = ["BaseAIProvider", "OpenAIAdapter"]
