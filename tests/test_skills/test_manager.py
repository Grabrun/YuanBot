"""YuanBot Skills 管理器测试"""

from __future__ import annotations

from typing import Any

import pytest

from yuanbot.core.interfaces import SkillMetadata, SkillModule
from yuanbot.skills.manager import SkillManager


class MockSkillMetadata(SkillMetadata):
    def __init__(
        self,
        name: str = "test_skill",
        description: str = "测试技能",
        category: str = "emotional",
        capability_tags: list[str] | None = None,
        token_cost: int = 100,
    ):
        self._name = name
        self._description = description
        self._category = category
        self._capability_tags = capability_tags or []
        self._token_cost = token_cost

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def category(self) -> str:
        return self._category

    @property
    def capability_tags(self) -> list[str]:
        return self._capability_tags

    @property
    def token_cost(self) -> int:
        return self._token_cost


class MockSkill(SkillModule):
    def __init__(
        self,
        name: str = "test_skill",
        category: str = "emotional",
        tags: list[str] | None = None,
        token_cost: int = 100,
    ):
        self._metadata = MockSkillMetadata(
            name=name, category=category, capability_tags=tags, token_cost=token_cost
        )

    def get_metadata(self) -> SkillMetadata:
        return self._metadata

    def get_definition(self) -> str:
        return f"Definition of {self._metadata.name}"

    async def execute(
        self,
        context: dict[str, Any],
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {"result": "ok"}


@pytest.fixture
def manager():
    return SkillManager()


class TestRegisterSkill:
    def test_register(self, manager: SkillManager):
        skill = MockSkill(name="comfort")
        manager.register_skill(skill)
        assert manager.get_skill("comfort") is skill

    def test_metadata_indexed(self, manager: SkillManager):
        skill = MockSkill(name="comfort", category="emotional")
        manager.register_skill(skill)
        index = manager.get_metadata_index()
        assert len(index) == 1
        assert index[0].name == "comfort"

    def test_register_multiple(self, manager: SkillManager):
        manager.register_skill(MockSkill(name="s1"))
        manager.register_skill(MockSkill(name="s2"))
        assert len(manager.get_metadata_index()) == 2


class TestGetSkill:
    def test_existing(self, manager: SkillManager):
        skill = MockSkill(name="test")
        manager.register_skill(skill)
        assert manager.get_skill("test") is skill

    def test_nonexistent(self, manager: SkillManager):
        assert manager.get_skill("nonexistent") is None


class TestMatchSkills:
    def test_match_by_domain(self, manager: SkillManager):
        manager.register_skill(MockSkill(name="s1", tags=["emotional_care"]))
        manager.register_skill(MockSkill(name="s2", tags=["daily_chat"]))

        matched = manager.match_skills("emotional_care")
        assert len(matched) == 1
        assert matched[0].name == "s1"

    def test_match_by_category(self, manager: SkillManager):
        manager.register_skill(MockSkill(name="s1", category="emotional"))
        manager.register_skill(MockSkill(name="s2", category="utility"))

        matched = manager.match_skills("emotional")
        assert len(matched) == 1

    def test_match_by_query(self, manager: SkillManager):
        manager.register_skill(MockSkill(name="s1", tags=["天气", "查询"]))
        manager.register_skill(MockSkill(name="s2", tags=["音乐"]))

        matched = manager.match_skills("utility", query="天气怎么样")
        assert len(matched) == 1
        assert matched[0].name == "s1"

    def test_sorted_by_token_cost(self, manager: SkillManager):
        manager.register_skill(MockSkill(name="expensive", tags=["test"], token_cost=500))
        manager.register_skill(MockSkill(name="cheap", tags=["test"], token_cost=50))

        matched = manager.match_skills("test")
        assert matched[0].name == "cheap"
        assert matched[1].name == "expensive"

    def test_no_match(self, manager: SkillManager):
        manager.register_skill(MockSkill(name="s1", tags=["cooking"]))
        matched = manager.match_skills("sports")
        assert len(matched) == 0


class TestGetFullDefinition:
    def test_existing(self, manager: SkillManager):
        skill = MockSkill(name="test")
        manager.register_skill(skill)
        assert manager.get_full_definition("test") == "Definition of test"

    def test_nonexistent(self, manager: SkillManager):
        assert manager.get_full_definition("nonexistent") is None
