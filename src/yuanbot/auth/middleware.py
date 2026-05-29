"""认证与鉴权中间件

为 FastAPI 提供 JWT Token 认证和 RBAC 鉴权。
支持 Cookie 和 Authorization Header 两种 token 传递方式。

设计参考: user-interface-system.md 第3节
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog
from fastapi import Depends, HTTPException, Request, WebSocket, status
from fastapi.security import HTTPBearer

from yuanbot.auth.models import User, UserRole
from yuanbot.gateway.jwt_auth import (
    JWTAuthManager,
    TokenExpiredError,
    TokenPayload,
)

logger = structlog.get_logger(__name__)

# HTTP Bearer scheme (用于 Swagger UI)
_bearer_scheme = HTTPBearer(auto_error=False)

# 默认 JWT 配置
_DEFAULT_SECRET_KEY = "yuanbot-change-this-in-production"
_DEFAULT_TOKEN_EXPIRE_HOURS = 24


@dataclass
class AuthConfig:
    """认证配置"""

    secret_key: str = _DEFAULT_SECRET_KEY
    token_expire_hours: int = _DEFAULT_TOKEN_EXPIRE_HOURS
    cookie_name: str = "yuanbot_token"
    header_name: str = "Authorization"


class AuthManager:
    """认证管理器

    统一管理 JWT token 生成、验证和用户查询。
    """

    def __init__(
        self,
        secret_key: str = _DEFAULT_SECRET_KEY,
        token_expire_hours: int = _DEFAULT_TOKEN_EXPIRE_HOURS,
    ):
        self._config = AuthConfig(
            secret_key=secret_key,
            token_expire_hours=token_expire_hours,
        )
        self._jwt_manager = JWTAuthManager(
            secret_key=secret_key,
            default_expires_in=token_expire_hours * 3600,
        )
        self._user_store: Any = None  # 延迟注入

    def set_user_store(self, user_store: Any) -> None:
        """注入用户存储（在 app 启动时调用）"""
        self._user_store = user_store

    @property
    def jwt_manager(self) -> JWTAuthManager:
        return self._jwt_manager

    def create_session_token(self, user: User) -> str:
        """为用户创建会话 JWT Token

        Args:
            user: 用户对象

        Returns:
            JWT token 字符串
        """
        return self._jwt_manager.create_token(
            sub=user.user_id,
            scopes=["user_data"] if user.role == UserRole.USER else ["system"],
            metadata={
                "username": user.username,
                "role": user.role.value,
            },
        )

    def verify_token(self, token: str) -> TokenPayload | None:
        """验证 token

        Returns:
            TokenPayload 如果有效，None 如果无效或过期
        """
        try:
            return self._jwt_manager.verify_token(token)
        except (TokenExpiredError, Exception):
            return None

    def extract_token_from_request(self, request: Request) -> str | None:
        """从请求中提取 token

        优先级：Authorization Header > Cookie
        """
        # 1. Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:]

        # 2. Cookie
        token = request.cookies.get(self._config.cookie_name)
        if token:
            return token

        # 3. Query parameter (for WebSocket)
        token = request.query_params.get("token")
        if token:
            return token

        return None

    async def get_current_user_from_request(self, request: Request) -> User | None:
        """从请求中获取当前用户

        Returns:
            User 如果认证成功，None 如果未认证
        """
        token = self.extract_token_from_request(request)
        if not token:
            return None

        payload = self.verify_token(token)
        if not payload:
            return None

        if not self._user_store:
            return None

        user = self._user_store.get_user(payload.sub)
        if not user or not user.enabled:
            return None

        return user

    async def get_user_from_websocket(self, ws: WebSocket) -> User | None:
        """从 WebSocket 连接中获取用户

        认证方式：URL 参数 ?token=<jwt>
        """
        token = ws.query_params.get("token")
        if not token:
            return None

        payload = self.verify_token(token)
        if not payload:
            return None

        if not self._user_store:
            return None

        user = self._user_store.get_user(payload.sub)
        if not user or not user.enabled:
            return None

        return user


# ── FastAPI 依赖注入 ──────────────────────────

# 全局 AuthManager 实例（在 app.py 中初始化）
_auth_manager: AuthManager | None = None


def init_auth_manager(auth_manager: AuthManager) -> None:
    """初始化全局认证管理器"""
    global _auth_manager
    _auth_manager = auth_manager


def get_auth_manager() -> AuthManager:
    """获取全局认证管理器"""
    if _auth_manager is None:
        raise RuntimeError("AuthManager not initialized. Call init_auth_manager() first.")
    return _auth_manager


async def get_current_user(request: Request) -> User:
    """FastAPI 依赖：获取当前已认证用户

    未认证时返回 401。
    """
    auth = get_auth_manager()
    user = await auth.get_current_user_from_request(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_user_optional(request: Request) -> User | None:
    """FastAPI 依赖：获取当前用户（可选，未认证返回 None）"""
    auth = get_auth_manager()
    return await auth.get_current_user_from_request(request)


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """FastAPI 依赖：要求管理员角色"""
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


async def get_current_user_from_ws(ws: WebSocket) -> User | None:
    """从 WebSocket 获取用户"""
    auth = get_auth_manager()
    return await auth.get_user_from_websocket(ws)
