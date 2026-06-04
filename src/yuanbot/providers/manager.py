"""AI 提供商管理器

管理活跃提供商选择、模型列表解析和凭据加载。
v2.0: 支持从 configs/Providers/*.yaml 加载 Provider 配置，
实现"适配器复用，配置文件定义 Provider"。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
import yaml

from yuanbot.core.interfaces import AIProviderAdapter
from yuanbot.providers.registry import ProviderRegistry

logger = structlog.get_logger(__name__)

# 环境变量占位符正则: ${VAR_NAME}
_ENV_VAR_RE = re.compile(r"\$\{(\w+)}")


def _substitute_env_vars(value: Any) -> Any:
    """递归替换字符串中的 ${ENV_VAR} 占位符"""
    if isinstance(value, str):

        def _replace(match: re.Match[str]) -> str:
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))

        return _ENV_VAR_RE.sub(_replace, value)
    if isinstance(value, dict):
        return {k: _substitute_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env_vars(item) for item in value]
    return value


@dataclass
class ModelInfo:
    """模型信息"""

    id: str
    type: str  # "chat" | "embedding" | "multimodal"
    max_tokens: int = 128000
    dimension: int | None = None  # 仅 embedding 模型


@dataclass
class ProviderConfig:
    """提供商配置（对应 configs/Providers/*.yaml v2.0 格式）"""

    provider_id: str
    name: str = ""
    adapter: str = ""  # 适配器标识（如 "openai-adapter", "anthropic-adapter"）
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)
    models: list[ModelInfo] = field(default_factory=list)
    default_model: str | None = None
    embedding_model: str | None = None


class ProviderManager:
    """AI 提供商管理器

    职责：
    1. 从 configs/Providers/ 目录加载 Provider YAML 配置
    2. 管理多个 AI 提供商的配置
    3. 选择活跃提供商和默认模型
    4. 创建和缓存适配器实例
    5. 支持运行时切换提供商和热重载
    """

    def __init__(
        self,
        registry: ProviderRegistry | None = None,
        config_dir: str | Path | None = None,
    ):
        self._registry = registry or ProviderRegistry()
        self._config_dir = Path(config_dir) if config_dir else Path("configs")
        self._providers: dict[str, ProviderConfig] = {}
        self._adapters: dict[str, AIProviderAdapter] = {}  # 缓存的适配器实例
        self._default_provider_id: str | None = None
        self._embedding_provider_id: str | None = None

    def load_providers(self) -> None:
        """扫描 configs/Providers/ 目录，加载所有 Provider 配置

        v2.0 YAML 格式：
        ```yaml
        provider_id: openai
        name: "OpenAI"
        adapter: openai-adapter
        enabled: true
        config:
          api_key: "${OPENAI_API_KEY}"
          base_url: "https://api.openai.com/v1"
          models:
            - id: gpt-4o
              type: chat
              max_tokens: 128000
          default: gpt-4o
        ```
        """
        providers_dir = self._config_dir / "Providers"
        if not providers_dir.exists():
            logger.warning("providers_dir_not_found", path=str(providers_dir))
            return

        for yaml_file in sorted(providers_dir.glob("*.yaml")):
            try:
                self._load_provider_from_yaml(yaml_file)
            except Exception as e:
                logger.error(
                    "provider_load_error",
                    file=yaml_file.name,
                    error=str(e),
                )

    def validate_provider_config(self, raw: dict[str, Any]) -> list[str]:
        """验证 Provider 配置的必需字段

        Args:
            raw: 原始 YAML 配置字典

        Returns:
            错误消息列表，空列表表示验证通过
        """
        errors: list[str] = []

        # 必需字段
        if not raw.get("provider_id"):
            errors.append("缺少 provider_id")
        if not raw.get("adapter"):
            errors.append("缺少 adapter 字段")

        config = raw.get("config", {})
        if not config:
            errors.append("缺少 config 字段")
            return errors

        # base_url 验证
        base_url = config.get("base_url", "")
        if not base_url:
            errors.append("config.base_url 不能为空")
        elif not base_url.startswith(("http://", "https://")):
            errors.append(f"config.base_url 格式无效: {base_url}")

        # models 验证
        models = config.get("models", [])
        if not models:
            errors.append("config.models 不能为空")
        else:
            for i, m in enumerate(models):
                if not isinstance(m, dict):
                    errors.append(f"config.models[{i}] 必须是字典")
                    continue
                if not m.get("id"):
                    errors.append(f"config.models[{i}].id 不能为空")
                mtype = m.get("type", "chat")
                if mtype not in ("chat", "embedding", "multimodal"):
                    errors.append(
                        f"config.models[{i}].type 无效: {mtype}"
                        f" (应为 chat/embedding/multimodal)"
                    )

        # default 模型必须在列表中
        default_model = config.get("default")
        if default_model and models:
            model_ids = {m["id"] for m in models if isinstance(m, dict)}
            if default_model not in model_ids:
                errors.append(
                    f"config.default '{default_model}' 不在 models 列表中"
                    f" (可用: {sorted(model_ids)})"
                )

        return errors

    def _load_provider_from_yaml(self, yaml_path: Path) -> None:
        """从单个 YAML 文件加载 Provider 配置"""
        with open(yaml_path) as f:
            raw = yaml.safe_load(f)

        if not raw:
            return

        # 验证配置
        validation_errors = self.validate_provider_config(raw)
        if validation_errors:
            logger.error(
                "provider_validation_failed",
                file=yaml_path.name,
                errors=validation_errors,
            )
            # 严格模式下可以跳过加载，目前仅记录警告

        # 替换环境变量占位符
        raw = _substitute_env_vars(raw)

        provider_id = raw.get("provider_id", yaml_path.stem)
        enabled = raw.get("enabled", True)

        if not enabled:
            logger.info("provider_disabled", provider_id=provider_id)
            # 仍然注册，但标记为禁用

        # 解析配置
        adapter_id = raw.get("adapter", "")
        name = raw.get("name", provider_id)
        config = raw.get("config", {})

        # 解析模型列表
        models: list[ModelInfo] = [
            ModelInfo(
                id=m["id"],
                type=m.get("type", "chat"),
                max_tokens=m.get("max_tokens", 128000),
                dimension=m.get("dimension"),
            )
            for m in config.get("models", [])
        ]

        default_model = config.get("default")
        embedding_model = config.get("embedding_model")

        # 如果没有指定 embedding_model，自动选择第一个 embedding 类型的模型
        if not embedding_model:
            for m in models:
                if m.type == "embedding":
                    embedding_model = m.id
                    break

        provider_config = ProviderConfig(
            provider_id=provider_id,
            name=name,
            adapter=adapter_id,
            enabled=enabled,
            config=config,
            models=models,
            default_model=default_model,
            embedding_model=embedding_model,
        )

        self._providers[provider_id] = provider_config
        logger.info(
            "provider_loaded",
            provider_id=provider_id,
            adapter=adapter_id,
            enabled=enabled,
            model_count=len(models),
        )

    def register_provider(self, config: ProviderConfig) -> None:
        """注册提供商配置（编程方式，用于测试和动态注册）"""
        self._providers[config.provider_id] = config
        logger.info(
            "provider_configured",
            provider_id=config.provider_id,
            enabled=config.enabled,
            model_count=len(config.models),
        )

    def set_default_provider(self, provider_id: str) -> None:
        """设置默认提供商"""
        if provider_id not in self._providers:
            raise ValueError(f"Provider '{provider_id}' not registered")
        self._default_provider_id = provider_id

    def set_embedding_provider(self, provider_id: str) -> None:
        """设置嵌入专用提供商"""
        if provider_id not in self._providers:
            raise ValueError(f"Provider '{provider_id}' not registered")
        self._embedding_provider_id = provider_id

    def get_default_provider(self) -> ProviderConfig | None:
        """获取默认提供商配置"""
        if self._default_provider_id:
            return self._providers.get(self._default_provider_id)
        # 返回第一个启用的提供商
        for config in self._providers.values():
            if config.enabled:
                return config
        return None

    def get_provider(self, provider_id: str) -> ProviderConfig | None:
        """获取指定提供商配置"""
        return self._providers.get(provider_id)

    def get_enabled_providers(self) -> list[ProviderConfig]:
        """获取所有启用的提供商"""
        return [p for p in self._providers.values() if p.enabled]

    async def get_adapter(
        self,
        provider_id: str | None = None,
    ) -> AIProviderAdapter:
        """获取提供商的适配器实例

        Args:
            provider_id: 提供商 ID，None 则使用默认

        Returns:
            适配器实例

        Raises:
            ValueError: 如果提供商未找到或未启用
        """
        pid = provider_id or self._default_provider_id
        if not pid:
            # 尝试使用第一个启用的提供商
            for config in self._providers.values():
                if config.enabled:
                    pid = config.provider_id
                    break
            if not pid:
                raise ValueError("No enabled AI provider found")

        # 检查缓存
        if pid in self._adapters:
            return self._adapters[pid]

        config = self._providers.get(pid)
        if not config:
            raise ValueError(f"Provider '{pid}' not found")

        if not config.enabled:
            raise ValueError(f"Provider '{pid}' is disabled")

        # 创建适配器：传入 config 字典（包含 api_key, base_url, models 等）
        # 适配器通过 config 中的字段进行初始化
        adapter = self._registry.create_adapter(config.adapter, config.config, provider_id=pid)
        self._adapters[pid] = adapter

        logger.info("adapter_created", provider_id=pid, adapter=config.adapter)
        return adapter

    def get_default_model(self, provider_id: str | None = None) -> str | None:
        """获取提供商的默认模型"""
        pid = provider_id or self._default_provider_id
        if not pid:
            return None
        config = self._providers.get(pid)
        if not config:
            return None
        return config.default_model

    def get_models(
        self,
        provider_id: str | None = None,
        model_type: str | None = None,
    ) -> list[ModelInfo]:
        """获取提供商的模型列表

        Args:
            provider_id: 提供商 ID
            model_type: 模型类型过滤（"chat" | "embedding"）

        Returns:
            模型信息列表
        """
        pid = provider_id or self._default_provider_id
        if not pid:
            return []
        config = self._providers.get(pid)
        if not config:
            return []
        if model_type:
            return [m for m in config.models if m.type == model_type]
        return config.models

    def get_embedding_model(self, provider_id: str | None = None) -> ModelInfo | None:
        """获取提供商的嵌入模型"""
        # 优先使用 embedding_provider
        pid = provider_id or self._embedding_provider_id
        if pid:
            config = self._providers.get(pid)
            if config and config.embedding_model:
                for m in config.models:
                    if m.id == config.embedding_model:
                        return m

        # 回退到默认提供商的嵌入模型
        pid = pid or self._default_provider_id
        if not pid:
            return None
        models = self.get_models(pid, model_type="embedding")
        return models[0] if models else None

    async def reload_provider(self, provider_id: str, new_config: dict[str, Any]) -> None:
        """热重载提供商配置

        当配置文件变化时调用，更新提供商配置并清除缓存的适配器实例，
        使其在下次请求时使用新配置重新创建。

        Args:
            provider_id: 提供商 ID
            new_config: 新的配置字典（对应 YAML 文件内容）
        """
        logger.info("reloading_provider", provider_id=provider_id)

        # 替换环境变量
        new_config = _substitute_env_vars(new_config)

        # 解析新配置（支持 v2.0 格式）
        config_data = new_config.get("config", {})
        models = [
            ModelInfo(
                id=m["id"],
                type=m.get("type", "chat"),
                max_tokens=m.get("max_tokens", 128000),
                dimension=m.get("dimension"),
            )
            for m in config_data.get("models", [])
        ]

        default_model = config_data.get("default")
        embedding_model = config_data.get("embedding_model")

        new_provider_config = ProviderConfig(
            provider_id=provider_id,
            name=new_config.get("name", provider_id),
            adapter=new_config.get("adapter", ""),
            enabled=new_config.get("enabled", True),
            config=config_data,
            models=models,
            default_model=default_model,
            embedding_model=embedding_model,
        )

        # 更新配置
        self._providers[provider_id] = new_provider_config

        # 清除缓存的适配器实例，使其下次使用新配置重建
        old_adapter = self._adapters.pop(provider_id, None)
        if old_adapter and hasattr(old_adapter, "close"):
            try:
                await old_adapter.close()
            except Exception as e:
                logger.error(
                    "adapter_close_error_during_reload",
                    provider_id=provider_id,
                    error=str(e),
                )

        logger.info(
            "provider_reloaded",
            provider_id=provider_id,
            enabled=new_provider_config.enabled,
            model_count=len(models),
        )

    def resolve_model(self, model_ref: str | None = None) -> tuple[str, str]:
        """解析模型引用，返回 (provider_id, model_id)

        支持格式：
        - None: 使用默认提供商的默认模型
        - "gpt-4o": 在默认提供商中查找
        - "openai/gpt-4o": 指定提供商+模型
        - "deepseek/deepseek-chat": 指定提供商+模型

        Returns:
            (provider_id, model_id) 元组

        Raises:
            ValueError: 无法解析模型引用
        """
        if model_ref is None:
            default_config = self.get_default_provider()
            if not default_config:
                raise ValueError("No default AI provider configured")
            default_model = default_config.default_model
            if not default_model:
                # 使用第一个 chat 模型
                chat_models = self.get_models(
                    default_config.provider_id, model_type="chat"
                )
                if chat_models:
                    default_model = chat_models[0].id
                else:
                    raise ValueError(
                        f"No chat model found for provider '{default_config.provider_id}'"
                    )
            return default_config.provider_id, default_model

        # 检查是否包含提供商前缀 (provider/model)
        if "/" in model_ref:
            pid, mid = model_ref.split("/", 1)
            if pid not in self._providers:
                raise ValueError(
                    f"Provider '{pid}' not found. "
                    f"Available: {list(self._providers.keys())}"
                )
            return pid, mid

        # 在默认提供商中查找
        default_config = self.get_default_provider()
        if default_config:
            return default_config.provider_id, model_ref

        raise ValueError(f"Cannot resolve model '{model_ref}'")

    def list_providers(self) -> list[dict[str, Any]]:
        """列出所有 Provider 的摘要信息

        Returns:
            包含 provider 信息的字典列表
        """
        result = [
            {
                "provider_id": config.provider_id,
                "name": config.name,
                "adapter": config.adapter,
                "enabled": config.enabled,
                "default_model": config.default_model,
                "embedding_model": config.embedding_model,
                "model_count": len(config.models),
                "is_default": config.provider_id == self._default_provider_id,
                "is_embedding": config.provider_id == self._embedding_provider_id,
            }
            for config in self._providers.values()
        ]
        return result

    async def close_all(self) -> None:
        """关闭所有适配器"""
        for pid, adapter in self._adapters.items():
            try:
                if hasattr(adapter, "close"):
                    await adapter.close()
            except Exception as e:
                logger.error("adapter_close_error", provider_id=pid, error=str(e))
        self._adapters.clear()
