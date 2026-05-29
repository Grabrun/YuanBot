"""认证 API 路由

设计参考: user-interface-system.md 第7.1节

端点:
- POST /api/auth/login        用户名/密码登录
- POST /api/auth/api-key      API Key 验证
- POST /api/auth/logout        注销
- POST /api/auth/refresh       刷新 token
- GET  /api/auth/me            获取当前用户信息
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response, status

from yuanbot.auth.middleware import get_auth_manager, get_current_user
from yuanbot.auth.models import (
    ApiKeyLoginRequest,
    LoginRequest,
    LoginResponse,
    User,
)
from yuanbot.auth.store import UserStore

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _get_user_store() -> UserStore:
    """获取用户存储（从 auth manager）"""
    return get_auth_manager()._user_store


def _set_token_cookie(response: Response, token: str) -> None:
    """设置认证 Cookie"""
    auth = get_auth_manager()
    response.set_cookie(
        key=auth._config.cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=auth._config.token_expire_hours * 3600,
    )


@router.post("/login")
async def login(body: LoginRequest, response: Response) -> LoginResponse:
    """用户名/密码登录

    验证成功后返回 JWT token 并设置 Cookie。
    """
    store = _get_user_store()
    user = store.verify_password(body.username, body.password)

    if not user:
        logger.warning("login_failed", username=body.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    auth = get_auth_manager()
    token = auth.create_session_token(user)
    store.record_login(user)

    _set_token_cookie(response, token)

    logger.info("login_success", username=user.username, role=user.role.value)
    return LoginResponse(
        token=token,
        user=user.to_safe_dict(),
        expires_in=auth._config.token_expire_hours * 3600,
    )


@router.post("/api-key")
async def login_with_api_key(body: ApiKeyLoginRequest, response: Response) -> LoginResponse:
    """API Key 验证登录

    使用长期 API Key 换取短期 Session Token。
    """
    store = _get_user_store()
    user = store.get_user_by_api_key(body.api_key)

    if not user or not user.enabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    auth = get_auth_manager()
    token = auth.create_session_token(user)
    store.record_login(user)

    _set_token_cookie(response, token)

    logger.info("api_key_login_success", username=user.username)
    return LoginResponse(
        token=token,
        user=user.to_safe_dict(),
        expires_in=auth._config.token_expire_hours * 3600,
    )


@router.post("/logout")
async def logout(user: User = Depends(get_current_user), response: Response = None) -> dict:
    """注销当前会话

    清除 Cookie。
    """
    auth = get_auth_manager()
    response.delete_cookie(key=auth._config.cookie_name)
    logger.info("logout", username=user.username)
    return {"status": "ok"}


@router.post("/refresh")
async def refresh_token(user: User = Depends(get_current_user)) -> dict:
    """刷新即将过期的 token

    验证当前 token 有效后，签发新 token。
    """
    auth = get_auth_manager()
    new_token = auth.create_session_token(user)
    return {
        "token": new_token,
        "expires_in": auth._config.token_expire_hours * 3600,
    }


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)) -> dict:
    """获取当前用户信息"""
    return user.to_safe_dict()
