"""YuanBot 核心类型测试"""


from yuanbot.core.types import (
    ContentType,
    MemoryNode,
    MemoryType,
    Message,
    SendResult,
    UserMessage,
    UserProfile,
)


class TestMemoryNode:
    def test_create_working_memory(self):
        node = MemoryNode(
            memory_type=MemoryType.WORKING,
            content="用户说今天天气不错",
        )
        assert node.memory_type == MemoryType.WORKING
        assert node.content == "用户说今天天气不错"
        assert node.importance_score == 0.5
        assert node.access_count == 0

    def test_create_episodic_memory(self):
        node = MemoryNode(
            memory_type=MemoryType.EPISODIC,
            content="用户聊到工作压力",
            summary="工作压力相关对话",
            emotional_tone="negative",
            key_entities=["工作", "压力"],
            importance_score=0.8,
        )
        assert node.memory_type == MemoryType.EPISODIC
        assert node.emotional_tone == "negative"
        assert "工作" in node.key_entities
        assert node.importance_score == 0.8


class TestUserMessage:
    def test_create_message(self):
        msg = UserMessage(
            platform="telegram",
            platform_user_id="tg_123",
            yuanbot_user_id="yb_tg_123",
            session_id="telegram:tg_123",
            content_type=ContentType.TEXT,
            text="你好呀",
        )
        assert msg.platform == "telegram"
        assert msg.text == "你好呀"
        assert msg.content_type == ContentType.TEXT


class TestUserProfile:
    def test_default_profile(self):
        profile = UserProfile(user_id="test_user")
        assert profile.relationship_stage == "initial"
        assert profile.trust_score == 0.0
        assert profile.total_interactions == 0

    def test_update_preferences(self):
        profile = UserProfile(user_id="test_user")
        profile.preferences["favorite_color"] = "蓝色"
        assert profile.preferences["favorite_color"] == "蓝色"


class TestMessage:
    def test_system_message(self):
        msg = Message(role="system", content="你是一个AI助手")
        assert msg.role == "system"
        assert msg.content == "你是一个AI助手"

    def test_user_message(self):
        msg = Message(role="user", content="你好")
        assert msg.role == "user"


class TestSendResult:
    def test_success(self):
        result = SendResult(success=True, message_id="msg_123")
        assert result.success
        assert result.message_id == "msg_123"

    def test_failure(self):
        result = SendResult(success=False, error="网络错误")
        assert not result.success
        assert result.error == "网络错误"
