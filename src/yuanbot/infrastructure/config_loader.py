"""统一配置加载器

支持 configs/ 目录结构的配置文件加载。
配置加载优先级：环境变量 > 配置文件 > 默认值。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import structlog
import yaml

logger = structlog.get_logger(__name__)


class ConfigLoader:
    """统一配置加载器

    支持 v1.4 的 configs/ 目录结构：
    configs/
    ├── bot.yaml           # 根配置
    ├── database.yaml      # 数据库配置
    ├── memory.yaml        # 记忆系统参数
    ├── Channels/          # 消息通道配置
    ├── Providers/         # AI 提供商配置
    └── Plugins/           # Skills/Tools 配置
    """

    def __init__(self, config_dir: str | Path | None = None):
        self._config_dir = Path(config_dir) if config_dir else Path("configs")
        self._cache: dict[str, Any] = {}

    @property
    def config_dir(self) -> Path:
        return self._config_dir

    def load_bot_config(self) -> dict[str, Any]:
        """加载根配置 (bot.yaml)"""
        return self._load_yaml("bot.yaml")

    def load_database_config(self) -> dict[str, Any]:
        """加载数据库配置 (database.yaml)"""
        return self._load_yaml("database.yaml")

    def load_memory_config(self) -> dict[str, Any]:
        """加载记忆系统配置 (memory.yaml)"""
        return self._load_yaml("memory.yaml")

    def load_channel_config(self, platform: str) -> dict[str, Any]:
        """加载消息通道配置

        Args:
            platform: 平台标识（如 'telegram', 'discord'）

        Returns:
            通道配置字典
        """
        return self._load_yaml(f"Channels/{platform}.yaml")

    def load_all_channel_configs(self) -> dict[str, dict[str, Any]]:
        """加载所有消息通道配置"""
        return self._load_all_in_dir("Channels")

    def load_provider_config(self, provider_id: str) -> dict[str, Any]:
        """加载 AI 提供商配置

        Args:
            provider_id: 提供商标识（如 'openai', 'claude'）

        Returns:
            提供商配置字典
        """
        return self._load_yaml(f"Providers/{provider_id}.yaml")

    def load_all_provider_configs(self) -> dict[str, dict[str, Any]]:
        """加载所有 AI 提供商配置"""
        return self._load_all_in_dir("Providers")

    def load_skill_config(self, skill_name: str) -> dict[str, Any]:
        """加载 Skill 配置"""
        return self._load_yaml(f"Plugins/skills/{skill_name}.yaml")

    def load_tool_config(self, tool_name: str) -> dict[str, Any]:
        """加载 Tool 配置"""
        return self._load_yaml(f"Plugins/tools/{tool_name}.yaml")

    def apply_env_overrides(self, config: dict[str, Any]) -> dict[str, Any]:
        """应用环境变量覆盖

        环境变量命名规则：
        - YUAN_BOT_{KEY} → bot config
        - YUAN_AI_{PROVIDER}_{KEY} → provider config
        """
        result = dict(config)

        # 根配置覆盖
        for key in ("debug", "log_level", "version"):
            env_key = f"YUAN_BOT_{key.upper()}"
            env_val = os.getenv(env_key)
            if env_val is not None:
                if key == "debug":
                    result[key] = env_val.lower() in ("true", "1", "yes")
                else:
                    result[key] = env_val

        # AI 提供商覆盖
        ai_provider = result.get("ai_provider", {})
        if provider := os.getenv("YUAN_AI_PROVIDER"):
            ai_provider["provider_id"] = provider
        if api_key := os.getenv("YUAN_AI_API_KEY"):
            ai_provider["api_key"] = api_key
        if base_url := os.getenv("YUAN_AI_BASE_URL"):
            ai_provider["base_url"] = base_url
        if model := os.getenv("YUAN_AI_MODEL"):
            ai_provider["default_model"] = model
        result["ai_provider"] = ai_provider

        return result

    def _load_yaml(self, relative_path: str) -> dict[str, Any]:
        """加载 YAML 配置文件"""
        if relative_path in self._cache:
            return self._cache[relative_path]

        file_path = self._config_dir / relative_path
        if not file_path.exists():
            logger.debug("config_file_not_found", path=str(file_path))
            return {}

        try:
            with open(file_path) as f:
                data = yaml.safe_load(f) or {}
            self._cache[relative_path] = data
            logger.debug("config_loaded", path=str(file_path))
            return data
        except Exception as e:
            logger.error("config_load_error", path=str(file_path), error=str(e))
            return {}

    def _load_all_in_dir(self, subdir: str) -> dict[str, dict[str, Any]]:
        """加载目录下所有 YAML 配置"""
        dir_path = self._config_dir / subdir
        if not dir_path.exists():
            return {}

        configs = {}
        for yaml_file in dir_path.glob("*.yaml"):
            name = yaml_file.stem
            configs[name] = self._load_yaml(f"{subdir}/{yaml_file.name}")

        for yml_file in dir_path.glob("*.yml"):
            name = yml_file.stem
            configs[name] = self._load_yaml(f"{subdir}/{yml_file.name}")

        return configs

    def clear_cache(self) -> None:
        """清除配置缓存"""
        self._cache.clear()
