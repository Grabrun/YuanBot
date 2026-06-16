"""YuanBot CLI — 安装引导工具

用法:
    yuanbot install           全自动交互式安装 YuanBot
    yuanbot install --help    查看帮助
    yuanbot version           查看版本
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


# ── ANSI 颜色 ──────────────────────────────

_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def _c(text: str, color: str) -> str:
    if not sys.stderr.isatty():
        return text
    return f"{color}{text}{_RESET}"


def _header(title: str) -> None:
    print(f"\n  {_c('==', _CYAN + _BOLD)} {title}")


def _ok(msg: str) -> None:
    print(f"  {_c('✅', '')} {msg}")


def _fail(msg: str) -> None:
    print(f"  {_c('❌', '')} {_c(msg, _RED)}")


def _warn(msg: str) -> None:
    print(f"  {_c('⚠️', '')} {_c(msg, _YELLOW)}")


def _info(msg: str) -> None:
    print(f"  {_c('ℹ️', '')} {msg}")


# ── 核心安装逻辑 ──────────────────────────

VERSION = "1.0.0"
REPO_URL = "https://github.com/Grabrun/YuanBot.git"
MIN_PYTHON = (3, 12)

# 支持的 AI 提供商
PROVIDERS = {
    "deepseek": {
        "name": "DeepSeek",
        "file": "deepseek.yaml",
        "model": "deepseek-v4-flash",
        "key_hint": "sk-...",
    },
    "openai": {
        "name": "OpenAI",
        "file": "openai.yaml",
        "model": "gpt-5.5",
        "key_hint": "sk-...",
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "file": "anthropic.yaml",
        "model": "claude-sonnet-4-6",
        "key_hint": "sk-ant-...",
    },
}


def _run_install(args: argparse.Namespace) -> None:
    """全自动安装 YuanBot"""

    provider_id: str | None = args.provider
    api_key: str | None = args.api_key
    non_interactive: bool = args.non_interactive

    # ── 1. 欢迎 ─────────────────────────
    print()
    print(f"  {_c('🌸 YuanBot 安装程序', _CYAN + _BOLD)}")
    print(f"  {_c('版本', _DIM)} {VERSION}")
    print(f"  {_c('—' * 40, _DIM)}")
    print()

    # ── 2. Python 版本 ───────────────────
    _header("环境检查")
    if sys.version_info < MIN_PYTHON:
        _fail(f"需要 Python 3.12+，当前 {sys.version_info.major}.{sys.version_info.minor}")
        sys.exit(1)
    _ok(f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

    if not shutil.which("git"):
        _warn("未检测到 git，将跳过版本控制")
    else:
        _ok("git 已安装")
    print()

    # ── 3. 确定安装目录 ─────────────────
    _header("安装位置")
    target_dir: Path
    if args.dir:
        target_dir = Path(args.dir).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        _info(f"目标目录: {target_dir}")
    else:
        target_dir = Path.cwd() / "YuanBot"
        _info(f"默认目录: {target_dir}")

    # 检查是否已存在
    is_existing = (target_dir / "pyproject.toml").exists() and (target_dir / "src" / "yuanbot").exists()
    if is_existing:
        if args.force:
            _warn("目录已有 YuanBot 项目，--force 模式下将覆盖安装")
        else:
            _info("检测到已有 YuanBot 项目")
            answer = input(f"  {_c('?', _CYAN)} 是否重新安装？(y/N): ").strip().lower()
            if answer not in ("y", "yes"):
                _info("已取消")
                return
    print()

    # ── 4. 克隆/更新代码 ────────────────
    _header("获取代码")
    if target_dir.exists() and is_existing:
        _info("拉取最新代码...")
        subprocess.run(["git", "pull"], cwd=target_dir, capture_output=True)
        _ok("代码已更新")
    else:
        _info(f"正在从 GitHub 克隆...")
        result = subprocess.run(
            ["git", "clone", "--depth=1", REPO_URL, str(target_dir)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            _fail(f"克隆失败: {result.stderr.strip()}")
            sys.exit(1)
        _ok("代码已下载")
    print()

    # ── 5. 创建虚拟环境 ─────────────────
    _header("虚拟环境")
    venv_path = target_dir / ".venv"
    if not venv_path.exists():
        _info("创建中...")
        result = subprocess.run(
            [sys.executable, "-m", "venv", str(venv_path)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            _fail(f"创建失败: {result.stderr.strip()}")
            sys.exit(1)
        _ok(".venv 已创建")
    else:
        _ok(".venv 已存在")

    # venv 里的 python/pip
    if sys.platform == "win32":
        py_venv = venv_path / "Scripts" / "python"
        pip_venv = venv_path / "Scripts" / "pip"
    else:
        py_venv = venv_path / "bin" / "python"
        pip_venv = venv_path / "bin" / "pip"
    print()

    # ── 6. 安装依赖 ─────────────────────
    _header("安装依赖")
    _info("正在安装 YuanBot (这可能需要几分钟)...")
    result = subprocess.run(
        [str(pip_venv), "install", "-e", str(target_dir)],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        _warn(f"安装输出: {result.stderr[-200:]}")
    # 额外安装开发依赖
    subprocess.run(
        [str(pip_venv), "install", "-e", str(target_dir) + "[dev]"],
        capture_output=True, timeout=300,
    )
    _ok("YuanBot 已安装")
    print()

    # ── 7. 初始化配置 ───────────────────
    _header("初始化配置")
    result = subprocess.run(
        [str(py_venv), "-m", "yuanbot.cli", "config", "init"],
        capture_output=True, text=True, cwd=target_dir,
    )
    if result.returncode == 0:
        _ok("配置模板已生成")
    else:
        _warn(f"config init 输出: {result.stderr[-200:]}")
    print()

    # ── 8. 配置 AI 提供商 ───────────────
    if not non_interactive and not (provider_id and api_key):
        _header("AI 提供商")
        print(f"  {_c('选择 AI 提供商:', _BOLD)}")
        choices = list(PROVIDERS.keys())
        for i, pid in enumerate(choices, 1):
            p = PROVIDERS[pid]
            print(f"    {i}. {p['name']} ({p['model']})")
        print(f"    {len(choices) + 1}. 稍后手动配置")

        try:
            sel = input(f"\n  {_c('?', _CYAN)} 请选择 [1-{len(choices) + 1}] (默认 1): ").strip()
            if not sel or sel == "1":
                provider_id = "deepseek"
            else:
                idx = int(sel) - 1
                provider_id = choices[idx] if 0 <= idx < len(choices) else None
        except (ValueError, IndexError):
            provider_id = None

        if provider_id:
            p = PROVIDERS[provider_id]
            api_key = input(f"  {_c('?', _CYAN)} 输入 {p['name']} API Key (如 {p['key_hint']}): ").strip()

    if provider_id and api_key:
        _header("写入配置")
        p = PROVIDERS[provider_id]

        # 写 API Key 到 provider 配置
        provider_path = target_dir / "configs" / "Providers" / p["file"]
        if provider_path.exists():
            import yaml  # type: ignore[import-untyped]
            with open(provider_path) as f:
                cfg = yaml.safe_load(f) or {}
            cfg.setdefault("config", {})["api_key"] = api_key
            cfg["enabled"] = True
            with open(provider_path, "w") as f:
                yaml.safe_dump(cfg, f, allow_unicode=True, default_flow_style=False)
            _ok(f"API Key 已配置到 {p['file']}")

        # 写默认提供商到 bot.yaml
        bot_path = target_dir / "configs" / "bot.yaml"
        if bot_path.exists():
            import yaml
            with open(bot_path) as f:
                bot_cfg = yaml.safe_load(f) or {}
            bot_cfg.setdefault("ai", {})["default_provider"] = provider_id
            bot_cfg["ai"]["default_model"] = p["model"]
            with open(bot_path, "w") as f:
                yaml.safe_dump(bot_cfg, f, allow_unicode=True, default_flow_style=False)
            _ok(f"默认提供商设为 {p['name']}")

        print()

    # ── 9. 运行诊断 ─────────────────────
    _header("运行诊断")
    subprocess.run(
        [str(py_venv), "-m", "yuanbot.cli", "doctor"],
        cwd=target_dir,
    )
    print()

    # ── 10. 完成 ─────────────────────────
    if sys.platform == "win32":
        activate_cmd = f"{venv_path}\\Scripts\\activate"
    else:
        activate_cmd = f"source {venv_path / 'bin' / 'activate'}"

    print(f"  {_c('🎉 YuanBot 安装成功!', _GREEN + _BOLD)}")
    print()
    _info(f"安装目录: {target_dir}")
    print()
    _header("下一步")
    print(f"    {_c(activate_cmd, _CYAN)}    # 激活虚拟环境")
    print(f"    {_c('yuanbot start', _CYAN)}             # 启动服务")
    print(f"    {_c('yuanbot tui', _CYAN)}               # 终端聊天")
    print(f"    打开 {_c('http://localhost:8000', _CYAN)}   # WebUI")
    print()
    _info(f"📖 文档: https://grabrun.github.io/YuanBot")
    print()


# ── CLI 入口 ──────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="yuanbot",
        description="YuanBot 安装引导工具 — 一行命令部署 AI 虚拟伴侣",
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"yuanbot-cli {VERSION}",
        help="显示版本号",
    )

    sub = parser.add_subparsers(dest="command")

    # yuanbot install
    install_parser = sub.add_parser("install", help="全自动安装 YuanBot")
    install_parser.add_argument(
        "--dir", default="",
        help="安装目录（默认当前目录下的 YuanBot/）",
    )
    install_parser.add_argument(
        "--provider", default=None,
        help="AI 提供商 (deepseek/openai/anthropic)",
    )
    install_parser.add_argument(
        "--api-key", default=None,
        help="API Key",
    )
    install_parser.add_argument(
        "--non-interactive", action="store_true",
        help="非交互式安装（需同时指定 --provider 和 --api-key）",
    )
    install_parser.add_argument(
        "--force", action="store_true",
        help="强制重新安装",
    )

    # yuanbot version
    sub.add_parser("version", help="显示版本号")

    args = parser.parse_args()

    if args.command == "install":
        _run_install(args)
    else:
        parser.print_help()
