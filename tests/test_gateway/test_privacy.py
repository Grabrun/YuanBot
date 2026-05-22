"""GDPR 隐私管理器测试"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from yuanbot.gateway.privacy import AuditLogEntry, PrivacyManager


class TestAuditLogEntry:
    """审计日志条目测试"""

    def test_create_entry(self):
        """测试创建审计日志条目"""
        entry = AuditLogEntry(
            action="data_export",
            user_id="user1",
            details={"fact_count": 5},
        )
        assert entry.action == "data_export"
        assert entry.user_id == "user1"
        assert entry.success is True
        assert entry.error is None
        assert entry.details == {"fact_count": 5}

    def test_to_dict(self):
        """测试转换为字典"""
        entry = AuditLogEntry(action="data_deletion", user_id="user2")
        d = entry.to_dict()
        assert d["action"] == "data_deletion"
        assert d["user_id"] == "user2"
        assert d["success"] is True
        assert "timestamp" in d

    def test_failed_entry(self):
        """测试失败的审计日志条目"""
        entry = AuditLogEntry(
            action="data_export",
            user_id="user3",
            success=False,
            error="Memory manager not available",
        )
        assert entry.success is False
        assert entry.error == "Memory manager not available"


class TestPrivacyManagerAuditLog:
    """隐私管理器审计日志测试"""

    def test_get_audit_log_empty(self):
        """测试空审计日志"""
        pm = PrivacyManager()
        log = pm.get_audit_log()
        assert log == []

    def test_get_audit_log_filtered(self):
        """测试按用户过滤审计日志"""
        pm = PrivacyManager()
        pm._audit_log = [
            AuditLogEntry(action="data_export", user_id="user1"),
            AuditLogEntry(action="data_deletion", user_id="user2"),
            AuditLogEntry(action="data_export", user_id="user1"),
        ]

        all_log = pm.get_audit_log()
        assert len(all_log) == 3

        user1_log = pm.get_audit_log(user_id="user1")
        assert len(user1_log) == 2
        assert all(e["user_id"] == "user1" for e in user1_log)

        user2_log = pm.get_audit_log(user_id="user2")
        assert len(user2_log) == 1

    @pytest.mark.asyncio
    async def test_export_creates_audit_entry(self):
        """测试数据导出创建审计日志"""
        mock_memory = AsyncMock()
        mock_profile = MagicMock()
        mock_profile.display_name = "Test User"
        mock_profile.relationship_stage = "initial"
        mock_profile.trust_score = 0.5
        mock_profile.total_interactions = 10
        mock_profile.first_interaction = None
        mock_profile.last_interaction = None
        mock_profile.preferences = {}
        mock_profile.platform_ids = {}
        mock_profile.typical_mood_patterns = {}
        mock_memory.get_or_create_user_profile.return_value = mock_profile
        mock_memory.get_fact_memories.return_value = []
        mock_memory.get_episodic_memories.return_value = []
        mock_memory.get_semantic_memories.return_value = []
        mock_memory.get_emotion_trend.return_value = None

        pm = PrivacyManager(memory_manager=mock_memory)
        result = await pm.export_user_data("user1")

        assert "error" not in result or result.get("error") is None
        assert len(pm._audit_log) == 1
        assert pm._audit_log[0].action == "data_export"
        assert pm._audit_log[0].user_id == "user1"
        assert pm._audit_log[0].success is True

    @pytest.mark.asyncio
    async def test_export_failure_creates_audit_entry(self):
        """测试导出失败时创建审计日志"""
        mock_memory = AsyncMock()
        mock_memory.get_or_create_user_profile.side_effect = RuntimeError("DB error")

        pm = PrivacyManager(memory_manager=mock_memory)
        result = await pm.export_user_data("user1")

        assert result.get("error") == "DB error"
        assert len(pm._audit_log) == 1
        assert pm._audit_log[0].success is False
        assert pm._audit_log[0].error == "DB error"

    @pytest.mark.asyncio
    async def test_delete_creates_audit_entry(self):
        """测试数据删除创建审计日志"""
        mock_memory = AsyncMock()
        mock_memory.get_fact_memories.return_value = []
        mock_memory.get_episodic_memories.return_value = []
        mock_memory.get_semantic_memories.return_value = []
        mock_memory._fact_memories = {}
        mock_memory._episodic_memories = {}
        mock_memory._semantic_memories = {}
        mock_memory._user_profiles = {}

        pm = PrivacyManager(memory_manager=mock_memory)
        result = await pm.delete_user_data("user1")

        assert "error" not in result or result.get("error") is None
        assert len(pm._audit_log) == 1
        assert pm._audit_log[0].action == "data_deletion"
        assert pm._audit_log[0].success is True

    @pytest.mark.asyncio
    async def test_delete_failure_creates_audit_entry(self):
        """测试删除失败时创建审计日志"""
        mock_memory = AsyncMock()
        mock_memory.get_fact_memories.side_effect = RuntimeError("Connection lost")

        pm = PrivacyManager(memory_manager=mock_memory)
        result = await pm.delete_user_data("user1")

        assert result.get("error") == "Connection lost"
        assert len(pm._audit_log) == 1
        assert pm._audit_log[0].success is False


class TestPrivacyManagerPrivateSession:
    """隐私模式测试"""

    def test_enable_disable_private_session(self):
        """测试启用/禁用隐私模式"""
        pm = PrivacyManager()
        assert pm.is_private_session("session1") is False

        pm.enable_private_session("session1")
        assert pm.is_private_session("session1") is True
        assert pm.should_record_memory("session1") is False

        pm.disable_private_session("session1")
        assert pm.is_private_session("session1") is False
        assert pm.should_record_memory("session1") is True

    def test_disable_nonexistent_session(self):
        """测试禁用不存在的会话不会报错"""
        pm = PrivacyManager()
        pm.disable_private_session("nonexistent")  # 不应抛异常
