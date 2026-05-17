"""YuanBot 配置管理"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


class AIProviderConfig(BaseModel):
    """AI 提供商配置"""

    provider_id: str = "openai"
    api_key: str | None = None
    base_url: str | None = None
    default_model: str = "gpt-4o"


class ChannelProviderConfig(BaseModel):
    """消息通道配置"""

    platform: str
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class MemoryConfig(BaseModel):
    """记忆系统配置"""

    # 向量数据库
    vector_db: str = "qdrant"
    vector_db_url: str = "http://localhost:6333"

    # 关系数据库
    db_url: str = "postgresql://yuanbot:yuanbot@localhost:5432/yuanbot"

    # Redis 缓存
    redis_url: str = "redis://localhost:6379/0"

    # 图数据库
    graph_db: str = "neo4j"
    graph_db_url: str = "bolt://localhost:7687"

    # 记忆参数
    max_working_memory_turns: int = 20
    episodic_memory_max_age_days: int = 90
    forget_curve_half_life_days: int = 14
    consolidation_threshold: int = 3  # 出现 3 次以上的话题升级为事实记忆


class ProactiveConfig(BaseModel):
    """主动交互配置"""

    enabled: bool = True
    greeting_enabled: bool = True
    frequency: str = "medium"  # "high" | "medium" | "low" | "event_only"
    quiet_hours_start: int = 23
    quiet_hours_end: int = 8
    max_per_day: int = 5
    event_triggers_enabled: bool = True


class YuanBotConfig(BaseModel):
    """YuanBot 主配置"""

    # 基础配置
    app_name: str = "YuanBot"
    version: str = "1.0.0"
    debug: bool = False
    log_level: str = "INFO"

    # AI 提供商
    ai_provider: AIProviderConfig = Field(default_factory=AIProviderConfig)

    # 消息通道
    channels: list[ChannelProviderConfig] = Field(default_factory=list)

    # 记忆系统
    memory: MemoryConfig = Field(default_factory=MemoryConfig)

    # 主动交互
    proactive: ProactiveConfig = Field(default_factory=ProactiveConfig)

    # Agent 人设
    persona_id: str = "default"
    persona_config_path: str | None = None


def load_config(
    config_path: str | Path | None = None,
    env_file: str | Path | None = None,
) -> YuanBotConfig:
    """加载配置

    优先级：环境变量 > 配置文件 > 默认值
    """
    # 加载 .env 文件
    if env_file:
        load_dotenv(env_file)
    else:
        load_dotenv()

    # 加载 YAML 配置文件
    config_data: dict[str, Any] = {}
    if config_path:
        path = Path(config_path)
        if path.exists():
            with open(path) as f:
                config_data = yaml.safe_load(f) or {}

    # 环境变量覆盖
    env_overrides = _load_env_overrides()
    config_data = _deep_merge(config_data, env_overrides)

    return YuanBotConfig(**config_data)


def _load_env_overrides() -> dict[str, Any]:
    """从环境变量加载配置覆盖"""
    overrides: dict[str, Any] = {}

    # AI 提供商
    if provider := os.getenv("YUAN_AI_PROVIDER"):
        overrides.setdefault("ai_provider", {})["provider_id"] = provider

    if api_key := os.getenv("YUAN_AI_API_KEY"):
        overrides.setdefault("ai_provider", {})["api_key"] = api_key

    if base_url := os.getenv("YUAN_AI_BASE_URL"):
        overrides.setdefault("ai_provider", {})["base_url"] = base_url

    if model := os.getenv("YUAN_AI_MODEL"):
        overrides.setdefault("ai_provider", {})["default_model"] = model

    # 调试模式
    if debug := os.getenv("YUAN_DEBUG"):
        overrides["debug"] = debug.lower() in ("true", "1", "yes")

    # 日志级别
    if log_level := os.getenv("YUAN_LOG_LEVEL"):
        overrides["log_level"] = log_level.upper()

    return overrides


def _deep_merge(base: dict, override: dict) -> dict:
    """深度合并两个字典"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
