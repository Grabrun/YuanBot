"""YuanBot Skills 管理器

实现三层渐进式加载机制：
1. 元数据索引（永久驻留，每项约 50 Tokens）
2. 按需注入定义（临时，200-500 Tokens/项）
3. 资源文档按需获取（不常驻）
"""

from __future__ import annotations

import structlog

from yuanbot.core.interfaces import SkillMetadata, SkillModule

logger = structlog.get_logger(__name__)


class SkillManager:
    """Skills 动态管理器"""

    def __init__(self):
        self._skills: dict[str, SkillModule] = {}
        self._metadata_index: list[SkillMetadata] = []

    def register_skill(self, skill: SkillModule) -> None:
        """注册 Skill 模块"""
        metadata = skill.get_metadata()
        self._skills[metadata.name] = skill
        self._metadata_index.append(metadata)
        logger.info("skill_registered", name=metadata.name, category=metadata.category)

    def get_skill(self, name: str) -> SkillModule | None:
        """获取 Skill 模块"""
        return self._skills.get(name)

    def get_metadata_index(self) -> list[SkillMetadata]:
        """获取所有 Skill 的元数据索引（阶段一：元数据层）"""
        return self._metadata_index

    def match_skills(
        self,
        capability_domain: str,
        query: str | None = None,
    ) -> list[SkillMetadata]:
        """语义匹配 Skills（阶段二：指令层）

        根据能力域和查询语义匹配最相关的 Skills。
        """
        matched = []
        for meta in self._metadata_index:
            # 能力域匹配
            if capability_domain in meta.capability_tags:
                matched.append(meta)
                continue
            # 类别匹配
            if capability_domain == meta.category:
                matched.append(meta)
                continue
            # 关键词匹配
            if query and any(tag in query for tag in meta.capability_tags):
                matched.append(meta)

        # 按 token_cost 排序（优先加载成本低的）
        matched.sort(key=lambda m: m.token_cost)
        return matched

    def get_full_definition(self, name: str) -> str | None:
        """获取 Skill 完整定义（阶段二：按需注入）"""
        skill = self._skills.get(name)
        if skill:
            return skill.get_definition()
        return None
