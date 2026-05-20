"""YuanBot 消息通道适配器"""

from yuanbot.adapters.channel.base import BaseChannelAdapter
from yuanbot.adapters.channel.discord_adapter import DiscordAdapter  # noqa: I001
from yuanbot.adapters.channel.telegram_adapter import TelegramAdapter
from yuanbot.adapters.channel.web_adapter import WebAdapter
from yuanbot.adapters.channel.wecom_adapter import WeComAdapter

__all__ = [
    "BaseChannelAdapter",
    "DiscordAdapter",
    "TelegramAdapter",
    "WeComAdapter",
    "WebAdapter",
]
