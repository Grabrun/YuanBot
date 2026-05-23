"""TUI API 客户端

通过 HTTP/WebSocket 与 YuanBot 后端通信。
处理认证、会话管理和消息收发。
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)


class TUIClientError(Exception):
    """TUI 客户端错误"""


class TUIClient:
    """TUI API 客户端

    封装与 YuanBot 后端的所有通信。
    """

    def __init__(self, base_url: str = "http://localhost:8000"):
        self._base_url = base_url.rstrip("/")
        self._token: str | None = None
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=60.0,
            )
        return self._client

    def set_token(self, token: str) -> None:
        """设置认证 token"""
        self._token = token

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ── 认证 ──────────────────────────────────

    async def login(self, username: str, password: str) -> dict[str, Any]:
        """用户名密码登录"""
        client = await self._ensure_client()
        resp = await client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        if resp.status_code != 200:
            raise TUIClientError(f"登录失败: {resp.json().get('detail', resp.text)}")
        data = resp.json()
        self._token = data["token"]
        return data

    async def login_with_api_key(self, api_key: str) -> dict[str, Any]:
        """API Key 登录"""
        client = await self._ensure_client()
        resp = await client.post(
            "/api/auth/api-key",
            json={"api_key": api_key},
        )
        if resp.status_code != 200:
            raise TUIClientError(f"API Key 验证失败: {resp.json().get('detail', resp.text)}")
        data = resp.json()
        self._token = data["token"]
        return data

    async def get_me(self) -> dict[str, Any]:
        """获取当前用户信息"""
        client = await self._ensure_client()
        resp = await client.get("/api/auth/me", headers=self._headers())
        if resp.status_code != 200:
            raise TUIClientError("获取用户信息失败")
        return resp.json()

    @property
    def is_authenticated(self) -> bool:
        return self._token is not None

    # ── 会话 ──────────────────────────────────

    async def list_conversations(self) -> list[dict[str, Any]]:
        """获取会话列表"""
        client = await self._ensure_client()
        resp = await client.get("/api/conversations", headers=self._headers())
        if resp.status_code != 200:
            raise TUIClientError("获取会话列表失败")
        return resp.json()["conversations"]

    async def create_conversation(self, title: str = "新会话") -> dict[str, Any]:
        """创建新会话"""
        client = await self._ensure_client()
        resp = await client.post(
            "/api/conversations",
            json={"title": title},
            headers=self._headers(),
        )
        if resp.status_code != 200:
            raise TUIClientError("创建会话失败")
        return resp.json()

    async def delete_conversation(self, conversation_id: str) -> bool:
        """删除会话"""
        client = await self._ensure_client()
        resp = await client.delete(
            f"/api/conversations/{conversation_id}",
            headers=self._headers(),
        )
        return resp.status_code == 200

    async def get_messages(
        self, conversation_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """获取会话消息"""
        client = await self._ensure_client()
        resp = await client.get(
            f"/api/conversations/{conversation_id}/messages",
            params={"limit": limit},
            headers=self._headers(),
        )
        if resp.status_code != 200:
            raise TUIClientError("获取消息失败")
        return resp.json()["messages"]

    async def send_message(
        self, content: str, conversation_id: str | None = None
    ) -> dict[str, Any]:
        """发送消息"""
        client = await self._ensure_client()
        body: dict[str, Any] = {"content": content}
        if conversation_id:
            body["conversation_id"] = conversation_id
        resp = await client.post(
            "/api/chat",
            json=body,
            headers=self._headers(),
        )
        if resp.status_code != 200:
            raise TUIClientError(f"发送消息失败: {resp.text}")
        return resp.json()

    # ── Provider ──────────────────────────────

    async def list_providers(self) -> list[dict[str, Any]]:
        """获取 AI 提供商列表"""
        client = await self._ensure_client()
        resp = await client.get("/api/providers", headers=self._headers())
        if resp.status_code != 200:
            raise TUIClientError("获取提供商列表失败")
        return resp.json()["providers"]

    # ── WebSocket ─────────────────────────────

    def ws_url(self) -> str:
        """获取 WebSocket URL"""
        ws_base = self._base_url.replace("http://", "ws://").replace("https://", "wss://")
        token_param = f"?token={self._token}" if self._token else ""
        return f"{ws_base}/ws/chat{token_param}"
