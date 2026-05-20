"""YuanBot CLI - 命令行工具

命令列表:
    yuanbot start          启动 YuanBot 服务
    yuanbot doctor         检查系统组件连通性
    yuanbot config show    显示当前配置
    yuanbot config init    初始化配置目录
    yuanbot memory stats   显示记忆统计
    yuanbot memory clear   清除用户记忆
    yuanbot version        显示版本信息
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import structlog

# ANSI 颜色辅助
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def _c(text: str, color: str) -> str:
    """为终端输出着色（非 TTY 时自动跳过）"""
    if not sys.stderr.isatty():
        return text
    return f"{color}{text}{_RESET}"


def _header(title: str) -> None:
    print(f"\n{_c('🌸 缘·Bot (YuanBot)', _CYAN + _BOLD)} — {title}\n")


def _ok(msg: str) -> None:
    print(f"  {_c('✅', '')} {msg}")


def _fail(msg: str) -> None:
    print(f"  {_c('❌', '')} {_c(msg, _RED)}")


def _warn(msg: str) -> None:
    print(f"  {_c('⚠️', '')} {_c(msg, _YELLOW)}")


def _info(msg: str) -> None:
    print(f"  {_c('ℹ️', '')} {msg}")


# --------------------------------------------------------------------------- #
# CLI 入口
# --------------------------------------------------------------------------- #


def main() -> None:
    """CLI 主入口"""
    parser = argparse.ArgumentParser(
        prog="yuanbot",
        description="缘·Bot (YuanBot) - AI 虚拟伴侣系统",
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # yuanbot start
    start_parser = subparsers.add_parser("start", help="启动 YuanBot 服务")
    start_parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认 0.0.0.0)")
    start_parser.add_argument("--port", type=int, default=8000, help="监听端口 (默认 8000)")
    start_parser.add_argument("--config", help="配置文件/目录路径")
    start_parser.add_argument("--reload", action="store_true", help="开发模式：代码变更自动重载")

    # yuanbot doctor
    subparsers.add_parser("doctor", help="检查系统组件连通性")

    # yuanbot config
    config_parser = subparsers.add_parser("config", help="配置管理")
    config_sub = config_parser.add_subparsers(dest="config_action")
    config_sub.add_parser("show", help="显示当前配置")
    config_sub.add_parser("init", help="初始化配置目录")

    # yuanbot memory
    memory_parser = subparsers.add_parser("memory", help="记忆管理")
    memory_sub = memory_parser.add_subparsers(dest="memory_action")
    memory_sub.add_parser("stats", help="显示记忆统计")
    clear_parser = memory_sub.add_parser("clear", help="清除指定用户记忆")
    clear_parser.add_argument("--user-id", required=True, help="目标用户 ID")

    # yuanbot version
    subparsers.add_parser("version", help="显示版本信息")

    args = parser.parse_args()

    # 配置日志
    structlog.configure(
        processors=[
            structlog.dev.ConsoleRenderer()
            if sys.stderr.isatty()
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            structlog.get_config().get("log_level", 20)
        ),
    )

    if args.command == "start":
        _run_start(args)
    elif args.command == "doctor":
        _run_doctor(args)
    elif args.command == "config":
        if args.config_action == "show":
            _run_config_show(args)
        elif args.config_action == "init":
            _run_config_init(args)
        else:
            parser.parse_args(["config", "--help"])
    elif args.command == "memory":
        if args.memory_action == "stats":
            _run_memory_stats(args)
        elif args.memory_action == "clear":
            _run_memory_clear(args)
        else:
            parser.parse_args(["memory", "--help"])
    elif args.command == "version":
        _run_version()
    else:
        parser.print_help()


# --------------------------------------------------------------------------- #
# yuanbot start
# --------------------------------------------------------------------------- #


def _run_start(args: argparse.Namespace) -> None:
    """启动 FastAPI 服务"""
    import uvicorn

    from yuanbot import __version__
    from yuanbot.config import load_config

    config_path = args.config
    config = load_config(config_path)

    _header("启动中...")
    print(f"  版本:     {_c('v' + __version__, _BOLD)}")
    print(f"  地址:     {_c(f'{args.host}:{args.port}', _CYAN)}")
    print(f"  AI 提供商: {config.ai_provider.provider_id}")
    print(f"  调试模式:  {'开' if config.debug else '关'}")
    print(f"  热重载:    {'开' if args.reload else '关'}")
    print()

    from yuanbot.app import create_app

    app = create_app(config)

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=config.log_level.lower(),
    )


# --------------------------------------------------------------------------- #
# yuanbot doctor
# --------------------------------------------------------------------------- #


def _run_doctor(args: argparse.Namespace) -> None:
    """检查系统组件连通性"""
    _header("系统诊断")

    from yuanbot.config import load_config

    config = load_config()

    all_ok = True

    # 1. Python 版本
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    _ok(f"Python {py_ver}")

    # 2. AI 提供商连通性
    provider_id = config.ai_provider.provider_id
    api_key = config.ai_provider.api_key
    if api_key:
        _ok(f"AI 提供商 [{provider_id}] API Key 已配置")
        # 尝试简单连通性检查
        try:
            if provider_id == "openai":
                import openai  # noqa: F401

                _ok("openai 库已安装")
            elif provider_id == "anthropic":
                import anthropic  # noqa: F401

                _ok("anthropic 库已安装")
        except ImportError:
            _warn(f"{provider_id} Python 库未安装 (pip install yuanbot[{provider_id}])")
    else:
        _warn(f"AI 提供商 [{provider_id}] API Key 未配置")
        all_ok = False

    # 3. Redis 连通性
    redis_url = config.memory.redis_url
    try:
        import redis

        r = redis.from_url(redis_url, socket_connect_timeout=3)
        r.ping()
        _ok(f"Redis 连接正常 ({redis_url})")
    except ImportError:
        _warn("redis 库未安装")
    except Exception as e:
        _fail(f"Redis 连接失败: {e}")
        all_ok = False

    # 4. 数据库连通性
    db_url = config.memory.db_url
    if db_url.startswith("sqlite"):
        _ok(f"SQLite 数据库 ({db_url})")
    elif "postgresql" in db_url or "mysql" in db_url:
        try:
            import asyncpg  # noqa: F401

            _ok("asyncpg 库已安装")
        except ImportError:
            _warn("asyncpg 库未安装 (仅 SQLite 无需额外依赖)")

    # 5. 配置文件
    configs_dir = Path("configs")
    if configs_dir.exists():
        yaml_count = len(list(configs_dir.rglob("*.yaml")))
        _ok(f"配置目录 configs/ ({yaml_count} 个 YAML 文件)")
    else:
        _warn("配置目录 configs/ 不存在 (运行 yuanbot config init 初始化)")

    # 6. 依赖检查
    optional_deps = {
        "openai": "openai",
        "anthropic": "anthropic",
        "yaml": "pyyaml",
        "dotenv": "python-dotenv",
    }
    for name, package in optional_deps.items():
        try:
            __import__(name)
            _ok(f"依赖 {package} ✓")
        except ImportError:
            _warn(f"依赖 {package} 未安装")

    print()
    if all_ok:
        print(f"  {_c('🎉 系统状态良好！', _GREEN + _BOLD)}")
    else:
        print(f"  {_c('⚠️  部分组件存在问题，请检查上方输出', _YELLOW + _BOLD)}")
    print()


# --------------------------------------------------------------------------- #
# yuanbot config show
# --------------------------------------------------------------------------- #


def _run_config_show(args: argparse.Namespace) -> None:
    """显示当前配置"""
    _header("当前配置")

    from yuanbot.config import ConfigLoader, load_config

    config = load_config()

    print(f"  {_c('应用名称:', _BOLD)} {config.app_name}")
    print(f"  {_c('版本:', _BOLD)} {config.version}")
    print(f"  {_c('调试模式:', _BOLD)} {config.debug}")
    print(f"  {_c('日志级别:', _BOLD)} {config.log_level}")
    print()

    print(f"  {_c('AI 提供商:', _BOLD)}")
    print(f"    提供商: {config.ai_provider.provider_id}")
    print(f"    模型:   {config.ai_provider.default_model}")
    print(f"    API Key: {'已配置' if config.ai_provider.api_key else '未配置'}")
    if config.ai_provider.base_url:
        print(f"    Base URL: {config.ai_provider.base_url}")
    print()

    print(f"  {_c('消息通道:', _BOLD)}")
    if config.channels:
        for ch in config.channels:
            status = "✅ 启用" if ch.enabled else "❌ 禁用"
            print(f"    - {ch.platform}: {status}")
    else:
        print("    (无通道配置)")
    print()

    print(f"  {_c('记忆系统:', _BOLD)}")
    print(f"    向量数据库: {config.memory.vector_db}")
    print(f"    关系数据库: {config.memory.db_url}")
    print(f"    Redis:      {config.memory.redis_url}")
    print(f"    图数据库:   {config.memory.graph_db}")
    print()

    print(f"  {_c('主动交互:', _BOLD)}")
    print(f"    启用: {'是' if config.proactive.enabled else '否'}")
    print(f"    频率: {config.proactive.frequency}")
    start_h = config.proactive.quiet_hours_start
    end_h = config.proactive.quiet_hours_end
    print(f"    安静时段: {start_h}:00 - {end_h}:00")
    print(f"    每日上限: {config.proactive.max_per_day}")
    print()

    # 显示 configs/ 目录下的提供商
    configs_dir = Path("configs")
    if configs_dir.exists():
        loader = ConfigLoader(configs_dir)
        providers = loader.load_provider_configs()
        if providers:
            print(f"  {_c('已注册的 AI 提供商:', _BOLD)}")
            for pid, entry in providers.items():
                default_mark = " (默认)" if entry.default else ""
                enabled_mark = "✅" if entry.enabled else "❌"
                models = ", ".join(m.id for m in entry.models[:3])
                if len(entry.models) > 3:
                    models += f" ... (+{len(entry.models) - 3})"
                print(f"    {enabled_mark} {entry.display_name or pid}{default_mark}: {models}")

        channels = loader.load_channel_configs()
        if channels:
            print(f"\n  {_c('已注册的通道:', _BOLD)}")
            for name, entry in channels.items():
                enabled_mark = "✅" if entry.enabled else "❌"
                print(f"    {enabled_mark} {entry.display_name or name} ({entry.platform})")
    print()


# --------------------------------------------------------------------------- #
# yuanbot config init
# --------------------------------------------------------------------------- #


def _run_config_init(args: argparse.Namespace) -> None:
    """初始化配置目录结构"""
    _header("初始化配置目录")

    configs_dir = Path("configs")
    if configs_dir.exists():
        existing = len(list(configs_dir.rglob("*.yaml")))
        if existing > 0:
            _warn(f"configs/ 目录已存在 ({existing} 个配置文件)")
            answer = input("  是否覆盖？(y/N): ").strip().lower()
            if answer not in ("y", "yes"):
                _info("已取消")
                return

    # 创建目录结构
    configs_dir.mkdir(parents=True, exist_ok=True)
    (configs_dir / "Providers").mkdir(exist_ok=True)
    (configs_dir / "Channels").mkdir(exist_ok=True)

    # bot.yaml
    bot_yaml = configs_dir / "bot.yaml"
    bot_yaml.write_text(_BOT_YAML_TEMPLATE, encoding="utf-8")
    _ok("configs/bot.yaml")

    # database.yaml
    db_yaml = configs_dir / "database.yaml"
    db_yaml.write_text(_DATABASE_YAML_TEMPLATE, encoding="utf-8")
    _ok("configs/database.yaml")

    # memory.yaml
    mem_yaml = configs_dir / "memory.yaml"
    mem_yaml.write_text(_MEMORY_YAML_TEMPLATE, encoding="utf-8")
    _ok("configs/memory.yaml")

    # Providers
    for name, content in _PROVIDER_TEMPLATES.items():
        p = configs_dir / "Providers" / f"{name}.yaml"
        p.write_text(content, encoding="utf-8")
        _ok(f"configs/Providers/{name}.yaml")

    # Channels
    for name, content in _CHANNEL_TEMPLATES.items():
        p = configs_dir / "Channels" / f"{name}.yaml"
        p.write_text(content, encoding="utf-8")
        _ok(f"configs/Channels/{name}.yaml")

    # data 和 logs 目录
    Path("data").mkdir(exist_ok=True)
    Path("logs").mkdir(exist_ok=True)
    _ok("data/ 目录")
    _ok("logs/ 目录")

    print()
    print(f"  {_c('🎉 配置目录初始化完成！', _GREEN + _BOLD)}")
    print(f"  请编辑 {_c('configs/Providers/openai.yaml', _CYAN)} 填入你的 API Key")
    print()


# --------------------------------------------------------------------------- #
# yuanbot memory stats
# --------------------------------------------------------------------------- #


def _run_memory_stats(args: argparse.Namespace) -> None:
    """显示记忆系统统计"""
    _header("记忆统计")

    from yuanbot.config import load_config
    from yuanbot.memory.manager import MemoryManager

    config = load_config()
    manager = MemoryManager(config=config.memory.model_dump())

    # 全局统计
    working_sessions = len(manager._working_memories)
    total_facts = sum(len(v) for v in manager._fact_memories.values())
    total_episodic = sum(len(v) for v in manager._episodic_memories.values())
    total_semantic = sum(len(v) for v in manager._semantic_memories.values())
    total_users = len(
        set(
            list(manager._fact_memories.keys())
            + list(manager._episodic_memories.keys())
            + list(manager._semantic_memories.keys())
        )
    )
    total_emotion_records = sum(len(v) for v in manager._emotion_tracker._records.values())

    print(f"  {_c('全局统计:', _BOLD)}")
    print(f"    活跃会话 (工作记忆):  {working_sessions}")
    print(f"    注册用户:             {total_users}")
    print(f"    事实记忆总数:         {total_facts}")
    print(f"    情景记忆总数:         {total_episodic}")
    print(f"    语义记忆总数:         {total_semantic}")
    print(f"    情感记录总数:         {total_emotion_records}")
    print()

    # 逐用户统计
    all_user_ids = set(
        list(manager._fact_memories.keys())
        + list(manager._episodic_memories.keys())
        + list(manager._semantic_memories.keys())
        + list(manager._user_profiles.keys())
    )

    if all_user_ids:
        print(f"  {_c('用户明细:', _BOLD)}")
        for uid in sorted(all_user_ids):
            facts = len(manager._fact_memories.get(uid, []))
            episodic = len(manager._episodic_memories.get(uid, []))
            semantic = len(manager._semantic_memories.get(uid, []))
            emotions = len(manager._emotion_tracker._records.get(uid, []))
            profile = manager._user_profiles.get(uid)
            stage = profile.relationship_stage if profile else "unknown"
            print(
                f"    {uid}: 事实={facts} 情景={episodic} 语义={semantic} "
                f"情感={emotions} 关系={stage}"
            )
    else:
        print(f"  {_c('(暂无用户数据)', _DIM)}")
    print()


# --------------------------------------------------------------------------- #
# yuanbot memory clear
# --------------------------------------------------------------------------- #


def _run_memory_clear(args: argparse.Namespace) -> None:
    """清除指定用户的记忆"""
    _header("清除用户记忆")

    user_id = args.user_id
    from yuanbot.config import load_config
    from yuanbot.memory.manager import MemoryManager

    config = load_config()
    manager = MemoryManager(config=config.memory.model_dump())

    # 统计待清除的记忆
    facts = len(manager._fact_memories.get(user_id, []))
    episodic = len(manager._episodic_memories.get(user_id, []))
    semantic = len(manager._semantic_memories.get(user_id, []))
    emotions = len(manager._emotion_tracker._records.get(user_id, []))
    total = facts + episodic + semantic + emotions

    if total == 0:
        _info(f"用户 {user_id} 没有记忆数据")
        return

    print(f"  用户: {_c(user_id, _BOLD)}")
    print(f"  事实记忆: {facts}")
    print(f"  情景记忆: {episodic}")
    print(f"  语义记忆: {semantic}")
    print(f"  情感记录: {emotions}")
    print(f"  总计: {total}")
    print()

    answer = input(f"  确认清除用户 {user_id} 的全部记忆？(y/N): ").strip().lower()
    if answer not in ("y", "yes"):
        _info("已取消")
        return

    # 清除各类记忆
    manager._fact_memories.pop(user_id, None)
    manager._episodic_memories.pop(user_id, None)
    manager._semantic_memories.pop(user_id, None)
    manager._emotion_tracker._records.pop(user_id, None)
    manager._emotion_tracker._patterns.pop(user_id, None)
    manager._user_profiles.pop(user_id, None)

    _ok(f"已清除用户 {user_id} 的 {total} 条记忆")
    print()


# --------------------------------------------------------------------------- #
# yuanbot version
# --------------------------------------------------------------------------- #


def _run_version() -> None:
    from yuanbot import __version__

    print(f"缘·Bot (YuanBot) v{__version__}")


# --------------------------------------------------------------------------- #
# 配置模板
# --------------------------------------------------------------------------- #

_BOT_YAML_TEMPLATE = """\
# YuanBot 根配置 (bot.yaml)
# 配置加载优先级: 环境变量 > 配置文件 > 默认值

app_name: "YuanBot"
version: "1.0.0"
debug: false
log_level: "INFO"

# AI 提供商
ai:
  default_provider: "openai"
  default_model: "gpt-4o"

# 消息通道
channels:
  default_channel: "webchat"

# Agent 人设
persona:
  id: "default"
  config_path: null

# 主动交互
proactive:
  enabled: true
  greeting_enabled: true
  frequency: "medium"  # high | medium | low | event_only
  quiet_hours:
    start: 23
    end: 8
  max_per_day: 5
  event_triggers_enabled: true

# 编排引擎
orchestrator:
  intent_engine:
    enabled: true
    confidence_threshold: 0.7
  emotion_engine:
    enabled: true
    decay_rate: 0.1
  token_budget:
    max_input_tokens: 8000
    max_output_tokens: 2000
    reserved_for_memory: 2000
"""

_DATABASE_YAML_TEMPLATE = """\
# 数据库配置 (database.yaml)
# 支持 SQLite (默认) / MySQL 切换

# 关系型数据库
relational:
  type: "sqlite"  # sqlite | mysql
  sqlite:
    path: "data/yuanbot.db"
  mysql:
    host: "localhost"
    port: 3306
    database: "yuanbot"
    user: "yuanbot"
    password: "${YUAN_DB_MYSQL_PASSWORD}"
    pool_size: 10

# 向量数据库 (Milvus Lite)
vector:
  type: "milvus_lite"  # milvus_lite | milvus
  milvus_lite:
    persist_dir: "data/milvus"
  milvus:
    host: "localhost"
    port: 19530

# 缓存
redis:
  url: "redis://localhost:6379/0"
  max_connections: 20

# 图数据库
graph:
  type: "kuzu"  # kuzu | neo4j
  kuzu:
    persist_dir: "data/kuzu"
  neo4j:
    uri: "bolt://localhost:7687"
    user: "neo4j"
    password: "${YUAN_DB_NEO4J_PASSWORD}"
"""

_MEMORY_YAML_TEMPLATE = """\
# 记忆系统参数 (memory.yaml)

# 工作记忆
working_memory:
  max_turns: 20
  redis_ttl_seconds: 3600

# 事实记忆
fact_memory:
  max_entries_per_user: 1000
  importance_threshold: 0.3

# 情景记忆
episodic_memory:
  max_age_days: 90
  summary_max_length: 500
  embedding_batch_size: 32

# 遗忘曲线
forgetting_curve:
  enabled: true
  half_life_days: 14
  min_retention_score: 0.1
  review_interval_days: 7

# 记忆固化
consolidation:
  enabled: true
  threshold: 3
  schedule: "0 3 * * *"
  batch_size: 100

# 语义记忆
semantic_memory:
  graph_update_on_interaction: true
  relationship_depth: 3
"""

_PROVIDER_TEMPLATES: dict[str, str] = {
    "openai": """\
# OpenAI 提供商配置
provider_id: "openai"
display_name: "OpenAI"
enabled: true
default: true

api:
  base_url: "https://api.openai.com/v1"
  api_key: "${YUAN_AI_API_KEY}"
  timeout: 60
  max_retries: 3

models:
  - id: "gpt-4o"
    type: "chat"
    default: true
    max_tokens: 128000
    supports_tools: true
    supports_streaming: true
  - id: "gpt-4o-mini"
    type: "chat"
    default: false
    max_tokens: 128000
    supports_tools: true
    supports_streaming: true
  - id: "text-embedding-3-small"
    type: "embedding"
    dimensions: 1536
""",
    "deepseek": """\
# DeepSeek 提供商配置
provider_id: "deepseek"
display_name: "DeepSeek"
enabled: false
default: false

api:
  base_url: "https://api.deepseek.com/v1"
  api_key: "${DEEPSEEK_API_KEY}"
  timeout: 60
  max_retries: 3

models:
  - id: "deepseek-chat"
    type: "chat"
    default: true
    max_tokens: 64000
    supports_tools: true
    supports_streaming: true
""",
    "claude": """\
# Anthropic Claude 提供商配置
provider_id: "anthropic"
display_name: "Anthropic Claude"
enabled: false
default: false

api:
  base_url: "https://api.anthropic.com"
  api_key: "${ANTHROPIC_API_KEY}"
  timeout: 60
  max_retries: 3

models:
  - id: "claude-sonnet-4-20250514"
    type: "chat"
    default: true
    max_tokens: 200000
    supports_tools: true
    supports_streaming: true
""",
    "ollama": """\
# Ollama 本地模型配置
provider_id: "ollama"
display_name: "Ollama (本地)"
enabled: false
default: false

api:
  base_url: "http://localhost:11434"
  api_key: null
  timeout: 120
  max_retries: 1

models:
  - id: "qwen2.5:7b"
    type: "chat"
    default: true
    max_tokens: 32000
    supports_tools: true
    supports_streaming: true
""",
}

_CHANNEL_TEMPLATES: dict[str, str] = {
    "webchat": """\
# Web Chat 通道配置
platform: "webchat"
display_name: "Web Chat"
enabled: true
config: {}
""",
    "telegram": """\
# Telegram 通道配置
platform: "telegram"
display_name: "Telegram Bot"
enabled: false
config:
  bot_token: "${TELEGRAM_BOT_TOKEN}"
""",
    "discord": """\
# Discord 通道配置
platform: "discord"
display_name: "Discord Bot"
enabled: false
config:
  bot_token: "${DISCORD_BOT_TOKEN}"
  public_key: "${DISCORD_PUBLIC_KEY}"
""",
    "wecom": """\
# 企业微信通道配置
platform: "wecom"
display_name: "企业微信"
enabled: false
config:
  corp_id: "${WECOM_CORP_ID}"
  corp_secret: "${WECOM_CORP_SECRET}"
  agent_id: "${WECOM_AGENT_ID}"
""",
}


if __name__ == "__main__":
    main()
