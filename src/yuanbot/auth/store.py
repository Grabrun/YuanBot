"""用户与会话存储

基于 JSON 文件的持久化存储，支持用户、会话和消息。

设计参考: user-interface-system.md 第3节
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import bcrypt
import structlog

from yuanbot.auth.models import (
    Conversation,
    ConversationMessage,
    User,
    UserRole,
)

logger = structlog.get_logger(__name__)


class UserStore:
    """用户存储

    基于 JSON 文件的用户持久化。
    文件位置: data/users.json
    """

    def __init__(self, data_dir: str | Path = "data"):
        self._data_dir = Path(data_dir)
        self._users_file = self._data_dir / "users.json"
        self._users: dict[str, User] = {}  # user_id -> User
        self._username_index: dict[str, str] = {}  # username -> user_id
        self._api_key_index: dict[str, str] = {}  # api_key -> user_id
        self._loaded = False

    async def initialize(self) -> None:
        """初始化存储，加载已有数据"""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._load()
        self._loaded = True
        logger.info("user_store_initialized", user_count=len(self._users))

    def _load(self) -> None:
        """从文件加载用户数据"""
        if not self._users_file.exists():
            return
        try:
            with open(self._users_file) as f:
                data = json.load(f)
            for item in data:
                user = User(**item)
                self._users[user.user_id] = user
                self._username_index[user.username] = user.user_id
                if user.api_key:
                    self._api_key_index[user.api_key] = user.user_id
        except Exception as e:
            logger.error("user_store_load_error", error=str(e))

    def _save(self) -> None:
        """持久化用户数据到文件"""
        try:
            data = [u.model_dump(mode="json") for u in self._users.values()]
            with open(self._users_file, "w") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            logger.error("user_store_save_error", error=str(e))

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            raise RuntimeError("UserStore not initialized. Call initialize() first.")

    # ── 用户 CRUD ─────────────────────────────

    def create_user(
        self,
        username: str,
        password: str,
        display_name: str = "",
        role: UserRole | str = UserRole.USER,
    ) -> User:
        """创建新用户

        Args:
            username: 用户名（唯一）
            password: 明文密码（存储前 bcrypt 哈希）
            display_name: 显示名称
            role: 用户角色（UserRole 枚举或字符串 "admin"/"user"）

        Returns:
            创建的用户对象

        Raises:
            ValueError: 用户名已存在
        """
        self._ensure_loaded()
        if username in self._username_index:
            raise ValueError(f"Username '{username}' already exists")

        # 支持字符串或枚举
        if isinstance(role, str):
            role = UserRole(role)

        password_hash = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

        user = User(
            username=username,
            display_name=display_name or username,
            role=role,
            password_hash=password_hash,
        )

        self._users[user.user_id] = user
        self._username_index[username] = user.user_id
        self._save()

        logger.info("user_created", username=username, role=role.value)
        return user

    def get_user(self, user_id: str) -> User | None:
        """按 user_id 获取用户"""
        self._ensure_loaded()
        return self._users.get(user_id)

    def get_user_by_username(self, username: str) -> User | None:
        """按用户名获取用户"""
        self._ensure_loaded()
        uid = self._username_index.get(username)
        if uid:
            return self._users.get(uid)
        return None

    def get_user_by_api_key(self, api_key: str) -> User | None:
        """按 API Key 获取用户"""
        self._ensure_loaded()
        uid = self._api_key_index.get(api_key)
        if uid:
            return self._users.get(uid)
        return None

    def list_users(self) -> list[User]:
        """列出所有用户"""
        self._ensure_loaded()
        return list(self._users.values())

    def update_user(self, user: User) -> None:
        """更新用户信息"""
        self._ensure_loaded()
        old = self._users.get(user.user_id)
        if old:
            # 更新索引
            if old.username != user.username:
                self._username_index.pop(old.username, None)
                self._username_index[user.username] = user.user_id
            if old.api_key != user.api_key:
                if old.api_key:
                    self._api_key_index.pop(old.api_key, None)
                if user.api_key:
                    self._api_key_index[user.api_key] = user.user_id

        self._users[user.user_id] = user
        self._save()

    def delete_user(self, user_id: str) -> bool:
        """删除用户

        Returns:
            True 如果删除成功，False 如果用户不存在
        """
        self._ensure_loaded()
        user = self._users.pop(user_id, None)
        if not user:
            return False
        self._username_index.pop(user.username, None)
        if user.api_key:
            self._api_key_index.pop(user.api_key, None)
        self._save()
        logger.info("user_deleted", username=user.username)
        return True

    def verify_password(self, username: str, password: str) -> User | None:
        """验证用户名密码

        Returns:
            验证通过返回 User，否则返回 None
        """
        self._ensure_loaded()
        user = self.get_user_by_username(username)
        if not user:
            return None
        if not user.enabled:
            return None
        if not user.password_hash:
            return None
        if bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8")):
            return user
        return None

    def set_api_key(self, user_id: str) -> str:
        """为用户生成 API Key

        Returns:
            生成的 API Key
        """
        self._ensure_loaded()
        user = self._users.get(user_id)
        if not user:
            raise ValueError(f"User '{user_id}' not found")

        # 移除旧索引
        if user.api_key:
            self._api_key_index.pop(user.api_key, None)

        api_key = f"yuan_{uuid.uuid4().hex}"
        user.api_key = api_key
        self._api_key_index[api_key] = user_id
        self._save()

        logger.info("api_key_generated", username=user.username)
        return api_key

    def revoke_api_key(self, user_id: str) -> bool:
        """吊销用户的 API Key

        Returns:
            True 如果成功吊销
        """
        self._ensure_loaded()
        user = self._users.get(user_id)
        if not user or not user.api_key:
            return False

        self._api_key_index.pop(user.api_key, None)
        user.api_key = None
        self._save()
        logger.info("api_key_revoked", username=user.username)
        return True

    def record_login(self, user: User) -> None:
        """记录登录时间"""
        user.last_login = datetime.now()
        self.update_user(user)

    @property
    def user_count(self) -> int:
        return len(self._users)

    @property
    def admin_count(self) -> int:
        return sum(1 for u in self._users.values() if u.role == UserRole.ADMIN)


class ConversationStore:
    """会话存储

    基于 JSON 文件的会话和消息持久化。
    文件位置: data/conversations.json, data/messages_{conversation_id}.json
    """

    def __init__(self, data_dir: str | Path = "data"):
        self._data_dir = Path(data_dir)
        self._conversations_file = self._data_dir / "conversations.json"
        self._conversations: dict[str, Conversation] = {}
        self._messages: dict[str, list[ConversationMessage]] = {}
        self._user_conversations: dict[str, list[str]] = {}  # user_id -> [conv_id]
        self._loaded = False

    async def initialize(self) -> None:
        """初始化存储"""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._load()
        self._loaded = True
        logger.info(
            "conversation_store_initialized",
            conversation_count=len(self._conversations),
        )

    def _load(self) -> None:
        """加载会话数据"""
        if not self._conversations_file.exists():
            return
        try:
            with open(self._conversations_file) as f:
                data = json.load(f)
            for item in data:
                conv = Conversation(**item)
                self._conversations[conv.conversation_id] = conv
                self._user_conversations.setdefault(conv.user_id, []).append(
                    conv.conversation_id
                )
                # 加载消息
                self._load_messages(conv.conversation_id)
        except Exception as e:
            logger.error("conversation_store_load_error", error=str(e))

    def _load_messages(self, conversation_id: str) -> None:
        """加载单个会话的消息"""
        msg_file = self._data_dir / f"messages_{conversation_id}.json"
        if not msg_file.exists():
            self._messages[conversation_id] = []
            return
        try:
            with open(msg_file) as f:
                data = json.load(f)
            self._messages[conversation_id] = [ConversationMessage(**m) for m in data]
        except Exception:
            self._messages[conversation_id] = []

    def _save_conversations(self) -> None:
        """保存会话列表"""
        try:
            data = [c.model_dump(mode="json") for c in self._conversations.values()]
            with open(self._conversations_file, "w") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            logger.error("conversation_save_error", error=str(e))

    def _save_messages(self, conversation_id: str) -> None:
        """保存单个会话的消息"""
        messages = self._messages.get(conversation_id, [])
        msg_file = self._data_dir / f"messages_{conversation_id}.json"
        try:
            data = [m.model_dump(mode="json") for m in messages]
            with open(msg_file, "w") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            logger.error("messages_save_error", conversation_id=conversation_id, error=str(e))

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            raise RuntimeError("ConversationStore not initialized.")

    # ── 会话 CRUD ─────────────────────────────

    def create_conversation(self, user_id: str, title: str = "新会话") -> Conversation:
        """创建新会话"""
        self._ensure_loaded()
        conv = Conversation(user_id=user_id, title=title)
        self._conversations[conv.conversation_id] = conv
        self._messages[conv.conversation_id] = []
        self._user_conversations.setdefault(user_id, []).append(conv.conversation_id)
        self._save_conversations()
        return conv

    def get_conversation(
        self, conversation_id: str, user_id: str | None = None
    ) -> Conversation | None:
        """获取会话（可选校验归属）

        Args:
            conversation_id: 会话 ID
            user_id: 如果提供，校验会话归属

        Returns:
            会话对象，不存在或归属不匹配返回 None
        """
        self._ensure_loaded()
        conv = self._conversations.get(conversation_id)
        if not conv:
            return None
        if user_id and conv.user_id != user_id:
            return None
        return conv

    def list_conversations(self, user_id: str) -> list[Conversation]:
        """列出用户的所有会话"""
        self._ensure_loaded()
        conv_ids = self._user_conversations.get(user_id, [])
        convs = [self._conversations[cid] for cid in conv_ids if cid in self._conversations]
        return sorted(convs, key=lambda c: c.updated_at, reverse=True)

    def delete_conversation(self, conversation_id: str, user_id: str) -> bool:
        """删除会话（校验归属）

        Returns:
            True 如果删除成功
        """
        self._ensure_loaded()
        conv = self._conversations.get(conversation_id)
        if not conv or conv.user_id != user_id:
            return False

        del self._conversations[conversation_id]
        self._messages.pop(conversation_id, None)
        conv_ids = self._user_conversations.get(user_id, [])
        if conversation_id in conv_ids:
            conv_ids.remove(conversation_id)

        self._save_conversations()
        # 清理消息文件
        msg_file = self._data_dir / f"messages_{conversation_id}.json"
        msg_file.unlink(missing_ok=True)
        return True

    # ── 消息 CRUD ─────────────────────────────

    def add_message(
        self,
        conversation_id: str,
        user_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> ConversationMessage | None:
        """添加消息到会话

        Returns:
            创建的消息，如果会话不存在或归属不匹配返回 None
        """
        self._ensure_loaded()
        conv = self.get_conversation(conversation_id, user_id)
        if not conv:
            return None

        msg = ConversationMessage(
            conversation_id=conversation_id,
            user_id=user_id,
            role=role,
            content=content,
            metadata=metadata or {},
        )
        self._messages.setdefault(conversation_id, []).append(msg)

        # 更新会话
        conv.message_count += 1
        conv.updated_at = datetime.now()

        # 自动标题：使用第一条用户消息的前20个字符
        if conv.title == "新会话" and role == "user":
            conv.title = content[:20] + ("..." if len(content) > 20 else "")

        self._save_conversations()
        self._save_messages(conversation_id)
        return msg

    def get_messages(
        self,
        conversation_id: str,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ConversationMessage]:
        """获取会话消息（校验归属）

        Args:
            conversation_id: 会话 ID
            user_id: 用户 ID（校验归属）
            limit: 最大返回数
            offset: 偏移量

        Returns:
            消息列表，会话不存在或归属不匹配返回空列表
        """
        self._ensure_loaded()
        conv = self.get_conversation(conversation_id, user_id)
        if not conv:
            return []

        messages = self._messages.get(conversation_id, [])
        return messages[offset: offset + limit]

    def get_recent_messages(
        self,
        conversation_id: str,
        user_id: str,
        limit: int = 20,
    ) -> list[ConversationMessage]:
        """获取最近的消息"""
        messages = self.get_messages(conversation_id, user_id, limit=10000)
        return messages[-limit:]

    def search_messages(
        self,
        user_id: str,
        query: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """跨会话全文搜索消息

        在用户所有会话的消息内容中搜索关键词（大小写不敏感）。

        Args:
            user_id: 用户 ID
            query: 搜索关键词
            limit: 最大返回数
            offset: 偏移量

        Returns:
            匹配的消息列表，每条包含 conversation_id, title, message 字段
        """
        self._ensure_loaded()
        query_lower = query.lower()
        results: list[dict[str, Any]] = []

        conv_ids = self._user_conversations.get(user_id, [])
        for cid in conv_ids:
            conv = self._conversations.get(cid)
            if not conv:
                continue
            messages = self._messages.get(cid, [])
            results.extend(
                {
                    "conversation_id": cid,
                    "conversation_title": conv.title,
                    "message_id": msg.message_id,
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat(),
                }
                for msg in messages
                if query_lower in msg.content.lower()
            )

        # 按时间倒序排列
        results.sort(key=lambda r: r["timestamp"], reverse=True)
        return results[offset: offset + limit]

    def export_conversation_markdown(
        self,
        conversation_id: str,
        user_id: str,
    ) -> str | None:
        """导出会话为 Markdown 格式

        Args:
            conversation_id: 会话 ID
            user_id: 用户 ID（校验归属）

        Returns:
            Markdown 字符串，会话不存在或归属不匹配返回 None
        """
        self._ensure_loaded()
        conv = self.get_conversation(conversation_id, user_id)
        if not conv:
            return None

        messages = self._messages.get(conversation_id, [])
        lines: list[str] = []
        lines.append(f"# {conv.title}")
        lines.append("")
        lines.append(f"创建时间: {conv.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"消息数: {len(messages)}")
        lines.append("")
        lines.append("---")
        lines.append("")

        for msg in messages:
            role_label = "👤 用户" if msg.role == "user" else "🤖 助手"
            ts = msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            lines.append(f"**{role_label}** ({ts})")
            lines.append("")
            lines.append(msg.content)
            lines.append("")
            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    def export_conversation_json(
        self,
        conversation_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        """导出会话为 JSON 格式

        Args:
            conversation_id: 会话 ID
            user_id: 用户 ID（校验归属）

        Returns:
            会话数据字典，会话不存在或归属不匹配返回 None
        """
        self._ensure_loaded()
        conv = self.get_conversation(conversation_id, user_id)
        if not conv:
            return None

        messages = self._messages.get(conversation_id, [])
        return {
            "conversation_id": conv.conversation_id,
            "title": conv.title,
            "created_at": conv.created_at.isoformat(),
            "updated_at": conv.updated_at.isoformat(),
            "messages": [
                {
                    "message_id": m.message_id,
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp.isoformat(),
                    "metadata": m.metadata,
                }
                for m in messages
            ],
        }

    @property
    def conversation_count(self) -> int:
        return len(self._conversations)

    @property
    def total_message_count(self) -> int:
        return sum(len(msgs) for msgs in self._messages.values())
