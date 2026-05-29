"""网关系统

统一的消息通道管理，包括网关核心、适配器管理、身份认证、隐私保护。
"""

from yuanbot.gateway.adapter_manager import AdapterManager
from yuanbot.gateway.gateway import YuanGateway
from yuanbot.gateway.identity_service import IdentityService
from yuanbot.gateway.push_dispatcher import PushDispatcher

__all__ = [
    "AdapterManager",
    "IdentityService",
    "PushDispatcher",
    "YuanGateway",
]
