"""测试接入与通信系统"""

from __future__ import annotations

import pytest

from yuanbot.core.types import ContentType, MessageContent
from yuanbot.gateway.adapter_manager import AdapterManager
from yuanbot.gateway.gateway import YuanGateway
from yuanbot.gateway.identity_service import IdentityService
from yuanbot.gateway.push_dispatcher import PushDispatcher


class TestIdentityService:
    """身份链接服务测试"""

    def test_resolve_new_user(self):
        service = IdentityService()
        uid = service.resolve_user_id("telegram", "tg_123")
        assert uid.startswith("yb_")

    def test_resolve_same_user_returns_same_id(self):
        service = IdentityService()
        uid1 = service.resolve_user_id("telegram", "tg_123")
        uid2 = service.resolve_user_id("telegram", "tg_123")
        assert uid1 == uid2

    def test_different_platforms_different_ids(self):
        service = IdentityService()
        uid1 = service.resolve_user_id("telegram", "tg_123")
        uid2 = service.resolve_user_id("discord", "dc_456")
        assert uid1 != uid2

    def test_build_session_id(self):
        service = IdentityService()
        sid = service.build_session_id("telegram", "tg_123")
        assert sid == "telegram:tg_123"

    def test_link_accounts(self):
        service = IdentityService()
        uid = service.resolve_user_id("telegram", "tg_123")
        result = service.link_accounts(uid, "discord", "dc_456")
        assert result is True
        # 现在 discord 账号应该映射到同一个用户
        uid2 = service.resolve_user_id("discord", "dc_456")
        assert uid == uid2

    def test_link_accounts_invalid_primary(self):
        service = IdentityService()
        result = service.link_accounts("nonexistent", "discord", "dc_456")
        assert result is False

    def test_get_linked_platforms(self):
        service = IdentityService()
        uid = service.resolve_user_id("telegram", "tg_123")
        service.link_accounts(uid, "discord", "dc_456")
        platforms = service.get_linked_platforms(uid)
        assert len(platforms) == 2

    def test_get_all_identities(self):
        service = IdentityService()
        service.resolve_user_id("telegram", "tg_123")
        service.resolve_user_id("discord", "dc_456")
        info = service.get_all_identities()
        assert info["total_mappings"] == 2
        assert info["total_users"] == 2


class TestPushDispatcher:
    """主动推送调度器测试"""

    @pytest.mark.asyncio
    async def test_dispatch_without_callback(self):
        dispatcher = PushDispatcher()
        content = MessageContent(content_type=ContentType.TEXT, text="Hello")
        result = await dispatcher.dispatch("telegram", "tg_123", content)
        assert result is True
        assert len(dispatcher.get_pending_tasks()) == 1

    @pytest.mark.asyncio
    async def test_dispatch_with_callback(self):
        dispatcher = PushDispatcher()

        async def mock_callback(platform, target_id, content):
            return True

        dispatcher.set_send_callback(mock_callback)
        content = MessageContent(content_type=ContentType.TEXT, text="Hello")
        result = await dispatcher.dispatch("telegram", "tg_123", content)
        assert result is True
        assert len(dispatcher.get_sent_tasks()) == 1

    @pytest.mark.asyncio
    async def test_dispatch_with_failing_callback(self):
        dispatcher = PushDispatcher()

        async def mock_callback(platform, target_id, content):
            raise Exception("Network error")

        dispatcher.set_send_callback(mock_callback)
        content = MessageContent(content_type=ContentType.TEXT, text="Hello")
        result = await dispatcher.dispatch("telegram", "tg_123", content)
        assert result is False
        assert len(dispatcher.get_sent_tasks()) == 1
        assert dispatcher.get_sent_tasks()[0]["status"] == "error"

    def test_clear_pending(self):
        dispatcher = PushDispatcher()
        dispatcher._pending_tasks = [{"id": "1"}, {"id": "2"}]
        count = dispatcher.clear_pending()
        assert count == 2
        assert len(dispatcher.get_pending_tasks()) == 0


class TestAdapterManager:
    """适配器管理器测试"""

    def test_get_adapter_not_loaded(self):
        manager = AdapterManager()
        assert manager.get_adapter("telegram") is None

    def test_get_all_adapters_empty(self):
        manager = AdapterManager()
        assert len(manager.get_all_adapters()) == 0

    def test_get_health_status_empty(self):
        manager = AdapterManager()
        assert len(manager.get_health_status()) == 0

    def test_set_health_status(self):
        manager = AdapterManager()
        manager.set_health_status("telegram", True)
        assert manager.get_health_status()["telegram"] is True

    @pytest.mark.asyncio
    async def test_unload_nonexistent(self):
        manager = AdapterManager()
        result = await manager.unload_adapter("telegram")
        assert result is False


class TestYuanGateway:
    """统一网关测试"""

    @pytest.mark.asyncio
    async def test_start_stop(self):
        gateway = YuanGateway()
        await gateway.start()
        status = gateway.get_health_status()
        assert status["status"] == "ok"

        await gateway.stop()
        status = gateway.get_health_status()
        assert status["status"] == "stopped"

    def test_resolve_identity(self):
        gateway = YuanGateway()
        uid, sid = gateway.resolve_identity("telegram", "tg_123")
        assert uid.startswith("yb_")
        assert sid == "telegram:tg_123"

    def test_resolve_identity_consistency(self):
        gateway = YuanGateway()
        uid1, sid1 = gateway.resolve_identity("telegram", "tg_123")
        uid2, sid2 = gateway.resolve_identity("telegram", "tg_123")
        assert uid1 == uid2
        assert sid1 == sid2

    def test_health_status_structure(self):
        gateway = YuanGateway()
        status = gateway.get_health_status()
        assert "status" in status
        assert "adapters" in status
        assert "identities" in status
