"""首次管理员设置端点测试

测试 /api/auth/setup 和 /api/auth/setup/status 端点。
设计参考: user-interface-system.md 第5.3/5.4节
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from yuanbot.auth.middleware import AuthManager, init_auth_manager
from yuanbot.auth.routes import router as auth_router
from yuanbot.auth.store import UserStore


@pytest.fixture
def app(tmp_path):
    """创建测试用 FastAPI 应用（仅认证路由）"""
    application = FastAPI()
    user_store = UserStore(data_dir=tmp_path)
    auth_manager = AuthManager(secret_key="test-secret", token_expire_hours=1)
    auth_manager.set_user_store(user_store)
    application.include_router(auth_router)
    init_auth_manager(auth_manager)
    application.state.user_store = user_store
    return application


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def init_client(app):
    """已初始化存储的客户端"""
    asyncio.get_event_loop().run_until_complete(app.state.user_store.initialize())
    return TestClient(app, raise_server_exceptions=False)


class TestSetupStatus:
    """GET /api/auth/setup/status 测试"""

    def test_needs_setup_when_no_users(self, init_client):
        """没有用户时返回 needs_setup=True"""
        resp = init_client.get("/api/auth/setup/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["needs_setup"] is True
        assert data["user_count"] == 0

    def test_no_setup_when_admin_exists(self, init_client):
        """已有管理员时返回 needs_setup=False"""
        store = init_client.app.state.user_store
        store.create_user("admin", "password123", role="admin")

        resp = init_client.get("/api/auth/setup/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["needs_setup"] is False
        assert data["user_count"] == 1

    def test_needs_setup_when_only_regular_user(self, init_client):
        """只有普通用户时仍需要设置"""
        store = init_client.app.state.user_store
        store.create_user("alice", "password123", role="user")

        resp = init_client.get("/api/auth/setup/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["needs_setup"] is True
        assert data["user_count"] == 1


class TestSetupFirstAdmin:
    """POST /api/auth/setup 测试"""

    def test_create_first_admin(self, init_client):
        """首次设置创建管理员"""
        resp = init_client.post(
            "/api/auth/setup",
            json={
                "username": "admin",
                "password": "admin_pass_123",
                "display_name": "管理员",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["username"] == "admin"
        assert data["user"]["role"] == "admin"
        assert data["user"]["display_name"] == "管理员"

    def test_setup_returns_token_and_cookie(self, init_client):
        """设置返回 token 和 Cookie"""
        resp = init_client.post(
            "/api/auth/setup",
            json={"username": "admin", "password": "admin_pass_123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert "expires_in" in data
        # Cookie 也被设置（cookie 名称来自配置，默认为 yuanbot_token）
        assert any("token" in key for key in resp.cookies.keys())

    def test_setup_rejected_when_admin_exists(self, init_client):
        """已有管理员时拒绝设置"""
        store = init_client.app.state.user_store
        store.create_user("existing_admin", "password123", role="admin")

        resp = init_client.post(
            "/api/auth/setup",
            json={"username": "new_admin", "password": "new_pass_123"},
        )
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]

    def test_setup_validates_username_length(self, init_client):
        """用户名长度验证（最少3字符）"""
        resp = init_client.post(
            "/api/auth/setup",
            json={"username": "ab", "password": "admin_pass_123"},
        )
        assert resp.status_code == 422  # Pydantic validation error

    def test_setup_validates_password_length(self, init_client):
        """密码长度验证（最少6字符）"""
        resp = init_client.post(
            "/api/auth/setup",
            json={"username": "admin", "password": "short"},
        )
        assert resp.status_code == 422

    def test_setup_default_display_name(self, init_client):
        """不指定 display_name 时默认使用 username"""
        resp = init_client.post(
            "/api/auth/setup",
            json={"username": "admin", "password": "admin_pass_123"},
        )
        assert resp.status_code == 200
        assert resp.json()["user"]["display_name"] == "admin"

    def test_setup_can_login_after(self, init_client):
        """设置后可以用密码登录"""
        init_client.post(
            "/api/auth/setup",
            json={"username": "admin", "password": "admin_pass_123"},
        )

        login_resp = init_client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin_pass_123"},
        )
        assert login_resp.status_code == 200
        assert login_resp.json()["user"]["role"] == "admin"

    def test_setup_creates_only_admin_role(self, init_client):
        """通过 setup 创建的用户始终是 admin 角色"""
        resp = init_client.post(
            "/api/auth/setup",
            json={"username": "admin", "password": "admin_pass_123"},
        )
        assert resp.status_code == 200
        assert resp.json()["user"]["role"] == "admin"

        # 验证存储中确实是 admin
        store = init_client.app.state.user_store
        user = store.get_user_by_username("admin")
        assert user is not None
        assert user.role.value == "admin"
