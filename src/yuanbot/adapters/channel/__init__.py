"""YuanBot 消息通道适配器"""

from yuanbot.adapters.channel.base import BaseChannelAdapter
from yuanbot.adapters.channel.telegram_adapter import TelegramAdapter
from yuanbot.adapters.channel.web_adapter import WebAdapter

__all__ = ["BaseChannelAdapter", "TelegramAdapter", "WebAdapter"]
