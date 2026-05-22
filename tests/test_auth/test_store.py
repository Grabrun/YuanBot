"""用户存储与认证系统测试"""

from __future__ import annotations

import pytest

from yuanbot.auth.models import UserRole
from yuanbot.auth.store import ConversationStore, UserStore


class TestUserStore:
    """UserStore 测试"""

    @pytest.fixture
    def store(self, tmp_path):
        s = UserStore(data_dir=tmp_path)
        return s

    @pytest.mark.asyncio
    async def test_initialize(self, store):
        await store.initialize()
        assert store.user_count == 0

    @pytest.mark.asyncio
    async def test_create_user(self, store):
        await store.initialize()
        user = store.create_user("alice", "password123", display_name="Alice")
        assert user.username == "alice"
        assert user.display_name == "Alice"
        assert user.role == UserRole.USER
        assert user.password_hash != "password123"  # 不存明文
        assert store.user_count == 1

    @pytest.mark.asyncio
    async def test_create_admin(self, store):
        await store.initialize()
        user = store.create_user("admin", "admin123", role=UserRole.ADMIN)
        assert user.role == UserRole.ADMIN
        assert store.admin_count == 1

    @pytest.mark.asyncio
    async def test_duplicate_username_raises(self, store):
        await store.initialize()
        store.create_user("alice", "pass1")
        with pytest.raises(ValueError, match="already exists"):
            store.create_user("alice", "pass2")

    @pytest.mark.asyncio
    async def test_get_user_by_id(self, store):
        await store.initialize()
        user = store.create_user("bob", "pass")
        found = store.get_user(user.user_id)
        assert found is not None
        assert found.username == "bob"

    @pytest.mark.asyncio
    async def test_get_user_by_username(self, store):
        await store.initialize()
        store.create_user("charlie", "pass")
        found = store.get_user_by_username("charlie")
        assert found is not None

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, store):
        await store.initialize()
        assert store.get_user("no-such-id") is None
        assert store.get_user_by_username("no-such-user") is None

    @pytest.mark.asyncio
    async def test_verify_password_correct(self, store):
        await store.initialize()
        store.create_user("alice", "correct-password")
        user = store.verify_password("alice", "correct-password")
        assert user is not None
        assert user.username == "alice"

    @pytest.mark.asyncio
    async def test_verify_password_wrong(self, store):
        await store.initialize()
        store.create_user("alice", "correct-password")
        user = store.verify_password("alice", "wrong-password")
        assert user is None

    @pytest.mark.asyncio
    async def test_verify_password_nonexistent_user(self, store):
        await store.initialize()
        assert store.verify_password("ghost", "pass") is None

    @pytest.mark.asyncio
    async def test_api_key_lifecycle(self, store):
        await store.initialize()
        user = store.create_user("alice", "pass")

        # 生成 API Key
        api_key = store.set_api_key(user.user_id)
        assert api_key.startswith("yuan_")

        # 通过 API Key 查找用户
        found = store.get_user_by_api_key(api_key)
        assert found is not None
        assert found.username == "alice"

        # 吊销 API Key
        assert store.revoke_api_key(user.user_id) is True
        assert store.get_user_by_api_key(api_key) is None

    @pytest.mark.asyncio
    async def test_delete_user(self, store):
        await store.initialize()
        user = store.create_user("alice", "pass")
        assert store.delete_user(user.user_id) is True
        assert store.user_count == 0
        assert store.get_user(user.user_id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false(self, store):
        await store.initialize()
        assert store.delete_user("no-such-id") is False

    @pytest.mark.asyncio
    async def test_persistence(self, tmp_path):
        """数据持久化测试：重启后数据不丢失"""
        store1 = UserStore(data_dir=tmp_path)
        await store1.initialize()
        store1.create_user("alice", "pass123")
        api_key = store1.set_api_key(store1.get_user_by_username("alice").user_id)

        # 模拟重启
        store2 = UserStore(data_dir=tmp_path)
        await store2.initialize()
        assert store2.user_count == 1

        found = store2.get_user_by_username("alice")
        assert found is not None
        assert store2.verify_password("alice", "pass123") is not None
        assert store2.get_user_by_api_key(api_key) is not None

    @pytest.mark.asyncio
    async def test_list_users(self, store):
        await store.initialize()
        store.create_user("alice", "pass1")
        store.create_user("bob", "pass2")
        users = store.list_users()
        assert len(users) == 2
        usernames = {u.username for u in users}
        assert usernames == {"alice", "bob"}

    @pytest.mark.asyncio
    async def test_record_login(self, store):
        await store.initialize()
        user = store.create_user("alice", "pass")
        assert user.last_login is None
        store.record_login(user)
        updated = store.get_user(user.user_id)
        assert updated.last_login is not None


class TestConversationStore:
    """ConversationStore 测试"""

    @pytest.fixture
    def store(self, tmp_path):
        s = ConversationStore(data_dir=tmp_path)
        return s

    @pytest.mark.asyncio
    async def test_initialize(self, store):
        await store.initialize()
        assert store.conversation_count == 0

    @pytest.mark.asyncio
    async def test_create_conversation(self, store):
        await store.initialize()
        conv = store.create_conversation("user1", title="测试会话")
        assert conv.user_id == "user1"
        assert conv.title == "测试会话"
        assert store.conversation_count == 1

    @pytest.mark.asyncio
    async def test_list_conversations(self, store):
        await store.initialize()
        store.create_conversation("user1", "会话1")
        store.create_conversation("user1", "会话2")
        store.create_conversation("user2", "会话3")

        user1_convs = store.list_conversations("user1")
        assert len(user1_convs) == 2

        user2_convs = store.list_conversations("user2")
        assert len(user2_convs) == 1

    @pytest.mark.asyncio
    async def test_get_conversation_with_ownership(self, store):
        await store.initialize()
        conv = store.create_conversation("user1")

        # 所有者可以访问
        assert store.get_conversation(conv.conversation_id, "user1") is not None
        # 非所有者不能访问
        assert store.get_conversation(conv.conversation_id, "user2") is None
        # 不校验归属时可以访问
        assert store.get_conversation(conv.conversation_id) is not None

    @pytest.mark.asyncio
    async def test_delete_conversation(self, store):
        await store.initialize()
        conv = store.create_conversation("user1")

        # 非所有者不能删除
        assert store.delete_conversation(conv.conversation_id, "user2") is False
        assert store.conversation_count == 1

        # 所有者可以删除
        assert store.delete_conversation(conv.conversation_id, "user1") is True
        assert store.conversation_count == 0

    @pytest.mark.asyncio
    async def test_add_message(self, store):
        await store.initialize()
        conv = store.create_conversation("user1")

        msg = store.add_message(conv.conversation_id, "user1", "user", "你好")
        assert msg is not None
        assert msg.content == "你好"
        assert msg.role == "user"

        # 会话消息数更新
        updated = store.get_conversation(conv.conversation_id)
        assert updated.message_count == 1

    @pytest.mark.asyncio
    async def test_auto_title_from_first_message(self, store):
        await store.initialize()
        conv = store.create_conversation("user1")

        store.add_message(conv.conversation_id, "user1", "user", "今天天气真不错啊")
        updated = store.get_conversation(conv.conversation_id)
        assert updated.title == "今天天气真不错啊"

    @pytest.mark.asyncio
    async def test_auto_title_truncates_long_message(self, store):
        await store.initialize()
        conv = store.create_conversation("user1")

        long_msg = "这是一条很长很长很长很长很长很长很长很长的消息"
        store.add_message(conv.conversation_id, "user1", "user", long_msg)
        updated = store.get_conversation(conv.conversation_id)
        assert len(updated.title) <= 23  # 20 + "..."

    @pytest.mark.asyncio
    async def test_get_messages(self, store):
        await store.initialize()
        conv = store.create_conversation("user1")

        store.add_message(conv.conversation_id, "user1", "user", "消息1")
        store.add_message(conv.conversation_id, "user1", "assistant", "回复1")
        store.add_message(conv.conversation_id, "user1", "user", "消息2")

        messages = store.get_messages(conv.conversation_id, "user1")
        assert len(messages) == 3
        assert messages[0].content == "消息1"
        assert messages[1].role == "assistant"

    @pytest.mark.asyncio
    async def test_get_messages_with_limit(self, store):
        await store.initialize()
        conv = store.create_conversation("user1")

        for i in range(10):
            store.add_message(conv.conversation_id, "user1", "user", f"消息{i}")

        messages = store.get_messages(conv.conversation_id, "user1", limit=3, offset=5)
        assert len(messages) == 3
        assert messages[0].content == "消息5"

    @pytest.mark.asyncio
    async def test_get_messages_ownership_check(self, store):
        await store.initialize()
        conv = store.create_conversation("user1")
        store.add_message(conv.conversation_id, "user1", "user", "秘密消息")

        # 非所有者获取不到消息
        messages = store.get_messages(conv.conversation_id, "user2")
        assert len(messages) == 0

    @pytest.mark.asyncio
    async def test_persistence(self, tmp_path):
        """数据持久化测试"""
        store1 = ConversationStore(data_dir=tmp_path)
        await store1.initialize()
        conv = store1.create_conversation("user1", "测试")
        store1.add_message(conv.conversation_id, "user1", "user", "你好")
        store1.add_message(conv.conversation_id, "user1", "assistant", "你好呀~")

        # 模拟重启
        store2 = ConversationStore(data_dir=tmp_path)
        await store2.initialize()
        assert store2.conversation_count == 1

        convs = store2.list_conversations("user1")
        assert len(convs) == 1
        assert convs[0].title == "测试"

        messages = store2.get_messages(convs[0].conversation_id, "user1")
        assert len(messages) == 2
        assert messages[0].content == "你好"
        assert messages[1].content == "你好呀~"
