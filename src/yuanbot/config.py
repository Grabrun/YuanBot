"""YuanBot 配置管理

重构为支持 configs/ 目录结构的配置系统。
保持向后兼容：YuanBotConfig 和 load_config() 仍然可用。

配置加载优先级：环境变量 > 配置文件 > 默认值
"""

from __future__ import annotations

import contextlib
import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 新配置模型 (v1.5 configs/ 目录结构)
# ---------------------------------------------------------------------------


class ModelEntry(BaseModel):
    """模型列表条目"""

    id: str
    type: str = "chat"  # chat | embedding
    max_tokens: int = 128000
    dimension: int | None = None  # 仅 embedding 类型


class ProviderConfigEntry(BaseModel):
    """AI 提供商配置条目 (v2.0 格式, 对应 Providers/*.yaml)"""

    provider_id: str
    name: str = ""
    adapter: str = ""
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)
    models: list[ModelEntry] = Field(default_factory=list)
    default_model: str | None = None
    embedding_model: str | None = None

    @classmethod
    def from_yaml(cls, raw: dict[str, Any]) -> ProviderConfigEntry:
        """从 YAML 原始数据创建（处理嵌套结构）"""
        config_data = raw.get("config", {})
        models = [ModelEntry(**m) for m in config_data.get("models", [])]
        return cls(
            provider_id=raw.get("provider_id", ""),
            name=raw.get("name", ""),
            adapter=raw.get("adapter", ""),
            enabled=raw.get("enabled", True),
            config=config_data,
            models=models,
            default_model=config_data.get("default"),
            embedding_model=config_data.get("embedding_model"),
        )


# 向后兼容
ProviderApiConfig = dict


class ChannelConfigEntry(BaseModel):
    """消息通道配置条目 (对应 Channels/*.yaml)"""

    platform: str
    display_name: str = ""
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class AiConfig(BaseModel):
    """AI 子系统配置 (bot.yaml 的 ai 段)"""

    default_provider: str = "deepseek"
    default_model: str = "deepseek-v4-flash"
    embedding_provider: str | None = None


class PersonaConfig(BaseModel):
    """人设配置 (bot.yaml 的 persona 段)"""

    id: str = "default"
    config_path: str | None = None


class QuietHoursConfig(BaseModel):
    """安静时段"""

    start: int = 23
    end: int = 8


class ProactiveSectionConfig(BaseModel):
    """主动交互配置 (bot.yaml 的 proactive 段)"""

    enabled: bool = True
    greeting_enabled: bool = True
    frequency: str = "medium"
    quiet_hours: QuietHoursConfig = Field(default_factory=QuietHoursConfig)
    max_per_day: int = 5
    event_triggers_enabled: bool = True


class IntentEngineConfig(BaseModel):
    """意图识别引擎配置"""

    enabled: bool = True
    confidence_threshold: float = 0.7
    use_ml_model: bool = False
    model_path: str = "models/intent_model.onnx"
    tokenizer_path: str = "models/tokenizer.json"
    labels_path: str = "models/labels.json"


class EmotionEngineConfig(BaseModel):
    """情感分析引擎配置"""

    enabled: bool = True
    decay_rate: float = 0.1


class TokenBudgetConfig(BaseModel):
    """Token 预算配置"""

    max_input_tokens: int = 8000
    max_output_tokens: int = 2000
    reserved_for_memory: int = 2000


class OrchestratorConfig(BaseModel):
    """编排引擎配置"""

    intent_engine: IntentEngineConfig = Field(default_factory=IntentEngineConfig)
    emotion_engine: EmotionEngineConfig = Field(default_factory=EmotionEngineConfig)
    token_budget: TokenBudgetConfig = Field(default_factory=TokenBudgetConfig)


class BotConfig(BaseModel):
    """根配置 (对应 bot.yaml)"""

    app_name: str = "YuanBot"
    version: str = "1.0.0"
    debug: bool = False
    log_level: str = "INFO"
    ai: AiConfig = Field(default_factory=AiConfig)
    channels: dict[str, Any] = Field(default_factory=dict)
    persona: PersonaConfig = Field(default_factory=PersonaConfig)
    proactive: ProactiveSectionConfig = Field(default_factory=ProactiveSectionConfig)
    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)


# -- database.yaml 模型 --


class SQLiteConfig(BaseModel):
    """SQLite 配置"""

    path: str = "data/yuanbot.db"


class MySQLConfig(BaseModel):
    """MySQL 配置"""

    host: str = "localhost"
    port: int = 3306
    database: str = "yuanbot"
    user: str = "yuanbot"
    password: str = ""
    pool_size: int = 10


class RelationalDBConfig(BaseModel):
    """关系型数据库配置"""

    type: str = "sqlite"  # sqlite | mysql
    sqlite: SQLiteConfig = Field(default_factory=SQLiteConfig)
    mysql: MySQLConfig = Field(default_factory=MySQLConfig)


class MilvusLiteConfig(BaseModel):
    """Milvus Lite 配置"""

    persist_dir: str = "data/milvus"


class MilvusConfig(BaseModel):
    """Milvus 服务端配置"""

    host: str = "localhost"
    port: int = 19530


class VectorDBConfig(BaseModel):
    """向量数据库配置"""

    type: str = "milvus_lite"
    milvus_lite: MilvusLiteConfig = Field(default_factory=MilvusLiteConfig)
    milvus: MilvusConfig = Field(default_factory=MilvusConfig)


class RedisConfig(BaseModel):
    """Redis 配置"""

    url: str = "redis://localhost:6379/0"
    max_connections: int = 20


class KuzuConfig(BaseModel):
    """Kuzu 图数据库配置"""

    persist_dir: str = "data/kuzu"


class Neo4jConfig(BaseModel):
    """Neo4j 配置"""

    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    password: str = ""


class GraphDBConfig(BaseModel):
    """图数据库配置"""

    type: str = "kuzu"
    kuzu: KuzuConfig = Field(default_factory=KuzuConfig)
    neo4j: Neo4jConfig = Field(default_factory=Neo4jConfig)


class DatabaseConfig(BaseModel):
    """数据库配置 (对应 database.yaml)"""

    relational: RelationalDBConfig = Field(default_factory=RelationalDBConfig)
    vector: VectorDBConfig = Field(default_factory=VectorDBConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    graph: GraphDBConfig = Field(default_factory=GraphDBConfig)


# -- memory.yaml 模型 --


class WorkingMemoryConfig(BaseModel):
    """工作记忆配置"""

    max_turns: int = 20
    redis_ttl_seconds: int = 3600


class FactMemoryConfig(BaseModel):
    """事实记忆配置"""

    max_entries_per_user: int = 1000
    importance_threshold: float = 0.3


class EpisodicMemoryConfig(BaseModel):
    """情景记忆配置"""

    max_age_days: int = 90
    summary_max_length: int = 500
    embedding_batch_size: int = 32


class ForgettingCurveConfig(BaseModel):
    """遗忘曲线配置"""

    enabled: bool = True
    half_life_days: int = 14
    min_retention_score: float = 0.1
    review_interval_days: int = 7


class ConsolidationConfig(BaseModel):
    """记忆固化配置"""

    enabled: bool = True
    threshold: int = 3
    schedule: str = "0 3 * * *"
    batch_size: int = 100


class SemanticMemoryConfig(BaseModel):
    """语义记忆配置"""

    graph_update_on_interaction: bool = True
    relationship_depth: int = 3


class MemorySystemConfig(BaseModel):
    """记忆系统配置 (对应 memory.yaml)"""

    working_memory: WorkingMemoryConfig = Field(default_factory=WorkingMemoryConfig)
    fact_memory: FactMemoryConfig = Field(default_factory=FactMemoryConfig)
    episodic_memory: EpisodicMemoryConfig = Field(default_factory=EpisodicMemoryConfig)
    forgetting_curve: ForgettingCurveConfig = Field(default_factory=ForgettingCurveConfig)
    consolidation: ConsolidationConfig = Field(default_factory=ConsolidationConfig)
    semantic_memory: SemanticMemoryConfig = Field(default_factory=SemanticMemoryConfig)


# ---------------------------------------------------------------------------
# ConfigLoader - 支持 configs/ 目录化 YAML 加载
# ---------------------------------------------------------------------------

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


def _deep_merge(base: dict, override: dict) -> dict:
    """深度合并两个字典"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_yaml_file(path: Path) -> dict[str, Any]:
    """安全加载 YAML 文件，不存在时返回空字典"""
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
        if data is None:
            return {}
        return _substitute_env_vars(data)
    except Exception:
        return {}


class ConfigLoader:
    """统一配置加载器

    支持 v1.4 的 configs/ 目录结构，同时保持向后兼容。

    使用方式::

        loader = ConfigLoader("configs")
        bot_config = loader.load_bot_config()
        providers = loader.load_provider_configs()
        channels = loader.load_channel_configs()
    """

    def __init__(self, config_dir: str | Path | None = None):
        self._config_dir = Path(config_dir) if config_dir else Path("configs")
        self._cache: dict[str, Any] = {}

    @property
    def config_dir(self) -> Path:
        return self._config_dir

    # -- 新增加载方法 --

    def load_bot_config(self) -> BotConfig:
        """加载根配置 (bot.yaml)"""
        raw = self._load_yaml("bot.yaml")
        return BotConfig(**raw)

    def load_database_config(self) -> DatabaseConfig:
        """加载数据库配置 (database.yaml)"""
        raw = self._load_yaml("database.yaml")
        return DatabaseConfig(**raw)

    def load_memory_config(self) -> MemorySystemConfig:
        """加载记忆系统配置 (memory.yaml)"""
        raw = self._load_yaml("memory.yaml")
        return MemorySystemConfig(**raw)

    def load_provider_configs(self) -> dict[str, ProviderConfigEntry]:
        """扫描 Providers/ 目录加载所有提供商配置

        支持 v2.0 YAML 格式（嵌套 config 字段）。

        Returns:
            字典，key 为 provider_id，value 为 ProviderConfigEntry
        """
        providers: dict[str, ProviderConfigEntry] = {}
        providers_dir = self._config_dir / "Providers"
        if not providers_dir.exists():
            return providers

        for yaml_file in sorted(providers_dir.glob("*.yaml")):
            raw = self._load_yaml(f"Providers/{yaml_file.name}")
            if not raw:
                continue
            try:
                entry = ProviderConfigEntry.from_yaml(raw)
                providers[entry.provider_id] = entry
            except Exception:
                continue
        return providers

    def load_channel_configs(self) -> dict[str, ChannelConfigEntry]:
        """扫描 Channels/ 目录加载所有通道配置

        Returns:
            字典，key 为 platform，value 为 ChannelConfigEntry
        """
        channels: dict[str, ChannelConfigEntry] = {}
        channels_dir = self._config_dir / "Channels"
        if not channels_dir.exists():
            return channels

        for yaml_file in sorted(channels_dir.glob("*.yaml")):
            raw = self._load_yaml(f"Channels/{yaml_file.name}")
            if not raw:
                continue
            try:
                entry = ChannelConfigEntry(**raw)
                channels[entry.platform] = entry
            except Exception:
                continue
        return channels

    def load_provider_config(self, provider_id: str) -> ProviderConfigEntry | None:
        """加载单个提供商配置"""
        raw = self._load_yaml(f"Providers/{provider_id}.yaml")
        if not raw:
            return None
        try:
            return ProviderConfigEntry.from_yaml(raw)
        except Exception:
            return None

    def load_channel_config(self, platform: str) -> ChannelConfigEntry | None:
        """加载单个通道配置"""
        raw = self._load_yaml(f"Channels/{platform}.yaml")
        if not raw:
            return None
        try:
            return ChannelConfigEntry(**raw)
        except Exception:
            return None

    def apply_env_overrides(self, config: dict[str, Any]) -> dict[str, Any]:
        """应用环境变量覆盖

        环境变量命名规则 (双下划线分隔层级):
        YUAN_BOT__AI__DEFAULT_PROVIDER → ai.default_provider
        YUAN_BOT__DEBUG → debug
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

        # 支持双下划线分隔的环境变量 (YUAN_BOT__AI__DEFAULT_PROVIDER)
        for env_key, env_val in os.environ.items():
            if not env_key.startswith("YUAN_BOT__"):
                continue
            parts = env_key[len("YUAN_BOT__") :].lower().split("__")
            _set_nested(result, parts, env_val)

        return result

    # -- 内部方法 --

    def _load_yaml(self, relative_path: str) -> dict[str, Any]:
        """加载 YAML 配置文件（带缓存）"""
        if relative_path in self._cache:
            return self._cache[relative_path]

        file_path = self._config_dir / relative_path
        data = _load_yaml_file(file_path)
        self._cache[relative_path] = data
        return data

    def clear_cache(self) -> None:
        """清除配置缓存"""
        self._cache.clear()


def _set_nested(d: dict, keys: list[str], value: Any) -> None:
    """在嵌套字典中设置值

    _set_nested({"a": {"b": 1}}, ["a", "b"], 2)
    → {"a": {"b": 2}}
    """
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    # 尝试保持类型一致
    existing = d.get(keys[-1])
    if isinstance(existing, bool):
        value = value.lower() in ("true", "1", "yes")  # type: ignore[assignment]
    elif isinstance(existing, int):
        with contextlib.suppress(ValueError):
            value = int(value)  # type: ignore[assignment]
    elif isinstance(existing, float):
        with contextlib.suppress(ValueError):
            value = float(value)  # type: ignore[assignment]
    d[keys[-1]] = value


# ---------------------------------------------------------------------------
# 向后兼容层 - 旧的 YuanBotConfig 和 load_config()
# ---------------------------------------------------------------------------


class AIProviderConfig(BaseModel):
    """AI 提供商配置 (向后兼容)"""

    provider_id: str = "openai"
    api_key: str | None = None
    base_url: str | None = None
    default_model: str = "gpt-5.4"


class ChannelProviderConfig(BaseModel):
    """消息通道配置 (向后兼容)"""

    platform: str
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class MemoryConfig(BaseModel):
    """记忆系统配置 (向后兼容)"""

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
    consolidation_threshold: int = 3


class ProactiveConfig(BaseModel):
    """主动交互配置 (向后兼容)"""

    enabled: bool = True
    greeting_enabled: bool = True
    frequency: str = "medium"
    quiet_hours_start: int = 23
    quiet_hours_end: int = 8
    max_per_day: int = 5
    event_triggers_enabled: bool = True


class YuanBotConfig(BaseModel):
    """YuanBot 主配置 (向后兼容)

    内部使用新的 ConfigLoader 加载，但对外接口保持不变。
    """

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

    支持两种模式：
    1. 传统单文件模式：传入 config_path 指向单个 YAML 文件
    2. 目录模式：传入 config_path 指向 configs/ 目录（或自动检测）

    向后兼容：始终返回 YuanBotConfig 实例。
    """
    # 加载 .env 文件
    if env_file:
        load_dotenv(env_file)
    else:
        load_dotenv()

    config_data: dict[str, Any] = {}

    if config_path:
        path = Path(config_path)
        if path.is_dir():
            # 目录模式：使用 ConfigLoader
            loader = ConfigLoader(path)
            config_data = _load_from_directory(loader)
        elif path.is_file():
            # 传统单文件模式
            config_data = _load_yaml_file(path)
    else:
        # 自动检测：如果 configs/ 目录存在，使用目录模式
        default_dir = Path("configs")
        if default_dir.exists() and (default_dir / "bot.yaml").exists():
            loader = ConfigLoader(default_dir)
            config_data = _load_from_directory(loader)

    # 环境变量覆盖（兼容旧的环境变量名）
    env_overrides = _load_env_overrides()
    config_data = _deep_merge(config_data, env_overrides)

    return YuanBotConfig(**config_data)


def _load_from_directory(loader: ConfigLoader) -> dict[str, Any]:
    """从 configs/ 目录加载并转换为 YuanBotConfig 兼容格式"""
    bot = loader.load_bot_config()
    providers = loader.load_provider_configs()
    channels = loader.load_channel_configs()
    db = loader.load_database_config()
    mem = loader.load_memory_config()

    # 找到默认 provider
    default_provider_id = bot.ai.default_provider
    default_provider = providers.get(default_provider_id)

    # 构建 ai_provider 兼容格式
    ai_provider: dict[str, Any] = {
        "provider_id": default_provider_id,
        "default_model": bot.ai.default_model,
    }
    if default_provider:
        provider_cfg = default_provider.config
        if provider_cfg.get("api_key"):
            ai_provider["api_key"] = provider_cfg["api_key"]
        if provider_cfg.get("base_url"):
            ai_provider["base_url"] = provider_cfg["base_url"]

    # 构建 channels 兼容格式
    channel_list = [
        {
            "platform": ch.platform,
            "enabled": ch.enabled,
            "config": ch.config,
        }
        for ch in channels.values()
    ]

    # 构建 memory 兼容格式
    memory: dict[str, Any] = {
        "max_working_memory_turns": mem.working_memory.max_turns,
        "episodic_memory_max_age_days": mem.episodic_memory.max_age_days,
        "forget_curve_half_life_days": mem.forgetting_curve.half_life_days,
        "consolidation_threshold": mem.consolidation.threshold,
        "redis_url": db.redis.url,
    }

    # 根据数据库类型设置 db_url
    rel = db.relational
    if rel.type == "mysql":
        m = rel.mysql
        memory["db_url"] = f"mysql+pymysql://{m.user}:{m.password}@{m.host}:{m.port}/{m.database}"
        memory["vector_db"] = "milvus"
    else:
        memory["db_url"] = f"sqlite:///{rel.sqlite.path}"
        memory["vector_db"] = "milvus_lite"

    memory["vector_db_url"] = (
        f"http://{db.vector.milvus.host}:{db.vector.milvus.port}"
        if db.vector.type == "milvus"
        else db.vector.milvus_lite.persist_dir
    )
    memory["graph_db"] = db.graph.type
    memory["graph_db_url"] = (
        db.graph.neo4j.uri if db.graph.type == "neo4j" else db.graph.kuzu.persist_dir
    )

    # 构建 proactive 兼容格式
    proactive: dict[str, Any] = {
        "enabled": bot.proactive.enabled,
        "greeting_enabled": bot.proactive.greeting_enabled,
        "frequency": bot.proactive.frequency,
        "quiet_hours_start": bot.proactive.quiet_hours.start,
        "quiet_hours_end": bot.proactive.quiet_hours.end,
        "max_per_day": bot.proactive.max_per_day,
        "event_triggers_enabled": bot.proactive.event_triggers_enabled,
    }

    return {
        "app_name": bot.app_name,
        "version": bot.version,
        "debug": bot.debug,
        "log_level": bot.log_level,
        "ai_provider": ai_provider,
        "channels": channel_list,
        "memory": memory,
        "proactive": proactive,
        "persona_id": bot.persona.id,
        "persona_config_path": bot.persona.config_path,
    }


def _load_env_overrides() -> dict[str, Any]:
    """从环境变量加载配置覆盖 (兼容旧环境变量名)"""
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
