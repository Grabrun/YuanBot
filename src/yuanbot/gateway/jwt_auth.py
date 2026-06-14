"""JWT 权限令牌模块

实现 JWT token 的生成和验证，支持权限范围（scopes）。
用于工具执行时的权限验证。

Scopes:
- readonly: 只读操作
- user_data: 用户数据访问
- system: 系统管理操作
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# 可选依赖: PyJWT
try:
    import jwt

    _HAS_PYJWT = True
except ImportError:
    _HAS_PYJWT = False


# 支持的权限范围
VALID_SCOPES = {"readonly", "user_data", "system"}

# scope 层级: system > user_data > readonly
SCOPE_HIERARCHY: dict[str, int] = {
    "readonly": 0,
    "user_data": 1,
    "system": 2,
}


@dataclass
class TokenPayload:
    """JWT Token 载荷"""

    sub: str  # 用户 ID 或客户端 ID
    scopes: list[str] = field(default_factory=lambda: ["readonly"])
    exp: int | None = None  # 过期时间戳
    iat: int | None = None  # 签发时间戳
    jti: str | None = None  # Token 唯一标识
    metadata: dict[str, Any] = field(default_factory=dict)


class JWTAuthError(Exception):
    """JWT 认证错误基类"""


class TokenExpiredError(JWTAuthError):
    """Token 已过期"""


class InvalidTokenError(JWTAuthError):
    """Token 无效（签名错误、格式错误等）"""


class InsufficientScopeError(JWTAuthError):
    """权限不足"""


class JWTAuthManager:
    """JWT 认证管理器

    负责 JWT token 的生成、验证和权限检查。

    使用方式::

        manager = JWTAuthManager(secret_key="your-secret-key")

        # 生成 token
        token = manager.create_token(
            sub="user123",
            scopes=["readonly", "user_data"],
            expires_in=3600,
        )

        # 验证 token
        payload = manager.verify_token(token)

        # 检查权限
        manager.require_scope(payload, "user_data")
    """

    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        default_expires_in: int = 3600,
    ):
        if not _HAS_PYJWT:
            raise ImportError(
                "PyJWT is required for JWT authentication. Install it with: pip install PyJWT"
            )
        self._secret_key = secret_key
        self._algorithm = algorithm
        self._default_expires_in = default_expires_in

    def create_token(
        self,
        sub: str,
        scopes: list[str] | None = None,
        expires_in: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """生成 JWT token

        Args:
            sub: 用户 ID 或客户端 ID
            scopes: 权限范围列表（默认 ["readonly"]）
            expires_in: 过期时间（秒），默认使用构造时配置
            metadata: 额外元数据

        Returns:
            编码后的 JWT token 字符串

        Raises:
            ValueError: 如果 scope 不合法
        """
        if not _HAS_PYJWT:
            raise ImportError("PyJWT is required")

        token_scopes = scopes or ["readonly"]

        # 验证 scope 合法性
        for scope in token_scopes:
            if scope not in VALID_SCOPES:
                raise ValueError(
                    f"Invalid scope: '{scope}'. Valid scopes: {', '.join(sorted(VALID_SCOPES))}"
                )

        now = int(time.time())
        exp_seconds = expires_in if expires_in is not None else self._default_expires_in

        payload = {
            "sub": sub,
            "scopes": token_scopes,
            "iat": now,
            "exp": now + exp_seconds,
        }

        if metadata:
            payload["metadata"] = metadata

        token = jwt.encode(payload, self._secret_key, algorithm=self._algorithm)
        logger.info("token_created", sub=sub, scopes=token_scopes)
        return token

    def verify_token(self, token: str) -> TokenPayload:
        """验证 JWT token 并返回载荷

        Args:
            token: JWT token 字符串

        Returns:
            TokenPayload: 解析后的载荷

        Raises:
            TokenExpiredError: Token 已过期
            InvalidTokenError: Token 无效
        """
        if not _HAS_PYJWT:
            raise ImportError("PyJWT is required")

        try:
            decoded = jwt.decode(
                token,
                self._secret_key,
                algorithms=[self._algorithm],
            )
        except jwt.ExpiredSignatureError as err:
            raise TokenExpiredError("Token has expired") from err
        except jwt.InvalidTokenError as err:
            raise InvalidTokenError(f"Invalid token: {err}") from err

        return TokenPayload(
            sub=decoded.get("sub", ""),
            scopes=decoded.get("scopes", ["readonly"]),
            exp=decoded.get("exp"),
            iat=decoded.get("iat"),
            jti=decoded.get("jti"),
            metadata=decoded.get("metadata", {}),
        )

    @staticmethod
    def require_scope(payload: TokenPayload, required_scope: str) -> None:
        """检查 token 是否具有所需权限

        权限层级:
        - system 包含所有权限
        - user_data 包含 readonly
        - readonly 只有只读权限

        Args:
            payload: 已验证的 token 载荷
            required_scope: 所需的权限范围

        Raises:
            InsufficientScopeError: 权限不足
        """
        if required_scope not in VALID_SCOPES:
            raise ValueError(f"Invalid required scope: '{required_scope}'")

        required_level = SCOPE_HIERARCHY.get(required_scope, 0)

        for scope in payload.scopes:
            scope_level = SCOPE_HIERARCHY.get(scope, 0)
            if scope_level >= required_level:
                return

        raise InsufficientScopeError(
            f"Insufficient scope: requires '{required_scope}', but token has {payload.scopes}"
        )

    @staticmethod
    def has_scope(payload: TokenPayload, required_scope: str) -> bool:
        """检查 token 是否具有所需权限（不抛异常）

        Args:
            payload: 已验证的 token 载荷
            required_scope: 所需的权限范围

        Returns:
            True 如果具有所需权限
        """
        try:
            JWTAuthManager.require_scope(payload, required_scope)
            return True
        except (InsufficientScopeError, ValueError):
            return False

    def refresh_token(
        self,
        token: str,
        extends_seconds: int | None = None,
    ) -> str:
        """刷新 token（续期）

        验证原 token 有效性后，生成新的 token。

        Args:
            token: 原 JWT token
            extends_seconds: 续期时长（秒），默认使用 default_expires_in

        Returns:
            新的 JWT token 字符串

        Raises:
            TokenExpiredError: 原 token 已过期
            InvalidTokenError: 原 token 无效
        """
        payload = self.verify_token(token)
        return self.create_token(
            sub=payload.sub,
            scopes=payload.scopes,
            expires_in=extends_seconds,
            metadata=payload.metadata,
        )
