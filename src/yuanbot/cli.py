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
import os
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

    # yuanbot tui
    tui_parser = subparsers.add_parser("tui", help="启动终端聊天界面")
    tui_parser.add_argument("--host", default="http://localhost:8000", help="后端地址")
    tui_parser.add_argument("--token", default=None, help="JWT Token")
    tui_parser.add_argument("--api-key", default=None, help="API Key")

    # yuanbot webui
    webui_parser = subparsers.add_parser("webui", help="启动 WebUI 服务")
    webui_parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    webui_parser.add_argument("--port", type=int, default=3000, help="监听端口 (默认 3000)")
    webui_parser.add_argument("--backend", default="http://localhost:8000", help="后端 API 地址")

    # yuanbot logs
    logs_parser = subparsers.add_parser("logs", help="查看实时日志")
    logs_parser.add_argument("--follow", "-f", action="store_true", help="持续输出新日志")
    logs_parser.add_argument("--lines", "-n", type=int, default=50, help="显示行数 (默认 50)")
    logs_parser.add_argument(
        "--level",
        choices=["debug", "info", "warning", "error"],
        help="过滤日志级别",
    )

    # yuanbot list
    list_parser = subparsers.add_parser("list", help="列出已安装的扩展")
    list_sub = list_parser.add_subparsers(dest="list_target")
    list_sub.add_parser("channels", help="列出通道")
    list_sub.add_parser("providers", help="列出提供商")
    list_sub.add_parser("plugins", help="列出插件 (Skills/Tools)")

    # yuanbot config edit
    config_edit_parser = config_sub.add_parser("edit", help="在默认编辑器中打开配置文件")
    config_edit_parser.add_argument(
        "file", nargs="?", default="bot.yaml", help="配置文件名 (默认 bot.yaml)"
    )

    # yuanbot provider
    provider_parser = subparsers.add_parser("provider", help="AI 提供商管理")
    provider_sub = provider_parser.add_subparsers(dest="provider_action")
    provider_sub.add_parser("list", help="列出所有已配置的提供商")
    info_parser = provider_sub.add_parser("info", help="显示提供商详细信息")
    info_parser.add_argument("provider_id", help="提供商 ID")
    set_parser = provider_sub.add_parser("set", help="设置默认提供商")
    set_parser.add_argument("target", choices=["default", "embedding"], help="设置目标")
    set_parser.add_argument("provider_id", help="提供商 ID")
    create_parser = provider_sub.add_parser("create", help="交互式创建新的 Provider 配置")
    create_parser.add_argument("--id", help="Provider ID")
    create_parser.add_argument(
        "--adapter", default="openai-adapter", help="适配器 (默认 openai-adapter)"
    )
    create_parser.add_argument("--base-url", help="API Base URL")
    create_parser.add_argument("--name", help="显示名称")

    # yuanbot create
    create_parser = subparsers.add_parser("create", help="创建扩展项目")
    create_parser.add_argument(
        "--type",
        required=True,
        choices=["ai_provider", "channel", "skill", "tool", "persona", "trigger"],
        help="扩展类型",
    )
    create_parser.add_argument("--name", help="扩展名称")
    create_parser.add_argument("--output-dir", default=".", help="输出目录 (默认当前目录)")

    # yuanbot validate
    validate_parser = subparsers.add_parser("validate", help="验证扩展是否符合 Y.E.S. 规范")
    validate_parser.add_argument("path", nargs="?", default=".", help="扩展项目路径")

    # yuanbot test
    test_parser = subparsers.add_parser("test", help="在本地运行扩展测试")
    test_parser.add_argument("path", nargs="?", default=".", help="扩展项目路径")
    test_parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")

    # yuanbot build
    build_parser = subparsers.add_parser("build", help="打包扩展为 .yuanbot 文件")
    build_parser.add_argument("path", nargs="?", default=".", help="扩展项目路径")
    build_parser.add_argument("--output", "-o", help="输出文件路径")

    # yuanbot publish
    publish_parser = subparsers.add_parser("publish", help="发布扩展到社区市场")
    publish_parser.add_argument("path", nargs="?", default=".", help="扩展项目路径")
    publish_parser.add_argument("--dry-run", action="store_true", help="仅验证，不实际发布")

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
        elif args.config_action == "edit":
            _run_config_edit(args)
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
    elif args.command == "tui":
        _run_tui(args)
    elif args.command == "webui":
        _run_webui(args)
    elif args.command == "logs":
        _run_logs(args)
    elif args.command == "list":
        if args.list_target == "channels":
            _run_list_channels(args)
        elif args.list_target == "providers":
            _run_provider_list(args)
        elif args.list_target == "plugins":
            _run_list_plugins(args)
        else:
            parser.parse_args(["list", "--help"])
    elif args.command == "provider":
        if args.provider_action == "list":
            _run_provider_list(args)
        elif args.provider_action == "info":
            _run_provider_info(args)
        elif args.provider_action == "set":
            _run_provider_set(args)
        elif args.provider_action == "create":
            _run_provider_create(args)
        else:
            parser.parse_args(["provider", "--help"])
    elif args.command == "create":
        _run_create(args)
    elif args.command == "validate":
        _run_validate(args)
    elif args.command == "test":
        _run_test(args)
    elif args.command == "build":
        _run_build(args)
    elif args.command == "publish":
        _run_publish(args)
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
# yuanbot tui
# --------------------------------------------------------------------------- #


def _run_tui(args: argparse.Namespace) -> None:
    """启动 TUI 终端聊天界面"""
    from yuanbot.tui.app import run_tui

    run_tui(host=args.host, token=args.token, api_key=args.api_key)


# --------------------------------------------------------------------------- #
# yuanbot provider
# --------------------------------------------------------------------------- #


def _run_provider_list(args: argparse.Namespace) -> None:
    """列出所有已配置的 AI 提供商"""
    _header("AI 提供商列表")

    from pathlib import Path

    from yuanbot.providers.manager import ProviderManager
    from yuanbot.providers.registry import ProviderRegistry

    manager = ProviderManager(
        registry=ProviderRegistry(),
        config_dir=Path("configs"),
    )
    manager.load_providers()

    providers = manager.list_providers()
    if not providers:
        _info("未找到任何 Provider 配置")
        _info("运行 yuanbot provider create 创建新配置")
        return

    # 表头
    print(
        f"  {_c('状态', _BOLD)}  {_c('Provider ID', _BOLD)}  "
        f"{_c('适配器', _BOLD)}  {_c('默认模型', _BOLD)}  "
        f"{_c('模型数', _BOLD)}  {_c('角色', _BOLD)}"
    )
    print("  " + "─" * 70)

    for p in providers:
        status = _c("✅", "") if p["enabled"] else _c("❌", "")
        roles = []
        if p["is_default"]:
            roles.append("默认")
        if p["is_embedding"]:
            roles.append("嵌入")
        role_str = ", ".join(roles) if roles else "-"
        default_model = p["default_model"] or "(未设置)"

        print(
            f"  {status}  {p['provider_id']:20s} {p['adapter']:20s} "
            f"{default_model:20s} {p['model_count']:5d}  {role_str}"
        )
    print()


def _run_provider_info(args: argparse.Namespace) -> None:
    """显示提供商详细信息"""
    _header(f"Provider 详情: {args.provider_id}")

    from pathlib import Path

    from yuanbot.providers.manager import ProviderManager
    from yuanbot.providers.registry import ProviderRegistry

    manager = ProviderManager(
        registry=ProviderRegistry(),
        config_dir=Path("configs"),
    )
    manager.load_providers()

    provider = manager.get_provider(args.provider_id)
    if not provider:
        _fail(f"Provider '{args.provider_id}' 未找到")
        _info(f"可用: {', '.join(p['provider_id'] for p in manager.list_providers())}")
        return

    print(f"  {_c('Provider ID:', _BOLD)} {provider.provider_id}")
    print(f"  {_c('显示名称:', _BOLD)} {provider.name}")
    print(f"  {_c('适配器:', _BOLD)} {provider.adapter}")
    print(f"  {_c('启用:', _BOLD)} {'是' if provider.enabled else '否'}")
    print(f"  {_c('默认模型:', _BOLD)} {provider.default_model or '(未设置)'}")
    print(f"  {_c('嵌入模型:', _BOLD)} {provider.embedding_model or '(未设置)'}")
    print()

    if provider.models:
        print(f"  {_c('模型列表:', _BOLD)}")
        for m in provider.models:
            emb_info = f" (维度: {m.dimension})" if m.dimension else ""
            print(f"    - {m.id}  类型: {m.type}  上下文: {m.max_tokens}{emb_info}")
    else:
        _info("无模型配置")
    print()

    # 显示 API 端点（脱敏）
    api_key = provider.config.get("api_key", "")
    base_url = provider.config.get("base_url", "")
    print(f"  {_c('API 端点:', _BOLD)} {base_url or '(未设置)'}")
    if api_key:
        # 日志脱敏：只显示前 8 位和后 4 位
        masked = _mask_secret(api_key)
        print(f"  {_c('API Key:', _BOLD)} {masked}")
    else:
        print(f"  {_c('API Key:', _BOLD)} (未设置)")
    print()


def _run_provider_set(args: argparse.Namespace) -> None:
    """设置默认提供商"""
    _header(f"设置{'默认' if args.target == 'default' else '嵌入'}提供商")

    from pathlib import Path

    from yaml import safe_dump

    from yuanbot.providers.manager import ProviderManager
    from yuanbot.providers.registry import ProviderRegistry

    manager = ProviderManager(
        registry=ProviderRegistry(),
        config_dir=Path("configs"),
    )
    manager.load_providers()

    provider = manager.get_provider(args.provider_id)
    if not provider:
        _fail(f"Provider '{args.provider_id}' 未找到")
        return

    if not provider.enabled:
        _warn(f"Provider '{args.provider_id}' 当前已禁用")

    # 更新 bot.yaml
    bot_yaml_path = Path("configs/bot.yaml")
    if not bot_yaml_path.exists():
        _fail("configs/bot.yaml 不存在")
        return

    import yaml

    with open(bot_yaml_path) as f:
        bot_config = yaml.safe_load(f) or {}

    if "ai" not in bot_config:
        bot_config["ai"] = {}

    if args.target == "default":
        bot_config["ai"]["default_provider"] = args.provider_id
        _ok(f"默认对话提供商已设置为: {args.provider_id}")
    else:
        bot_config["ai"]["embedding_provider"] = args.provider_id
        _ok(f"嵌入专用提供商已设置为: {args.provider_id}")

    with open(bot_yaml_path, "w") as f:
        safe_dump(bot_config, f, allow_unicode=True, default_flow_style=False)

    _info("配置已写入 configs/bot.yaml，重启后生效")
    print()


def _run_provider_create(args: argparse.Namespace) -> None:
    """交互式创建新的 Provider 配置"""
    _header("创建新 Provider")

    from pathlib import Path

    from yaml import safe_dump

    provider_id = args.id
    if not provider_id:
        provider_id = input("  ? Provider ID (如 my-llm): ").strip()
        if not provider_id:
            _fail("Provider ID 不能为空")
            return

    # 检查是否已存在
    provider_file = Path(f"configs/Providers/{provider_id}.yaml")
    if provider_file.exists():
        _fail(f"Provider '{provider_id}' 配置已存在: {provider_file}")
        return

    adapter = args.adapter
    name = args.name or provider_id
    base_url = args.base_url
    if not base_url:
        base_url = input("  ? API Base URL: ").strip()
        if not base_url:
            _fail("Base URL 不能为空")
            return

    default_model = input("  ? 默认模型 ID (如 gpt-4o): ").strip() or ""

    # 构建配置
    config = {
        "provider_id": provider_id,
        "name": name,
        "adapter": adapter,
        "enabled": True,
        "config": {
            "api_key": f"${{{provider_id.upper()}_API_KEY}}",
            "base_url": base_url,
            "models": [],
        },
    }

    if default_model:
        config["config"]["default"] = default_model
        config["config"]["models"].append({
            "id": default_model,
            "type": "chat",
            "max_tokens": 128000,
        })

    # 写入文件
    provider_file.parent.mkdir(parents=True, exist_ok=True)
    with open(provider_file, "w") as f:
        safe_dump(config, f, allow_unicode=True, default_flow_style=False)

    _ok(f"Provider 配置已创建: {provider_file}")
    _info(f"请设置环境变量 {provider_id.upper()}_API_KEY")
    _info("重启服务后生效")
    print()


def _mask_secret(secret: str) -> str:
    """脱敏显示密钥，只显示前 8 位和后 4 位"""
    if len(secret) <= 12:
        return "****"
    return f"{secret[:8]}...{secret[-4:]}"


# --------------------------------------------------------------------------- #
# yuanbot create
# --------------------------------------------------------------------------- #


_TYPE_PREFIXES = {
    "ai_provider": "yuanbot-ai-provider",
    "channel": "yuanbot-channel",
    "skill": "yuanbot-skill",
    "tool": "yuanbot-tool",
    "persona": "yuanbot-persona",
    "trigger": "yuanbot-trigger",
}

_TYPE_TEMPLATES: dict[str, dict[str, str]] = {
    "ai_provider": {
        "src/adapter.py": '    pass\n',
        "tests/test_adapter.py": 'import pytest\n\n\ndef test_placeholder():\n    assert True\n',
    },
    "channel": {
        "src/adapter.py": '    pass\n',
        "tests/test_adapter.py": 'import pytest\n\n\ndef test_placeholder():\n    assert True\n',
    },
    "skill": {
        "src/definition.yaml": '',
        "tests/test_skill.py": 'import pytest\n\n\ndef test_placeholder():\n    assert True\n',
    },
    "tool": {
        "src/executor.py": '    pass\n',
        "tests/test_tool.py": 'import pytest\n\n\ndef test_placeholder():\n    assert True\n',
    },
    "persona": {
        "src/persona.yaml": '',
    },
    "trigger": {
        "src/trigger.py": '    pass\n',
        "tests/test_trigger.py": 'import pytest\n\n\ndef test_placeholder():\n    assert True\n',
    },
}


def _run_create(args: argparse.Namespace) -> None:
    """创建扩展项目脚手架"""
    import json as _json

    ext_type = args.type
    prefix = _TYPE_PREFIXES[ext_type]

    name = args.name
    if not name:
        name = input(f"  ? {ext_type} 名称: ").strip()
        if not name:
            _fail("名称不能为空")
            return

    safe_name = name.replace("-", "_")
    dir_name = f"{prefix}-{safe_name}"
    output_dir = Path(args.output_dir)
    project_dir = output_dir / dir_name

    if project_dir.exists():
        _fail(f"目录已存在: {project_dir}")
        return

    _header(f"创建扩展: {dir_name}")

    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "src").mkdir(exist_ok=True)
    (project_dir / "tests").mkdir(exist_ok=True)

    manifest = {
        "$schema": "https://yuanbot.app/schemas/manifest-v1.json",
        "type": ext_type,
        "id": safe_name,
        "name": name,
        "version": "1.0.0",
        "author": {"name": "", "email": "", "url": ""},
        "description": f"TODO: {name} {ext_type} extension",
        "license": "MIT",
        "keywords": [],
        "yuanbot": {"min_core_version": "1.4.0"},
    }
    (project_dir / "manifest.json").write_text(
        _json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _ok("manifest.json")

    (project_dir / "README.md").write_text(
        f"# {name}\n\nTODO: Extension description\n",
        encoding="utf-8",
    )
    _ok("README.md")

    (project_dir / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    _ok("LICENSE")

    templates = _TYPE_TEMPLATES.get(ext_type, {})
    for rel_path, content_template in templates.items():
        content = content_template.format(name=safe_name, display_name=name)
        file_path = project_dir / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        _ok(rel_path)

    print()
    print(f"  {_c('🎉 扩展项目已创建！', _GREEN + _BOLD)}")
    print(f"  路径: {_c(str(project_dir), _CYAN)}")
    print(f"  下一步: cd {dir_name} && yuanbot test")
    print()


# --------------------------------------------------------------------------- #
# yuanbot validate
# --------------------------------------------------------------------------- #


def _run_validate(args: argparse.Namespace) -> None:
    """验证扩展是否符合 Y.E.S. 规范"""
    import json as _json

    _header("Y.E.S. 规范验证")

    project_dir = Path(args.path).resolve()
    all_ok = True

    manifest_path = project_dir / "manifest.json"
    if not manifest_path.exists():
        _fail("缺少 manifest.json")
        all_ok = False
    else:
        try:
            manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
            _ok("manifest.json 格式正确")

            required = ["type", "id", "name", "version", "description", "license"]
            for field_name in required:
                if field_name not in manifest:
                    _fail(f"manifest.json 缺少必需字段: {field_name}")
                    all_ok = False
                else:
                    _ok(f"manifest.{field_name} ✓")

            valid_types = ["ai_provider", "channel", "skill", "tool", "persona", "trigger"]
            mtype = manifest.get("type")
            if mtype and mtype not in valid_types:
                _fail(f"未知扩展类型: {mtype}")
                all_ok = False

        except _json.JSONDecodeError as e:
            _fail(f"manifest.json 解析失败: {e}")
            all_ok = False

    for fname in ["README.md", "LICENSE"]:
        if (project_dir / fname).exists():
            _ok(f"{fname} ✓")
        else:
            _fail(f"缺少 {fname}")
            all_ok = False

    src_dir = project_dir / "src"
    if src_dir.exists():
        total = len(list(src_dir.rglob("*.py"))) + len(list(src_dir.rglob("*.yaml")))
        if total > 0:
            _ok(f"src/ 包含 {total} 个源文件")
        else:
            _warn("src/ 目录为空")
    else:
        _fail("缺少 src/ 目录")
        all_ok = False

    print()
    if all_ok:
        print(f"  {_c('✅ 验证通过！扩展符合 Y.E.S. 规范', _GREEN + _BOLD)}")
    else:
        print(f"  {_c('❌ 验证失败，请修复上方问题', _RED + _BOLD)}")
    print()


# --------------------------------------------------------------------------- #
# yuanbot test
# --------------------------------------------------------------------------- #


def _run_test(args: argparse.Namespace) -> None:
    """在本地运行扩展测试"""
    import subprocess

    _header("运行扩展测试")

    project_dir = Path(args.path).resolve()
    tests_dir = project_dir / "tests"

    if not tests_dir.exists():
        _warn("tests/ 目录不存在，跳过测试")
        return

    test_files = list(tests_dir.rglob("test_*.py"))
    if not test_files:
        _warn("未找到测试文件")
        return

    _info(f"找到 {len(test_files)} 个测试文件")

    cmd = [sys.executable, "-m", "pytest", str(tests_dir)]
    if args.verbose:
        cmd.append("-v")
    else:
        cmd.extend(["-q", "--tb=short"])

    result = subprocess.run(cmd, cwd=str(project_dir))
    print()
    if result.returncode == 0:
        print(f"  {_c('✅ 测试通过！', _GREEN + _BOLD)}")
    else:
        print(f"  {_c('❌ 测试失败', _RED + _BOLD)}")
        sys.exit(result.returncode)


# --------------------------------------------------------------------------- #
# yuanbot build
# --------------------------------------------------------------------------- #


def _run_build(args: argparse.Namespace) -> None:
    """打包扩展为 .yuanbot 文件"""
    import json as _json
    import zipfile

    _header("打包扩展")

    project_dir = Path(args.path).resolve()
    manifest_path = project_dir / "manifest.json"
    if not manifest_path.exists():
        _fail("缺少 manifest.json")
        return

    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    ext_id = manifest.get("id", "unknown")
    ext_version = manifest.get("version", "0.0.0")

    output_path = Path(args.output) if args.output else Path(f"{ext_id}-{ext_version}.yuanbot")

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(project_dir.rglob("*")):
            if file_path.is_file():
                rel = file_path.relative_to(project_dir)
                if any(p.startswith(".") or p == "__pycache__" for p in rel.parts):
                    continue
                zf.write(file_path, str(rel))

    size_kb = output_path.stat().st_size / 1024
    _ok(f"已打包: {output_path} ({size_kb:.1f} KB)")
    print()
    print(f"  {_c('🎉 打包完成！', _GREEN + _BOLD)}")
    print()


# --------------------------------------------------------------------------- #
# yuanbot publish
# --------------------------------------------------------------------------- #


def _run_publish(args: argparse.Namespace) -> None:
    """发布扩展到社区市场"""
    import json as _json

    _header("发布扩展")

    project_dir = Path(args.path).resolve()
    manifest_path = project_dir / "manifest.json"
    if not manifest_path.exists():
        _fail("缺少 manifest.json，无法发布")
        return

    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    ext_id = manifest.get("id", "unknown")
    ext_version = manifest.get("version", "0.0.0")

    print(f"  {_c('扩展 ID:', _BOLD)} {ext_id}")
    print(f"  {_c('版本:', _BOLD)} {ext_version}")
    print(f"  {_c('类型:', _BOLD)} {manifest.get('type', 'unknown')}")
    print()

    if args.dry_run:
        _info("--dry-run 模式，仅验证不实际发布")
        validate_args = argparse.Namespace(path=str(project_dir))
        _run_validate(validate_args)
        return

    _warn("扩展市场功能尚未上线，请通过 GitHub PR 发布：")
    print()
    print("  1. Fork https://github.com/yuanbot-ai/yuanbot-extensions")
    print("  2. 将扩展目录复制到对应类型文件夹")
    print("  3. 提交 Pull Request")
    print()
    print(f"  {_c('文档: https://docs.yuanbot.app/marketplace/publish', _CYAN)}")
    print()


# --------------------------------------------------------------------------- #
# yuanbot webui
# --------------------------------------------------------------------------- #


def _run_webui(args: argparse.Namespace) -> None:
    """启动 WebUI 开发服务器"""
    import subprocess

    webui_dir = Path(__file__).parent.parent.parent / "webui"
    if not webui_dir.exists():
        _fail("webui/ 目录不存在")
        return

    if not (webui_dir / "node_modules").exists():
        _info("首次启动，安装依赖中...")
        subprocess.run(["npm", "install"], cwd=str(webui_dir), check=True)

    _header("启动 WebUI")
    print(f"  地址: {_c(f'{args.host}:{args.port}', _CYAN)}")
    print(f"  后端: {args.backend}")
    print()

    env = os.environ.copy()
    env["VITE_API_BASE"] = args.backend

    subprocess.run(
        ["npm", "run", "dev", "--", "--host", args.host, "--port", str(args.port)],
        cwd=str(webui_dir),
        env=env,
    )


# --------------------------------------------------------------------------- #
# yuanbot logs
# --------------------------------------------------------------------------- #


def _run_logs(args: argparse.Namespace) -> None:
    """查看实时日志"""
    logs_dir = Path("logs")
    if not logs_dir.exists():
        _fail("logs/ 目录不存在")
        return

    # 查找最新的日志文件
    log_files = sorted(logs_dir.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not log_files:
        _warn("未找到日志文件")
        return

    log_file = log_files[0]
    _header(f"日志: {log_file.name}")

    if args.follow:
        # tail -f 模式
        import subprocess

        cmd = ["tail", "-f", str(log_file)]
        if args.lines:
            cmd = ["tail", "-n", str(args.lines), "-f", str(log_file)]
        try:
            subprocess.run(cmd)
        except KeyboardInterrupt:
            print()
    else:
        # 显示最后 N 行
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        if args.level:
            level = args.level.upper()
            lines = [line for line in lines if level in line]
        for line in lines[-args.lines:]:
            print(f"  {line}")


# --------------------------------------------------------------------------- #
# yuanbot config edit
# --------------------------------------------------------------------------- #


def _run_config_edit(args: argparse.Namespace) -> None:
    """在默认编辑器中打开配置文件"""
    import os
    import subprocess

    file_name = args.file
    file_path = Path("configs") / file_name

    if not file_path.exists():
        _fail(f"配置文件不存在: {file_path}")
        _info("运行 yuanbot config init 初始化配置目录")
        return

    editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "vi"))
    _info(f"使用编辑器: {editor}")
    subprocess.run([editor, str(file_path)])


# --------------------------------------------------------------------------- #
# yuanbot list channels
# --------------------------------------------------------------------------- #


def _run_list_channels(args: argparse.Namespace) -> None:
    """列出已配置的通道"""
    _header("通道列表")

    channels_dir = Path("configs/Channels")
    if not channels_dir.exists():
        _info("configs/Channels/ 目录不存在")
        return

    import yaml

    for yaml_file in sorted(channels_dir.glob("*.yaml")):
        try:
            with open(yaml_file) as f:
                config = yaml.safe_load(f) or {}
            platform = config.get("platform", yaml_file.stem)
            enabled = config.get("enabled", True)
            display = config.get("display_name", platform)
            status = _c("✅", "") if enabled else _c("❌", "")
            print(f"  {status} {display:20s} ({platform})  [{yaml_file.name}]")
        except Exception as e:
            print(f"  ❌ {yaml_file.name}: {e}")

    print()


# --------------------------------------------------------------------------- #
# yuanbot list plugins
# --------------------------------------------------------------------------- #


def _run_list_plugins(args: argparse.Namespace) -> None:
    """列出已安装的 Skills 和 Tools"""
    _header("插件列表")

    import yaml

    # Skills
    skills_dir = Path("configs/Plugins/skills")
    if skills_dir.exists():
        print(f"  {_c('🎯 Skills:', _BOLD)}")
        for yaml_file in sorted(skills_dir.glob("*.yaml")):
            try:
                with open(yaml_file) as f:
                    config = yaml.safe_load(f) or {}
                name = config.get("name", yaml_file.stem)
                category = config.get("category", "-")
                enabled = config.get("enabled", True)
                status = _c("✅", "") if enabled else _c("❌", "")
                print(f"    {status} {name:20s} 分类: {category}")
            except Exception:
                print(f"    ❌ {yaml_file.name}")
    else:
        _info("无 Skills 配置")

    # Tools
    tools_dir = Path("configs/Plugins/tools")
    if tools_dir.exists():
        print(f"\n  {_c('🔧 Tools:', _BOLD)}")
        for yaml_file in sorted(tools_dir.glob("*.yaml")):
            try:
                with open(yaml_file) as f:
                    config = yaml.safe_load(f) or {}
                name = config.get("name", yaml_file.stem)
                category = config.get("category", "-")
                executor = config.get("executor", {}).get("type", "-")
                enabled = config.get("enabled", True)
                status = _c("✅", "") if enabled else _c("❌", "")
                print(f"    {status} {name:20s} 分类: {category}  执行器: {executor}")
            except Exception:
                print(f"    ❌ {yaml_file.name}")
    else:
        _info("无 Tools 配置")

    print()


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
