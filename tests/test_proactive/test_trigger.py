"""测试 ProactiveTrigger ABC 和 TriggerManager

设计参考: proactive-companion-system.md 第7.1节
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from yuanbot.proactive.trigger import (
    ProactiveTrigger,
    TriggerManager,
    TriggerResult,
)

# ── 测试用触发器 ──────────────────────────────

class AlwaysTrigger(ProactiveTrigger):
    """总是触发的测试触发器"""

    def get_event_type(self) -> str:
        return "test_event"

    async def check(self, user_id: str) -> TriggerResult:
        return TriggerResult(
            triggered=True,
            event_type="test_event",
            data={"reason": "always"},
            priority=8,
        )

    def get_name(self) -> str:
        return "AlwaysTrigger"

    def get_priority(self) -> int:
        return 8


class NeverTrigger(ProactiveTrigger):
    """从不触发的测试触发器"""

    def get_event_type(self) -> str:
        return "test_event"

    async def check(self, user_id: str) -> TriggerResult:
        return TriggerResult(triggered=False)

    def get_name(self) -> str:
        return "NeverTrigger"


class FailingTrigger(ProactiveTrigger):
    """抛异常的测试触发器"""

    def get_event_type(self) -> str:
        return "error_event"

    async def check(self, user_id: str) -> TriggerResult:
        raise RuntimeError("trigger error")

    def get_name(self) -> str:
        return "FailingTrigger"


# ── TriggerResult 测试 ──────────────────────────

class TestTriggerResult:
    def test_default_values(self):
        result = TriggerResult(triggered=False)
        assert not result.triggered
        assert result.event_type == ""
        assert result.data == {}
        assert result.priority == 5

    def test_triggered_with_data(self):
        result = TriggerResult(
            triggered=True,
            event_type="weather_change",
            data={"temp_drop": 8},
            priority=7,
        )
        assert result.triggered
        assert result.event_type == "weather_change"
        assert result.data["temp_drop"] == 8
        assert result.priority == 7


# ── ProactiveTrigger ABC 测试 ──────────────────

class TestProactiveTriggerABC:
    @pytest.mark.asyncio
    async def test_always_trigger(self):
        trigger = AlwaysTrigger()
        result = await trigger.check("user1")
        assert result.triggered
        assert result.data["reason"] == "always"

    @pytest.mark.asyncio
    async def test_never_trigger(self):
        trigger = NeverTrigger()
        result = await trigger.check("user1")
        assert not result.triggered

    @pytest.mark.asyncio
    async def test_failing_trigger(self):
        trigger = FailingTrigger()
        with pytest.raises(RuntimeError, match="trigger error"):
            await trigger.check("user1")

    def test_get_event_type(self):
        trigger = AlwaysTrigger()
        assert trigger.get_event_type() == "test_event"

    def test_get_priority(self):
        trigger = AlwaysTrigger()
        assert trigger.get_priority() == 8

    def test_default_priority(self):
        trigger = NeverTrigger()
        assert trigger.get_priority() == 5

    @pytest.mark.asyncio
    async def test_initialize_and_shutdown(self):
        """测试可选的初始化和关闭钩子"""
        trigger = AlwaysTrigger()
        # 默认实现不做任何事情
        await trigger.initialize({"key": "value"})
        await trigger.shutdown()


# ── TriggerManager 测试 ──────────────────────────

class TestTriggerManager:
    def test_register(self):
        mgr = TriggerManager()
        trigger = AlwaysTrigger()
        name = mgr.register(trigger)
        assert name == "AlwaysTrigger"
        assert mgr.trigger_count == 1

    def test_register_with_manifest(self):
        mgr = TriggerManager()
        trigger = AlwaysTrigger()
        manifest = {"name": "always", "version": "1.0.0", "event_type": "test_event"}
        name = mgr.register(trigger, manifest=manifest)
        assert name == "AlwaysTrigger"
        assert mgr.get_manifests()["AlwaysTrigger"] == manifest

    def test_unregister(self):
        mgr = TriggerManager()
        mgr.register(AlwaysTrigger())
        assert mgr.unregister("AlwaysTrigger")
        assert mgr.trigger_count == 0

    def test_unregister_nonexistent(self):
        mgr = TriggerManager()
        assert not mgr.unregister("nonexistent")

    def test_get(self):
        mgr = TriggerManager()
        trigger = AlwaysTrigger()
        mgr.register(trigger)
        assert mgr.get("AlwaysTrigger") is trigger
        assert mgr.get("nonexistent") is None

    def test_get_all(self):
        mgr = TriggerManager()
        mgr.register(AlwaysTrigger())
        mgr.register(NeverTrigger())
        all_triggers = mgr.get_all()
        assert len(all_triggers) == 2

    def test_get_by_event_type(self):
        mgr = TriggerManager()
        mgr.register(AlwaysTrigger())  # event_type = "test_event"
        mgr.register(NeverTrigger())  # event_type = "test_event"
        mgr.register(FailingTrigger())  # event_type = "error_event"

        test_triggers = mgr.get_by_event_type("test_event")
        assert len(test_triggers) == 2

        error_triggers = mgr.get_by_event_type("error_event")
        assert len(error_triggers) == 1

        assert mgr.get_by_event_type("nonexistent") == []

    @pytest.mark.asyncio
    async def test_check_all(self):
        mgr = TriggerManager()
        mgr.register(AlwaysTrigger())
        mgr.register(NeverTrigger())

        results = await mgr.check_all("user1")
        assert len(results) == 1
        assert results[0].triggered
        assert results[0].event_type == "test_event"

    @pytest.mark.asyncio
    async def test_check_all_with_failing(self):
        """失败的触发器不影响其他触发器"""
        mgr = TriggerManager()
        mgr.register(AlwaysTrigger())
        mgr.register(FailingTrigger())

        results = await mgr.check_all("user1")
        assert len(results) == 1
        assert results[0].triggered

    @pytest.mark.asyncio
    async def test_check_all_none_triggered(self):
        mgr = TriggerManager()
        mgr.register(NeverTrigger())

        results = await mgr.check_all("user1")
        assert len(results) == 0


# ── 插件加载测试 ──────────────────────────────

class TestTriggerPluginLoading:
    @pytest.mark.asyncio
    async def test_load_plugins_from_dir(self):
        """测试从目录加载触发器插件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "test_trigger"
            plugin_dir.mkdir()

            # 创建 manifest
            manifest = {
                "name": "test_trigger",
                "version": "1.0.0",
                "event_type": "test_event",
                "entry_point": "trigger.py",
                "enabled": True,
            }
            (plugin_dir / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )

            # 创建触发器代码
            trigger_code = '''
from yuanbot.proactive.trigger import ProactiveTrigger, TriggerResult

class TestPluginTrigger(ProactiveTrigger):
    def get_event_type(self) -> str:
        return "test_event"

    async def check(self, user_id: str) -> TriggerResult:
        return TriggerResult(triggered=True, data={"plugin": True})
'''
            (plugin_dir / "trigger.py").write_text(trigger_code, encoding="utf-8")

            mgr = TriggerManager()
            loaded = await mgr.load_plugins(tmpdir)

            assert loaded == 1
            assert mgr.trigger_count == 1

            # 验证触发器可以工作
            results = await mgr.check_all("user1")
            assert len(results) == 1
            assert results[0].data["plugin"] is True

    @pytest.mark.asyncio
    async def test_load_plugins_disabled(self):
        """测试禁用的插件不会被加载"""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "disabled_trigger"
            plugin_dir.mkdir()

            manifest = {
                "name": "disabled_trigger",
                "enabled": False,
                "entry_point": "trigger.py",
            }
            (plugin_dir / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )

            trigger_code = '''
from yuanbot.proactive.trigger import ProactiveTrigger, TriggerResult

class DisabledTrigger(ProactiveTrigger):
    def get_event_type(self) -> str:
        return "test_event"
    async def check(self, user_id: str) -> TriggerResult:
        return TriggerResult(triggered=True)
'''
            (plugin_dir / "trigger.py").write_text(trigger_code, encoding="utf-8")

            mgr = TriggerManager()
            loaded = await mgr.load_plugins(tmpdir)
            assert loaded == 0
            assert mgr.trigger_count == 0

    @pytest.mark.asyncio
    async def test_load_plugins_no_manifest(self):
        """测试没有 manifest 的目录被跳过"""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "no_manifest"
            plugin_dir.mkdir()
            (plugin_dir / "trigger.py").write_text("pass", encoding="utf-8")

            mgr = TriggerManager()
            loaded = await mgr.load_plugins(tmpdir)
            assert loaded == 0

    @pytest.mark.asyncio
    async def test_load_plugins_nonexistent_dir(self):
        """测试不存在的目录返回 0"""
        mgr = TriggerManager()
        loaded = await mgr.load_plugins("/nonexistent/path")
        assert loaded == 0

    @pytest.mark.asyncio
    async def test_load_plugins_empty_dir(self):
        """测试空目录返回 0"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = TriggerManager()
            loaded = await mgr.load_plugins(tmpdir)
            assert loaded == 0

    @pytest.mark.asyncio
    async def test_load_plugins_multiple(self):
        """测试加载多个插件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(3):
                plugin_dir = Path(tmpdir) / f"trigger_{i}"
                plugin_dir.mkdir()

                manifest = {
                    "name": f"trigger_{i}",
                    "version": "1.0.0",
                    "event_type": f"event_{i}",
                    "entry_point": "trigger.py",
                    "enabled": True,
                }
                (plugin_dir / "manifest.json").write_text(
                    json.dumps(manifest), encoding="utf-8"
                )

                trigger_code = f'''
from yuanbot.proactive.trigger import ProactiveTrigger, TriggerResult

class Trigger{i}(ProactiveTrigger):
    def get_event_type(self) -> str:
        return "event_{i}"

    async def check(self, user_id: str) -> TriggerResult:
        return TriggerResult(triggered=True, data={{"index": {i}}})

    def get_name(self) -> str:
        return "Trigger{i}"
'''
                (plugin_dir / "trigger.py").write_text(
                    trigger_code, encoding="utf-8"
                )

            mgr = TriggerManager()
            loaded = await mgr.load_plugins(tmpdir)
            assert loaded == 3
            assert mgr.trigger_count == 3

    def test_load_trigger_class_nonexistent(self):
        """测试加载不存在的文件返回 None"""
        result = TriggerManager._load_trigger_class(Path("/nonexistent/file.py"))
        assert result is None

    def test_load_trigger_class_no_trigger_class(self):
        """测试文件中没有 ProactiveTrigger 子类"""
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("# No trigger class here\nx = 1\n")
            f.flush()
            result = TriggerManager._load_trigger_class(Path(f.name))
            assert result is None
