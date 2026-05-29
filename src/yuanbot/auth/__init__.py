"""用户认证与鉴权系统

设计参考: user-interface-system.md 第3节

提供:
- 用户模型与存储 (models, store)
- JWT 认证中间件 (middleware)
- 认证 API 路由 (routes)
- 会话管理 API 路由 (conversation_routes)
- 管理 API 路由 (admin_routes)
"""

from yuanbot.auth.middleware import AuthManager, init_auth_manager
from yuanbot.auth.models import (
    AuthToken,
    Conversation,
    ConversationMessage,
    LoginRequest,
    LoginResponse,
    User,
    UserRole,
)
from yuanbot.auth.store import ConversationStore, UserStore

__all__ = [
    "AuthManager",
    "UserStore",
    "ConversationStore",
    "User",
    "UserRole",
    "AuthToken",
    "Conversation",
    "ConversationMessage",
    "LoginRequest",
    "LoginResponse",
    "init_auth_manager",
]
