"""NapCat (OneBot v11) QQ 通道适配器

基于 OneBot v11 协议标准，支持 NapCat QQ 实现。
通过 HTTP API 发送消息，通过 HTTP Webhook 接收事件。

协议文档：https://napcat.apifox.cn
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
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
    通过 HTTP API 发送消息，通过 HTTP POST Webhook 接收事件。
    支持群聊和私聊消息收发。
    """

    def __init__(self) -> None:
        super().__init__()
        self._http_host: str = "127.0.0.1"
        self._http_port: int = 3000
        self._http_token: str = ""
        self._webhook_host: str = "0.0.0.0"
        self._webhook_port: int = 8081
        self._bot_qq: str = ""

        self._client: httpx.AsyncClient | None = None
        self._callback: Callable[[UserMessage], Awaitable[BotResponse]] | None = None
        self._running = False
        self._webhook_server: asyncio.AbstractServer | None = None

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
            config: 通道配置，包含 NapCat HTTP 服务和 Webhook 设置。
        """
        cfg = config.config
        self._http_host = cfg.get("http_host", "127.0.0.1")
        self._http_port = cfg.get("http_port", 3000)
        self._http_token = cfg.get("http_token", "")
        self._webhook_host = cfg.get("webhook_host", "0.0.0.0")
        self._webhook_port = cfg.get("webhook_port", 8081)

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(API_TIMEOUT_S),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

        await self._fetch_bot_info()

        logger.info(
            "napcat_adapter_initialized",
            http_host=self._http_host,
            http_port=self._http_port,
            webhook_port=self._webhook_port,
            bot_qq=self._bot_qq,
        )

    async def listen(
        self,
        callback: Callable[[UserMessage], Awaitable[BotResponse]],
    ) -> None:
        """启动消息监听（HTTP Webhook 服务器）

        启动一个 HTTP 服务器监听 NapCat 的事件上报。
        NapCat 会将消息/通知/请求事件以 POST 请求发送到该服务器。

        Args:
            callback: 收到用户消息后的回调函数。
        """
        if not self._client:
            raise RuntimeError(
                "NapCat adapter not initialized. Call initialize() first."
            )

        self._callback = callback
        self._running = True

        self._webhook_server = await asyncio.start_server(
            self._handle_webhook_connection,
            self._webhook_host,
            self._webhook_port,
        )

        logger.info(
            "napcat_listen_started",
            host=self._webhook_host,
            port=self._webhook_port,
        )

    async def send_message(
        self,
        target_id: str,
        content: MessageContent,
    ) -> SendResult:
        """发送消息到指定目标

        target_id 格式:
          - 私聊: "private:user_id"
          - 群聊: "group:group_id"

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
            return SendResult(
                success=False, error=f"Invalid target_id format: {target_id}"
            )

        target_type, target_value = parts

        if content.content_type == ContentType.TEXT:
            return await self.send_text(target_type, target_value, content.text or "")
        elif content.content_type == ContentType.IMAGE:
            return await self.send_image(
                target_type, target_value, content.media_url or "",
                media_data=content.media_data,
            )
        elif content.content_type == ContentType.VOICE:
            return await self.send_voice(
                target_type, target_value, content.media_url or "",
                media_data=content.media_data,
            )
        elif content.content_type == ContentType.VIDEO:
            return await self.send_video(
                target_type, target_value, content.media_url or "",
                media_data=content.media_data,
            )
        elif content.content_type == ContentType.FILE:
            return await self.send_file(
                target_type, target_value, content.media_url or "",
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
            # 消息事件
            user_id = raw_event.get("user_id", "")
            # 请求事件
            if not user_id:
                user_id = raw_event.get("user_id", "")
            return str(user_id) if user_id else ""
        return str(raw_event)

    async def shutdown(self) -> None:
        """关闭适配器"""
        self._running = False

        if self._webhook_server:
            self._webhook_server.close()
            await self._webhook_server.wait_closed()
            self._webhook_server = None

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

            last_result = await self._call_send_msg(
                target_type, target_value, segments
            )
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

        segments: list[dict[str, Any]] = [
            build_file_segment(resolved_file, name=filename)
        ]

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

    async def get_group_member_list(
        self, group_id: str | int
    ) -> list[dict[str, Any]]:
        """获取群成员列表

        Args:
            group_id: 群号。

        Returns:
            list[dict]: 成员列表。
        """
        result = await self._api_call(
            "get_group_member_list", {"group_id": group_id}
        )
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

    async def set_group_whole_ban(
        self, group_id: str | int, enable: bool = True
    ) -> SendResult:
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

    async def get_group_notice(
        self, group_id: str | int
    ) -> list[dict[str, Any]]:
        """获取群公告列表

        Args:
            group_id: 群号。

        Returns:
            list[dict]: 公告列表。
        """
        result = await self._api_call(
            "get_group_notice", {"group_id": group_id}
        )
        return result.get("data", [])

    async def send_group_notice(
        self, group_id: str | int, content: str
    ) -> SendResult:
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
        result = await self._api_call(
            "set_essence_msg", {"message_id": message_id}
        )
        if result.get("status") == "ok":
            return SendResult(success=True, message_id=str(message_id))
        return SendResult(
            success=False,
            error=result.get("wording", result.get("message", "Set essence failed")),
        )

    async def get_essence_msg_list(
        self, group_id: str | int
    ) -> list[dict[str, Any]]:
        """获取群精华消息列表

        Args:
            group_id: 群号。

        Returns:
            list[dict]: 精华消息列表。
        """
        result = await self._api_call(
            "get_essence_msg_list", {"group_id": group_id}
        )
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

    async def set_group_name(
        self, group_id: str | int, group_name: str
    ) -> SendResult:
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

    async def get_stranger_info(
        self, user_id: str | int
    ) -> dict[str, Any]:
        """获取陌生人信息

        Args:
            user_id: 用户 QQ。

        Returns:
            dict: 用户信息。
        """
        result = await self._api_call(
            "get_stranger_info", {"user_id": user_id}
        )
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

    async def get_record(
        self, file_id: str, out_format: str = "mp3"
    ) -> dict[str, Any]:
        """获取语音文件信息

        Args:
            file_id: 语音文件 ID。
            out_format: 输出格式。

        Returns:
            dict: 语音文件信息。
        """
        result = await self._api_call(
            "get_record", {"file_id": file_id, "out_format": out_format}
        )
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
        """调用 NapCat HTTP API

        Args:
            action: API 端点名称（如 "send_msg", "get_group_list"）。
            params: 请求参数。

        Returns:
            dict: API 响应，包含 status, retcode, data 等。
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
            return {
                "status": "failed",
                "retcode": -1,
                "data": None,
                "message": "Request timeout",
            }
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
            return {
                "status": "failed",
                "retcode": -1,
                "data": None,
                "message": str(exc),
            }

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
            return SendResult(
                success=False, error=f"Unsupported target type: {target_type}"
            )

        result = await self._api_call("send_msg", params)

        if result.get("status") == "ok":
            msg_id = result.get("data", {}).get("message_id", "")
            return SendResult(
                success=True,
                message_id=str(msg_id) if msg_id else None,
            )
        return SendResult(
            success=False,
            error=result.get(
                "wording", result.get("message", "Send failed")
            ),
        )

    async def _fetch_bot_info(self) -> None:
        """获取机器人自身信息（QQ 号）"""
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

    # ── Webhook HTTP 服务器 ────────────────────

    async def _handle_webhook_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """处理 Webhook HTTP 连接

        解析 HTTP POST 请求，提取 OneBot 事件 JSON body，
        根据事件类型执行对应处理。

        Args:
            reader: HTTP 请求读取流。
            writer: HTTP 响应写入流。
        """
        try:
            # 读取 HTTP 请求行
            request_line = await reader.readline()
            if not request_line:
                writer.close()
                return

            # 读取请求头
            headers: dict[str, str] = {}
            content_length = 0
            while True:
                line = await reader.readline()
                if line in (b"\r\n", b"\n", b""):
                    break
                line_str = line.decode("utf-8", errors="replace").strip()
                if ":" in line_str:
                    key, value = line_str.split(":", 1)
                    headers[key.strip().lower()] = value.strip()
                    if key.strip().lower() == "content-length":
                        content_length = int(value.strip())

            # 只处理 POST 请求
            request_parts = (
                request_line.decode("utf-8", errors="replace").strip().split()
            )
            if len(request_parts) < 2 or request_parts[0] != "POST":
                self._send_http_response(writer, 405, "Method Not Allowed")
                return

            # 读取请求体
            body = b""
            if content_length > 0:
                body = await reader.readexactly(content_length)

            # 解析 JSON
            try:
                event_data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self._send_http_response(writer, 400, '{"status":"failed"}')
                return

            # 验证 Authorization
            auth_header = headers.get("authorization", "")
            if self._http_token:
                expected = f"Bearer {self._http_token}"
                if auth_header != expected:
                    logger.warning(
                        "napcat_webhook_auth_failed",
                        received=auth_header[:20],
                    )
                    # NapCat HTTP 上报不强制鉴权，记录日志但不拒绝
                    # 如果配置了 token，建议只允许带 token 的请求

            # 处理事件
            await self._process_event(event_data)

            # 返回成功（NapCat 要求 200 OK 返回空 JSON）
            self._send_http_response(writer, 200, '{"status":"ok"}')

        except asyncio.IncompleteReadError:
            logger.warning("napcat_webhook_incomplete_read")
        except Exception as exc:
            logger.error("napcat_webhook_error", error=str(exc))
            with contextlib.suppress(Exception):
                self._send_http_response(writer, 500, '{"status":"failed"}')
        finally:
            with contextlib.suppress(Exception):
                writer.close()

    def _send_http_response(
        self,
        writer: asyncio.StreamWriter,
        status_code: int,
        body: str,
    ) -> None:
        """发送 HTTP 响应

        Args:
            writer: 写入流。
            status_code: HTTP 状态码。
            body: 响应体。
        """
        status_texts = {
            200: "OK",
            400: "Bad Request",
            405: "Method Not Allowed",
            500: "Internal Server Error",
        }
        status_text = status_texts.get(status_code, "Unknown")
        response = (
            f"HTTP/1.1 {status_code} {status_text}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(body.encode())}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
            f"{body}"
        )
        writer.write(response.encode())

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
        # 如果有图片/语音/视频/文件，优先使用对应类型
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
                # 将来可以在此处记录图片 URL 用于后续处理

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
                # QQ 表情转换为文字表示
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
                # 未知类型，保留原始信息
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
            result = await self.send_text(
                scene, target, text, reply_to=msg_id
            )
            if not result.success:
                logger.error("napcat_deliver_failed", error=result.error)

        elif content.content_type == ContentType.IMAGE:
            file = content.media_url or content.text or ""
            if content.media_data:
                result = await self.send_image(
                    scene, target, file, media_data=content.media_data
                )
            elif file:
                result = await self.send_image(scene, target, file)
            else:
                result = SendResult(
                    success=False, error="No image data available"
                )
            if not result.success:
                logger.error("napcat_deliver_image_failed", error=result.error)

        elif content.content_type == ContentType.VOICE:
            file = content.media_url or content.text or ""
            if content.media_data:
                result = await self.send_voice(
                    scene, target, file, media_data=content.media_data
                )
            elif file:
                result = await self.send_voice(scene, target, file)
            else:
                result = SendResult(
                    success=False, error="No voice data available"
                )
            if not result.success:
                logger.error("napcat_deliver_voice_failed", error=result.error)

        elif content.content_type == ContentType.VIDEO:
            file = content.media_url or content.text or ""
            if content.media_data:
                result = await self.send_video(
                    scene, target, file, media_data=content.media_data
                )
            elif file:
                result = await self.send_video(scene, target, file)
            else:
                result = SendResult(
                    success=False, error="No video data available"
                )
            if not result.success:
                logger.error("napcat_deliver_video_failed", error=result.error)

        elif content.content_type == ContentType.FILE:
            file = content.media_url or content.text or ""
            filename = content.metadata.get("filename")
            if content.media_data:
                result = await self.send_file(
                    scene, target, file, filename=filename,
                    media_data=content.media_data,
                )
            elif file:
                result = await self.send_file(
                    scene, target, file, filename=filename,
                )
            else:
                result = SendResult(
                    success=False, error="No file data available"
                )
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
