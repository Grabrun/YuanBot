"""YuanBot Skills 管理器测试

测试 YAML 加载、匹配、prompt 获取等功能。
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from yuanbot.skills.manager import SkillManager


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    """创建临时 Skills 配置目录"""
    d = tmp_path / "skills"
    d.mkdir()
    return d


@pytest.fixture
def manager(skills_dir: Path) -> SkillManager:
    return SkillManager(skills_dir=str(skills_dir))


def _write_skill(skills_dir: Path, skill_id: str, **overrides: object) -> Path:
    """辅助：写入一个 skill YAML 文件"""
    config = {
        "skill_id": skill_id,
        "name": overrides.get("name", f"Skill {skill_id}"),
        "version": "1.0.0",
        "category": overrides.get("category", "emotional_care"),
        "capability_tags": overrides.get("capability_tags", ["comfort"]),
        "persona_filters": [],
        "token_cost_estimate": overrides.get("token_cost_estimate", 200),
        "enabled": overrides.get("enabled", True),
        "prompt_template": overrides.get("prompt_template", f"Prompt for {skill_id}"),
    }
    path = skills_dir / f"{skill_id}.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True)
    return path


# ──────────────────────────────────────────────
# 加载测试
# ──────────────────────────────────────────────


class TestLoadSkills:
    async def test_load_single(self, manager: SkillManager, skills_dir: Path):
        _write_skill(skills_dir, "comfort")
        await manager.load_skills()
        skills = manager.get_all_skills()
        assert len(skills) == 1
        assert skills[0]["skill_id"] == "comfort"

    async def test_load_multiple(self, manager: SkillManager, skills_dir: Path):
        _write_skill(skills_dir, "s1")
        _write_skill(skills_dir, "s2")
        _write_skill(skills_dir, "s3")
        await manager.load_skills()
        assert len(manager.get_all_skills()) == 3

    async def test_load_skips_disabled(self, manager: SkillManager, skills_dir: Path):
        _write_skill(skills_dir, "enabled_skill", enabled=True)
        _write_skill(skills_dir, "disabled_skill", enabled=False)
        await manager.load_skills()
        skills = manager.get_all_skills()
        assert len(skills) == 1
        assert skills[0]["skill_id"] == "enabled_skill"

    async def test_load_missing_dir(self, tmp_path: Path):
        manager = SkillManager(skills_dir=str(tmp_path / "nonexistent"))
        await manager.load_skills()
        assert manager.get_all_skills() == []

    async def test_load_invalid_yaml(self, manager: SkillManager, skills_dir: Path):
        bad_file = skills_dir / "bad.yaml"
        bad_file.write_text(": : invalid yaml [{", encoding="utf-8")
        _write_skill(skills_dir, "good")
        await manager.load_skills()
        skills = manager.get_all_skills()
        assert len(skills) == 1
        assert skills[0]["skill_id"] == "good"

    async def test_load_missing_skill_id(self, manager: SkillManager, skills_dir: Path):
        path = skills_dir / "no_id.yaml"
        config = {"name": "No ID", "category": "test", "enabled": True}
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(config, f)
        await manager.load_skills()
        assert manager.get_all_skills() == []

    async def test_load_non_dict_yaml(self, manager: SkillManager, skills_dir: Path):
        path = skills_dir / "list.yaml"
        path.write_text("- item1\n- item2\n", encoding="utf-8")
        await manager.load_skills()
        assert manager.get_all_skills() == []

    async def test_load_prompt_template(self, manager: SkillManager, skills_dir: Path):
        _write_skill(skills_dir, "test_skill", prompt_template="Hello {{name}}")
        await manager.load_skills()
        assert manager.get_skill_prompt("test_skill") == "Hello {{name}}"

    async def test_load_preserves_metadata(self, manager: SkillManager, skills_dir: Path):
        _write_skill(
            skills_dir,
            "meta_test",
            name="Meta Test",
            category="daily_chat",
            capability_tags=["chat", "casual"],
            token_cost_estimate=150,
        )
        await manager.load_skills()
        skills = manager.get_all_skills()
        assert skills[0]["name"] == "Meta Test"
        assert skills[0]["category"] == "daily_chat"
        assert skills[0]["capability_tags"] == ["chat", "casual"]
        assert skills[0]["token_cost_estimate"] == 150


# ──────────────────────────────────────────────
# 匹配测试
# ──────────────────────────────────────────────


class TestGetSkillsForContext:
    async def test_match_by_capability_domain(self, manager: SkillManager, skills_dir: Path):
        _write_skill(skills_dir, "comfort", category="emotional_care")
        _write_skill(skills_dir, "chat", category="daily_chat")
        await manager.load_skills()

        matched = manager.get_skills_for_context(
            intent="", emotion="", capability_domains=["emotional_care"]
        )
        assert "comfort" in matched
        assert "chat" not in matched

    async def test_match_by_tags(self, manager: SkillManager, skills_dir: Path):
        _write_skill(skills_dir, "s1", capability_tags=["comfort", "anxiety"])
        _write_skill(skills_dir, "s2", capability_tags=["cooking"])
        await manager.load_skills()

        matched = manager.get_skills_for_context(
            intent="", emotion="", capability_domains=["comfort"]
        )
        assert "s1" in matched
        assert "s2" not in matched

    async def test_match_by_intent(self, manager: SkillManager, skills_dir: Path):
        _write_skill(
            skills_dir, "story", capability_tags=["story", "creative", "故事"], category="creative"
        )
        _write_skill(skills_dir, "chat", capability_tags=["chat"], category="daily_chat")
        await manager.load_skills()

        matched = manager.get_skills_for_context(
            intent="我想听故事", emotion="", capability_domains=[]
        )
        # "故事" is in "我想听故事" → match
        assert "story" in matched

    async def test_match_by_emotion(self, manager: SkillManager, skills_dir: Path):
        _write_skill(skills_dir, "comfort", capability_tags=["sadness", "comfort"])
        _write_skill(skills_dir, "fun", capability_tags=["joy"])
        await manager.load_skills()

        matched = manager.get_skills_for_context(
            intent="", emotion="sadness", capability_domains=[]
        )
        assert "comfort" in matched

    async def test_no_match(self, manager: SkillManager, skills_dir: Path):
        _write_skill(skills_dir, "cooking", capability_tags=["cooking"])
        await manager.load_skills()

        matched = manager.get_skills_for_context(
            intent="sports", emotion="joy", capability_domains=["fitness"]
        )
        assert len(matched) == 0

    async def test_sorted_by_score_then_cost(self, manager: SkillManager, skills_dir: Path):
        _write_skill(
            skills_dir,
            "expensive",
            capability_tags=["test"],
            category="emotional_care",
            token_cost_estimate=500,
        )
        _write_skill(
            skills_dir,
            "cheap",
            capability_tags=["test"],
            category="emotional_care",
            token_cost_estimate=50,
        )
        await manager.load_skills()

        matched = manager.get_skills_for_context(
            intent="", emotion="", capability_domains=["emotional_care"]
        )
        # Same score, cheaper first
        assert matched.index("cheap") < matched.index("expensive")

    async def test_multiple_domains(self, manager: SkillManager, skills_dir: Path):
        _write_skill(skills_dir, "s1", category="emotional_care")
        _write_skill(skills_dir, "s2", category="daily_chat")
        _write_skill(skills_dir, "s3", category="creative")
        await manager.load_skills()

        matched = manager.get_skills_for_context(
            intent="",
            emotion="",
            capability_domains=["emotional_care", "daily_chat"],
        )
        assert "s1" in matched
        assert "s2" in matched
        assert "s3" not in matched


# ──────────────────────────────────────────────
# Prompt 获取测试
# ──────────────────────────────────────────────


class TestGetSkillPrompt:
    async def test_existing(self, manager: SkillManager, skills_dir: Path):
        _write_skill(skills_dir, "test", prompt_template="Hello World")
        await manager.load_skills()
        assert manager.get_skill_prompt("test") == "Hello World"

    async def test_nonexistent(self, manager: SkillManager, skills_dir: Path):
        await manager.load_skills()
        assert manager.get_skill_prompt("nonexistent") is None

    async def test_multiline_prompt(self, manager: SkillManager, skills_dir: Path):
        prompt = textwrap.dedent("""\
            [技能激活：测试]
            第一行
            第二行
            第三行
        """)
        _write_skill(skills_dir, "multi", prompt_template=prompt)
        await manager.load_skills()
        result = manager.get_skill_prompt("multi")
        assert "第一行" in result
        assert "第三行" in result


# ──────────────────────────────────────────────
# 元数据获取测试
# ──────────────────────────────────────────────


class TestGetAllSkills:
    async def test_empty(self, manager: SkillManager):
        assert manager.get_all_skills() == []

    async def test_returns_all_fields(self, manager: SkillManager, skills_dir: Path):
        _write_skill(skills_dir, "full", name="Full Skill", category="test")
        await manager.load_skills()
        skills = manager.get_all_skills()
        assert len(skills) == 1
        skill = skills[0]
        assert skill["skill_id"] == "full"
        assert skill["name"] == "Full Skill"
        assert skill["category"] == "test"
        assert "version" in skill
        assert "capability_tags" in skill
        assert "token_cost_estimate" in skill
        assert "enabled" in skill
