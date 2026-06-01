"""决策引擎自定义插件系统测试

测试 DecisionPlugin、DecisionPluginManager 以及与 DialogueDecisionEngine 的集成。
"""

from __future__ import annotations

import asyncio
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
import yaml

from yuanbot.core.types import EmotionState
from yuanbot.persona.engines.decision_plugin import (
    DecisionPlugin,
    DecisionPluginConfig,
    DecisionPluginManager,
    PluginDecisionResult,
)
from yuanbot.persona.engines.dialogue_decision import DialogueDecisionEngine
from yuanbot.persona.engines.intent_engine import IntentResult


# ── 测试用插件 ──────────────────────────────


class AlwaysComfortPlugin(DecisionPlugin):
    """测试插件: 总是返回 comfort 策略"""

    plugin_id_override = "always_comfort"

    @property
    def plugin_id(self) -> str:
        return "always_comfort"

    async def process(self, text, user_id, session_id, intent, emotion, **kwargs):
        return PluginDecisionResult(response_strategy="comfort")


class TakeoverPlugin(DecisionPlugin):
    """测试插件: 接管整个决策"""

    @property
    def plugin_id(self) -> str:
        return "takeover"

    async def process(self, text, user_id, session_id, intent, emotion, **kwargs):
        return PluginDecisionResult(
            response_strategy="custom",
            should_use_skills=["custom_skill"],
            should_use_tools=["custom_tool"],
            takeover=True,
        )


class DisabledPlugin(DecisionPlugin):
    """测试插件: 被禁用的插件"""

    def __init__(self, config=None):
        super().__init__(config)
        self._enabled = False

    @property
    def plugin_id(self) -> str:
        return "disabled"

    async def process(self, text, user_id, session_id, intent, emotion, **kwargs):
        return PluginDecisionResult(response_strategy="should_not_reach")


class ErrorPlugin(DecisionPlugin):
    """测试插件: 抛出异常"""

    @property
    def plugin_id(self) -> str:
        return "error"

    async def process(self, text, user_id, session_id, intent, emotion, **kwargs):
        raise RuntimeError("Plugin error!")


class PriorityPlugin(DecisionPlugin):
    """测试插件: 基于优先级覆盖策略"""

    async def process(self, text, user_id, session_id, intent, emotion, **kwargs):
        return PluginDecisionResult(
            response_strategy="high_priority",
            metadata={"priority": self.priority},
        )


class SkillAdderPlugin(DecisionPlugin):
    """测试插件: 追加 Skills"""

    async def process(self, text, user_id, session_id, intent, emotion, **kwargs):
        return PluginDecisionResult(should_use_skills=["extra_skill"])


# ── DecisionPlugin 基础测试 ──────────────────


class TestDecisionPlugin:
    """DecisionPlugin 基类测试"""

    def test_default_properties(self):
        plugin = AlwaysComfortPlugin()
        assert plugin.enabled is True
        assert plugin.priority == 100

    def test_custom_config(self):
        plugin = AlwaysComfortPlugin(config={"enabled": False, "priority": 50})
        assert plugin.enabled is False
        assert plugin.priority == 50

    def test_subclass_must_implement_process(self):
        """DecisionPlugin 是抽象类，不能直接实例化"""
        with pytest.raises(TypeError):
            DecisionPlugin()


# ── PluginDecisionResult 测试 ────────────────


class TestPluginDecisionResult:
    """PluginDecisionResult 测试"""

    def test_default_values(self):
        result = PluginDecisionResult()
        assert result.response_strategy is None
        assert result.should_use_skills is None
        assert result.should_use_tools is None
        assert result.context_priority is None
        assert result.token_budget_ratio is None
        assert result.metadata == {}
        assert result.takeover is False

    def test_custom_values(self):
        result = PluginDecisionResult(
            response_strategy="comfort",
            should_use_skills=["skill1"],
            takeover=True,
        )
        assert result.response_strategy == "comfort"
        assert result.should_use_skills == ["skill1"]
        assert result.takeover is True


# ── DecisionPluginManager 测试 ───────────────


class TestDecisionPluginManager:
    """DecisionPluginManager 加载与管理测试"""

    @pytest.fixture
    def plugins_dir(self, tmp_path):
        return tmp_path / "Plugins" / "decision"

    @pytest.mark.asyncio
    async def test_empty_dir(self, plugins_dir):
        """空目录不报错"""
        plugins_dir.mkdir(parents=True)
        manager = DecisionPluginManager(plugins_dir=plugins_dir)
        await manager.load_plugins()
        assert manager.loaded is True
        assert len(manager.plugins) == 0

    @pytest.mark.asyncio
    async def test_nonexistent_dir(self, tmp_path):
        """不存在的目录不报错"""
        manager = DecisionPluginManager(plugins_dir=tmp_path / "nonexistent")
        await manager.load_plugins()
        assert manager.loaded is True
        assert len(manager.plugins) == 0

    @pytest.mark.asyncio
    async def test_load_valid_plugin(self, plugins_dir):
        """加载有效插件配置"""
        plugins_dir.mkdir(parents=True)
        config = {
            "plugin_id": "test_comfort",
            "module": "tests.test_persona.test_decision_plugin.AlwaysComfortPlugin",
            "enabled": True,
            "priority": 50,
        }
        with open(plugins_dir / "comfort.yaml", "w") as f:
            yaml.dump(config, f)

        manager = DecisionPluginManager(plugins_dir=plugins_dir)
        await manager.load_plugins()

        assert manager.loaded is True
        assert len(manager.plugins) == 1
        assert manager.plugins[0].plugin_id == "always_comfort"
        assert manager.plugins[0].priority == 50

    @pytest.mark.asyncio
    async def test_load_disabled_plugin(self, plugins_dir):
        """加载被禁用的插件"""
        plugins_dir.mkdir(parents=True)
        config = {
            "plugin_id": "disabled_test",
            "module": "tests.test_persona.test_decision_plugin.DisabledPlugin",
            "enabled": True,  # config says enabled, but plugin itself sets _enabled=False
        }
        with open(plugins_dir / "disabled.yaml", "w") as f:
            yaml.dump(config, f)

        manager = DecisionPluginManager(plugins_dir=plugins_dir)
        await manager.load_plugins()

        assert len(manager.plugins) == 1
        assert manager.plugins[0].enabled is False

    @pytest.mark.asyncio
    async def test_skip_invalid_config(self, plugins_dir):
        """跳过缺少 module 的配置"""
        plugins_dir.mkdir(parents=True)
        config = {"plugin_id": "no_module"}
        with open(plugins_dir / "invalid.yaml", "w") as f:
            yaml.dump(config, f)

        manager = DecisionPluginManager(plugins_dir=plugins_dir)
        await manager.load_plugins()

        assert len(manager.plugins) == 0

    @pytest.mark.asyncio
    async def test_priority_ordering(self, plugins_dir):
        """插件按优先级排序（数值小的先执行）"""
        plugins_dir.mkdir(parents=True)

        for name, priority in [("high.yaml", 10), ("low.yaml", 100), ("mid.yaml", 50)]:
            config = {
                "plugin_id": f"plugin_{priority}",
                "module": "tests.test_persona.test_decision_plugin.PriorityPlugin",
                "enabled": True,
                "priority": priority,
            }
            with open(plugins_dir / name, "w") as f:
                yaml.dump(config, f)

        manager = DecisionPluginManager(plugins_dir=plugins_dir)
        await manager.load_plugins()

        assert len(manager.plugins) == 3
        priorities = [p.priority for p in manager.plugins]
        assert priorities == [10, 50, 100]

    @pytest.mark.asyncio
    async def test_process_all_merges_results(self, plugins_dir):
        """多个插件的结果正确合并"""
        plugins_dir.mkdir(parents=True)

        # 插件1: 追加 skill
        config1 = {
            "plugin_id": "adder",
            "module": "tests.test_persona.test_decision_plugin.SkillAdderPlugin",
            "enabled": True,
            "priority": 10,
        }
        with open(plugins_dir / "adder.yaml", "w") as f:
            yaml.dump(config1, f)

        # 插件2: 覆盖策略
        config2 = {
            "plugin_id": "comfort",
            "module": "tests.test_persona.test_decision_plugin.AlwaysComfortPlugin",
            "enabled": True,
            "priority": 20,
        }
        with open(plugins_dir / "comfort.yaml", "w") as f:
            yaml.dump(config2, f)

        manager = DecisionPluginManager(plugins_dir=plugins_dir)
        await manager.load_plugins()

        intent = IntentResult(primary="casual_chat", confidence=0.8)
        result = await manager.process_all(
            text="你好",
            user_id="u1",
            session_id="s1",
            intent=intent,
            emotion=None,
        )

        assert result.response_strategy == "comfort"
        assert result.should_use_skills == ["extra_skill"]
        assert result.takeover is False

    @pytest.mark.asyncio
    async def test_takeover_stops_execution(self, plugins_dir):
        """takeover=True 时停止后续插件"""
        plugins_dir.mkdir(parents=True)

        config1 = {
            "plugin_id": "takeover",
            "module": "tests.test_persona.test_decision_plugin.TakeoverPlugin",
            "enabled": True,
            "priority": 10,
        }
        with open(plugins_dir / "takeover.yaml", "w") as f:
            yaml.dump(config1, f)

        config2 = {
            "plugin_id": "comfort",
            "module": "tests.test_persona.test_decision_plugin.AlwaysComfortPlugin",
            "enabled": True,
            "priority": 20,
        }
        with open(plugins_dir / "comfort.yaml", "w") as f:
            yaml.dump(config2, f)

        manager = DecisionPluginManager(plugins_dir=plugins_dir)
        await manager.load_plugins()

        intent = IntentResult(primary="casual_chat", confidence=0.8)
        result = await manager.process_all(
            text="你好",
            user_id="u1",
            session_id="s1",
            intent=intent,
            emotion=None,
        )

        assert result.response_strategy == "custom"
        assert result.should_use_skills == ["custom_skill"]
        assert result.should_use_tools == ["custom_tool"]
        assert result.takeover is True

    @pytest.mark.asyncio
    async def test_error_plugin_does_not_crash(self, plugins_dir):
        """插件异常不影响其他插件执行"""
        plugins_dir.mkdir(parents=True)

        config1 = {
            "plugin_id": "error",
            "module": "tests.test_persona.test_decision_plugin.ErrorPlugin",
            "enabled": True,
            "priority": 10,
        }
        with open(plugins_dir / "error.yaml", "w") as f:
            yaml.dump(config1, f)

        config2 = {
            "plugin_id": "comfort",
            "module": "tests.test_persona.test_decision_plugin.AlwaysComfortPlugin",
            "enabled": True,
            "priority": 20,
        }
        with open(plugins_dir / "comfort.yaml", "w") as f:
            yaml.dump(config2, f)

        manager = DecisionPluginManager(plugins_dir=plugins_dir)
        await manager.load_plugins()

        intent = IntentResult(primary="casual_chat", confidence=0.8)
        result = await manager.process_all(
            text="你好",
            user_id="u1",
            session_id="s1",
            intent=intent,
            emotion=None,
        )

        # ErrorPlugin 抛异常后，AlwaysComfortPlugin 仍然执行
        assert result.response_strategy == "comfort"

    @pytest.mark.asyncio
    async def test_shutdown_all(self, plugins_dir):
        """shutdown_all 清理所有插件"""
        plugins_dir.mkdir(parents=True)
        config = {
            "plugin_id": "test",
            "module": "tests.test_persona.test_decision_plugin.AlwaysComfortPlugin",
        }
        with open(plugins_dir / "test.yaml", "w") as f:
            yaml.dump(config, f)

        manager = DecisionPluginManager(plugins_dir=plugins_dir)
        await manager.load_plugins()
        assert len(manager.plugins) == 1

        await manager.shutdown_all()
        assert len(manager.plugins) == 0


# ── DialogueDecisionEngine 集成测试 ──────────


class TestDecisionEngineWithPlugins:
    """测试 DialogueDecisionEngine 与插件的集成"""

    @pytest.mark.asyncio
    async def test_engine_without_plugins(self):
        """无插件时引擎正常工作"""
        engine = DialogueDecisionEngine()
        result = await engine.decide(
            text="你好",
            user_id="u1",
            session_id="s1",
        )
        assert result.response_strategy is not None
        assert result.intent.primary == "greeting"

    @pytest.mark.asyncio
    async def test_engine_with_plugin_overrides_strategy(self):
        """插件可以覆盖响应策略"""
        plugin = AlwaysComfortPlugin()
        manager = DecisionPluginManager()
        manager._plugins = [plugin]
        manager._loaded = True

        engine = DialogueDecisionEngine(plugin_manager=manager)
        result = await engine.decide(
            text="你好",
            user_id="u1",
            session_id="s1",
        )
        # 插件覆盖了默认的 greeting 策略
        assert result.response_strategy == "comfort"

    @pytest.mark.asyncio
    async def test_engine_with_takeover_plugin(self):
        """接管插件完全控制决策结果"""
        plugin = TakeoverPlugin()
        manager = DecisionPluginManager()
        manager._plugins = [plugin]
        manager._loaded = True

        engine = DialogueDecisionEngine(plugin_manager=manager)
        result = await engine.decide(
            text="你好",
            user_id="u1",
            session_id="s1",
        )
        assert result.response_strategy == "custom"
        assert result.should_use_skills == ["custom_skill"]
        assert result.should_use_tools == ["custom_tool"]

    @pytest.mark.asyncio
    async def test_engine_plugin_preserves_intent(self):
        """即使插件覆盖策略，意图识别结果不变"""
        plugin = AlwaysComfortPlugin()
        manager = DecisionPluginManager()
        manager._plugins = [plugin]
        manager._loaded = True

        engine = DialogueDecisionEngine(plugin_manager=manager)
        result = await engine.decide(
            text="谢谢你！",
            user_id="u1",
            session_id="s1",
        )
        assert result.response_strategy == "comfort"
        assert result.intent.primary == "expressing_gratitude"

    @pytest.mark.asyncio
    async def test_engine_plugin_metadata_merged(self):
        """插件的 metadata 正确合并到决策结果"""
        plugin = PriorityPlugin(config={"priority": 10})
        manager = DecisionPluginManager()
        manager._plugins = [plugin]
        manager._loaded = True

        engine = DialogueDecisionEngine(plugin_manager=manager)
        result = await engine.decide(
            text="你好",
            user_id="u1",
            session_id="s1",
        )
        assert result.metadata.get("priority") == 10
