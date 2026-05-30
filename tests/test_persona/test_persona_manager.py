"""人设管理器测试"""

from __future__ import annotations

from pathlib import Path

import pytest

from yuanbot.persona.manager import PersonaManager, YamlPersona


@pytest.fixture
def persona_env(tmp_path: Path):
    """创建临时人设配置环境"""
    config_dir = tmp_path / "configs"
    personas_dir = config_dir / "Personas"
    personas_dir.mkdir(parents=True)

    # 创建自定义人设
    (personas_dir / "cheerful.yaml").write_text(
        'id: "cheerful"\n'
        'name: "小晴"\n'
        'description: "活泼开朗"\n'
        'relationship_stage: "initial"\n'
        'system_prompt: "你是小晴，活泼开朗的AI朋友。"\n'
        'behavior_rules:\n'
        '  - "保持积极乐观"\n'
        'voice_style:\n'
        '  tone: "活泼"\n'
        'capability_domains:\n'
        '  - "daily_chat"\n',
    )

    (personas_dir / "mentor.yaml").write_text(
        'id: "mentor"\n'
        'name: "明远"\n'
        'description: "沉稳睿智"\n'
        'relationship_stage: "familiar"\n'
        'system_prompt: "你是明远，沉稳睿智的AI导师。"\n'
        'behavior_rules:\n'
        '  - "先理解再回答"\n'
        'capability_domains:\n'
        '  - "daily_chat"\n'
        'stage_overrides:\n'
        '  familiar:\n'
        '    system_prompt_append: "可以更随和。"\n'
        '    extra_behavior_rules:\n'
        '      - "可以分享经历"\n',
    )

    return {
        "config_dir": config_dir,
        "personas_dir": personas_dir,
    }


class TestYamlPersona:
    """测试 YAML 人设"""

    def test_basic_properties(self):
        config = {
            "id": "test",
            "name": "测试人设",
            "system_prompt": "你是测试人设。",
            "behavior_rules": ["规则1"],
            "voice_style": {"tone": "温柔"},
            "capability_domains": ["daily_chat"],
        }
        persona = YamlPersona(config)

        assert persona.persona_id == "test"
        assert persona.name == "测试人设"

    def test_system_prompt(self):
        config = {
            "id": "test",
            "name": "测试",
            "system_prompt": "自定义 prompt",
        }
        persona = YamlPersona(config)
        prompt = persona.get_system_prompt()

        assert "自定义 prompt" in prompt
        assert "关系阶段" in prompt

    def test_empty_prompt_fallback(self):
        config = {"id": "test", "name": "测试", "system_prompt": ""}
        persona = YamlPersona(config)
        prompt = persona.get_system_prompt()

        # 应该降级到 DefaultPersona 的 prompt
        assert "小缘" in prompt

    def test_relationship_stage(self):
        config = {
            "id": "test",
            "name": "测试",
            "system_prompt": "测试",
            "relationship_stage": "initial",
        }
        persona = YamlPersona(config)

        assert persona.relationship_stage == "initial"
        persona.relationship_stage = "intimate"
        assert persona.relationship_stage == "intimate"

    def test_invalid_stage_ignored(self):
        config = {
            "id": "test",
            "name": "测试",
            "system_prompt": "测试",
            "relationship_stage": "initial",
        }
        persona = YamlPersona(config)
        persona.relationship_stage = "invalid_stage"
        assert persona.relationship_stage == "initial"

    def test_stage_overrides(self):
        config = {
            "id": "test",
            "name": "测试",
            "system_prompt": "基础 prompt",
            "relationship_stage": "initial",
            "stage_overrides": {
                "familiar": {
                    "system_prompt_append": "追加内容",
                },
            },
        }
        persona = YamlPersona(config)
        persona.relationship_stage = "familiar"

        prompt = persona.get_system_prompt()
        assert "基础 prompt" in prompt
        assert "追加内容" in prompt

    def test_to_dict(self):
        config = {
            "id": "test",
            "name": "测试",
            "system_prompt": "测试 prompt",
            "capability_domains": ["daily_chat"],
        }
        persona = YamlPersona(config)
        info = persona.to_dict()

        assert info["id"] == "test"
        assert info["name"] == "测试"
        assert info["has_custom_prompt"] is True


class TestPersonaManager:
    """测试人设管理器"""

    def test_load_personas(self, persona_env: dict):
        manager = PersonaManager(config_dir=persona_env["config_dir"])
        count = manager.load_personas()

        # default + cheerful + mentor = 3
        assert count == 3

    def test_default_persona_always_loaded(self, persona_env: dict):
        manager = PersonaManager(config_dir=persona_env["config_dir"])
        manager.load_personas()

        assert "default" in [p["id"] for p in manager.list_personas()]

    def test_active_persona_is_default(self, persona_env: dict):
        manager = PersonaManager(config_dir=persona_env["config_dir"])
        manager.load_personas()

        assert manager.active_id == "default"

    def test_switch_persona(self, persona_env: dict):
        manager = PersonaManager(config_dir=persona_env["config_dir"])
        manager.load_personas()

        result = manager.switch_persona("cheerful")

        assert result["status"] == "ok"
        assert result["previous"] == "default"
        assert result["current"] == "cheerful"
        assert result["name"] == "小晴"
        assert manager.active_id == "cheerful"
        assert manager.active_persona.name == "小晴"

    def test_switch_persona_not_found(self, persona_env: dict):
        manager = PersonaManager(config_dir=persona_env["config_dir"])
        manager.load_personas()

        with pytest.raises(ValueError, match="不存在"):
            manager.switch_persona("nonexistent")

    def test_switch_tracks_history(self, persona_env: dict):
        manager = PersonaManager(config_dir=persona_env["config_dir"])
        manager.load_personas()

        manager.switch_persona("cheerful")
        manager.switch_persona("mentor")
        manager.switch_persona("default")

        history = manager.get_switch_history()
        assert len(history) == 3
        assert history[0]["from"] == "default"
        assert history[0]["to"] == "cheerful"
        assert history[-1]["to"] == "default"

    def test_list_personas(self, persona_env: dict):
        manager = PersonaManager(config_dir=persona_env["config_dir"])
        manager.load_personas()

        personas = manager.list_personas()
        assert len(personas) == 3

        # 检查 is_active 标记
        active_count = sum(1 for p in personas if p.get("is_active"))
        assert active_count == 1

    def test_get_persona(self, persona_env: dict):
        manager = PersonaManager(config_dir=persona_env["config_dir"])
        manager.load_personas()

        persona = manager.get_persona("mentor")
        assert persona is not None
        assert persona.name == "明远"

        assert manager.get_persona("nonexistent") is None

    def test_set_relationship_stage(self, persona_env: dict):
        manager = PersonaManager(config_dir=persona_env["config_dir"])
        manager.load_personas()

        result = manager.set_relationship_stage("intimate")
        assert result["status"] == "ok"
        assert result["previous_stage"] == "initial"
        assert result["current_stage"] == "intimate"

    def test_set_invalid_stage(self, persona_env: dict):
        manager = PersonaManager(config_dir=persona_env["config_dir"])
        manager.load_personas()

        with pytest.raises(ValueError, match="不存在"):
            manager.set_relationship_stage("invalid")

    def test_empty_personas_dir(self, tmp_path: Path):
        config_dir = tmp_path / "configs"
        config_dir.mkdir()

        manager = PersonaManager(config_dir=config_dir)
        count = manager.load_personas()

        # 即使没有 Personas/ 目录，default 也应该加载
        assert count == 1
        assert manager.active_id == "default"

    def test_reload_persona(self, persona_env: dict):
        manager = PersonaManager(config_dir=persona_env["config_dir"])
        manager.load_personas()

        # 切换到 cheerful
        manager.switch_persona("cheerful")

        # 重新加载
        assert manager.reload_persona("cheerful") is True
        assert manager.active_id == "cheerful"

    def test_reload_nonexistent(self, persona_env: dict):
        manager = PersonaManager(config_dir=persona_env["config_dir"])
        manager.load_personas()

        assert manager.reload_persona("nonexistent") is False

    def test_switch_activates_persona_in_orchestrator(self, persona_env: dict):
        """切换人设后，active_persona 属性应反映新人设"""
        manager = PersonaManager(config_dir=persona_env["config_dir"])
        manager.load_personas()

        manager.switch_persona("mentor")
        persona = manager.active_persona
        assert persona.name == "明远"

        manager.set_relationship_stage("deep")
        assert manager.active_persona.relationship_stage == "deep"
