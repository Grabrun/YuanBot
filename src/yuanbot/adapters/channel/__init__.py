"""通道适配器

各聊天平台的适配器实现。
"""

from yuanbot.adapters.channel.base import BaseChannelAdapter
from yuanbot.adapters.channel.dingtalk_adapter import DingTalkAdapter
from yuanbot.adapters.channel.feishu_adapter import FeishuAdapter
from yuanbot.adapters.channel.napcat_adapter import NapCatAdapter
from yuanbot.adapters.channel.wechat_adapter import WeixinAdapter

__all__ = [
    "BaseChannelAdapter",
    "DingTalkAdapter",
    "FeishuAdapter",
    "NapCatAdapter",
    "WeixinAdapter",
]
