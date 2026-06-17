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

VERSION = "1.2.4"
REPO_URL = "https://github.com/Grabrun/YuanBot.git"


def _run_cmd(cmd: list[str], cwd: str | None = None, timeout: int | None = None) -> int:
    """运行命令并实时显示输出（流式输出到终端，避免管道死锁）"""
    import subprocess as _sp

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["GIT_TERMINAL_PROMPT"] = "0"
    # 不捕获输出，直接透传到终端
    proc = _sp.Popen(cmd, cwd=cwd, env=env)
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        raise
    return proc.returncode


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

# 支持的聊天通道
CHANNELS = {
    "telegram": {
        "name": "Telegram",
        "desc": "Telegram Bot，长轮询模式",
        "file": "telegram.yaml",
        "fields": [
            ("bot_token", "Bot Token", "", True),
        ],
    },
    "napcat": {
        "name": "QQ (NapCat)",
        "desc": "基于 NapCat + OneBot v11 的 QQ 机器人 (WebSocket)",
        "file": "napcat.yaml",
        "fields": [
            ("http_host", "NapCat HTTP 地址", "127.0.0.1", False),
            ("http_port", "NapCat HTTP 端口", "3000", False),
            ("http_token", "NapCat HTTP Token (可选)", "", False),
            ("ws_host", "WebSocket 监听地址", "0.0.0.0", False),
            ("ws_port", "WebSocket 监听端口", "8081", False),
        ],
    },
    "wechat": {
        "name": "微信 (iLink)",
        "desc": "微信 iLink 协议接入，支持扫码登录",
        "file": "wechat.yaml",
        "fields": [],  # 微信走扫码登录特殊流程
    },
    "dingtalk": {
        "name": "钉钉",
        "desc": "钉钉企业内部应用机器人",
        "file": "dingtalk.yaml",
        "fields": [
            ("app_key", "App Key / Client ID", "", True),
            ("app_secret", "App Secret / Client Secret", "", True),
            ("webhook_token", "Webhook Token (可选)", "", False),
            ("webhook_port", "Webhook 监听端口", "8080", False),
        ],
    },
    "discord": {
        "name": "Discord",
        "desc": "Discord Bot，支持 Slash 命令",
        "file": "discord.yaml",
        "fields": [
            ("bot_token", "Bot Token", "", True),
            ("public_key", "Public Key (可选)", "", False),
        ],
    },
    "feishu": {
        "name": "飞书",
        "desc": "飞书企业自建应用机器人",
        "file": "feishu.yaml",
        "fields": [
            ("app_id", "App ID", "", True),
            ("app_secret", "App Secret", "", True),
            ("verification_token", "Verification Token (可选)", "", False),
            ("encrypt_key", "Encrypt Key (可选)", "", False),
        ],
    },
    "qq": {
        "name": "QQ (官方)",
        "desc": "QQ 官方机器人 API (WebSocket)",
        "file": "qq.yaml",
        "fields": [
            ("app_id", "App ID", "", True),
            ("app_secret", "App Secret", "", True),
        ],
    },
    "wecom": {
        "name": "企业微信",
        "desc": "企业微信应用机器人",
        "file": "wecom.yaml",
        "fields": [
            ("corp_id", "企业 ID (CorpID)", "", True),
            ("corp_secret", "应用 Secret", "", True),
            ("agent_id", "应用 AgentID", "", True),
            ("token", "Token (可选)", "", False),
            ("encoding_aes_key", "EncodingAESKey (可选)", "", False),
        ],
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
        target_dir = Path.cwd()
        _info(f"当前目录: {target_dir}")

    # 检查是否已存在
    is_existing = (target_dir / "pyproject.toml").exists() and (
        target_dir / "src" / "yuanbot"
    ).exists()
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
    if args.no_clone:
        _info("跳过克隆（--no-clone）")
        if not is_existing:
            _fail(f"目标目录 {target_dir} 中未找到 YuanBot 项目")
            _info("请先手动下载代码到该目录，或去掉 --no-clone 参数")
            sys.exit(1)
    elif target_dir.exists() and is_existing:
        _info("拉取最新代码...")
        _run_cmd(["git", "pull"], cwd=str(target_dir))
        _ok("代码已更新")
    else:
        _info("正在从 GitHub 克隆...")
        # 如果目标目录是当前目录，用 "."；否则用完整路径
        clone_target = "." if str(target_dir) == str(Path.cwd()) else str(target_dir)
        code = _run_cmd(["git", "clone", "--depth=1", REPO_URL, clone_target])
        if code != 0:
            _fail("克隆失败")
            _info("可能的原因:")
            _info("  1. 网络连接问题 — 请检查能否访问 github.com")
            _info("  2. 防火墙/代理限制 — 可设置 HTTP_PROXY 环境变量")
            _info("  3. Git 未正确配置 — 运行 git config --global http.sslVerify false 尝试")
            _info(f"  4. 也可手动下载代码到 {target_dir}，再用 --no-clone 跳过此步骤")
            sys.exit(1)
        _ok("代码已下载")
    print()

    # ── 5. 创建虚拟环境 ─────────────────
    _header("虚拟环境")
    venv_path = target_dir / ".venv"
    if not venv_path.exists():
        _info("创建中...")
        code = _run_cmd([sys.executable, "-m", "venv", str(venv_path)])
        if code != 0:
            _fail("创建虚拟环境失败")
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
    code = _run_cmd([str(pip_venv), "install", "-e", str(target_dir)], timeout=300)
    if code != 0:
        _warn("部分依赖安装有警告，继续执行...")
    code = _run_cmd([str(pip_venv), "install", "-e", str(target_dir) + "[dev]"], timeout=300)
    _ok("YuanBot 已安装")
    print()

    # ── 7. 初始化配置 ───────────────────
    _header("初始化配置")
    _info("生成配置模板...")
    code = _run_cmd([str(py_venv), "-m", "yuanbot.cli", "config", "init"], cwd=str(target_dir))
    if code == 0:
        _ok("配置模板已生成")
    else:
        _warn("config init 遇到问题，继续执行...")
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
            api_key = input(
                f"  {_c('?', _CYAN)} 输入 {p['name']} API Key (如 {p['key_hint']}): "
            ).strip()

    if provider_id and api_key:
        _header("写入配置")
        p = PROVIDERS[provider_id]

        # 写 API Key 到 provider 配置
        provider_path = target_dir / "configs" / "Providers" / p["file"]
        if provider_path.exists():
            import yaml  # type: ignore[import-untyped]

            with open(provider_path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            cfg.setdefault("config", {})["api_key"] = api_key
            cfg["enabled"] = True
            with open(provider_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(cfg, f, allow_unicode=True, default_flow_style=False)
            _ok(f"API Key 已配置到 {p['file']}")

        # 写默认提供商到 bot.yaml
        bot_path = target_dir / "configs" / "bot.yaml"
        if bot_path.exists():
            import yaml

            with open(bot_path, encoding="utf-8") as f:
                bot_cfg = yaml.safe_load(f) or {}
            bot_cfg.setdefault("ai", {})["default_provider"] = provider_id
            bot_cfg["ai"]["default_model"] = p["model"]
            with open(bot_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(bot_cfg, f, allow_unicode=True, default_flow_style=False)
            _ok(f"默认提供商设为 {p['name']}")

        print()

    # ── 9. 配置聊天通道 ────────────────
    if not non_interactive:
        _configure_channels(target_dir)
    print()

    # ── 10. 运行诊断 ────────────────────
    _header("运行诊断")
    _run_cmd([str(py_venv), "-m", "yuanbot.cli", "doctor"], cwd=str(target_dir))
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
    _info("📖 文档: https://grabrun.github.io/YuanBot")
    print()


# ── 更新 ──────────────────────────────


def _run_update(args: argparse.Namespace) -> None:
    """更新已有 YuanBot 到最新版本"""
    target_dir: Path
    if args.dir:
        target_dir = Path(args.dir).resolve()
    else:
        target_dir = Path.cwd()

    print()
    print(f"  {_c('🌸 正在更新 YuanBot', _CYAN + _BOLD)}")
    print(f"  {_c('—' * 40, _DIM)}")

    # 1. 检查是否是 YuanBot 项目
    _header("检查项目")
    is_valid = (target_dir / "pyproject.toml").exists() and (
        target_dir / "src" / "yuanbot"
    ).exists()
    if not is_valid:
        _fail(f"{target_dir} 中未找到 YuanBot 项目")
        _info("请 cd 到 YuanBot 安装目录后重试，或使用 --dir 指定目录")
        sys.exit(1)
    _ok(f"YuanBot 项目: {target_dir}")
    print()

    # 2. 检查 git 并拉取最新代码
    _header("拉取代码")
    if not shutil.which("git"):
        _fail("需要安装 Git")
        sys.exit(1)

    if not (target_dir / ".git").exists():
        _warn("不是 Git 仓库，跳过代码更新")
        _info("如需更新，请手动下载最新代码")
    else:
        _info("拉取最新代码...")
        code = _run_cmd(["git", "pull"], cwd=str(target_dir))
        if code == 0:
            _ok("代码已更新到最新")
        else:
            _warn("git pull 返回非零，请检查是否有冲突")
    print()

    # 3. 检测虚拟环境
    _header("虚拟环境")
    venv_path = target_dir / ".venv"
    if sys.platform == "win32":
        py_venv = venv_path / "Scripts" / "python"
        pip_venv = venv_path / "Scripts" / "pip"
    else:
        py_venv = venv_path / "bin" / "python"
        pip_venv = venv_path / "bin" / "pip"

    if not venv_path.exists():
        _warn("虚拟环境不存在，将重新创建")
        _info("创建虚拟环境...")
        code = _run_cmd([sys.executable, "-m", "venv", str(venv_path)])
        if code != 0:
            _fail("创建虚拟环境失败")
            sys.exit(1)
        _ok(".venv 已创建")
    else:
        _ok(".venv 已存在")
    print()

    # 4. 重新安装依赖
    _header("更新依赖")
    _info("安装核心包...")
    _run_cmd([str(pip_venv), "install", "-e", str(target_dir)], timeout=300)
    _info("安装可选依赖...")
    _run_cmd([str(pip_venv), "install", "-e", str(target_dir) + "[dev]"], timeout=300)
    _ok("依赖已更新")
    print()

    # 5. 刷新配置模板
    _header("刷新配置")
    _info("更新配置模板...")
    _run_cmd([str(py_venv), "-m", "yuanbot.cli", "config", "init"], cwd=str(target_dir))
    _ok("配置模板已刷新")
    print()

    # 6. 运行诊断
    _header("运行诊断")
    _run_cmd([str(py_venv), "-m", "yuanbot.cli", "doctor"], cwd=str(target_dir))
    print()

    # 7. 完成
    print(f"  {_c('🎉 YuanBot 已更新到最新版!', _GREEN + _BOLD)}")
    _info(f"目录: {target_dir}")
    print()
    _header("提示")
    _info("如果下方有配置模板更新提示，请手动合并差异")
    print()


# ── 通道配置 ──────────────────────────


def _configure_channels(target_dir: Path) -> None:
    """交互式选择并配置消息通道"""
    channels_dir = target_dir / "configs" / "Channels"
    if not channels_dir.exists():
        _info("通道配置目录不存在，跳过")
        return

    _header("聊天通道")
    _info("YuanBot 支持接入多个聊天平台 ヽ(✧∀✧)ﾉ")
    print()

    # 列出可用通道
    available = []
    for ch_file in sorted(channels_dir.glob("*.yaml")):
        platform = ch_file.stem
        if platform in CHANNELS:
            available.append(platform)

    if not available:
        _info("没有可配置的通道")
        return

    print(f"  {_c('可用通道:', _BOLD)}")
    for i, platform in enumerate(available, 1):
        info = CHANNELS[platform]
        mark = _c("*", _GREEN) if platform == "wechat" else " "
        print(f"  {_c(str(i), _BOLD):>3}. {mark} {info['name']} — {info['desc']}")
    print(f"  \n  {_c('* 微信支持扫码自动登录', _DIM)}")

    choice = input(
        f"\n  {_c('?', _CYAN)} 选择通道 (1-{len(available)}，逗号分隔，a=全部，0=跳过): "
    ).strip()

    if choice == "0":
        _info("跳过通道配置，可通过 yuanbot install 重新配置")
        return

    if choice.lower() == "a":
        selected = list(range(1, len(available) + 1))
    else:
        try:
            selected = [int(x.strip()) for x in choice.split(",")]
            selected = [x for x in selected if 1 <= x <= len(available)]
        except ValueError:
            _warn("输入无效，跳过通道配置")
            return

    if not selected:
        _info("未选择任何通道")
        return

    for idx in selected:
        platform = available[idx - 1]
        info = CHANNELS[platform]
        print()
        print(f"  {_c('──', _DIM)} {_c(info['name'], _BOLD)} {'─' * 20}")

        if platform == "wechat":
            _setup_wechat_qrcode(target_dir, channels_dir)
        else:
            _configure_channel_basic(target_dir / "configs", channels_dir, platform, info)

    print()
    _ok("通道配置完成！(◕‿◕✿)")


def _configure_channel_basic(
    configs_dir: Path,
    channels_dir: Path,
    platform: str,
    info: dict,
) -> None:
    """配置非微信通道（逐字段引导填写）"""
    import yaml

    config_file = channels_dir / info["file"]
    if not config_file.exists():
        _warn(f"{info['file']} 不存在，跳过")
        return

    try:
        with open(config_file, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except Exception:
        cfg = {}

    if "config" not in cfg:
        cfg["config"] = {}
    cfg["enabled"] = True

    for field_key, field_label, default_val, required in info["fields"]:
        current = cfg["config"].get(field_key, "")
        req_mark = _c(" *", _RED) if required else ""
        default_hint = f" [{_c(current or default_val, _DIM)}]" if current or default_val else ""
        prompt = f"  {field_label}{req_mark}{default_hint}: "
        val = input(prompt).strip()
        if val:
            cfg["config"][field_key] = val
        elif not current and default_val and not required:
            cfg["config"][field_key] = default_val

    with open(config_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, default_flow_style=False)
    _ok(f"{info['name']} 配置已保存")


def _setup_wechat_qrcode(target_dir: Path, channels_dir: Path) -> None:
    """配置微信个人通道（QR 码扫码登录）"""
    import json
    import urllib.parse
    import urllib.request

    wechat_path = channels_dir / "wechat.yaml"
    if not wechat_path.exists():
        _warn("wechat.yaml 配置文件不存在")
        return

    api_base = "https://ilinkai.weixin.qq.com"
    _info("正在获取微信登录二维码...")

    try:
        # 1. 获取二维码
        req = urllib.request.Request(
            f"{api_base}/ilink/bot/get_bot_qrcode?bot_type=3",
            data=json.dumps({"local_token_list": []}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            qr_data = json.loads(resp.read())

        qrcode = qr_data.get("qrcode", "")
        qrcode_url = qr_data.get("qrcode_img_content", "")
        if not qrcode:
            _fail("获取二维码失败")
            return

        _ok("二维码已获取")
        print()
        _info("请用手机微信扫描以下二维码以登录：")

        try:
            import qrcode as _qr

            qr = _qr.QRCode(border=1, box_size=2)
            qr.add_data(qrcode_url)
            qr.print_ascii()
        except ImportError:
            print(f"    {_c(qrcode_url, _CYAN)}")
        print(f"  {_c('或打开此链接扫码: ' + qrcode_url, _DIM)}")
        print()

        print()
        _info("扫码后等待确认...")

        # 2. 轮询二维码状态
        import time as _time

        deadline = _time.time() + 480
        bot_token = ""
        ilink_user_id = ""
        ilink_bot_id = ""
        base_url = ""

        while _time.time() < deadline:
            query = urllib.parse.urlencode({"qrcode": qrcode})
            status_url = f"{api_base}/ilink/bot/get_qrcode_status?{query}"
            try:
                req = urllib.request.Request(status_url)
                with urllib.request.urlopen(req, timeout=35) as resp:
                    status_data = json.loads(resp.read())

                status = status_data.get("status", "wait")
                if status == "wait":
                    print(f"  {_c('.', _DIM)}", end="", flush=True)
                elif status == "scaned":
                    print()
                    _ok("已扫码，等待确认...")
                elif status == "confirmed":
                    bot_token = status_data.get("bot_token", "")
                    ilink_bot_id = status_data.get("ilink_bot_id", "")
                    ilink_user_id = status_data.get("ilink_user_id", "")
                    base_url = status_data.get("baseurl", api_base)
                    _ok("微信登录成功！")
                    break
                elif status == "expired":
                    _warn("二维码已过期，请重新运行")
                    return
                elif status == "need_verifycode":
                    code = input(f"  {_c('?', _CYAN)} 输入手机微信显示的数字: ").strip()
                    status_url += f"&verify_code={urllib.parse.quote(code)}"
                    continue
                elif status == "binded_redirect":
                    _info("此微信已连接过此 OpenClaw")
                    return
                else:
                    _info(f"状态: {status}")

            except Exception as e:
                _warn(f"轮询异常: {e}")
                _time.sleep(3)
                continue

            _time.sleep(1)

        if not bot_token:
            _fail("微信登录超时")
            return

        # 3. 保存配置
        import yaml

        with open(wechat_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

        cfg["enabled"] = True
        cfg["config"]["token"] = bot_token
        cfg["config"]["ilink_user_id"] = ilink_user_id
        cfg["config"]["bot_id"] = ilink_bot_id
        cfg["config"]["base_url"] = base_url

        with open(wechat_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, allow_unicode=True, default_flow_style=False)

        _ok("微信通道配置已保存")
        _info(f"微信用户: {ilink_user_id}")
        _info(f"Bot ID: {ilink_bot_id}")

    except Exception as e:
        _fail(f"微信配置失败: {e}")
        _info("可在安装完成后手动配置")


# ── CLI 入口 ──────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="yuanbot",
        description="YuanBot 安装引导工具 — 一行命令部署 AI 虚拟伴侣",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"yuanbot-cli {VERSION}",
        help="显示版本号",
    )

    sub = parser.add_subparsers(dest="command")

    # yuanbot install
    install_parser = sub.add_parser("install", help="全自动安装 YuanBot")
    install_parser.add_argument(
        "--dir",
        default="",
        help="安装目录（默认直接安装到当前目录）",
    )
    install_parser.add_argument(
        "--provider",
        default=None,
        help="AI 提供商 (deepseek/openai/anthropic)",
    )
    install_parser.add_argument(
        "--api-key",
        default=None,
        help="API Key",
    )
    install_parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="非交互式安装（需同时指定 --provider 和 --api-key）",
    )
    install_parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新安装",
    )
    install_parser.add_argument(
        "--no-clone",
        action="store_true",
        help="跳过 git clone（代码已存在时使用）",
    )

    # yuanbot version
    sub.add_parser("version", help="显示版本号")

    # yuanbot update
    update_parser = sub.add_parser("update", help="更新 YuanBot 到最新版本")
    update_parser.add_argument(
        "--dir",
        default="",
        help="YuanBot 安装目录（默认当前目录）",
    )

    args = parser.parse_args()

    if args.command == "install":
        _run_install(args)
    elif args.command == "update":
        _run_update(args)
    else:
        parser.print_help()
