"""YuanBot CLI 入口"""

from __future__ import annotations

import argparse
import sys

import structlog

from yuanbot.config import load_config


def main() -> None:
    """CLI 主入口"""
    parser = argparse.ArgumentParser(
        prog="yuanbot",
        description="缘·Bot (YuanBot) - AI 虚拟伴侣系统",
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # serve 命令
    serve_parser = subparsers.add_parser("serve", help="启动 YuanBot 服务")
    serve_parser.add_argument(
        "-c",
        "--config",
        type=str,
        default=None,
        help="配置文件路径 (YAML)",
    )
    serve_parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=8000,
        help="API 服务端口",
    )

    # version 命令
    subparsers.add_parser("version", help="显示版本信息")

    # init 命令
    init_parser = subparsers.add_parser("init", help="初始化配置文件")
    init_parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="yuanbot.yaml",
        help="输出配置文件路径",
    )

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

    if args.command == "version":
        from yuanbot import __version__

        print(f"缘·Bot (YuanBot) v{__version__}")

    elif args.command == "serve":
        _run_serve(args.config, args.port)

    elif args.command == "init":
        _run_init(args.output)

    else:
        parser.print_help()


def _run_serve(config_path: str | None, port: int) -> None:
    """启动服务"""
    import uvicorn

    config = load_config(config_path)

    print(f"🌸 缘·Bot (YuanBot) v{config.version} 启动中...")
    print(f"   API 端口: {port}")
    print(f"   AI 提供商: {config.ai_provider.provider_id}")
    print(f"   调试模式: {'开' if config.debug else '关'}")

    # 延迟导入避免循环依赖
    from yuanbot.app import create_app

    app = create_app(config)

    uvicorn.run(app, host="0.0.0.0", port=port, log_level=config.log_level.lower())


def _run_init(output_path: str) -> None:
    """初始化配置文件"""
    import yaml

    default_config = {
        "app_name": "YuanBot",
        "version": "0.1.0",
        "debug": False,
        "log_level": "INFO",
        "ai_provider": {
            "provider_id": "openai",
            "default_model": "gpt-4o",
        },
        "channels": [
            {
                "platform": "telegram",
                "enabled": True,
                "config": {
                    "bot_token": "YOUR_BOT_TOKEN_HERE",
                },
            },
        ],
        "memory": {
            "vector_db": "qdrant",
            "vector_db_url": "http://localhost:6333",
            "db_url": "postgresql://yuanbot:yuanbot@localhost:5432/yuanbot",
            "redis_url": "redis://localhost:6379/0",
        },
        "proactive": {
            "enabled": True,
            "greeting_enabled": True,
            "frequency": "medium",
            "quiet_hours_start": 23,
            "quiet_hours_end": 8,
            "max_per_day": 5,
        },
        "persona_id": "default",
    }

    with open(output_path, "w") as f:
        yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True)

    print(f"✅ 配置文件已生成: {output_path}")
    print("   请编辑配置文件，填入你的 API Key 和通道配置。")


if __name__ == "__main__":
    main()
