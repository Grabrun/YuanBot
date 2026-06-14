"""YuanBot 人设管理器

支持多人设运行时切换：
- 从 configs/Personas/*.yaml 加载人设配置
- 运行时动态切换当前活跃人设
- 人设列表查询
- 配置热加载

设计参考: persona-decision-system.md + architecture-v1.5.md 第4章
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import structlog
import yaml

from yuanbot.core.interfaces import PersonaProfile, SkillMetadata
from yuanbot.persona.default import RELATIONSHIP_STAGES, DefaultPersona

logger = structlog.get_logger(__name__)


class YamlPersona(PersonaProfile):
    """基于 YAML 配置的动态人设

    从 YAML 文件加载人设参数，支持运行时修改。
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._persona_id = config.get("id", "custom")
        self._name = config.get("name", self._persona_id)
        self._relationship_stage = config.get("relationship_stage", "initial")
        self._system_prompt = config.get("system_prompt", "")
        self._behavior_rules = config.get("behavior_rules", [])
        self._voice_style = config.get("voice_style", {})
        self._capability_domains = config.get(
            "capability_domains",
            ["emotional_care", "daily_chat", "creative_storytelling", "life_companion"],
        )
        self._stage_overrides = config.get("stage_overrides", {})

    @property
    def persona_id(self) -> str:
        return self._persona_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def relationship_stage(self) -> str:
        return self._relationship_stage

    @relationship_stage.setter
    def relationship_stage(self, stage: str) -> None:
        if stage in RELATIONSHIP_STAGES:
            self._relationship_stage = stage

    def get_system_prompt(self) -> str:
        """获取系统提示词（合并基础 prompt 和阶段覆盖）"""
        base = self._system_prompt

        # 如果 YAML 中定义了当前阶段的覆盖
        stage_over = self._stage_overrides.get(self._relationship_stage, {})
        if stage_over.get("system_prompt_append"):
            base = f"{base}\n\n{stage_over['system_prompt_append']}"

        # 如果没有自定义 prompt，降级到默认人设
        if not base:
            return DefaultPersona(self._relationship_stage).get_system_prompt()

        # 注入关系阶段信息
        stage_config = RELATIONSHIP_STAGES.get(self._relationship_stage, {})
        base += f"\n\n## 当前关系阶段: {self._relationship_stage}"
        if stage_config:
            base += f"\n- 亲密度: {stage_config.get('intimacy_level', 0.5):.0%}"
            base += f"\n- 语气风格: {stage_config.get('tone_modifier', '自然')}"

        return base

    def get_behavior_rules(self) -> list[str]:
        rules = list(self._behavior_rules)
        if not rules:
            return DefaultPersona(self._relationship_stage).get_behavior_rules()

        # 合并阶段特定规则
        stage_over = self._stage_overrides.get(self._relationship_stage, {})
        extra = stage_over.get("extra_behavior_rules", [])
        rules.extend(extra)

        return rules

    def get_voice_style(self) -> dict[str, Any]:
        style = dict(self._voice_style)
        if not style:
            return DefaultPersona(self._relationship_stage).get_voice_style()
        return style

    def get_capability_domains(self) -> list[str]:
        return list(self._capability_domains)

    def should_use_skill(self, skill_metadata: SkillMetadata) -> bool:
        compatible_categories = {"emotional", "creative", "utility"}
        return skill_metadata.category in compatible_categories or any(
            tag in self.get_capability_domains() for tag in skill_metadata.capability_tags
        )

    def to_dict(self) -> dict[str, Any]:
        """导出为人设信息字典"""
        return {
            "id": self._persona_id,
            "name": self._name,
            "relationship_stage": self._relationship_stage,
            "system_prompt_preview": (
                self._system_prompt[:200] + "..."
                if len(self._system_prompt) > 200
                else self._system_prompt
            ),
            "capability_domains": self._capability_domains,
            "has_custom_prompt": bool(self._system_prompt),
            "has_custom_voice": bool(self._voice_style),
        }


class PersonaManager:
    """人设管理器

    管理所有人设配置，支持运行时切换。
    线程安全设计（通过属性原子赋值保证）。
    """

    def __init__(
        self,
        config_dir: Path | str | None = None,
        default_persona_id: str = "default",
    ) -> None:
        self._config_dir = Path(config_dir) if config_dir else Path("configs")
        self._personas_dir = self._config_dir / "Personas"
        self._personas: dict[str, YamlPersona] = {}
        self._active_persona: PersonaProfile = DefaultPersona()
        self._active_id: str = default_persona_id
        self._default_id: str = default_persona_id
        self._switch_history: list[dict[str, Any]] = []

    @property
    def active_persona(self) -> PersonaProfile:
        """获取当前活跃人设"""
        return self._active_persona

    @property
    def active_id(self) -> str:
        """获取当前活跃人设 ID"""
        return self._active_id

    def load_personas(self) -> int:
        """从 configs/Personas/ 目录加载所有人设配置

        Returns:
            加载的人设数量
        """
        self._personas.clear()

        # 默认人设始终可用
        self._personas["default"] = YamlPersona(
            {
                "id": "default",
                "name": "小缘",
                "system_prompt": "",  # 空 = 使用 DefaultPersona 的 prompt
                "relationship_stage": "initial",
            }
        )

        if not self._personas_dir.exists():
            logger.info("personas_dir_not_found", path=str(self._personas_dir))
            return len(self._personas)

        for yaml_file in sorted(self._personas_dir.glob("*.yaml")):
            try:
                with open(yaml_file, encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}

                persona_id = data.get("id", yaml_file.stem)
                data["id"] = persona_id

                persona = YamlPersona(data)
                self._personas[persona_id] = persona

                logger.info(
                    "persona_loaded",
                    id=persona_id,
                    name=persona.name,
                    file=yaml_file.name,
                )

            except Exception as e:
                logger.error(
                    "persona_load_failed",
                    file=yaml_file.name,
                    error=str(e),
                )

        # 设置活跃人设
        if self._default_id in self._personas:
            self._active_persona = self._personas[self._default_id]
            self._active_id = self._default_id

        logger.info("personas_loaded", count=len(self._personas))
        return len(self._personas)

    def switch_persona(self, persona_id: str) -> dict[str, Any]:
        """运行时切换活跃人设

        Args:
            persona_id: 目标人设 ID

        Returns:
            切换结果字典

        Raises:
            ValueError: 人设不存在
        """
        if persona_id not in self._personas:
            available = ", ".join(self._personas.keys())
            raise ValueError(f"人设 '{persona_id}' 不存在。可用人设: {available}")

        old_id = self._active_id
        new_persona = self._personas[persona_id]

        # 原子切换
        self._active_persona = new_persona
        self._active_id = persona_id

        # 记录切换历史
        record = {
            "from": old_id,
            "to": persona_id,
            "timestamp": time.time(),
        }
        self._switch_history.append(record)

        # 保留最近 100 条历史
        if len(self._switch_history) > 100:
            self._switch_history = self._switch_history[-100:]

        logger.info(
            "persona_switched",
            from_id=old_id,
            to_id=persona_id,
        )

        return {
            "status": "ok",
            "previous": old_id,
            "current": persona_id,
            "name": new_persona.name,
        }

    def get_persona(self, persona_id: str) -> YamlPersona | None:
        """获取指定人设"""
        return self._personas.get(persona_id)

    def list_personas(self) -> list[dict[str, Any]]:
        """列出所有人设

        Returns:
            人设信息列表
        """
        result = []
        for pid, persona in sorted(self._personas.items()):
            info = persona.to_dict()
            info["is_active"] = pid == self._active_id
            info["is_default"] = pid == self._default_id
            result.append(info)
        return result

    def set_relationship_stage(self, stage: str) -> dict[str, Any]:
        """设置当前活跃人设的关系阶段

        Args:
            stage: 目标阶段 (initial, familiar, intimate, deep)

        Returns:
            设置结果

        Raises:
            ValueError: 阶段不存在
        """
        if stage not in RELATIONSHIP_STAGES:
            available = ", ".join(RELATIONSHIP_STAGES.keys())
            raise ValueError(f"关系阶段 '{stage}' 不存在。可用阶段: {available}")

        old_stage = self._active_persona.relationship_stage
        self._active_persona.relationship_stage = stage

        logger.info(
            "relationship_stage_changed",
            from_stage=old_stage,
            to_stage=stage,
            persona_id=self._active_id,
        )

        return {
            "status": "ok",
            "persona_id": self._active_id,
            "previous_stage": old_stage,
            "current_stage": stage,
            "stage_config": RELATIONSHIP_STAGES[stage],
        }

    def get_switch_history(self) -> list[dict[str, Any]]:
        """获取人设切换历史"""
        return list(self._switch_history)

    def reload_persona(self, persona_id: str) -> bool:
        """重新加载单个人设配置

        Args:
            persona_id: 人设 ID

        Returns:
            是否重新加载成功
        """
        if persona_id == "default":
            return True

        yaml_file = self._personas_dir / f"{persona_id}.yaml"
        if not yaml_file.exists():
            return False

        try:
            with open(yaml_file, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            data["id"] = persona_id
            persona = YamlPersona(data)
            self._personas[persona_id] = persona

            # 如果正在切换的是当前活跃人设，更新引用
            if self._active_id == persona_id:
                self._active_persona = persona

            logger.info("persona_reloaded", id=persona_id)
            return True

        except Exception as e:
            logger.error("persona_reload_failed", id=persona_id, error=str(e))
            return False
