"""AI 提供商适配系统

提供商管理器、适配器注册表和统一 AI API。
"""

from yuanbot.providers.manager import ProviderManager
from yuanbot.providers.registry import ProviderRegistry

__all__ = [
    "ProviderManager",
    "ProviderRegistry",
]
