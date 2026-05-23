"""🌸 缘·Bot TUI 终端聊天界面

基于 Textual 框架，通过 HTTP API 与 YuanBot 后端通信。

使用方式:
    python -m yuanbot.tui --host http://localhost:8000
    yuanbot-cli tui --host http://localhost:8000
"""

from yuanbot.tui.app import YuanBotTUI, run_tui
from yuanbot.tui.client import TUIClient

__all__ = ["YuanBotTUI", "TUIClient", "run_tui"]
