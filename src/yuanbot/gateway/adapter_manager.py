"""消息通道适配器管理器

负责动态加载、注册和管理所有消息通道适配器的生命周期。
"""

from __future__ import annotations

import structlog

from yuanbot.core.interfaces import ChannelAdapter
from yuanbot.core.types import ChannelConfig

logger = structlog.get_logger(__name__)

# 内置适配器类型映射
_BUILTIN_ADAPTERS: dict[str, str] = {
    "telegram": "yuanbot.adapters.channel.telegram_adapter.TelegramAdapter",
    "web": "yuanbot.adapters.channel.web_adapter.WebAdapter",
    "discord": "yuanbot.adapters.channel.discord_adapter.DiscordAdapter",
    "wecom": "yuanbot.adapters.channel.wecom_adapter.WeComAdapter",
}


class AdapterManager:
    """消息通道适配器管理器

    职责：
    1. 扫描配置文件，动态加载适配器类
    2. 管理适配器的生命周期（初始化、运行、关闭）
    3. 提供适配器查询和健康检查
    """

    def __init__(self) -> None:
        self._adapters: dict[str, ChannelAdapter] = {}  # platform_name -> adapter
        self._configs: dict[str, ChannelConfig] = {}
        self._health_status: dict[str, bool] = {}

    async def load_adapter(
        self,
        platform: str,
        config: ChannelConfig,
    ) -> ChannelAdapter:
        """加载并初始化一个通道适配器

        Args:
            platform: 平台标识（如 'telegram', 'web'）
            config: 通道配置

        Returns:
            初始化后的适配器实例
        """
        adapter = self._create_adapter(platform)
        await adapter.initialize(config)

        self._adapters[platform] = adapter
        self._configs[platform] = config
        self._health_status[platform] = True

        logger.info("adapter_loaded", platform=platform, enabled=config.enabled)
        return adapter

    def get_adapter(self, platform: str) -> ChannelAdapter | None:
        """获取指定平台的适配器"""
        return self._adapters.get(platform)

    def get_all_adapters(self) -> dict[str, ChannelAdapter]:
        """获取所有已加载的适配器"""
        return dict(self._adapters)

    def get_enabled_adapters(self) -> dict[str, ChannelAdapter]:
        """获取所有已启用的适配器"""
        return {
            platform: adapter
            for platform, adapter in self._adapters.items()
            if self._configs.get(platform, ChannelConfig(platform=platform)).enabled
        }

    async def unload_adapter(self, platform: str) -> bool:
        """卸载指定平台的适配器

        Returns:
            True if adapter was unloaded, False if not found.
        """
        adapter = self._adapters.pop(platform, None)
        if adapter is None:
            return False

        self._configs.pop(platform, None)
        self._health_status.pop(platform, None)

        logger.info("adapter_unloaded", platform=platform)
        return True

    async def shutdown_all(self) -> None:
        """关闭所有适配器"""
        for platform, adapter in self._adapters.items():
            try:
                if hasattr(adapter, "close"):
                    await adapter.close()
                logger.info("adapter_shutdown", platform=platform)
            except Exception as e:
                logger.error("adapter_shutdown_error", platform=platform, error=str(e))

        self._adapters.clear()
        self._configs.clear()
        self._health_status.clear()

    def get_health_status(self) -> dict[str, bool]:
        """获取所有适配器的健康状态"""
        return dict(self._health_status)

    def set_health_status(self, platform: str, healthy: bool) -> None:
        """更新适配器健康状态"""
        self._health_status[platform] = healthy

    def _create_adapter(self, platform: str) -> ChannelAdapter:
        """根据平台标识创建适配器实例"""
        if platform == "telegram":
            from yuanbot.adapters.channel.telegram_adapter import TelegramAdapter

            return TelegramAdapter()
        elif platform == "web":
            from yuanbot.adapters.channel.web_adapter import WebAdapter

            return WebAdapter()
        elif platform == "discord":
            from yuanbot.adapters.channel.discord_adapter import DiscordAdapter

            return DiscordAdapter()
        elif platform == "wecom":
            from yuanbot.adapters.channel.wecom_adapter import WeComAdapter

            return WeComAdapter()
        else:
            raise ValueError(f"Unknown channel platform: {platform}")
