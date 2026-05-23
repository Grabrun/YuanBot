"""🌸 缘·Bot TUI 终端聊天界面

基于 Textual 框架的终端聊天客户端。
通过 HTTP API 与 YuanBot 后端通信。

启动方式:
    python -m yuanbot.tui [--host URL] [--token TOKEN] [--api-key KEY]

快捷键:
    Ctrl+N       新建会话
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

    BINDINGS = [
        Binding("escape", "cancel", "取消"),
    ]

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
        width: 60;
        height: auto;
        max-height: 30;
        border: solid $primary;
        padding: 1 2;
        background: $surface;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "关闭"),
    ]

    HELP_TEXT = """\
# 🌸 缘·Bot TUI 帮助

## 快捷键
- **Ctrl+N** — 新建会话
- **Ctrl+Q** — 退出
- **Ctrl+L** — 清屏
- **F1** — 帮助
- **Esc** — 关闭弹窗

## 命令
- `/help` — 显示帮助
- `/new` — 新建会话
- `/list` — 列出会话
- `/switch <n>` — 切换到第 n 个会话
- `/delete` — 删除当前会话
- `/me` — 显示用户信息
- `/clear` — 清屏
- `/quit` — 退出

## 使用说明
直接输入消息即可与 AI 对话。
支持多会话，每个会话保留独立上下文。
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
        display = f"{title[:20]}  [{message_count}条]"
        self._label = Label(display)

    def compose(self) -> ComposeResult:
        yield self._label


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
        Binding("ctrl+n", "new_conversation", "新建会话"),
        Binding("ctrl+q", "quit", "退出"),
        Binding("ctrl+l", "clear_chat", "清屏"),
        Binding("f1", "show_help", "帮助", show=True),
    ]

    def __init__(self, client: TUIClient):
        super().__init__()
        self._client = client
        self._user: dict | None = None
        self._conversations: list[dict] = []
        self._current_conv_id: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Label("📌 会话列表", id="sidebar-title")
                yield ListView(id="conv-list")
                yield Static("[dim]Ctrl+N 新建[/dim]")
            with Vertical(id="chat-area"):
                yield RichLog(id="chat-log", wrap=True, markup=True, highlight=True)
                with Horizontal(id="input-area"):
                    yield Input(placeholder="输入消息或 /help ...", id="msg-input")
        yield Static("未连接", id="status-bar")
        yield Footer()

    async def on_mount(self) -> None:
        """应用启动"""
        # 尝试自动登录（API Key 或本地信任）
        await self._try_auto_login()

    async def _try_auto_login(self) -> None:
        """尝试自动登录"""
        import os

        api_key = os.environ.get("YUANBOT_API_KEY")
        if api_key:
            try:
                await self._client.login_with_api_key(api_key)
                await self._on_login_success()
                return
            except TUIClientError:
                pass

        # 显示登录界面
        await self._show_login()

    async def _show_login(self) -> None:
        """显示登录界面"""
        result = await self.push_screen_wait(LoginScreen(self._client))
        if result:
            await self._on_login_success()
        else:
            self.exit("未登录")

    async def _on_login_success(self) -> None:
        """登录成功后初始化"""
        try:
            self._user = await self._client.get_me()
            self._update_status(f"已登录: {self._user['display_name']} ({self._user['role']})")

            # 加载会话列表
            await self._load_conversations()

            # 聚焦输入框
            self.query_one("#msg-input", Input).focus()

        except TUIClientError as e:
            self._chat_log(f"[red]初始化失败: {e}[/red]")

    async def _load_conversations(self) -> None:
        """加载会话列表"""
        try:
            self._conversations = await self._client.list_conversations()
            list_view = self.query_one("#conv-list", ListView)
            await list_view.clear()

            for i, conv in enumerate(self._conversations):
                updated = conv.get("updated_at", "")[:16]
                item = ConversationItem(
                    conv["conversation_id"],
                    conv["title"],
                    updated,
                    conv.get("message_count", 0),
                )
                await list_view.append(item)

            # 自动选择第一个
            if self._conversations and not self._current_conv_id:
                self._current_conv_id = self._conversations[0]["conversation_id"]
                await self._load_current_messages()

        except TUIClientError as e:
            self._chat_log(f"[red]加载会话失败: {e}[/red]")

    async def _load_current_messages(self) -> None:
        """加载当前会话的消息"""
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
                else:
                    self._chat_log(f"[bold green]🌸 小缘:[/bold green] {escape(content)}")

        except TUIClientError as e:
            self._chat_log(f"[red]加载消息失败: {e}[/red]")

    @on(Input.Submitted, "#msg-input")
    async def on_message_sent(self, event: Input.Submitted) -> None:
        """处理用户输入"""
        text = event.value.strip()
        if not text:
            return

        # 清空输入框
        event.input.value = ""

        # 处理命令
        if text.startswith("/"):
            await self._handle_command(text)
            return

        # 发送消息
        await self._send_chat_message(text)

    async def _send_chat_message(self, text: str) -> None:
        """发送聊天消息"""
        self._chat_log(f"[bold blue]你:[/bold blue] {escape(text)}")
        self._update_status("AI 思考中...")

        try:
            result = await self._client.send_message(
                content=text,
                conversation_id=self._current_conv_id,
            )

            ai_content = result["ai_message"]["content"]
            self._chat_log(f"[bold green]🌸 小缘:[/bold green] {escape(ai_content)}")

            # 更新会话 ID（如果是新会话）
            if not self._current_conv_id:
                self._current_conv_id = result["conversation_id"]
                await self._load_conversations()

            self._update_status(f"已登录: {self._user['display_name']}")

        except TUIClientError as e:
            self._chat_log(f"[red]发送失败: {e}[/red]")
            self._update_status("发送失败")

    async def _handle_command(self, cmd: str) -> None:
        """处理斜杠命令"""
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

        elif command == "/clear":
            self.query_one("#chat-log", RichLog).clear()

        elif command == "/quit":
            self.exit()

        else:
            self._chat_log(f"[red]未知命令: {command}[/red]")

    def action_new_conversation(self) -> None:
        """新建会话"""
        asyncio.create_task(self._handle_command("/new"))

    def action_clear_chat(self) -> None:
        """清屏"""
        self.query_one("#chat-log", RichLog).clear()

    def action_show_help(self) -> None:
        """显示帮助"""
        self.push_screen(HelpScreen())

    @on(ListView.Selected, "#conv-list")
    async def on_conversation_selected(self, event: ListView.Selected) -> None:
        """选择会话"""
        item = event.item
        if isinstance(item, ConversationItem):
            self._current_conv_id = item.conv_id
            await self._load_current_messages()

    def _chat_log(self, msg: str) -> None:
        """写入聊天日志"""
        log = self.query_one("#chat-log", RichLog)
        timestamp = datetime.now().strftime("%H:%M")
        log.write(f"[dim]{timestamp}[/dim] {msg}")

    def _update_status(self, text: str) -> None:
        """更新状态栏"""
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
