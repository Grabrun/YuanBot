"""NapCat (OneBot v11) QQ 通道适配器

基于 OneBot v11 协议标准，支持 NapCat QQ 实现。
NapCat 通过反向 WebSocket 主动连接 YuanBot，一个连接搞定收发。

通讯方式:
  - 反向 WS (主要): NapCat 主动连接 YuanBot 的 WS Server
    - 事件上报、API 调用均走此连接
  - HTTP API (备选): WS 不可用时通过 HTTP 调用接口

协议文档：https://napcat.apifox.cn
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any

import httpx
import structlog

from yuanbot.adapters.channel.base import BaseChannelAdapter
from yuanbot.core.types import (
    BotResponse,
    ChannelConfig,
    ContentType,
    MessageContent,
    SendResult,
    UserMessage,
)

logger = structlog.get_logger(__name__)

# ── 常量 ──────────────────────────────────────

API_TIMEOUT_S = 15
DOWNLOAD_TIMEOUT_S = 30

# NapCat 返回码
RETCODE_SUCCESS = 0
RETCODE_BAD_REQUEST = 1400


# ── 消息段类型 ────────────────────────────────


class MessageSegmentType(StrEnum):
    """OneBot v11 消息段类型"""

    TEXT = "text"
    FACE = "face"
    IMAGE = "image"
    RECORD = "record"
    VIDEO = "video"
    AT = "at"
    RPS = "rps"
    DICE = "dice"
    SHAKE = "shake"
    POKE = "poke"
    REPLY = "reply"
    FORWARD = "forward"
    NODE = "node"
    XML = "xml"
    JSON = "json"
    MARKDOWN = "markdown"
    MUSIC = "music"
    CUSTOM_MUSIC = "custom_music"
    LOCATION = "location"
    CONTACT = "contact"
    MINI_APP = "mini_app"
    MFACE = "mface"
    FILE = "file"
    ONLINE_FILE = "onlinefile"
    FLASH_TRANSFER = "flash_transfer"
    SHARE_PC = "share_pc"


# ── 事件类型 ──────────────────────────────────


class PostType(StrEnum):
    """OneBot 事件类型"""

    MESSAGE = "message"
    MESSAGE_SENT = "message_sent"
    NOTICE = "notice"
    REQUEST = "request"
    META_EVENT = "meta_event"


class MessageType(StrEnum):
    """OneBot 消息类型"""

    PRIVATE = "private"
    GROUP = "group"


class NoticeType(StrEnum):
    """OneBot 通知事件类型"""

    GROUP_INCREASE = "group_increase"
    GROUP_DECREASE = "group_decrease"
    GROUP_ADMIN = "group_admin"
    GROUP_BAN = "group_ban"
    GROUP_RECALL = "group_recall"
    FRIEND_ADD = "friend_add"
    FRIEND_RECALL = "friend_recall"
    NOTIFY = "notify"
    GROUP_LIFT_BAN = "group_lift_ban"
    GROUP_CARD = "group_card"
    LUCKY_KING = "lucky_king"
    HONOR = "honor"
    POKE = "poke"
    TITLE = "title"
    ESSENCE = "essence"


class RequestType(StrEnum):
    """OneBot 请求事件类型"""

    FRIEND = "friend"
    GROUP = "group"


# ── 工具函数 ──────────────────────────────────


def build_text_segment(text: str) -> dict[str, Any]:
    """构建纯文本消息段"""
    return {"type": MessageSegmentType.TEXT, "data": {"text": text}}


def build_image_segment(file: str, cache: bool = True) -> dict[str, Any]:
    """构建图片消息段"""
    return {"type": MessageSegmentType.IMAGE, "data": {"file": file, "cache": cache}}


def build_record_segment(file: str, cache: bool = True) -> dict[str, Any]:
    """构建语音消息段"""
    return {"type": MessageSegmentType.RECORD, "data": {"file": file, "cache": cache}}


def build_video_segment(file: str, cache: bool = True) -> dict[str, Any]:
    """构建视频消息段"""
    return {"type": MessageSegmentType.VIDEO, "data": {"file": file, "cache": cache}}


def build_file_segment(file: str, name: str | None = None) -> dict[str, Any]:
    """构建文件消息段"""
    data: dict[str, Any] = {"file": file}
    if name:
        data["name"] = name
    return {"type": MessageSegmentType.FILE, "data": data}


def build_at_segment(qq: str | int) -> dict[str, Any]:
    """构建 @ 消息段"""
    return {"type": MessageSegmentType.AT, "data": {"qq": str(qq)}}


def build_reply_segment(msg_id: int | str) -> dict[str, Any]:
    """构建回复/引用消息段"""
    return {"type": MessageSegmentType.REPLY, "data": {"id": str(msg_id)}}


def build_forward_segment(res_id: str) -> dict[str, Any]:
    """构建合并转发消息段"""
    return {"type": MessageSegmentType.FORWARD, "data": {"id": res_id}}


def build_node_segment(
    user_id: str | int,
    nickname: str,
    content: list[dict[str, Any]] | str,
) -> dict[str, Any]:
    """构建合并转发节点消息段"""
    return {
        "type": MessageSegmentType.NODE,
        "data": {
            "user_id": str(user_id),
            "nickname": nickname,
            "content": content,
        },
    }


def build_markdown_segment(data: str) -> dict[str, Any]:
    """构建 Markdown 消息段"""
    return {"type": MessageSegmentType.MARKDOWN, "data": {"data": data}}


def build_xml_segment(data: str) -> dict[str, Any]:
    """构建 XML 消息段"""
    return {"type": MessageSegmentType.XML, "data": {"data": data}}


def build_json_segment(data: str) -> dict[str, Any]:
    """构建 JSON 消息段"""
    return {"type": MessageSegmentType.JSON, "data": {"data": data}}


def build_face_segment(face_id: int) -> dict[str, Any]:
    """构建 QQ 表情消息段"""
    return {"type": MessageSegmentType.FACE, "data": {"id": str(face_id)}}


def build_music_segment(source: str, song_id: str) -> dict[str, Any]:
    """构建音乐分享消息段"""
    return {"type": MessageSegmentType.MUSIC, "data": {"type": source, "id": song_id}}


def build_custom_music_segment(
    url: str,
    audio: str,
    title: str,
    image: str | None = None,
) -> dict[str, Any]:
    """构建自定义音乐消息段"""
    data: dict[str, Any] = {"url": url, "audio": audio, "title": title}
    if image:
        data["image"] = image
    return {"type": MessageSegmentType.CUSTOM_MUSIC, "data": data}


def build_location_segment(
    lat: float,
    lng: float,
    title: str | None = None,
    content: str | None = None,
) -> dict[str, Any]:
    """构建位置消息段"""
    data: dict[str, Any] = {"lat": str(lat), "lng": str(lng)}
    if title:
        data["title"] = title
    if content:
        data["content"] = content
    return {"type": MessageSegmentType.LOCATION, "data": data}


def build_contact_segment(contact_type: str, target_id: str) -> dict[str, Any]:
    """构建推荐好友/群消息段"""
    return {
        "type": MessageSegmentType.CONTACT,
        "data": {"type": contact_type, "id": target_id},
    }


# ── 适配器主类 ────────────────────────────────


class NapCatAdapter(BaseChannelAdapter):
    """NapCat (OneBot v11) QQ 通道适配器

    实现 ChannelAdapter 接口，桥接 NapCat QQ 与 YuanBot。
    NapCat 通过反向 WebSocket 主动连接 YuanBot，一个连接搞定收发。

    通讯方式:
      - 反向 WS (主要): NapCat 主动连接 YuanBot 的 WS Server
        - 事件上报、API 调用均走此连接
      - HTTP API (备选): WS 不可用时通过 HTTP 调用接口
    """

    def __init__(self) -> None:
        super().__init__()
        # 反向 WS 配置（NapCat 主动连接过来）
        self._reverse_ws_host: str = "0.0.0.0"
        self._reverse_ws_port: int = 8080
        self._reverse_ws_path: str = "/onebot/v11/ws"
        self._reverse_ws_token: str = ""

        # HTTP API 配置（发送消息/调用接口）
        self._http_host: str = "127.0.0.1"
        self._http_port: int = 3000
        self._http_token: str = ""
        self._bot_qq: str = ""

        self._client: httpx.AsyncClient | None = None
        self._callback: Callable[[UserMessage], Awaitable[BotResponse]] | None = None
        self._running = False

        # WS 服务端状态
        self._ws_server: asyncio.Server | None = None
        self._ws_reader: asyncio.StreamReader | None = None
        self._ws_writer: asyncio.StreamWriter | None = None
        self._ws_connected: bool = False
        self._ws_read_task: asyncio.Task | None = None
        self._ws_connect_event: asyncio.Event = asyncio.Event()

        # 请求-响应匹配（echo -> Future），通过反向 WS 调用 API 时使用
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._echo_counter: int = 0
        self._echo_lock: asyncio.Lock = asyncio.Lock()

        # WebSocket 协议常量
        self._WS_GUID = "258EAFA5-E914-47DA-95CA-5AB9F11DCB11"

        # 最近消息的上下文缓存（用于被动回复的消息 ID 查找）
        self._msg_id_cache: dict[str, dict[str, Any]] = {}

    # ── ChannelAdapter 接口实现 ────────────────

    @property
    def platform_name(self) -> str:
        return "napcat"

    @property
    def supported_content_types(self) -> list[ContentType]:
        return [
            ContentType.TEXT,
            ContentType.IMAGE,
            ContentType.VOICE,
            ContentType.VIDEO,
            ContentType.FILE,
        ]

    @property
    def base_url(self) -> str:
        """构建 NapCat HTTP API 基础 URL"""
        return f"http://{self._http_host}:{self._http_port}"

    async def initialize(self, config: ChannelConfig) -> None:
        """初始化适配器

        Args:
            config: 通道配置，包含反向 WebSocket 和 HTTP 设置。
        """
        cfg = config.config

        # 反向 WS 配置
        self._reverse_ws_host = cfg.get("reverse_ws_host", "0.0.0.0")
        self._reverse_ws_port = cfg.get("reverse_ws_port", 8080)
        self._reverse_ws_path = cfg.get("reverse_ws_path", "/onebot/v11/ws")
        self._reverse_ws_token = cfg.get("reverse_ws_token", "")

        # HTTP API 配置
        self._http_host = cfg.get("http_host", "127.0.0.1")
        self._http_port = cfg.get("http_port", 3000)
        self._http_token = cfg.get("http_token", "")

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(API_TIMEOUT_S),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

        # 通过 HTTP 获取机器人信息
        await self._fetch_bot_info()

        logger.info(
            "napcat_adapter_initialized",
            reverse_ws_host=self._reverse_ws_host,
            reverse_ws_port=self._reverse_ws_port,
            reverse_ws_path=self._reverse_ws_path,
            http_host=self._http_host,
            http_port=self._http_port,
            bot_qq=self._bot_qq,
        )

    async def listen(
        self,
        callback: Callable[[UserMessage], Awaitable[BotResponse]],
    ) -> None:
        """启动反向 WebSocket 服务端，等待 NapCat 连接

        YuanBot 作为 WebSocket 服务端，等待 NapCat 主动连接。
        连接建立后，一个连接搞定一切：
          - 事件上报（NapCat → YuanBot）
          - API 调用（YuanBot → NapCat，带 echo 匹配）

        Args:
            callback: 收到用户消息后的回调函数。
        """
        if not self._client:
            raise RuntimeError("NapCat adapter not initialized. Call initialize() first.")

        self._callback = callback
        self._running = True

        # 启动 WebSocket 服务端
        self._ws_server = await asyncio.start_server(
            self._on_ws_connect,
            self._reverse_ws_host,
            self._reverse_ws_port,
        )

        addr = self._ws_server.sockets[0].getsockname()
        logger.info(
            "napcat_listen_started",
            host=self._reverse_ws_host,
            port=addr[1],
            path=self._reverse_ws_path,
        )

        # 持续服务
        async with self._ws_server:
            await self._ws_server.serve_forever()

    async def send_message(
        self,
        target_id: str,
        content: MessageContent,
    ) -> SendResult:
        """发送消息到指定目标

        target_id 格式:
          - 私聊: "private:user_id"
          - 群聊: "group:group_id"

        所有消息通过 HTTP API 发送。

        Args:
            target_id: 目标标识，格式为 "type:id"。
            content: 消息内容。

        Returns:
            SendResult: 发送结果。
        """
        if not self._client:
            return SendResult(success=False, error="Adapter not initialized")

        parts = target_id.split(":", 1)
        if len(parts) != 2:
            return SendResult(success=False, error=f"Invalid target_id format: {target_id}")

        target_type, target_value = parts

        if content.content_type == ContentType.TEXT:
            return await self.send_text(target_type, target_value, content.text or "")
        elif content.content_type == ContentType.IMAGE:
            return await self.send_image(
                target_type,
                target_value,
                content.media_url or "",
                media_data=content.media_data,
            )
        elif content.content_type == ContentType.VOICE:
            return await self.send_voice(
                target_type,
                target_value,
                content.media_url or "",
                media_data=content.media_data,
            )
        elif content.content_type == ContentType.VIDEO:
            return await self.send_video(
                target_type,
                target_value,
                content.media_url or "",
                media_data=content.media_data,
            )
        elif content.content_type == ContentType.FILE:
            return await self.send_file(
                target_type,
                target_value,
                content.media_url or "",
                filename=content.metadata.get("filename"),
                media_data=content.media_data,
            )
        else:
            return SendResult(
                success=False,
                error=f"Unsupported content type: {content.content_type}",
            )

    def get_platform_user_id(self, raw_event: Any) -> str:
        """从原始事件中提取平台用户 ID

        Args:
            raw_event: NapCat 上报的原始事件数据。

        Returns:
            str: 平台用户 ID（QQ 号）。
        """
        if isinstance(raw_event, dict):
            user_id = raw_event.get("user_id", "")
            if not user_id:
                user_id = raw_event.get("user_id", "")
            return str(user_id) if user_id else ""
        return str(raw_event)

    async def shutdown(self) -> None:
        """关闭适配器"""
        self._running = False

        # 关闭 WS 服务端
        if self._ws_server:
            self._ws_server.close()
            await self._ws_server.wait_closed()
            self._ws_server = None

        # 关闭当前 WS 连接
        if self._ws_writer:
            with contextlib.suppress(Exception):
                self._ws_writer.close()
                await self._ws_writer.wait_closed()
            self._ws_reader = None
            self._ws_writer = None
            self._ws_connected = False

        if self._ws_read_task and not self._ws_read_task.done():
            self._ws_read_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ws_read_task
            self._ws_read_task = None

        self._ws_connect_event.clear()

        # 取消所有待处理的 API 请求
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()

        if self._client:
            await self._client.aclose()
            self._client = None

        logger.info("napcat_adapter_shutdown")

    # ── 消息发送方法 ──────────────────────────

    async def send_text(
        self,
        target_type: str,
        target_value: str,
        text: str,
        reply_to: int | str | None = None,
    ) -> SendResult:
        """发送文本消息

        Args:
            target_type: 目标类型（"private" 或 "group"）。
            target_value: 目标值（用户 QQ 或群号）。
            text: 文本内容。长文本会自动分段发送。
            reply_to: 可选，要回复的消息 ID。

        Returns:
            SendResult: 发送结果。
        """
        chunks = self._split_text(text, max_len=2000)
        last_result = SendResult(success=False, error="No chunks")

        for chunk in chunks:
            segments: list[dict[str, Any]] = [build_text_segment(chunk)]
            if reply_to is not None:
                segments.insert(0, build_reply_segment(reply_to))

            last_result = await self._call_send_msg(target_type, target_value, segments)
            if not last_result.success:
                logger.error("napcat_send_text_failed", error=last_result.error)
                break
            # 后续分段不再带回复
            reply_to = None

        return last_result

    async def send_image(
        self,
        target_type: str,
        target_value: str,
        file: str,
        media_data: bytes | None = None,
        reply_to: int | str | None = None,
    ) -> SendResult:
        """发送图片消息

        file 可以是本地路径、网络 URL 或 Base64 编码。
        Base64 格式: base64://encoded_data

        Args:
            target_type: 目标类型。
            target_value: 目标值。
            file: 图片路径、URL 或 Base64。
            media_data: 可选，图片字节数据（优先使用）。
            reply_to: 可选，要回复的消息 ID。

        Returns:
            SendResult: 发送结果。
        """
        resolved_file = await self._resolve_media_file(file, media_data)
        if not resolved_file:
            return SendResult(success=False, error="Failed to resolve image file")

        segments: list[dict[str, Any]] = [build_image_segment(resolved_file)]
        if reply_to is not None:
            segments.insert(0, build_reply_segment(reply_to))

        return await self._call_send_msg(target_type, target_value, segments)

    async def send_voice(
        self,
        target_type: str,
        target_value: str,
        file: str,
        media_data: bytes | None = None,
        reply_to: int | str | None = None,
    ) -> SendResult:
        """发送语音消息

        Args:
            target_type: 目标类型。
            target_value: 目标值。
            file: 语音文件路径、URL 或 Base64。
            media_data: 可选，语音字节数据。
            reply_to: 可选，要回复的消息 ID。

        Returns:
            SendResult: 发送结果。
        """
        resolved_file = await self._resolve_media_file(file, media_data)
        if not resolved_file:
            return SendResult(success=False, error="Failed to resolve voice file")

        segments: list[dict[str, Any]] = [build_record_segment(resolved_file)]
        if reply_to is not None:
            segments.insert(0, build_reply_segment(reply_to))

        return await self._call_send_msg(target_type, target_value, segments)

    async def send_video(
        self,
        target_type: str,
        target_value: str,
        file: str,
        media_data: bytes | None = None,
        reply_to: int | str | None = None,
    ) -> SendResult:
        """发送视频消息

        Args:
            target_type: 目标类型。
            target_value: 目标值。
            file: 视频文件路径、URL 或 Base64。
            media_data: 可选，视频字节数据。
            reply_to: 可选，要回复的消息 ID。

        Returns:
            SendResult: 发送结果。
        """
        resolved_file = await self._resolve_media_file(file, media_data)
        if not resolved_file:
            return SendResult(success=False, error="Failed to resolve video file")

        segments: list[dict[str, Any]] = [build_video_segment(resolved_file)]
        if reply_to is not None:
            segments.insert(0, build_reply_segment(reply_to))

        return await self._call_send_msg(target_type, target_value, segments)

    async def send_file(
        self,
        target_type: str,
        target_value: str,
        file: str,
        filename: str | None = None,
        media_data: bytes | None = None,
    ) -> SendResult:
        """发送文件消息

        Args:
            target_type: 目标类型。
            target_value: 目标值。
            file: 文件路径、URL 或 Base64。
            filename: 可选，文件名。
            media_data: 可选，文件字节数据。

        Returns:
            SendResult: 发送结果。
        """
        resolved_file = await self._resolve_media_file(file, media_data)
        if not resolved_file:
            return SendResult(success=False, error="Failed to resolve file")

        segments: list[dict[str, Any]] = [build_file_segment(resolved_file, name=filename)]

        return await self._call_send_msg(target_type, target_value, segments)

    async def send_forward(
        self,
        target_type: str,
        target_value: str,
        nodes: list[dict[str, Any]],
    ) -> SendResult:
        """发送合并转发消息

        Args:
            target_type: 目标类型（"private" 或 "group"）。
            target_value: 目标值。
            nodes: 合并转发节点列表，每个节点需包含
                   user_id, nickname, content (消息段数组或字符串)。

        Returns:
            SendResult: 发送结果。
        """
        # 先创建合并转发消息
        if target_type == "group":
            result = await self._api_call(
                "send_group_forward_msg",
                {"group_id": target_value, "messages": nodes},
            )
        else:
            result = await self._api_call(
                "send_private_forward_msg",
                {"user_id": target_value, "messages": nodes},
            )

        if result.get("status") == "ok":
            forward_id = result.get("data", {}).get("forward_id", "")
            return SendResult(success=True, message_id=forward_id)
        return SendResult(
            success=False,
            error=result.get("wording", result.get("message", "Unknown error")),
        )

    async def delete_message(self, message_id: int | str) -> SendResult:
        """撤回消息（需要管理员或机器人自己的消息）

        Args:
            message_id: 要撤回的消息 ID。

        Returns:
            SendResult: 发送结果。
        """
        result = await self._api_call("delete_msg", {"message_id": message_id})
        if result.get("status") == "ok":
            return SendResult(success=True, message_id=str(message_id))
        return SendResult(
            success=False,
            error=result.get("wording", result.get("message", "Delete failed")),
        )

    # ── 群组操作 ──────────────────────────────

    async def get_group_list(self) -> list[dict[str, Any]]:
        """获取群列表

        Returns:
            list[dict]: 群列表，每个元素包含 group_id, group_name 等。
        """
        result = await self._api_call("get_group_list")
        return result.get("data", [])

    async def get_group_info(self, group_id: str | int) -> dict[str, Any]:
        """获取群信息

        Args:
            group_id: 群号。

        Returns:
            dict: 群信息。
        """
        result = await self._api_call("get_group_info", {"group_id": group_id})
        return result.get("data", {})

    async def get_group_member_list(self, group_id: str | int) -> list[dict[str, Any]]:
        """获取群成员列表

        Args:
            group_id: 群号。

        Returns:
            list[dict]: 成员列表。
        """
        result = await self._api_call("get_group_member_list", {"group_id": group_id})
        return result.get("data", [])

    async def get_group_member_info(
        self, group_id: str | int, user_id: str | int
    ) -> dict[str, Any]:
        """获取群成员信息

        Args:
            group_id: 群号。
            user_id: 用户 QQ。

        Returns:
            dict: 成员信息。
        """
        result = await self._api_call(
            "get_group_member_info",
            {"group_id": group_id, "user_id": user_id},
        )
        return result.get("data", {})

    async def set_group_ban(
        self,
        group_id: str | int,
        user_id: str | int,
        duration: int = 600,
    ) -> SendResult:
        """禁言群成员

        Args:
            group_id: 群号。
            user_id: 成员 QQ。
            duration: 禁言时长（秒），0 为解除禁言。

        Returns:
            SendResult: 操作结果。
        """
        result = await self._api_call(
            "set_group_ban",
            {"group_id": group_id, "user_id": user_id, "duration": duration},
        )
        if result.get("status") == "ok":
            return SendResult(success=True)
        return SendResult(
            success=False,
            error=result.get("wording", result.get("message", "Ban failed")),
        )

    async def set_group_whole_ban(self, group_id: str | int, enable: bool = True) -> SendResult:
        """全员禁言

        Args:
            group_id: 群号。
            enable: True=开启全员禁言，False=关闭。

        Returns:
            SendResult: 操作结果。
        """
        result = await self._api_call(
            "set_group_whole_ban",
            {"group_id": group_id, "enable": enable},
        )
        if result.get("status") == "ok":
            return SendResult(success=True)
        return SendResult(
            success=False,
            error=result.get("wording", result.get("message", "Whole ban failed")),
        )

    async def set_group_kick(
        self,
        group_id: str | int,
        user_id: str | int,
        reject_add_request: bool = False,
    ) -> SendResult:
        """踢出群成员

        Args:
            group_id: 群号。
            user_id: 成员 QQ。
            reject_add_request: 是否拒绝再次加群。

        Returns:
            SendResult: 操作结果。
        """
        result = await self._api_call(
            "set_group_kick",
            {
                "group_id": group_id,
                "user_id": user_id,
                "reject_add_request": reject_add_request,
            },
        )
        if result.get("status") == "ok":
            return SendResult(success=True)
        return SendResult(
            success=False,
            error=result.get("wording", result.get("message", "Kick failed")),
        )

    async def set_group_admin(
        self,
        group_id: str | int,
        user_id: str | int,
        enable: bool = True,
    ) -> SendResult:
        """设置群管理员

        Args:
            group_id: 群号。
            user_id: 成员 QQ。
            enable: True=设置为管理员，False=取消管理员。

        Returns:
            SendResult: 操作结果。
        """
        result = await self._api_call(
            "set_group_admin",
            {"group_id": group_id, "user_id": user_id, "enable": enable},
        )
        if result.get("status") == "ok":
            return SendResult(success=True)
        return SendResult(
            success=False,
            error=result.get("wording", result.get("message", "Set admin failed")),
        )

    async def get_group_notice(self, group_id: str | int) -> list[dict[str, Any]]:
        """获取群公告列表

        Args:
            group_id: 群号。

        Returns:
            list[dict]: 公告列表。
        """
        result = await self._api_call("get_group_notice", {"group_id": group_id})
        return result.get("data", [])

    async def send_group_notice(self, group_id: str | int, content: str) -> SendResult:
        """发送群公告

        Args:
            group_id: 群号。
            content: 公告内容。

        Returns:
            SendResult: 操作结果。
        """
        result = await self._api_call(
            "_send_group_notice",
            {"group_id": group_id, "content": content},
        )
        if result.get("status") == "ok":
            return SendResult(success=True)
        return SendResult(
            success=False,
            error=result.get("wording", result.get("message", "Notice failed")),
        )

    async def set_essence_msg(self, message_id: int | str) -> SendResult:
        """设置精华消息

        Args:
            message_id: 消息 ID。

        Returns:
            SendResult: 操作结果。
        """
        result = await self._api_call("set_essence_msg", {"message_id": message_id})
        if result.get("status") == "ok":
            return SendResult(success=True, message_id=str(message_id))
        return SendResult(
            success=False,
            error=result.get("wording", result.get("message", "Set essence failed")),
        )

    async def get_essence_msg_list(self, group_id: str | int) -> list[dict[str, Any]]:
        """获取群精华消息列表

        Args:
            group_id: 群号。

        Returns:
            list[dict]: 精华消息列表。
        """
        result = await self._api_call("get_essence_msg_list", {"group_id": group_id})
        return result.get("data", [])

    async def set_group_card(
        self,
        group_id: str | int,
        user_id: str | int,
        card: str = "",
    ) -> SendResult:
        """设置群名片

        Args:
            group_id: 群号。
            user_id: 成员 QQ。
            card: 群名片内容，空字符串表示清除。

        Returns:
            SendResult: 操作结果。
        """
        result = await self._api_call(
            "set_group_card",
            {"group_id": group_id, "user_id": user_id, "card": card},
        )
        if result.get("status") == "ok":
            return SendResult(success=True)
        return SendResult(
            success=False,
            error=result.get("wording", result.get("message", "Set card failed")),
        )

    async def set_group_name(self, group_id: str | int, group_name: str) -> SendResult:
        """设置群名称

        Args:
            group_id: 群号。
            group_name: 新群名。

        Returns:
            SendResult: 操作结果。
        """
        result = await self._api_call(
            "set_group_name",
            {"group_id": group_id, "group_name": group_name},
        )
        if result.get("status") == "ok":
            return SendResult(success=True)
        return SendResult(
            success=False,
            error=result.get("wording", result.get("message", "Set name failed")),
        )

    # ── 用户操作 ──────────────────────────────

    async def get_friend_list(self) -> list[dict[str, Any]]:
        """获取好友列表

        Returns:
            list[dict]: 好友列表。
        """
        result = await self._api_call("get_friend_list")
        return result.get("data", [])

    async def set_friend_add_request(
        self,
        flag: str,
        approve: bool = True,
        remark: str = "",
    ) -> SendResult:
        """处理好友请求

        Args:
            flag: 请求标识（从事件中获取）。
            approve: True=同意，False=拒绝。
            remark: 好友备注。

        Returns:
            SendResult: 操作结果。
        """
        result = await self._api_call(
            "set_friend_add_request",
            {"flag": flag, "approve": approve, "remark": remark},
        )
        if result.get("status") == "ok":
            return SendResult(success=True)
        return SendResult(
            success=False,
            error=result.get("wording", result.get("message", "Request failed")),
        )

    async def set_group_add_request(
        self,
        flag: str,
        sub_type: str,
        approve: bool = True,
        reason: str = "",
    ) -> SendResult:
        """处理加群请求

        Args:
            flag: 请求标识。
            sub_type: 子类型（"add" 或 "invite"）。
            approve: True=同意，False=拒绝。
            reason: 拒绝理由。

        Returns:
            SendResult: 操作结果。
        """
        result = await self._api_call(
            "set_group_add_request",
            {
                "flag": flag,
                "sub_type": sub_type,
                "approve": approve,
                "reason": reason,
            },
        )
        if result.get("status") == "ok":
            return SendResult(success=True)
        return SendResult(
            success=False,
            error=result.get("wording", result.get("message", "Request failed")),
        )

    async def get_stranger_info(self, user_id: str | int) -> dict[str, Any]:
        """获取陌生人信息

        Args:
            user_id: 用户 QQ。

        Returns:
            dict: 用户信息。
        """
        result = await self._api_call("get_stranger_info", {"user_id": user_id})
        return result.get("data", {})

    # ── 文件操作 ──────────────────────────────

    async def get_file(self, file_id: str) -> dict[str, Any]:
        """获取文件信息

        Args:
            file_id: 文件 ID。

        Returns:
            dict: 文件信息，包含 name, size, url 等。
        """
        result = await self._api_call("get_file", {"file_id": file_id})
        return result.get("data", {})

    async def get_image(self, file_id: str) -> dict[str, Any]:
        """获取图片信息

        Args:
            file_id: 图片文件 ID。

        Returns:
            dict: 图片信息，包含 file, url 等。
        """
        result = await self._api_call("get_image", {"file_id": file_id})
        return result.get("data", {})

    async def get_record(self, file_id: str, out_format: str = "mp3") -> dict[str, Any]:
        """获取语音文件信息

        Args:
            file_id: 语音文件 ID。
            out_format: 输出格式。

        Returns:
            dict: 语音文件信息。
        """
        result = await self._api_call("get_record", {"file_id": file_id, "out_format": out_format})
        return result.get("data", {})

    async def get_group_file_url(
        self, group_id: str | int, file_id: str, busid: int = 0
    ) -> str | None:
        """获取群文件下载链接

        Args:
            group_id: 群号。
            file_id: 文件 ID。
            busid: 文件类型标识。

        Returns:
            str | None: 文件下载 URL。
        """
        result = await self._api_call(
            "get_group_file_url",
            {"group_id": group_id, "file_id": file_id, "busid": busid},
        )
        data = result.get("data", {})
        return data.get("url")

    # ── 内部 HTTP API ─────────────────────────

    async def _api_call(
        self,
        action: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """调用 NapCat API

        优先通过反向 WebSocket 连接调用，失败时降级到 HTTP API。

        Args:
            action: API 端点名称（如 "send_msg", "get_group_list"）。
            params: 请求参数。

        Returns:
            dict: API 响应，包含 status, retcode, data 等。
        """
        return await self._ws_call_api(action, params)

    async def _http_api_call(
        self,
        action: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """通过 HTTP API 调用 NapCat

        Args:
            action: API 端点名称。
            params: 请求参数。

        Returns:
            dict: API 响应。
        """
        if not self._client:
            return {"status": "failed", "retcode": -1, "data": None}

        url = f"{self.base_url}/{action.lstrip('/')}"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._http_token:
            headers["Authorization"] = f"Bearer {self._http_token}"

        try:
            resp = await self._client.post(
                url,
                json=params or {},
                headers=headers,
                timeout=API_TIMEOUT_S,
            )
            resp.raise_for_status()
            data = resp.json()
            return data
        except httpx.TimeoutException:
            logger.error("napcat_api_timeout", action=action)
            return {"status": "failed", "retcode": -1, "data": None, "message": "Request timeout"}
        except httpx.HTTPStatusError as exc:
            logger.error(
                "napcat_api_http_error",
                action=action,
                status=exc.response.status_code,
                body=exc.response.text,
            )
            return {
                "status": "failed",
                "retcode": exc.response.status_code,
                "data": None,
                "message": f"HTTP {exc.response.status_code}",
            }
        except Exception as exc:
            logger.error("napcat_api_error", action=action, error=str(exc))
            return {"status": "failed", "retcode": -1, "data": None, "message": str(exc)}

    async def _ws_call_api(
        self,
        action: str,
        params: dict[str, Any] | None = None,
        timeout: float = API_TIMEOUT_S,
    ) -> dict[str, Any]:
        """通过反向 WebSocket 连接调用 NapCat API

        发送 JSON-RPC 请求，通过 echo 匹配响应。
        如果 WS 不可用，自动降级到 HTTP API。

        Args:
            action: API 端点名称。
            params: 请求参数。
            timeout: 超时时间（秒）。

        Returns:
            dict: API 响应。
        """
        # 优先使用反向 WebSocket
        if self._ws_connected and self._ws_writer:
            async with self._echo_lock:
                self._echo_counter += 1
                echo = f"napcat_{self._echo_counter}"

            payload = {
                "action": action,
                "params": params or {},
                "echo": echo,
            }

            try:
                fut: asyncio.Future[dict[str, Any]] = asyncio.Future()
                self._pending[echo] = fut

                payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                await self._ws_send_frame(
                    self._ws_writer,
                    0x1,
                    payload_bytes,
                )

                result = await asyncio.wait_for(fut, timeout=timeout)
                return result
            except TimeoutError:
                self._pending.pop(echo, None)
                logger.warning("napcat_ws_api_timeout", action=action)
                # 超时后降级到 HTTP
            except Exception as exc:
                self._pending.pop(echo, None)
                logger.warning("napcat_ws_api_error", action=action, error=str(exc))

        # HTTP API 备选
        return await self._http_api_call(action, params)

    async def _call_send_msg(
        self,
        target_type: str,
        target_value: str,
        message: list[dict[str, Any]] | str,
    ) -> SendResult:
        """调用 send_msg API 发送消息

        Args:
            target_type: "private" 或 "group"。
            target_value: 用户 QQ 或群号。
            message: 消息段列表或纯文本字符串。

        Returns:
            SendResult: 发送结果。
        """
        params: dict[str, Any] = {
            "message_type": target_type,
            "message": message,
        }

        if target_type == "private":
            params["user_id"] = str(target_value)
        elif target_type == "group":
            params["group_id"] = str(target_value)
        else:
            return SendResult(success=False, error=f"Unsupported target type: {target_type}")

        result = await self._api_call("send_msg", params)

        if result.get("status") == "ok":
            msg_id = result.get("data", {}).get("message_id", "")
            return SendResult(
                success=True,
                message_id=str(msg_id) if msg_id else None,
            )
        return SendResult(
            success=False,
            error=result.get("wording", result.get("message", "Send failed")),
        )

    async def _fetch_bot_info(self) -> None:
        """通过 HTTP 获取机器人自身信息（QQ 号）"""
        result = await self._api_call("get_login_info")
        data = result.get("data", {})
        self._bot_qq = str(data.get("user_id", ""))
        logger.info("napcat_bot_info", bot_qq=self._bot_qq)

    # ── 媒体文件解析 ──────────────────────────

    async def _resolve_media_file(
        self,
        file: str,
        media_data: bytes | None = None,
    ) -> str | None:
        """解析媒体文件为 NapCat 可接受的格式

        优先级：
        1. media_data → Base64 编码
        2. file 已经是 HTTP URL → 直接使用
        3. file 已经包含 base64:// 前缀 → 直接使用
        4. file 是本地路径 → 直接使用

        Args:
            file: 文件路径、URL 或标识。
            media_data: 可选的字节数据。

        Returns:
            str | None: 可用的文件标识。
        """
        if media_data:
            # 将字节数据编码为 Base64
            import base64

            encoded = base64.b64encode(media_data).decode("ascii")
            return f"base64://{encoded}"

        # 已经是 URL 或 base64 前缀
        if file.startswith(("http://", "https://", "base64://", "file://")):
            return file

        # 作为本地路径处理
        if file:
            return file

        return None

    # ── WebSocket 服务端（反向 WS）─────────────

    async def _on_ws_connect(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """处理新的 NapCat 反向 WebSocket 连接

        NapCat 作为 WS 客户端主动连接 YuanBot 服务端。
        连接建立后进行 WS 握手，进入消息读取循环。

        Args:
            reader: 读取流。
            writer: 写入流。
        """
        peer = writer.get_extra_info("peername")
        logger.info("napcat_reverse_ws_incoming", peer=peer)

        try:
            # 服务端 WebSocket 握手（接收 HTTP Upgrade，返回 101）
            path = await self._ws_do_server_handshake(reader, writer)
            if path is None:
                logger.warning("napcat_reverse_ws_handshake_failed", peer=peer)
                writer.close()
                return

            logger.info(
                "napcat_reverse_ws_connected",
                peer=peer,
                path=path,
            )

            # 关闭旧连接（如果有）
            if self._ws_writer:
                with contextlib.suppress(Exception):
                    self._ws_writer.close()
                self._ws_reader = None
                self._ws_writer = None
                self._ws_connected = False

            # 保存新连接
            self._ws_reader = reader
            self._ws_writer = writer
            self._ws_connected = True
            self._ws_connect_event.set()

            # 进入读取循环
            await self._ws_read_loop(reader)

        except Exception as exc:
            logger.error("napcat_reverse_ws_error", peer=peer, error=str(exc)[:200])
        finally:
            self._ws_connected = False
            self._ws_reader = None
            if self._ws_writer is writer:
                self._ws_writer = None
            with contextlib.suppress(Exception):
                writer.close()
            logger.info("napcat_reverse_ws_disconnected", peer=peer)

    async def _ws_do_server_handshake(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> str | None:
        """WebSocket 服务端握手

        接收 NapCat 发起的 HTTP Upgrade 请求，验证后返回 101。

        Args:
            reader: 读取流。
            writer: 写入流。

        Returns:
            str | None: 握手成功返回请求路径，失败返回 None。
        """

        # 读取请求行
        request_line = await reader.readline()
        if not request_line:
            return None

        try:
            decoded_line = request_line.decode("utf-8", errors="replace").strip()
            method, path, version = decoded_line.split(" ", 2)
        except ValueError:
            return None

        if method.upper() != "GET":
            writer.write(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
            await writer.drain()
            return None

        # 读取请求头
        headers: dict[str, str] = {}
        while True:
            line = await reader.readline()
            if line in (b"\r\n", b"\n", b""):
                break
            decoded = line.decode("utf-8", errors="replace").strip()
            if ":" in decoded:
                key, val = decoded.split(":", 1)
                headers[key.strip().lower()] = val.strip()

        # 验证 Sec-WebSocket-Key
        ws_key = headers.get("sec-websocket-key", "")
        if not ws_key:
            writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            await writer.drain()
            return None

        # 验证路径（如果配置了路径）
        expected_path = self._reverse_ws_path.rstrip("/")
        if expected_path and path.rstrip("/") != expected_path:
            logger.warning(
                "napcat_reverse_ws_path_mismatch",
                expected=expected_path,
                got=path,
            )

        # 验证 Token
        if self._reverse_ws_token:
            auth = headers.get("authorization", "")
            expected_auth = f"Bearer {self._reverse_ws_token}"
            if auth != expected_auth:
                writer.write(b"HTTP/1.1 401 Unauthorized\r\n\r\n")
                await writer.drain()
                return None

        # 计算 Accept key
        accept_key = base64.b64encode(
            hashlib.sha1((ws_key + self._WS_GUID).encode()).digest()
        ).decode()

        # 发送 101 响应
        response = (
            f"HTTP/1.1 101 Switching Protocols\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept_key}\r\n"
            f"\r\n"
        )
        writer.write(response.encode())
        await writer.drain()

        return path

    async def _ws_read_loop(self, reader: asyncio.StreamReader) -> None:
        """WebSocket 消息读取循环

        Args:
            reader: 读取流。
        """
        while self._running and self._ws_connected:
            frame = await self._ws_read_frame(reader)
            if frame is None:
                break
            opcode, payload = frame

            if opcode == 0x8:  # Close
                logger.info("napcat_ws_closed")
                break
            elif opcode == 0x9:  # Ping（客户端发来的 Ping，回复 Pong）
                if self._ws_writer:
                    await self._ws_send_frame(self._ws_writer, 0xA, payload)
            elif opcode == 0xA:  # Pong
                pass
            elif opcode == 0x1:  # Text
                await self._ws_on_text(payload.decode("utf-8", errors="replace"))

    async def _ws_on_text(self, text: str) -> None:
        """处理收到的 WebSocket 文本消息

        反向 WS 模式下，NapCat 通过此连接推送事件和返回 API 响应。
        消息格式为 JSON，通过 echo 字段区分：
          - 含 echo 且匹配 pending → API 响应
          - 无 echo 或不在 pending 中 → 事件推送

        Args:
            text: JSON 文本。
        """
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return

        echo = data.get("echo")
        if echo and echo in self._pending:
            # API 响应，交付给等待的 Future
            fut = self._pending.pop(echo, None)
            if fut and not fut.done():
                fut.set_result(data)
            return

        # 事件推送
        await self._process_event(data)

    # ── WebSocket 帧编解码 ────────────────────

    @staticmethod
    async def _ws_read_frame(
        reader: asyncio.StreamReader,
    ) -> tuple[int, bytes] | None:
        """读取 WebSocket 帧

        服务端模式下，客户端（NapCat）发送的帧必须带 mask。

        Args:
            reader: 读取流。

        Returns:
            (opcode, payload) 或 None（连接关闭）。
        """
        try:
            header = await reader.readexactly(2)
        except asyncio.IncompleteReadError:
            return None

        b0, b1 = header
        opcode = b0 & 0x0F
        masked = (b1 & 0x80) != 0
        length = b1 & 0x7F

        if length == 126:
            length_bytes = await reader.readexactly(2)
            length = int.from_bytes(length_bytes, "big")
        elif length == 127:
            length_bytes = await reader.readexactly(8)
            length = int.from_bytes(length_bytes, "big")

        mask_key: bytes = b""
        if masked:
            mask_key = await reader.readexactly(4)

        payload = await reader.readexactly(length)
        if masked:
            payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

        return opcode, payload

    @staticmethod
    async def _ws_send_frame(
        writer: asyncio.StreamWriter,
        opcode: int,
        payload: bytes,
    ) -> None:
        """发送 WebSocket 帧（服务端模式）

        服务端发送的帧不需要 mask。

        Args:
            writer: 写入流。
            opcode: 帧操作码。
            payload: 负载数据。
        """
        length = len(payload)
        header = bytearray()
        header.append(0x80 | opcode)  # FIN + opcode

        if length < 126:
            header.append(length)
        elif length < 65536:
            header.append(126)
            header.extend(length.to_bytes(2, "big"))
        else:
            header.append(127)
            header.extend(length.to_bytes(8, "big"))

        writer.write(bytes(header) + payload)
        await writer.drain()

    # ── 事件处理 ──────────────────────────────

    async def _process_event(self, event: dict[str, Any]) -> None:
        """处理 OneBot 事件

        Args:
            event: 事件数据。
        """
        post_type = event.get("post_type", "")

        if post_type == PostType.MESSAGE:
            await self._handle_message_event(event)
        elif post_type == PostType.MESSAGE_SENT:
            # 机器人自己发出的消息，忽略
            pass
        elif post_type == PostType.NOTICE:
            await self._handle_notice_event(event)
        elif post_type == PostType.REQUEST:
            await self._handle_request_event(event)
        elif post_type == PostType.META_EVENT:
            # 生命周期事件（connect, heartbeat 等）
            await self._handle_meta_event(event)
        else:
            logger.debug("napcat_unknown_post_type", post_type=post_type)

    async def _handle_message_event(self, event: dict[str, Any]) -> None:
        """处理消息事件

        Args:
            event: 消息事件数据。
        """
        if not self._callback:
            return

        message_type = event.get("message_type", "")
        user_id = str(event.get("user_id", ""))
        group_id = str(event.get("group_id", "")) if event.get("group_id") else ""
        message_id = event.get("message_id", 0)
        raw_message = event.get("raw_message", "")
        message_segments = event.get("message", [])
        sender = event.get("sender", {})

        if not user_id and not group_id:
            logger.debug("napcat_message_no_user_id")
            return

        # 解析消息段为文本
        text, metadata = self._parse_message_segments(message_segments, raw_message)

        # 如果没有有效文本/媒体内容，跳过
        if not text and not metadata.get("has_media"):
            logger.debug("napcat_empty_message")
            return

        # 判断消息场景
        if message_type == MessageType.GROUP:
            scene = "group"
            session_id_base = group_id
            platform_user_id = user_id
        else:
            scene = "private"
            session_id_base = user_id
            platform_user_id = user_id

        # 缓存 msg_id 用于被动回复
        cache_key = f"{scene}:{session_id_base}"
        self._msg_id_cache[cache_key] = {
            "msg_id": message_id,
            "user_id": user_id,
            "group_id": group_id,
        }

        yuanbot_uid = self._resolve_yuanbot_user_id(platform_user_id)
        session_id = self._build_session_id(platform_user_id)

        # 判断消息内容类型
        content_type = ContentType.TEXT
        media_url = metadata.get("media_url")

        if metadata.get("has_image"):
            content_type = ContentType.IMAGE
        elif metadata.get("has_voice"):
            content_type = ContentType.VOICE
        elif metadata.get("has_video"):
            content_type = ContentType.VIDEO
        elif metadata.get("has_file"):
            content_type = ContentType.FILE

        # 如果只有媒体没有文本，用一个空文本占位
        if not text and content_type != ContentType.TEXT:
            text = ""

        user_msg = UserMessage(
            platform="napcat",
            platform_user_id=platform_user_id,
            yuanbot_user_id=yuanbot_uid,
            session_id=session_id,
            content_type=content_type,
            text=text,
            media_url=media_url,
            metadata={
                "scene": scene,
                "group_id": group_id,
                "user_id": user_id,
                "message_id": message_id,
                "sender": sender,
                "raw_message": raw_message,
                "message_segments": message_segments,
                "reply_to": metadata.get("reply_to"),
                "at_me": metadata.get("at_me", False),
                "bot_qq": self._bot_qq,
            },
        )

        logger.info(
            "napcat_message_received",
            scene=scene,
            user_id=user_id,
            group_id=group_id or None,
            content_type=content_type.value,
            text_len=len(text),
        )

        response = await self._callback(user_msg)
        await self._deliver_response(scene, session_id_base, user_id, message_id, response)

    async def _handle_notice_event(self, event: dict[str, Any]) -> None:
        """处理通知事件

        记录通知事件日志，后续可扩展为触发主动交互。

        Args:
            event: 通知事件数据。
        """
        notice_type = event.get("notice_type", "")
        sub_type = event.get("sub_type", "")
        group_id = event.get("group_id", "")
        user_id = event.get("user_id", "")
        target_id = event.get("target_id", "")

        logger.info(
            "napcat_notice",
            notice_type=notice_type,
            sub_type=sub_type,
            group_id=group_id,
            user_id=user_id,
            target_id=target_id,
        )

        # 通知事件不需要回复，但可以用于触发主动交互
        # 这里预留扩展点：未来可在此生成主动问候/提醒

    async def _handle_request_event(self, event: dict[str, Any]) -> None:
        """处理请求事件

        Args:
            event: 请求事件数据。
        """
        request_type = event.get("request_type", "")
        flag = event.get("flag", "")
        user_id = event.get("user_id", "")
        comment = event.get("comment", "")

        logger.info(
            "napcat_request",
            request_type=request_type,
            user_id=user_id,
            flag=flag,
            comment=comment,
        )

        # 请求事件不自动处理，由业务逻辑决定是否同意
        # 可通过 self._callback 触发决策，或手动调用 set_friend_add_request/set_group_add_request

    async def _handle_meta_event(self, event: dict[str, Any]) -> None:
        """处理元事件

        Args:
            event: 元事件数据。
        """
        meta_event_type = event.get("meta_event_type", "")
        if meta_event_type == "lifecycle":
            sub_type = event.get("sub_type", "")
            logger.info("napcat_lifecycle", sub_type=sub_type)
        elif meta_event_type == "heartbeat":
            logger.debug("napcat_heartbeat")

    # ── 消息段解析 ────────────────────────────

    def _parse_message_segments(
        self,
        segments: list[dict[str, Any]] | str,
        raw_message: str,
    ) -> tuple[str, dict[str, Any]]:
        """解析 OneBot 消息段为纯文本 + 元数据

        Args:
            segments: 消息段列表或纯字符串。
            raw_message: 原始消息文本。

        Returns:
            tuple[str, dict]:
                - str: 提取的文本内容
                - dict: 元数据（包含 has_media, has_image, reply_to 等）
        """
        metadata: dict[str, Any] = {
            "has_media": False,
            "has_image": False,
            "has_voice": False,
            "has_video": False,
            "has_file": False,
            "has_face": False,
            "has_at": False,
            "at_me": False,
            "reply_to": None,
            "media_url": None,
        }

        # 纯文本消息
        if isinstance(segments, str):
            return segments.strip(), metadata

        if not isinstance(segments, list):
            return raw_message.strip(), metadata

        text_parts: list[str] = []

        for segment in segments:
            if not isinstance(segment, dict):
                continue

            seg_type = segment.get("type", "")
            seg_data = segment.get("data", {})

            if seg_type == MessageSegmentType.TEXT:
                text_parts.append(seg_data.get("text", ""))

            elif seg_type == MessageSegmentType.IMAGE:
                metadata["has_media"] = True
                metadata["has_image"] = True
                metadata["media_url"] = metadata["media_url"] or seg_data.get("url", "")

            elif seg_type == MessageSegmentType.RECORD:
                metadata["has_media"] = True
                metadata["has_voice"] = True
                metadata["media_url"] = metadata["media_url"] or seg_data.get("url", "")

            elif seg_type == MessageSegmentType.VIDEO:
                metadata["has_media"] = True
                metadata["has_video"] = True
                metadata["media_url"] = metadata["media_url"] or seg_data.get("url", "")

            elif seg_type == MessageSegmentType.FILE:
                metadata["has_media"] = True
                metadata["has_file"] = True
                metadata["media_url"] = metadata["media_url"] or seg_data.get("url", "")
                metadata["file_name"] = seg_data.get("name", "")
                metadata["file_size"] = seg_data.get("size", "")

            elif seg_type == MessageSegmentType.FACE:
                metadata["has_face"] = True
                face_id = seg_data.get("id", "")
                text_parts.append(f"[表情:{face_id}]")

            elif seg_type == MessageSegmentType.AT:
                metadata["has_at"] = True
                qq = seg_data.get("qq", "")
                if qq == "all":
                    text_parts.append("@全体成员")
                elif qq == self._bot_qq:
                    metadata["at_me"] = True
                    text_parts.append("@我")
                else:
                    text_parts.append(f"@{qq}")

            elif seg_type == MessageSegmentType.REPLY:
                reply_id = seg_data.get("id", "")
                seq = seg_data.get("seq", "")
                metadata["reply_to"] = reply_id or seq

            elif seg_type == MessageSegmentType.FORWARD:
                metadata["has_media"] = True
                text_parts.append("[合并转发消息]")

            elif seg_type == MessageSegmentType.XML:
                text_parts.append("[XML消息]")

            elif seg_type == MessageSegmentType.JSON:
                text_parts.append("[JSON消息]")

            elif seg_type == MessageSegmentType.MARKDOWN:
                text_parts.append(seg_data.get("data", ""))

            elif seg_type == MessageSegmentType.POKE:
                metadata["has_media"] = True
                text_parts.append("[戳一戳]")

            elif seg_type == MessageSegmentType.LOCATION:
                metadata["has_media"] = True
                title = seg_data.get("title", "")
                text_parts.append(f"[位置:{title}]" if title else "[位置]")

            elif seg_type == MessageSegmentType.CONTACT:
                contact_type = seg_data.get("type", "")
                target_id = seg_data.get("id", "")
                if contact_type == "qq":
                    text_parts.append(f"[推荐好友:{target_id}]")
                elif contact_type == "group":
                    text_parts.append(f"[推荐群:{target_id}]")
                else:
                    text_parts.append("[推荐]")

            else:
                logger.debug(
                    "napcat_unknown_segment",
                    seg_type=seg_type,
                    data=seg_data,
                )

        text = "".join(text_parts).strip()
        if not text and raw_message:
            text = raw_message.strip()

        return text, metadata

    # ── 回复投递 ──────────────────────────────

    async def _deliver_response(
        self,
        scene: str,
        target: str,
        user_id: str,
        msg_id: int | str,
        response: BotResponse,
    ) -> None:
        """投递 AI 回复

        根据消息场景将回复发送回 NapCat。
        长文本自动分段发送。

        Args:
            scene: "private" 或 "group"。
            target: 目标值（群号或用户 QQ）。
            user_id: 用户 QQ。
            msg_id: 原始消息 ID（用于被动回复）。
            response: AI 回复内容。
        """
        content = response.content

        if content.content_type == ContentType.TEXT:
            text = content.text or ""
            if not text:
                return
            result = await self.send_text(scene, target, text, reply_to=msg_id)
            if not result.success:
                logger.error("napcat_deliver_failed", error=result.error)

        elif content.content_type == ContentType.IMAGE:
            file = content.media_url or content.text or ""
            if content.media_data:
                result = await self.send_image(scene, target, file, media_data=content.media_data)
            elif file:
                result = await self.send_image(scene, target, file)
            else:
                result = SendResult(success=False, error="No image data available")
            if not result.success:
                logger.error("napcat_deliver_image_failed", error=result.error)

        elif content.content_type == ContentType.VOICE:
            file = content.media_url or content.text or ""
            if content.media_data:
                result = await self.send_voice(scene, target, file, media_data=content.media_data)
            elif file:
                result = await self.send_voice(scene, target, file)
            else:
                result = SendResult(success=False, error="No voice data available")
            if not result.success:
                logger.error("napcat_deliver_voice_failed", error=result.error)

        elif content.content_type == ContentType.VIDEO:
            file = content.media_url or content.text or ""
            if content.media_data:
                result = await self.send_video(scene, target, file, media_data=content.media_data)
            elif file:
                result = await self.send_video(scene, target, file)
            else:
                result = SendResult(success=False, error="No video data available")
            if not result.success:
                logger.error("napcat_deliver_video_failed", error=result.error)

        elif content.content_type == ContentType.FILE:
            file = content.media_url or content.text or ""
            filename = content.metadata.get("filename")
            if content.media_data:
                result = await self.send_file(
                    scene,
                    target,
                    file,
                    filename=filename,
                    media_data=content.media_data,
                )
            elif file:
                result = await self.send_file(
                    scene,
                    target,
                    file,
                    filename=filename,
                )
            else:
                result = SendResult(success=False, error="No file data available")
            if not result.success:
                logger.error("napcat_deliver_file_failed", error=result.error)

        else:
            logger.warning(
                "napcat_unhandled_content_type",
                content_type=content.content_type,
            )

    # ── 工具方法 ──────────────────────────────

    @staticmethod
    def _split_text(text: str, max_len: int = 2000) -> list[str]:
        """分段长文本

        Args:
            text: 原始文本。
            max_len: 每段最大长度。

        Returns:
            list[str]: 分段后的文本列表。
        """
        if len(text) <= max_len:
            return [text]
        chunks: list[str] = []
        while text:
            chunks.append(text[:max_len])
            text = text[max_len:]
        return chunks

    def get_cache_key(
        self,
        scene: str,
        target: str,
    ) -> str | None:
        """获取最近消息的缓存 key

        Args:
            scene: "private" 或 "group"。
            target: 目标值。

        Returns:
            str | None: 缓存消息信息，可用于获取 msg_id。
        """
        cache_key = f"{scene}:{target}"
        cached = self._msg_id_cache.get(cache_key)
        if cached:
            return cached.get("msg_id")
        return None

    def clear_msg_cache(self) -> None:
        """清空消息上下文缓存"""
        self._msg_id_cache.clear()
