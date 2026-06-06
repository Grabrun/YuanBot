"""决策引擎自定义插件接口

允许为决策引擎的特定策略注册自定义插件，例如自定义的意图分类器或情感分析器。
插件通过 Plugins/decision/ 目录配置，并在 bot.yaml 中声明。

设计参考: persona-decision-system.md 第7.2节
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
import yaml

from yuanbot.core.types import EmotionState
from yuanbot.persona.engines.intent_engine import IntentResult

logger = structlog.get_logger(__name__)


@dataclass
class PluginDecisionResult:
    """插件决策修改结果

    插件可以修改或补充决策结果中的任意字段。
    返回 None 的字段表示不修改原决策。
    """

    response_strategy: str | None = None
    should_use_skills: list[str] | None = None
    should_use_tools: list[str] | None = None
    context_priority: str | None = None
    token_budget_ratio: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    # 插件是否要接管整个决策（True 则跳过后续插件和默认逻辑）
    takeover: bool = False


class DecisionPlugin(ABC):
    """决策插件基类

    自定义决策插件必须继承此类并实现 `process` 方法。

    插件生命周期:
    1. __init__ - 接收配置字典
    2. initialize() - 异步初始化（可选）
    3. process() - 每次决策时调用
    4. shutdown() - 清理资源（可选）
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self._config = config or {}
        self._enabled: bool = self._config.get("enabled", True)
        self._priority: int = self._config.get("priority", 100)

    @property
    def plugin_id(self) -> str:
        """插件唯一标识"""
        return self.__class__.__name__

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def priority(self) -> int:
        """优先级，数值越小越先执行"""
        return self._priority

    async def initialize(self) -> None:  # noqa: B027
        """异步初始化，子类可覆盖"""

    async def shutdown(self) -> None:  # noqa: B027
        """清理资源，子类可覆盖"""

    @abstractmethod
    async def process(
        self,
        text: str,
        user_id: str,
        session_id: str,
        intent: IntentResult,
        emotion: EmotionState | None,
        context_summary: str | None = None,
        capability_domains: list[str] | None = None,
    ) -> PluginDecisionResult:
        """处理决策，返回修改建议

        Args:
            text: 用户输入文本
            user_id: 用户 ID
            session_id: 会话 ID
            intent: 意图识别结果
            emotion: 情感分析结果
            context_summary: 上下文摘要
            capability_domains: 能力域列表

        Returns:
            PluginDecisionResult: 插件的决策修改建议
        """


@dataclass
class DecisionPluginConfig:
    """决策插件配置"""

    plugin_id: str
    module: str  # Python 模块路径，如 "my_plugin.MyDecisionPlugin"
    enabled: bool = True
    priority: int = 100
    config: dict[str, Any] = field(default_factory=dict)


class DecisionPluginManager:
    """决策插件管理器

    负责从 Plugins/decision/ 目录扫描、加载和管理决策插件。

    配置文件格式 (Plugins/decision/*.yaml):
    ```yaml
    plugin_id: "custom_intent_classifier"
    module: "my_package.plugins.CustomIntentPlugin"
    enabled: true
    priority: 50
    config:
      model_path: "/path/to/model"
      threshold: 0.8
    ```
    """

    def __init__(self, plugins_dir: str | Path = "configs/Plugins/decision"):
        self._plugins_dir = Path(plugins_dir)
        self._plugins: list[DecisionPlugin] = []
        self._plugin_configs: list[DecisionPluginConfig] = []
        self._loaded = False

    async def load_plugins(self) -> None:
        """从配置目录扫描并加载所有决策插件"""
        if not self._plugins_dir.exists():
            logger.info("decision_plugins_dir_not_found", path=str(self._plugins_dir))
            self._loaded = True
            return

        config_files = sorted(self._plugins_dir.glob("*.yaml"))
        if not config_files:
            logger.info("no_decision_plugins_found", path=str(self._plugins_dir))
            self._loaded = True
            return

        for config_file in config_files:
            try:
                plugin_config = self._load_config(config_file)
                if not plugin_config:
                    continue

                plugin = self._instantiate_plugin(plugin_config)
                if plugin:
                    await plugin.initialize()
                    self._plugins.append(plugin)
                    self._plugin_configs.append(plugin_config)
                    logger.info(
                        "decision_plugin_loaded",
                        plugin_id=plugin_config.plugin_id,
                        module=plugin_config.module,
                        priority=plugin_config.priority,
                    )
            except Exception as e:
                logger.error(
                    "decision_plugin_load_error",
                    file=str(config_file),
                    error=str(e),
                )

        # 按优先级排序（数值小的先执行）
        self._plugins.sort(key=lambda p: p.priority)
        self._loaded = True
        logger.info(
            "decision_plugins_loaded",
            total=len(self._plugins),
            enabled=sum(1 for p in self._plugins if p.enabled),
        )

    def _load_config(self, config_file: Path) -> DecisionPluginConfig | None:
        """加载插件配置文件"""
        try:
            with open(config_file) as f:
                data = yaml.safe_load(f)
            if not data or not isinstance(data, dict):
                logger.warning("invalid_plugin_config", file=str(config_file))
                return None

            plugin_id = data.get("plugin_id", config_file.stem)
            module = data.get("module")
            if not module:
                logger.warning(
                    "plugin_missing_module",
                    plugin_id=plugin_id,
                    file=str(config_file),
                )
                return None

            return DecisionPluginConfig(
                plugin_id=plugin_id,
                module=module,
                enabled=data.get("enabled", True),
                priority=data.get("priority", 100),
                config=data.get("config", {}),
            )
        except Exception as e:
            logger.error("plugin_config_parse_error", file=str(config_file), error=str(e))
            return None

    def _instantiate_plugin(self, config: DecisionPluginConfig) -> DecisionPlugin | None:
        """动态实例化插件类"""
        try:
            module_path, class_name = config.module.rsplit(".", 1)
            import importlib

            module = importlib.import_module(module_path)
            plugin_class = getattr(module, class_name)

            if not issubclass(plugin_class, DecisionPlugin):
                logger.error(
                    "plugin_not_subclass",
                    plugin_id=config.plugin_id,
                    module=config.module,
                )
                return None

            # 合并顶层配置到 plugin config
            plugin_config = dict(config.config)
            plugin_config.setdefault("enabled", config.enabled)
            plugin_config.setdefault("priority", config.priority)
            return plugin_class(config=plugin_config)
        except Exception as e:
            logger.error(
                "plugin_instantiate_error",
                plugin_id=config.plugin_id,
                module=config.module,
                error=str(e),
            )
            return None

    async def process_all(
        self,
        text: str,
        user_id: str,
        session_id: str,
        intent: IntentResult,
        emotion: EmotionState | None,
        context_summary: str | None = None,
        capability_domains: list[str] | None = None,
    ) -> PluginDecisionResult:
        """运行所有已启用的插件，合并结果

        按优先级顺序执行插件。如果某个插件设置 takeover=True，
        则停止后续插件执行并直接返回。

        Returns:
            PluginDecisionResult: 合并后的插件决策结果
        """
        merged = PluginDecisionResult()

        for plugin in self._plugins:
            if not plugin.enabled:
                continue

            try:
                result = await plugin.process(
                    text=text,
                    user_id=user_id,
                    session_id=session_id,
                    intent=intent,
                    emotion=emotion,
                    context_summary=context_summary,
                    capability_domains=capability_domains,
                )

                # 合并结果（后执行的插件覆盖先前的）
                if result.response_strategy is not None:
                    merged.response_strategy = result.response_strategy
                if result.should_use_skills is not None:
                    merged.should_use_skills = result.should_use_skills
                if result.should_use_tools is not None:
                    merged.should_use_tools = result.should_use_tools
                if result.context_priority is not None:
                    merged.context_priority = result.context_priority
                if result.token_budget_ratio is not None:
                    merged.token_budget_ratio = result.token_budget_ratio
                if result.metadata:
                    merged.metadata.update(result.metadata)

                if result.takeover:
                    merged.takeover = True
                    break

            except Exception as e:
                logger.error(
                    "decision_plugin_error",
                    plugin_id=plugin.plugin_id,
                    error=str(e),
                )

        return merged

    @property
    def plugins(self) -> list[DecisionPlugin]:
        return list(self._plugins)

    @property
    def loaded(self) -> bool:
        return self._loaded

    async def shutdown_all(self) -> None:
        """关闭所有插件"""
        for plugin in self._plugins:
            try:
                await plugin.shutdown()
            except Exception as e:
                logger.error(
                    "decision_plugin_shutdown_error",
                    plugin_id=plugin.plugin_id,
                    error=str(e),
                )
        self._plugins.clear()
