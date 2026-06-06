"""配置热加载模块

监听配置文件变化，自动重载配置，无需重启系统。

设计参考: gateway-communication-system.md 6.3 + capability-tool-system.md 9.2
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# 文件变更回调类型
ConfigChangeCallback = Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]


class ConfigWatcher:
    """配置文件热加载监听器

    通过轮询方式监听配置文件的修改时间，
    检测到变化后自动重新加载并通知注册的回调。

    支持：
    - 单文件监听（如 bot.yaml）
    - 目录监听（如 Providers/, Channels/, Plugins/）
    - 递归监听（子目录中的 .yaml 文件）

    设计参考:
    - gateway-communication-system.md 6.3 动态热加载
    - capability-tool-system.md 9.2 技能/工具的启用与禁用
    """

    def __init__(
        self,
        config_dir: str | Path,
        poll_interval_seconds: float = 5.0,
    ):
        self._config_dir = Path(config_dir)
        self._poll_interval = poll_interval_seconds
        self._callbacks: dict[str, list[ConfigChangeCallback]] = {}
        self._file_mtimes: dict[str, float] = {}
        self._running = False
        self._loop_task: asyncio.Task[None] | None = None

    def on_change(
        self,
        pattern: str,
        callback: ConfigChangeCallback,
    ) -> None:
        """注册配置变更回调

        Args:
            pattern: 文件匹配模式（如 "bot.yaml", "Providers/*.yaml", "Channels/*"）
            callback: 异步回调函数 (file_path, new_config) -> None
        """
        if pattern not in self._callbacks:
            self._callbacks[pattern] = []
        self._callbacks[pattern].append(callback)
        logger.info("config_change_handler_registered", pattern=pattern)

    async def start(self) -> None:
        """启动配置监听"""
        if self._running:
            return

        self._running = True
        # 初始化所有文件的修改时间
        self._scan_all_mtimes()
        self._loop_task = asyncio.create_task(self._watch_loop())
        logger.info(
            "config_watcher_started",
            config_dir=str(self._config_dir),
            poll_interval=self._poll_interval,
            tracked_files=len(self._file_mtimes),
        )

    async def stop(self) -> None:
        """停止配置监听"""
        self._running = False
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        self._loop_task = None
        logger.info("config_watcher_stopped")

    def _scan_all_mtimes(self) -> None:
        """扫描所有配置文件的修改时间"""
        if not self._config_dir.exists():
            return

        for yaml_file in self._config_dir.rglob("*.yaml"):
            try:
                self._file_mtimes[str(yaml_file)] = yaml_file.stat().st_mtime
            except OSError:
                pass

    def _detect_changes(self) -> list[Path]:
        """检测配置文件变化

        Returns:
            变化的文件路径列表
        """
        changed: list[Path] = []
        current_files: set[str] = set()

        if not self._config_dir.exists():
            return changed

        for yaml_file in self._config_dir.rglob("*.yaml"):
            file_path = str(yaml_file)
            current_files.add(file_path)

            try:
                current_mtime = yaml_file.stat().st_mtime
            except OSError:
                continue

            prev_mtime = self._file_mtimes.get(file_path)
            if prev_mtime is None:
                # 新文件
                self._file_mtimes[file_path] = current_mtime
                changed.append(yaml_file)
                logger.info("config_file_added", path=file_path)
            elif current_mtime > prev_mtime:
                # 文件已修改
                self._file_mtimes[file_path] = current_mtime
                changed.append(yaml_file)
                logger.info("config_file_changed", path=file_path)

        # 检测删除的文件
        for file_path in list(self._file_mtimes.keys()):
            if file_path not in current_files:
                del self._file_mtimes[file_path]
                logger.info("config_file_removed", path=file_path)

        return changed

    def _match_pattern(self, file_path: Path, pattern: str) -> bool:
        """检查文件路径是否匹配模式"""
        relative = file_path.relative_to(self._config_dir)
        relative_str = str(relative)

        # 精确匹配
        if relative_str == pattern:
            return True

        # 通配符匹配
        if "*" in pattern:
            from fnmatch import fnmatch

            return fnmatch(relative_str, pattern)

        # 前缀匹配（如 "Providers" 匹配 "Providers/openai.yaml"）
        return relative_str.startswith(pattern.rstrip("/*"))

    async def _watch_loop(self) -> None:
        """配置监听主循环"""
        try:
            while self._running:
                changed_files = self._detect_changes()

                for file_path in changed_files:
                    await self._notify_change(file_path)

                await asyncio.sleep(self._poll_interval)
        except asyncio.CancelledError:
            logger.debug("config_watcher_loop_cancelled")

    async def _notify_change(self, file_path: Path) -> None:
        """通知所有匹配的回调"""
        import yaml

        # 重新加载文件
        try:
            with open(file_path, encoding="utf-8") as f:
                new_config = yaml.safe_load(f) or {}
        except Exception as e:
            logger.error("config_reload_failed", path=str(file_path), error=str(e))
            return

        relative = str(file_path.relative_to(self._config_dir))

        for pattern, callbacks in self._callbacks.items():
            if self._match_pattern(file_path, pattern):
                for callback in callbacks:
                    try:
                        await callback(relative, new_config)
                    except Exception:
                        logger.exception(
                            "config_change_callback_error",
                            pattern=pattern,
                            file=relative,
                        )

        logger.info("config_reloaded", file=relative)
