"""主动触发器插件系统

提供 ProactiveTrigger 抽象基类和 TriggerManager，
支持开发者按 Y.E.S. 规范开发自定义触发器。

设计参考: proactive-companion-system.md 第7.1节
"""

from __future__ import annotations

import importlib.util
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class TriggerResult:
    """触发器检查结果"""

    triggered: bool
    event_type: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    priority: int = 5


class ProactiveTrigger(ABC):
    """主动触发器抽象基类

    开发者可按 Y.E.S. 规范实现自定义触发器，存于 configs/Plugins/proactive_triggers/。

    示例:
        class WeatherAlertTrigger(ProactiveTrigger):
            def get_event_type(self) -> str:
                return "weather_change"

            async def check(self, user_id: str) -> TriggerResult:
                # 检查天气条件
                ...
                return TriggerResult(triggered=True, data={"temp_drop": 8})
    """

    @abstractmethod
    def get_event_type(self) -> str:
        """返回此触发器关联的事件类型"""
        ...

    @abstractmethod
    async def check(self, user_id: str) -> TriggerResult:
        """检查是否满足触发条件

        Args:
            user_id: 目标用户 ID

        Returns:
            TriggerResult 包含是否触发和相关数据
        """
        ...

    def get_name(self) -> str:
        """触发器名称（用于日志和识别）"""
        return self.__class__.__name__

    def get_priority(self) -> int:
        """触发优先级 1-10，默认 5"""
        return 5

    async def initialize(self, config: dict[str, Any] | None = None) -> None:
        """可选的初始化钩子，在加载后调用"""
        pass

    async def shutdown(self) -> None:
        """可选的关闭钩子，在卸载前调用"""
        pass


class TriggerManager:
    """触发器插件管理器

    负责扫描、加载和管理自定义触发器插件。
    触发器插件目录结构：
        configs/Plugins/proactive_triggers/
        ├── weather_alert/
        │   ├── manifest.json
        │   └── trigger.py
        └── festival_check/
            ├── manifest.json
            └── trigger.py

    manifest.json 格式：
        {
            "name": "weather_alert",
            "version": "1.0.0",
            "event_type": "weather_change",
            "entry_point": "trigger.py",
            "enabled": true
        }
    """

    def __init__(self, plugins_dir: str | Path | None = None) -> None:
        self._plugins_dir = Path(plugins_dir) if plugins_dir else None
        self._triggers: dict[str, ProactiveTrigger] = {}  # name -> trigger instance
        self._manifests: dict[str, dict[str, Any]] = {}  # name -> manifest

    @property
    def trigger_count(self) -> int:
        """已加载的触发器数量"""
        return len(self._triggers)

    def register(self, trigger: ProactiveTrigger, manifest: dict[str, Any] | None = None) -> str:
        """手动注册一个触发器

        Args:
            trigger: 触发器实例
            manifest: 可选的清单元数据

        Returns:
            触发器名称
        """
        name = trigger.get_name()
        self._triggers[name] = trigger
        if manifest:
            self._manifests[name] = manifest
        logger.info("trigger_registered", name=name, event_type=trigger.get_event_type())
        return name

    def unregister(self, name: str) -> bool:
        """注销触发器"""
        trigger = self._triggers.pop(name, None)
        if trigger:
            self._manifests.pop(name, None)
            logger.info("trigger_unregistered", name=name)
            return True
        return False

    def get(self, name: str) -> ProactiveTrigger | None:
        """获取指定触发器"""
        return self._triggers.get(name)

    def get_all(self) -> list[ProactiveTrigger]:
        """获取所有已注册的触发器"""
        return list(self._triggers.values())

    def get_by_event_type(self, event_type: str) -> list[ProactiveTrigger]:
        """获取指定事件类型的所有触发器"""
        return [t for t in self._triggers.values() if t.get_event_type() == event_type]

    async def check_all(self, user_id: str) -> list[TriggerResult]:
        """运行所有触发器检查

        Args:
            user_id: 目标用户 ID

        Returns:
            所有触发的 TriggerResult 列表
        """
        results: list[TriggerResult] = []
        for name, trigger in self._triggers.items():
            try:
                result = await trigger.check(user_id)
                if result.triggered:
                    logger.info(
                        "trigger_activated",
                        name=name,
                        user_id=user_id,
                        event_type=trigger.get_event_type(),
                    )
                    results.append(result)
            except Exception:
                logger.exception("trigger_check_error", name=name, user_id=user_id)
        return results

    async def load_plugins(self, plugins_dir: str | Path | None = None) -> int:
        """从目录加载触发器插件

        Args:
            plugins_dir: 插件目录路径，None 使用默认路径

        Returns:
            成功加载的插件数量
        """
        directory = Path(plugins_dir) if plugins_dir else self._plugins_dir
        if not directory or not directory.exists():
            return 0

        loaded = 0
        for plugin_dir in directory.iterdir():
            if not plugin_dir.is_dir():
                continue

            manifest_path = plugin_dir / "manifest.json"
            if not manifest_path.exists():
                continue

            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                logger.warning("trigger_manifest_read_failed", path=str(manifest_path))
                continue

            if not manifest.get("enabled", True):
                logger.debug("trigger_disabled", name=manifest.get("name", plugin_dir.name))
                continue

            entry_point = manifest.get("entry_point", "trigger.py")
            trigger_path = plugin_dir / entry_point
            if not trigger_path.exists():
                logger.warning("trigger_entry_missing", path=str(trigger_path))
                continue

            try:
                trigger_cls = self._load_trigger_class(trigger_path)
                if trigger_cls is None:
                    continue

                trigger = trigger_cls()
                name = manifest.get("name", plugin_dir.name)

                # 初始化
                plugin_config = manifest.get("config")
                await trigger.initialize(plugin_config)

                self._triggers[name] = trigger
                self._manifests[name] = manifest
                loaded += 1
                logger.info(
                    "trigger_plugin_loaded",
                    name=name,
                    event_type=trigger.get_event_type(),
                    path=str(trigger_path),
                )
            except Exception:
                logger.exception("trigger_plugin_load_failed", path=str(trigger_path))

        return loaded

    def get_manifests(self) -> dict[str, dict[str, Any]]:
        """获取所有触发器清单"""
        return dict(self._manifests)

    @staticmethod
    def _load_trigger_class(path: Path) -> type[ProactiveTrigger] | None:
        """从 Python 文件中加载 ProactiveTrigger 子类"""
        module_name = f"yuanbot_trigger_{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, str(path))
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception:
            return None

        # 查找 ProactiveTrigger 子类
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, ProactiveTrigger)
                and attr is not ProactiveTrigger
            ):
                return attr

        return None
