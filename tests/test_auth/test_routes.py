"""认证与会话 API 端点测试"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from yuanbot.auth.admin_routes import init_admin_stores
from yuanbot.auth.admin_routes import router as admin_router
from yuanbot.auth.conversation_routes import init_conversation_store
from yuanbot.auth.conversation_routes import router as conv_router
from yuanbot.auth.middleware import AuthManager, init_auth_manager
from yuanbot.auth.routes import router as auth_router
from yuanbot.auth.store import ConversationStore, UserStore


@pytest.fixture
def app(tmp_path):
    """创建测试用 FastAPI 应用"""
    application = FastAPI()

    # 初始化存储
    user_store = UserStore(data_dir=tmp_path)
    conv_store = ConversationStore(data_dir=tmp_path)

    # 初始化认证
    auth_manager = AuthManager(secret_key="test-secret-key-for-jwt-auth-32bytes", token_expire_hours=1)
    auth_manager.set_user_store(user_store)

    # 注册路由
    application.include_router(auth_router)
    application.include_router(conv_router)
    application.include_router(admin_router)

    # 初始化全局引用
    init_auth_manager(auth_manager)
    init_conversation_store(conv_store)
    init_admin_stores(user_store, conv_store)

    # 存储引用供测试使用
    application.state.user_store = user_store
    application.state.conv_store = conv_store

    return application


@pytest.fixture
def client(app):
    """测试客户端"""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
async def initialized_app(app):
    """已初始化存储的 app"""
    await app.state.user_store.initialize()
    await app.state.conv_store.initialize()
    return app


@pytest.fixture
def init_client(initialized_app):
    """已初始化的测试客户端"""
    return TestClient(initialized_app, raise_server_exceptions=False)


class TestAuthEndpoints:
    """认证端点测试"""

    def test_login_before_setup(self, client):
        """未初始化 store 时登录应返回 500"""
        resp = client.post("/api/auth/login", json={"username": "admin", "password": "pass"})
        # store 未初始化会抛 RuntimeError → 500
        assert resp.status_code == 500

    def test_register_and_login(self, init_client):
        """注册后登录"""
        # 先通过管理 API 创建用户（需要先有 admin 用户）
        # 这里直接操作 store
        store = init_client.app.state.user_store
        store.create_user("alice", "password123", display_name="Alice")

        # 登录
        resp = init_client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "password123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["username"] == "alice"
        assert data["user"]["display_name"] == "Alice"

    def test_login_wrong_password(self, init_client):
        """错误密码登录失败"""
        store = init_client.app.state.user_store
        store.create_user("alice", "correct")

        resp = init_client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "wrong"},
        )
        assert resp.status_code == 401

    def test_login_sets_cookie(self, init_client):
        """登录成功应设置 Cookie"""
        store = init_client.app.state.user_store
        store.create_user("alice", "pass123")

        resp = init_client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "pass123"},
        )
        assert resp.status_code == 200
        assert "yuanbot_token" in resp.cookies

    def test_get_me_authenticated(self, init_client):
        """已认证用户获取自身信息"""
        store = init_client.app.state.user_store
        store.create_user("alice", "pass123")

        # 登录获取 token
        login_resp = init_client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "pass123"},
        )
        token = login_resp.json()["token"]

        # 获取用户信息
        resp = init_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["username"] == "alice"

    def test_get_me_unauthenticated(self, init_client):
        """未认证访问 /me 应返回 401"""
        resp = init_client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_api_key_login(self, init_client):
        """API Key 登录"""
        store = init_client.app.state.user_store
        user = store.create_user("alice", "pass123")
        api_key = store.set_api_key(user.user_id)

        resp = init_client.post(
            "/api/auth/api-key",
            json={"api_key": api_key},
        )
        assert resp.status_code == 200
        assert "token" in resp.json()

    def test_api_key_login_invalid(self, init_client):
        """无效 API Key 登录失败"""
        resp = init_client.post(
            "/api/auth/api-key",
            json={"api_key": "invalid-key"},
        )
        assert resp.status_code == 401

    def test_refresh_token(self, init_client):
        """刷新 token"""
        store = init_client.app.state.user_store
        store.create_user("alice", "pass123")

        login_resp = init_client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "pass123"},
        )
        token = login_resp.json()["token"]

        resp = init_client.post(
            "/api/auth/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert "token" in resp.json()

    def test_logout(self, init_client):
        """注销"""
        store = init_client.app.state.user_store
        store.create_user("alice", "pass123")

        login_resp = init_client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "pass123"},
        )
        token = login_resp.json()["token"]

        resp = init_client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200


class TestConversationEndpoints:
    """会话端点测试"""

    def _login(self, client, username="alice", password="pass123"):
        """辅助：创建用户并登录"""
        store = client.app.state.user_store
        store.create_user(username, password)
        resp = client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        return resp.json()["token"]

    def test_create_conversation(self, init_client):
        """创建会话"""
        token = self._login(init_client)

        resp = init_client.post(
            "/api/conversations",
            json={"title": "测试会话"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "测试会话"
        assert "conversation_id" in data

    def test_list_conversations(self, init_client):
        """列出会话"""
        token = self._login(init_client)

        # 创建两个会话
        init_client.post(
            "/api/conversations",
            json={"title": "会话1"},
            headers={"Authorization": f"Bearer {token}"},
        )
        init_client.post(
            "/api/conversations",
            json={"title": "会话2"},
            headers={"Authorization": f"Bearer {token}"},
        )

        resp = init_client.get(
            "/api/conversations",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert len(resp.json()["conversations"]) == 2

    def test_get_conversation(self, init_client):
        """获取会话详情"""
        token = self._login(init_client)

        create_resp = init_client.post(
            "/api/conversations",
            json={"title": "详情测试"},
            headers={"Authorization": f"Bearer {token}"},
        )
        conv_id = create_resp.json()["conversation_id"]

        resp = init_client.get(
            f"/api/conversations/{conv_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "详情测试"

    def test_get_conversation_not_found(self, init_client):
        """获取不存在的会话"""
        token = self._login(init_client)
        resp = init_client.get(
            "/api/conversations/nonexistent",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    def test_delete_conversation(self, init_client):
        """删除会话"""
        token = self._login(init_client)

        create_resp = init_client.post(
            "/api/conversations",
            json={"title": "待删除"},
            headers={"Authorization": f"Bearer {token}"},
        )
        conv_id = create_resp.json()["conversation_id"]

        resp = init_client.delete(
            f"/api/conversations/{conv_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

        # 确认已删除
        resp = init_client.get(
            f"/api/conversations/{conv_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    def test_get_messages(self, init_client):
        """获取会话消息"""
        token = self._login(init_client)

        create_resp = init_client.post(
            "/api/conversations",
            json={"title": "消息测试"},
            headers={"Authorization": f"Bearer {token}"},
        )
        conv_id = create_resp.json()["conversation_id"]

        resp = init_client.get(
            f"/api/conversations/{conv_id}/messages",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["messages"] == []

    def test_send_message(self, init_client):
        """发送消息"""
        token = self._login(init_client)

        resp = init_client.post(
            "/api/chat",
            json={"content": "你好呀"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_message"]["content"] == "你好呀"
        assert data["ai_message"]["content"]  # 有 AI 回复
        assert "conversation_id" in data

    def test_send_message_to_existing_conversation(self, init_client):
        """向已有会话发送消息"""
        token = self._login(init_client)

        # 创建会话
        create_resp = init_client.post(
            "/api/conversations",
            json={"title": "持续对话"},
            headers={"Authorization": f"Bearer {token}"},
        )
        conv_id = create_resp.json()["conversation_id"]

        # 发送消息到该会话
        resp = init_client.post(
            "/api/chat",
            json={"content": "继续聊", "conversation_id": conv_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["conversation_id"] == conv_id

    def test_unauthenticated_access_denied(self, init_client):
        """未认证访问会话 API 应被拒绝"""
        resp = init_client.get("/api/conversations")
        assert resp.status_code == 401

        resp = init_client.post("/api/conversations", json={"title": "test"})
        assert resp.status_code == 401

        resp = init_client.post("/api/chat", json={"content": "test"})
        assert resp.status_code == 401

    def test_user_isolation(self, init_client):
        """用户数据隔离：user1 不能访问 user2 的会话"""
        store = init_client.app.state.user_store
        store.create_user("alice", "pass1")
        store.create_user("bob", "pass2")

        # alice 登录并创建会话
        alice_login = init_client.post(
            "/api/auth/login", json={"username": "alice", "password": "pass1"}
        )
        alice_token = alice_login.json()["token"]

        create_resp = init_client.post(
            "/api/conversations",
            json={"title": "Alice 的私密会话"},
            headers={"Authorization": f"Bearer {alice_token}"},
        )
        conv_id = create_resp.json()["conversation_id"]

        # bob 登录
        bob_login = init_client.post(
            "/api/auth/login", json={"username": "bob", "password": "pass2"}
        )
        bob_token = bob_login.json()["token"]

        # bob 不能访问 alice 的会话
        resp = init_client.get(
            f"/api/conversations/{conv_id}",
            headers={"Authorization": f"Bearer {bob_token}"},
        )
        assert resp.status_code == 404

        # bob 看不到 alice 的会话
        resp = init_client.get(
            "/api/conversations",
            headers={"Authorization": f"Bearer {bob_token}"},
        )
        assert len(resp.json()["conversations"]) == 0

    def test_search_messages(self, init_client):
        """跨会话全文搜索消息"""
        token = self._login(init_client)
        headers = {"Authorization": f"Bearer {token}"}

        # 创建会话并发送消息
        resp1 = init_client.post("/api/conversations", json={"title": "搜索测试"}, headers=headers)
        conv_id = resp1.json()["conversation_id"]

        # 直接通过 store 添加消息（避免调用 AI 回复）
        store = init_client.app.state.conv_store
        user_id = init_client.app.state.user_store.get_user_by_username("alice").user_id
        store.add_message(conv_id, user_id, "user", "今天天气真不错")
        store.add_message(conv_id, user_id, "assistant", "是呀，阳光明媚的～")
        store.add_message(conv_id, user_id, "user", "我想吃火锅")

        # 搜索"天气"
        resp = init_client.get("/api/messages/search", params={"q": "天气"}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "天气"
        assert len(data["results"]) == 1
        assert "天气" in data["results"][0]["content"]

        # 搜索"火锅"
        resp = init_client.get("/api/messages/search", params={"q": "火锅"}, headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()["results"]) == 1

        # 搜索不存在的关键词
        resp = init_client.get("/api/messages/search", params={"q": "不存在"}, headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()["results"]) == 0

    def test_search_messages_isolation(self, init_client):
        """搜索结果用户隔离"""
        store = init_client.app.state.conv_store
        user_store = init_client.app.state.user_store

        # 创建 alice 和 bob
        user_store.create_user("alice", "pass1")
        user_store.create_user("bob", "pass2")
        alice = user_store.get_user_by_username("alice")
        bob = user_store.get_user_by_username("bob")

        # alice 创建会话并添加消息
        conv = store.create_conversation(alice.user_id, "Alice 会话")
        store.add_message(conv.conversation_id, alice.user_id, "user", "我的秘密是喜欢吃披萨")

        # bob 创建会话并添加消息
        conv2 = store.create_conversation(bob.user_id, "Bob 会话")
        store.add_message(conv2.conversation_id, bob.user_id, "user", "我喜欢吃汉堡")

        # alice 搜索只能看到自己的消息
        alice_login = init_client.post("/api/auth/login", json={"username": "alice", "password": "pass1"})
        alice_token = alice_login.json()["token"]
        resp = init_client.get("/api/messages/search", params={"q": "吃"}, headers={"Authorization": f"Bearer {alice_token}"})
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 1
        assert "披萨" in results[0]["content"]

    def test_export_conversation_markdown(self, init_client):
        """导出会话为 Markdown"""
        token = self._login(init_client)
        headers = {"Authorization": f"Bearer {token}"}

        # 创建会话并添加消息
        resp1 = init_client.post("/api/conversations", json={"title": "导出测试"}, headers=headers)
        conv_id = resp1.json()["conversation_id"]

        store = init_client.app.state.conv_store
        user_id = init_client.app.state.user_store.get_user_by_username("alice").user_id
        store.add_message(conv_id, user_id, "user", "你好")
        store.add_message(conv_id, user_id, "assistant", "你好呀～有什么可以帮你的吗？")

        # 导出 Markdown
        resp = init_client.get(f"/api/conversations/{conv_id}/export", params={"format": "markdown"}, headers=headers)
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/markdown")
        body = resp.text
        assert "# 导出测试" in body
        assert "你好" in body
        assert "用户" in body
        assert "助手" in body

    def test_export_conversation_json(self, init_client):
        """导出会话为 JSON"""
        token = self._login(init_client)
        headers = {"Authorization": f"Bearer {token}"}

        resp1 = init_client.post("/api/conversations", json={"title": "JSON导出"}, headers=headers)
        conv_id = resp1.json()["conversation_id"]

        store = init_client.app.state.conv_store
        user_id = init_client.app.state.user_store.get_user_by_username("alice").user_id
        store.add_message(conv_id, user_id, "user", "测试消息")

        resp = init_client.get(f"/api/conversations/{conv_id}/export", params={"format": "json"}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "JSON导出"
        assert len(data["messages"]) == 1
        assert data["messages"][0]["content"] == "测试消息"

    def test_export_not_found(self, init_client):
        """导出不存在的会话"""
        token = self._login(init_client)
        resp = init_client.get("/api/conversations/nonexistent/export", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 404


class TestAdminEndpoints:
    """管理端点测试"""

    def _create_admin(self, store):
        """创建管理员用户"""
        return store.create_user("admin", "admin123", role="admin")

    def _login_admin(self, client):
        """管理员登录"""
        resp = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        return resp.json()["token"]

    def test_admin_list_users(self, init_client):
        """管理员列出用户"""
        store = init_client.app.state.user_store
        self._create_admin(store)
        store.create_user("alice", "pass")
        token = self._login_admin(init_client)

        resp = init_client.get(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert len(resp.json()["users"]) == 2

    def test_admin_create_user(self, init_client):
        """管理员创建用户"""
        store = init_client.app.state.user_store
        self._create_admin(store)
        token = self._login_admin(init_client)

        resp = init_client.post(
            "/api/admin/users",
            json={"username": "newuser", "password": "newpass", "display_name": "新用户"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["user"]["username"] == "newuser"

    def test_admin_delete_user(self, init_client):
        """管理员删除用户"""
        store = init_client.app.state.user_store
        self._create_admin(store)
        alice = store.create_user("alice", "pass")
        token = self._login_admin(init_client)

        resp = init_client.delete(
            f"/api/admin/users/{alice.user_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert store.user_count == 1  # 只剩 admin

    def test_admin_cannot_delete_self(self, init_client):
        """管理员不能删除自己"""
        store = init_client.app.state.user_store
        admin = self._create_admin(store)
        token = self._login_admin(init_client)

        resp = init_client.delete(
            f"/api/admin/users/{admin.user_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    def test_admin_generate_api_key(self, init_client):
        """管理员为用户生成 API Key"""
        store = init_client.app.state.user_store
        self._create_admin(store)
        alice = store.create_user("alice", "pass")
        token = self._login_admin(init_client)

        resp = init_client.post(
            f"/api/admin/users/{alice.user_id}/api-key",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["api_key"].startswith("yuan_")

    def test_admin_revoke_api_key(self, init_client):
        """管理员吊销 API Key"""
        store = init_client.app.state.user_store
        self._create_admin(store)
        alice = store.create_user("alice", "pass")
        store.set_api_key(alice.user_id)
        token = self._login_admin(init_client)

        resp = init_client.delete(
            f"/api/admin/users/{alice.user_id}/api-key",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    def test_non_admin_cannot_access_admin(self, init_client):
        """非管理员不能访问管理端点"""
        store = init_client.app.state.user_store
        store.create_user("alice", "pass")

        login_resp = init_client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "pass"},
        )
        token = login_resp.json()["token"]

        resp = init_client.get(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    def test_admin_metrics(self, init_client):
        """管理员获取系统指标"""
        store = init_client.app.state.user_store
        self._create_admin(store)
        token = self._login_admin(init_client)

        resp = init_client.get(
            "/api/admin/metrics",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "system" in data
        assert "yuanbot" in data
