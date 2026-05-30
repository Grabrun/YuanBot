"""通道适配器

各聊天平台的适配器实现。
"""

from yuanbot.adapters.channel.base import BaseChannelAdapter
from yuanbot.adapters.channel.dingtalk_adapter import DingTalkAdapter
from yuanbot.adapters.channel.feishu_adapter import FeishuAdapter

__all__ = [
    "BaseChannelAdapter",
    "DingTalkAdapter",
    "FeishuAdapter",
]
