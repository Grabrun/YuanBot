"""YuanBot Skills 管理器

扫描 configs/Plugins/skills/ 目录加载 YAML 定义，
根据意图、情感和能力域动态匹配 Skills。
"""

from __future__ import annotations

from pathlib import Path

import structlog
import yaml

logger = structlog.get_logger(__name__)


class SkillManager:
    """Skill 管理器 - 扫描 configs/Plugins/skills/ 加载 YAML 定义"""

    def __init__(self, skills_dir: str = "configs/Plugins/skills"):
        self._skills_dir = Path(skills_dir)
        self._skill_configs: dict[str, dict] = {}  # skill_id -> config
        self._skill_definitions: dict[str, str] = {}  # skill_id -> prompt_template

    async def load_skills(self) -> None:
        """扫描目录加载所有 *.yaml Skill 配置"""
        if not self._skills_dir.exists():
            logger.warning("skills_dir_not_found", path=str(self._skills_dir))
            return

        for yaml_file in sorted(self._skills_dir.glob("*.yaml")):
            try:
                with open(yaml_file, encoding="utf-8") as f:
                    config = yaml.safe_load(f)
            except (yaml.YAMLError, OSError) as exc:
                logger.error(
                    "skill_load_failed",
                    file=str(yaml_file),
                    error=str(exc),
                )
                continue

            if not isinstance(config, dict):
                logger.warning("skill_invalid_format", file=str(yaml_file))
                continue

            # 检查 enabled 字段（默认为 True）
            if not config.get("enabled", True):
                logger.info("skill_disabled", file=str(yaml_file))
                continue

            skill_id = config.get("skill_id")
            if not skill_id:
                logger.warning("skill_missing_id", file=str(yaml_file))
                continue

            self._skill_configs[skill_id] = config
            prompt = config.get("prompt_template", "")
            if prompt:
                self._skill_definitions[skill_id] = prompt

            logger.info(
                "skill_loaded",
                skill_id=skill_id,
                name=config.get("name", ""),
                category=config.get("category", ""),
            )

    def get_skills_for_context(
        self,
        intent: str,
        emotion: str,
        capability_domains: list[str],
    ) -> list[str]:
        """根据意图、情感和能力域匹配 Skills

        返回匹配的 skill_id 列表，按相关性排序。
        """
        matched: list[tuple[str, int]] = []  # (skill_id, score)

        for skill_id, config in self._skill_configs.items():
            score = 0
            tags = config.get("capability_tags", [])
            category = config.get("category", "")

            # 能力域匹配（权重最高）
            if category in capability_domains:
                score += 3
            for domain in capability_domains:
                if domain in tags:
                    score += 2

            # 意图匹配
            if intent and any(tag in intent for tag in tags):
                score += 2
            if intent and category in intent:
                score += 1

            # 情感匹配
            if emotion and any(tag in emotion for tag in tags):
                score += 1

            if score > 0:
                matched.append((skill_id, score))

        # 按分数降序排列，分数相同按 token_cost 升序
        def sort_key(item: tuple[str, int]) -> tuple[int, int]:
            sid, sc = item
            cost = self._skill_configs[sid].get("token_cost_estimate", 500)
            return (-sc, cost)

        matched.sort(key=sort_key)
        return [sid for sid, _ in matched]

    def get_skill_prompt(self, skill_id: str) -> str | None:
        """获取 Skill 的 prompt_template"""
        return self._skill_definitions.get(skill_id)

    def get_all_skills(self) -> list[dict]:
        """获取所有已注册 Skill 的元数据"""
        result = []
        for skill_id, config in self._skill_configs.items():
            result.append(
                {
                    "skill_id": skill_id,
                    "name": config.get("name", ""),
                    "version": config.get("version", "1.0.0"),
                    "category": config.get("category", ""),
                    "capability_tags": config.get("capability_tags", []),
                    "token_cost_estimate": config.get("token_cost_estimate", 0),
                    "enabled": config.get("enabled", True),
                }
            )
        return result
