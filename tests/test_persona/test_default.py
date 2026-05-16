"""YuanBot 默认人设测试"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from yuanbot.core.interfaces import SkillMetadata
from yuanbot.persona.default import DefaultPersona


@pytest.fixture
def persona():
    return DefaultPersona()


class TestDefaultPersona:
    def test_persona_id(self, persona: DefaultPersona):
        assert persona.persona_id == "default"

    def test_name(self, persona: DefaultPersona):
        assert persona.name == "小缘"

    def test_system_prompt(self, persona: DefaultPersona):
        prompt = persona.get_system_prompt()
        assert "小缘" in prompt
        assert "温柔" in prompt
        assert len(prompt) > 100

    def test_behavior_rules(self, persona: DefaultPersona):
        rules = persona.get_behavior_rules()
        assert len(rules) > 0
        assert all(isinstance(r, str) for r in rules)

    def test_voice_style(self, persona: DefaultPersona):
        style = persona.get_voice_style()
        assert "tone" in style
        assert style["tone"] == "温柔"

    def test_capability_domains(self, persona: DefaultPersona):
        domains = persona.get_capability_domains()
        assert "emotional_care" in domains
        assert "daily_chat" in domains

    def test_should_use_skill_emotional(self, persona: DefaultPersona):
        meta = MagicMock(spec=SkillMetadata)
        meta.category = "emotional"
        meta.capability_tags = []
        assert persona.should_use_skill(meta) is True

    def test_should_use_skill_creative(self, persona: DefaultPersona):
        meta = MagicMock(spec=SkillMetadata)
        meta.category = "creative"
        meta.capability_tags = []
        assert persona.should_use_skill(meta) is True

    def test_should_use_skill_utility(self, persona: DefaultPersona):
        meta = MagicMock(spec=SkillMetadata)
        meta.category = "utility"
        meta.capability_tags = []
        assert persona.should_use_skill(meta) is True

    def test_should_use_skill_by_tag(self, persona: DefaultPersona):
        meta = MagicMock(spec=SkillMetadata)
        meta.category = "other"
        meta.capability_tags = ["emotional_care"]
        assert persona.should_use_skill(meta) is True

    def test_should_not_use_unrelated_skill(self, persona: DefaultPersona):
        meta = MagicMock(spec=SkillMetadata)
        meta.category = "system"
        meta.capability_tags = ["admin", "debug"]
        assert persona.should_use_skill(meta) is False
