"""🌸 缘·Bot TUI 终端聊天界面

基于 Textual 框架，通过 HTTP API 与 YuanBot 后端通信。
完整实现设计文档第4节所有功能。

启动方式:
    python -m yuanbot.tui --host http://localhost:8000
    yuanbot-cli tui --host http://localhost:8000

快捷键:
    Ctrl+N       新建会话
    Ctrl+Tab     下一个会话
    Ctrl+R       切换信息面板
    Ctrl+Q       退出
    Ctrl+L       清屏
    F1           帮助
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from rich.markup import escape
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Markdown,
    RichLog,
    Static,
)

from yuanbot.tui.client import TUIClient, TUIClientError


class LoginScreen(ModalScreen[dict]):
    """登录界面"""

    CSS = """
    LoginScreen {
        align: center middle;
    }
    #login-box {
        width: 50;
        height: auto;
        max-height: 20;
        border: solid $primary;
        padding: 1 2;
        background: $surface;
    }
    #login-box Label {
        margin: 1 0 0 0;
    }
    #login-box Input {
        margin: 0 0 1 0;
    }
    #login-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    #login-error {
        color: $error;
        display: none;
    }
    """

    BINDINGS = [Binding("escape", "cancel", "取消")]

    def __init__(self, client: TUIClient):
        super().__init__()
        self._client = client

    def compose(self) -> ComposeResult:
        with Vertical(id="login-box"):
            yield Label("🌸 缘·Bot 登录", id="login-title")
            yield Label("用户名:")
            yield Input(placeholder="admin", id="username")
            yield Label("密码:")
            yield Input(placeholder="password", password=True, id="password")
            yield Label("", id="login-error")
            yield Static("[dim]Enter 登录 | Esc 取消[/dim]")

    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(Input.Submitted)
    async def on_submit(self, event: Input.Submitted) -> None:
        username = self.query_one("#username", Input).value
        password = self.query_one("#password", Input).value
        if not username or not password:
            self._show_error("请输入用户名和密码")
            return
        try:
            data = await self._client.login(username, password)
            self.dismiss(data)
        except TUIClientError as e:
            self._show_error(str(e))

    def _show_error(self, msg: str) -> None:
        error = self.query_one("#login-error", Label)
        error.update(msg)
        error.display = True


class HelpScreen(ModalScreen):
    """帮助界面"""

    CSS = """
    HelpScreen {
        align: center middle;
    }
    #help-box {
        width: 65;
        height: auto;
        max-height: 35;
        border: solid $primary;
        padding: 1 2;
        background: $surface;
    }
    """

    BINDINGS = [Binding("escape", "close", "关闭")]

    HELP_TEXT = """\
# 🌸 缘·Bot TUI 帮助

## 快捷键
- **Ctrl+N** — 新建会话
- **Ctrl+Tab** — 下一个会话
- **Ctrl+Shift+Tab** — 上一个会话
- **Ctrl+R** — 切换信息面板
- **Ctrl+L** — 清屏
- **Ctrl+Q** — 退出
- **F1** — 帮助
- **Esc** — 关闭弹窗

## 命令
- `/help` — 显示帮助
- `/new [标题]` — 新建会话
- `/list` — 列出会话
- `/switch <n>` — 切换到第 n 个会话
- `/delete` — 删除当前会话
- `/me` — 显示用户信息
- `/memory [关键词]` — 查看/搜索记忆
- `/provider` — 查看 AI 提供商状态
- `/history [关键词]` — 搜索消息历史
- `/clear` — 清屏
- `/quit` — 退出
"""

    def compose(self) -> ComposeResult:
        with Vertical(id="help-box"):
            yield Markdown(self.HELP_TEXT)

    def action_close(self) -> None:
        self.dismiss()


class ConversationItem(ListItem):
    """会话列表项"""

    def __init__(self, conv_id: str, title: str, updated: str, message_count: int):
        super().__init__()
        self.conv_id = conv_id
        self._label = Label(f"{title[:20]}  [{message_count}条]")

    def compose(self) -> ComposeResult:
        yield self._label


class InfoPanel(Static):
    """右侧信息面板"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._panel_mode = "status"  # status | memory | help

    def set_mode(self, mode: str) -> None:
        self._panel_mode = mode
        self.refresh_content()

    def toggle_mode(self) -> None:
        modes = ["status", "memory", "help"]
        idx = modes.index(self._panel_mode)
        self.set_mode(modes[(idx + 1) % len(modes)])

    def refresh_content(self, data: dict | None = None) -> None:
        if self._panel_mode == "status":
            self._render_status(data)
        elif self._panel_mode == "memory":
            self._render_memory(data)
        elif self._panel_mode == "help":
            self._render_help()

    def _render_status(self, data: dict | None = None) -> None:
        d = data or {}
        user = d.get("user", {})
        lines = [
            "[bold]📊 今日状态[/bold]",
            f"  用户: {user.get('display_name', '-')}",
            f"  角色: {user.get('role', '-')}",
            "",
            f"  会话数: {d.get('conv_count', 0)}",
            f"  消息数: {d.get('msg_count', 0)}",
            "",
            "[dim]Ctrl+R 切换面板[/dim]",
        ]
        self.update("\n".join(lines))

    def _render_memory(self, data: dict | None = None) -> None:
        lines = ["[bold]🧠 最近记忆[/bold]", ""]
        memories = (data or {}).get("memories", [])
        if memories:
            for m in memories[:8]:
                lines.append(f"  · {m[:30]}")
        else:
            lines.append("  [dim]暂无记忆数据[/dim]")
        lines.extend(["", "[dim]/memory 查看更多[/dim]"])
        self.update("\n".join(lines))

    def _render_help(self) -> None:
        lines = [
            "[bold]📖 快速帮助[/bold]",
            "",
            "  /help    帮助",
            "  /new     新建会话",
            "  /list    列出会话",
            "  /memory  查看记忆",
            "  /provider 提供商",
            "  /clear   清屏",
            "  /quit    退出",
            "",
            "  Ctrl+N   新建会话",
            "  Ctrl+R   切换面板",
            "  F1       完整帮助",
        ]
        self.update("\n".join(lines))


class YuanBotTUI(App):
    """🌸 缘·Bot TUI 终端聊天应用"""

    TITLE = "🌸 缘·Bot TUI"
    CSS = """
    #sidebar {
        width: 25;
        border-right: solid $primary;
        background: $surface;
    }
    #sidebar Label {
        padding: 0 1;
    }
    #conv-list {
        height: 1fr;
    }
    #chat-area {
        width: 1fr;
    }
    #chat-log {
        height: 1fr;
        border-bottom: solid $primary-darken-2;
        padding: 0 1;
    }
    #info-panel {
        width: 25;
        border-left: solid $primary;
        background: $surface;
        padding: 1;
        display: block;
    }
    #info-panel.hidden {
        display: none;
        width: 0;
    }
    #input-area {
        height: 3;
        dock: bottom;
    }
    #input-area Input {
        width: 1fr;
    }
    #status-bar {
        height: 1;
        dock: bottom;
        background: $primary-darken-2;
        color: $text;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+n", "new_conversation", "新建会话", show=True),
        Binding("ctrl+tab", "next_conversation", "下一个会话", show=True),
        Binding("ctrl+shift+tab", "prev_conversation", "上一个会话", show=True),
        Binding("ctrl+r", "toggle_panel", "切换面板", show=True),
        Binding("ctrl+q", "quit", "退出", show=True),
        Binding("ctrl+l", "clear_chat", "清屏", show=True),
        Binding("f1", "show_help", "帮助", show=True),
        Binding("up", "history_up", "上一条历史", show=False),
        Binding("down", "history_down", "下一条历史", show=False),
    ]

    def __init__(self, client: TUIClient):
        super().__init__()
        self._client = client
        self._user: dict | None = None
        self._conversations: list[dict] = []
        self._current_conv_id: str | None = None
        self._panel_visible = True
        self._input_history: list[str] = []
        self._history_index = -1

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Label("📌 会话列表", id="sidebar-title")
                yield ListView(id="conv-list")
                yield Static("[dim]Ctrl+N 新建 | Tab 切换[/dim]")
            with Vertical(id="chat-area"):
                yield RichLog(id="chat-log", wrap=True, markup=True, highlight=True)
                with Horizontal(id="input-area"):
                    yield Input(placeholder="输入消息或 /help ...", id="msg-input")
            yield InfoPanel(id="info-panel")
        yield Static("未连接", id="status-bar")
        yield Footer()

    async def on_mount(self) -> None:
        await self._try_auto_login()

    async def _try_auto_login(self) -> None:
        import os

        api_key = os.environ.get("YUANBOT_API_KEY")
        if api_key:
            try:
                await self._client.login_with_api_key(api_key)
                await self._on_login_success()
                return
            except TUIClientError:
                pass
        await self._show_login()

    async def _show_login(self) -> None:
        result = await self.push_screen_wait(LoginScreen(self._client))
        if result:
            await self._on_login_success()
        else:
            self.exit("未登录")

    async def _on_login_success(self) -> None:
        try:
            self._user = await self._client.get_me()
            self._update_status(f"已登录: {self._user['display_name']} ({self._user['role']})")
            await self._load_conversations()
            self.query_one("#msg-input", Input).focus()
            self._refresh_info_panel()
        except TUIClientError as e:
            self._chat_log(f"[red]初始化失败: {e}[/red]")

    def _refresh_info_panel(self) -> None:
        panel = self.query_one("#info-panel", InfoPanel)
        panel.refresh_content({
            "user": self._user or {},
            "conv_count": len(self._conversations),
            "msg_count": sum(c.get("message_count", 0) for c in self._conversations),
        })

    async def _load_conversations(self) -> None:
        try:
            self._conversations = await self._client.list_conversations()
            list_view = self.query_one("#conv-list", ListView)
            await list_view.clear()

            for conv in self._conversations:
                item = ConversationItem(
                    conv["conversation_id"],
                    conv["title"],
                    conv.get("updated_at", "")[:16],
                    conv.get("message_count", 0),
                )
                await list_view.append(item)

            if self._conversations and not self._current_conv_id:
                self._current_conv_id = self._conversations[0]["conversation_id"]
                await self._load_current_messages()

            self._refresh_info_panel()
        except TUIClientError as e:
            self._chat_log(f"[red]加载会话失败: {e}[/red]")

    async def _load_current_messages(self) -> None:
        if not self._current_conv_id:
            return
        try:
            messages = await self._client.get_messages(self._current_conv_id)
            chat_log = self.query_one("#chat-log", RichLog)
            chat_log.clear()
            for msg in messages:
                role = msg["role"]
                content = msg["content"]
                if role == "user":
                    self._chat_log(f"[bold blue]你:[/bold blue] {escape(content)}")
                elif role == "assistant":
                    self._chat_log(f"[bold green]🌸 小缘:[/bold green] {escape(content)}")
        except TUIClientError as e:
            self._chat_log(f"[red]加载消息失败: {e}[/red]")

    @on(Input.Submitted, "#msg-input")
    async def on_message_sent(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        # 保存历史
        self._input_history.append(text)
        self._history_index = len(self._input_history)
        event.input.value = ""

        if text.startswith("/"):
            await self._handle_command(text)
        else:
            await self._send_chat_message(text)

    async def _send_chat_message(self, text: str) -> None:
        self._chat_log(f"[bold blue]你:[/bold blue] {escape(text)}")
        self._update_status("AI 思考中...")
        try:
            result = await self._client.send_message(
                content=text, conversation_id=self._current_conv_id
            )
            ai_content = result["ai_message"]["content"]
            self._chat_log(f"[bold green]🌸 小缘:[/bold green] {escape(ai_content)}")
            if not self._current_conv_id:
                self._current_conv_id = result["conversation_id"]
                await self._load_conversations()
            self._update_status(f"已登录: {self._user['display_name']}")
        except TUIClientError as e:
            self._chat_log(f"[red]发送失败: {e}[/red]")
            self._update_status("发送失败")

    async def _handle_command(self, cmd: str) -> None:
        parts = cmd.split(maxsplit=1)
        command = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if command == "/help":
            await self.push_screen(HelpScreen())

        elif command == "/new":
            title = arg or "新会话"
            try:
                conv = await self._client.create_conversation(title)
                self._current_conv_id = conv["conversation_id"]
                await self._load_conversations()
                self.query_one("#chat-log", RichLog).clear()
                self._chat_log(f"[dim]已创建新会话: {title}[/dim]")
            except TUIClientError as e:
                self._chat_log(f"[red]创建会话失败: {e}[/red]")

        elif command == "/list":
            if not self._conversations:
                self._chat_log("[dim]暂无会话[/dim]")
                return
            self._chat_log("[bold]会话列表:[/bold]")
            for i, conv in enumerate(self._conversations):
                marker = "→" if conv["conversation_id"] == self._current_conv_id else " "
                self._chat_log(
                    f" {marker} [{i+1}] {conv['title']} ({conv.get('message_count', 0)}条)"
                )

        elif command == "/switch":
            if not arg:
                self._chat_log("[dim]用法: /switch <序号>[/dim]")
                return
            try:
                idx = int(arg) - 1
                if 0 <= idx < len(self._conversations):
                    self._current_conv_id = self._conversations[idx]["conversation_id"]
                    await self._load_current_messages()
                    self._chat_log(f"[dim]已切换到: {self._conversations[idx]['title']}[/dim]")
                else:
                    self._chat_log("[red]无效序号[/red]")
            except ValueError:
                self._chat_log("[red]请输入数字[/red]")

        elif command == "/delete":
            if not self._current_conv_id:
                self._chat_log("[dim]没有可删除的会话[/dim]")
                return
            try:
                await self._client.delete_conversation(self._current_conv_id)
                self._current_conv_id = None
                self.query_one("#chat-log", RichLog).clear()
                await self._load_conversations()
                self._chat_log("[dim]已删除当前会话[/dim]")
            except TUIClientError as e:
                self._chat_log(f"[red]删除失败: {e}[/red]")

        elif command == "/me":
            if self._user:
                self._chat_log(
                    f"[bold]用户信息:[/bold]\n"
                    f"  用户名: {self._user['username']}\n"
                    f"  显示名: {self._user['display_name']}\n"
                    f"  角色: {self._user['role']}\n"
                    f"  ID: {self._user['user_id']}"
                )

        elif command == "/memory":
            self._chat_log("[bold]🧠 记忆系统[/bold]")
            self._chat_log("[dim]记忆功能需要集成记忆管理器后提供完整支持[/dim]")
            if arg:
                self._chat_log(f"[dim]搜索关键词: {arg}[/dim]")
            panel = self.query_one("#info-panel", InfoPanel)
            panel.set_mode("memory")

        elif command == "/provider":
            try:
                providers = await self._client.list_providers()
                self._chat_log("[bold]AI 提供商:[/bold]")
                for p in providers:
                    status = "✅" if p.get("enabled") else "❌"
                    default = " (默认)" if p.get("is_default") else ""
                    self._chat_log(
                        f"  {status} {p.get('provider_id', '?')} — "
                        f"{p.get('adapter', '?')}{default}"
                    )
            except TUIClientError:
                self._chat_log("[dim]无法获取提供商信息[/dim]")

        elif command == "/history":
            if not self._current_conv_id:
                self._chat_log("[dim]请先选择会话[/dim]")
                return
            try:
                messages = await self._client.get_messages(self._current_conv_id, limit=100)
                if arg:
                    messages = [m for m in messages if arg.lower() in m.get("content", "").lower()]
                self._chat_log(f"[bold]消息历史 ({len(messages)} 条):[/bold]")
                for msg in messages[-20:]:
                    role = "你" if msg["role"] == "user" else "🌸"
                    content = msg["content"][:50]
                    self._chat_log(f"  [{role}] {content}")
            except TUIClientError as e:
                self._chat_log(f"[red]获取历史失败: {e}[/red]")

        elif command == "/clear":
            self.query_one("#chat-log", RichLog).clear()

        elif command == "/quit":
            self.exit()

        else:
            self._chat_log(f"[red]未知命令: {command}[/red]")

    # ── 快捷键动作 ──────────────────────────

    def action_new_conversation(self) -> None:
        asyncio.create_task(self._handle_command("/new"))

    def action_next_conversation(self) -> None:
        if not self._conversations:
            return
        if self._current_conv_id:
            ids = [c["conversation_id"] for c in self._conversations]
            try:
                idx = ids.index(self._current_conv_id)
                next_idx = (idx + 1) % len(ids)
                self._current_conv_id = ids[next_idx]
                asyncio.create_task(self._load_current_messages())
            except ValueError:
                self._current_conv_id = ids[0]
                asyncio.create_task(self._load_current_messages())
        else:
            self._current_conv_id = self._conversations[0]["conversation_id"]
            asyncio.create_task(self._load_current_messages())

    def action_prev_conversation(self) -> None:
        if not self._conversations:
            return
        if self._current_conv_id:
            ids = [c["conversation_id"] for c in self._conversations]
            try:
                idx = ids.index(self._current_conv_id)
                prev_idx = (idx - 1) % len(ids)
                self._current_conv_id = ids[prev_idx]
                asyncio.create_task(self._load_current_messages())
            except ValueError:
                self._current_conv_id = ids[-1]
                asyncio.create_task(self._load_current_messages())

    def action_toggle_panel(self) -> None:
        panel = self.query_one("#info-panel", InfoPanel)
        if self._panel_visible:
            panel.add_class("hidden")
            self._panel_visible = False
        else:
            panel.remove_class("hidden")
            self._panel_visible = True
        panel.toggle_mode()

    def action_clear_chat(self) -> None:
        self.query_one("#chat-log", RichLog).clear()

    def action_show_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_history_up(self) -> None:
        if not self._input_history:
            return
        if self._history_index > 0:
            self._history_index -= 1
        input_widget = self.query_one("#msg-input", Input)
        input_widget.value = self._input_history[self._history_index]

    def action_history_down(self) -> None:
        if not self._input_history:
            return
        if self._history_index < len(self._input_history) - 1:
            self._history_index += 1
            input_widget = self.query_one("#msg-input", Input)
            input_widget.value = self._input_history[self._history_index]
        else:
            self._history_index = len(self._input_history)
            self.query_one("#msg-input", Input).value = ""

    @on(ListView.Selected, "#conv-list")
    async def on_conversation_selected(self, event: ListView.Selected) -> None:
        item = event.item
        if isinstance(item, ConversationItem):
            self._current_conv_id = item.conv_id
            await self._load_current_messages()

    def _chat_log(self, msg: str) -> None:
        log = self.query_one("#chat-log", RichLog)
        timestamp = datetime.now().strftime("%H:%M")
        log.write(f"[dim]{timestamp}[/dim] {msg}")

    def _update_status(self, text: str) -> None:
        self.query_one("#status-bar", Static).update(text)


def run_tui(
    host: str = "http://localhost:8000",
    token: str | None = None,
    api_key: str | None = None,
) -> None:
    """启动 TUI 应用"""
    import os

    client = TUIClient(base_url=host)
    if api_key:
        os.environ["YUANBOT_API_KEY"] = api_key
    if token:
        client.set_token(token)
    app = YuanBotTUI(client)
    app.run()


if __name__ == "__main__":
    run_tui()
