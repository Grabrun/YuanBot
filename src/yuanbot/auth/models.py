"""用户与认证数据模型

设计参考: user-interface-system.md 第3节
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class UserRole(StrEnum):
    """用户角色"""

    ADMIN = "admin"
    USER = "user"


class TokenType(StrEnum):
    """令牌类型"""

    SESSION = "session"  # 短期会话令牌 (JWT)
    API_KEY = "api_key"  # 长期 API Key


class User(BaseModel):
    """用户模型"""

    user_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    username: str
    display_name: str = ""
    role: UserRole = UserRole.USER
    password_hash: str = ""  # bcrypt 哈希
    api_key: str | None = None  # 长期 API Key
    enabled: bool = True
    created_at: datetime = Field(default_factory=datetime.now)
    last_login: datetime | None = None

    def to_safe_dict(self) -> dict[str, Any]:
        """返回脱敏的用户信息（不含密码哈希和 API Key）"""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role.value,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "has_api_key": self.api_key is not None,
        }


class AuthToken(BaseModel):
    """认证令牌"""

    token: str
    user_id: str
    username: str
    role: UserRole
    expires_at: datetime
    token_type: TokenType = TokenType.SESSION


class Conversation(BaseModel):
    """会话"""

    conversation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    title: str = "新会话"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    message_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationMessage(BaseModel):
    """会话消息"""

    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: str
    user_id: str
    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LoginRequest(BaseModel):
    """登录请求"""

    username: str
    password: str


class LoginResponse(BaseModel):
    """登录响应"""

    token: str
    user: dict[str, Any]
    expires_in: int  # 秒


class ApiKeyLoginRequest(BaseModel):
    """API Key 登录请求"""

    api_key: str


class CreateUserRequest(BaseModel):
    """创建用户请求"""

    username: str
    password: str
    display_name: str = ""
    role: UserRole = UserRole.USER
