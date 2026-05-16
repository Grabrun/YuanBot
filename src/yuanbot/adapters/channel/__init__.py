"""YuanBot 消息通道适配器"""

from yuanbot.adapters.channel.base import BaseChannelAdapter
from yuanbot.adapters.channel.telegram_adapter import TelegramAdapter

__all__ = ["BaseChannelAdapter", "TelegramAdapter"]
