"""QQ 开放平台 Bot 通道适配器

基于 QQ 开放平台 API v2 规范实现。
支持单聊、群聊、频道消息收发。
通过 WebSocket 长连接接收消息，通过 REST API 发送消息。
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import time
import uuid
from collections.abc import Awaitable, Callable
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

OAUTH_URL = "https://bots.qq.com/app/getAppAccessToken"
API_BASE_URL = "https://api.sgroup.qq.com"
WS_API_BASE = "https://api.sgroup.qq.com"

# 消息类型
class MsgType:
    TEXT = 0
    MARKDOWN = 2
    ARK = 3
    EMBED = 4
    MEDIA = 7

# 媒体类型
class FileType:
    IMAGE = 1
    VIDEO = 2
    VOICE = 3
    FILE = 4

# 超时
OAUTH_TIMEOUT_S = 10
API_TIMEOUT_S = 15
WS_HEARTBEAT_INTERVAL_S = 40  # 服务端建议 45s，客户端提前 5s


class QQAdapter(BaseChannelAdapter):
    """QQ 开放平台 Bot 通道适配器

    实现 ChannelAdapter 接口，桥接 QQ 开放平台 API 与 YuanBot。
    支持单聊 (C2C)、群聊 (GROUP)、频道 (GUILD) 消息收发。
    """

    def __init__(self) -> None:
        super().__init__()
        self._app_id: str = ""
        self._app_secret: str = ""
        self._access_token: str = ""
        self._token_expires_at: float = 0
        self._client: httpx.AsyncClient | None = None
        self._callback: Callable[[UserMessage], Awaitable[BotResponse]] | None = None
        self._running = False

        # WebSocket 状态
        self._ws_task: asyncio.Task | None = None
        self._ws_heartbeat_task: asyncio.Task | None = None
        self._ws_session_id: str = ""
        self._ws_seq: int = 0
        self._ws_resume_url: str = ""
        self._ws_heartbeat_interval: int = 45000

        # 消息场景: c2c / group / guild
        self._enabled_scenes: list[str] = ["c2c", "group"]

        # 消息 ID 存储（用于被动回复）
        self._context_tokens: dict[str, str] = {}

    # ── ChannelAdapter 接口实现 ────────────────

    @property
    def platform_name(self) -> str:
        return "qq"

    @property
    def supported_content_types(self) -> list[ContentType]:
        return [ContentType.TEXT, ContentType.IMAGE, ContentType.VOICE, ContentType.VIDEO, ContentType.FILE]

    async def initialize(self, config: ChannelConfig) -> None:
        """初始化适配器"""
        cfg = config.config
        self._app_id = cfg.get("app_id", "")
        self._app_secret = cfg.get("app_secret", "")
        self._enabled_scenes = cfg.get("enabled_scenes", ["c2c", "group"])

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(API_TIMEOUT_S),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

        # 获取 Access Token
        await self._refresh_token()

        logger.info("qq_adapter_initialized", app_id=self._app_id)

    async def listen(
        self,
        callback: Callable[[UserMessage], Awaitable[BotResponse]],
    ) -> None:
        """启动消息监听（WebSocket 长连接）"""
        if not self._client:
            raise RuntimeError("QQ adapter not initialized. Call initialize() first.")

        self._callback = callback
        self._running = True

        # 启动 WebSocket 连接
        self._ws_task = asyncio.create_task(self._ws_connect_loop())
        logger.info("qq_listen_started")

    async def send_message(
        self,
        target_id: str,
        content: MessageContent,
    ) -> SendResult:
        """发送消息到指定目标

        target_id 格式: "scene:openid"，如 "c2c:xxx" 或 "group:xxx"
        """
        if not self._client or not self._access_token:
            return SendResult(success=False, error="Adapter not initialized")

        # 解析 target_id
        parts = target_id.split(":", 1)
        if len(parts) != 2:
            return SendResult(success=False, error=f"Invalid target_id format: {target_id}")

        scene, openid = parts

        if content.content_type == ContentType.TEXT:
            return await self._send_text(scene, openid, content.text or "")
        elif content.content_type in (ContentType.IMAGE, ContentType.VOICE, ContentType.VIDEO, ContentType.FILE):
            return await self._send_media(scene, openid, content)
        else:
            return SendResult(success=False, error=f"Unsupported content type: {content.content_type}")

    def get_platform_user_id(self, raw_event: Any) -> str:
        """从原始事件中提取用户 ID"""
        if isinstance(raw_event, dict):
            author = raw_event.get("author", {})
            return author.get("user_openid", author.get("member_openid", ""))
        return str(raw_event)

    # ── Access Token 管理 ──────────────────────

    async def _refresh_token(self) -> None:
        """获取/刷新 Access Token"""
        if not self._client:
            return

        now = time.time()
        if self._access_token and now < self._token_expires_at - 60:
            return  # Token 仍然有效

        try:
            resp = await self._client.post(
                OAUTH_URL,
                json={
                    "appId": self._app_id,
                    "clientSecret": self._app_secret,
                },
                timeout=OAUTH_TIMEOUT_S,
            )
            resp.raise_for_status()
            data = resp.json()

            self._access_token = data.get("access_token", "")
            expires_in = data.get("expires_in", 7200)
            self._token_expires_at = now + expires_in

            logger.info("qq_token_refreshed", expires_in=expires_in)

        except Exception as exc:
            logger.error("qq_token_refresh_failed", error=str(exc))

    def _build_auth_headers(self) -> dict[str, str]:
        """构建认证请求头"""
        return {
            "Authorization": f"QQBot {self._access_token}",
            "Content-Type": "application/json",
        }

    # ── 消息发送 ──────────────────────────────

    async def _send_text(
        self,
        scene: str,
        openid: str,
        text: str,
        msg_id: str = "",
    ) -> SendResult:
        """发送文本消息"""
        await self._refresh_token()

        if scene == "c2c":
            url = f"{API_BASE_URL}/v2/users/{openid}/messages"
        elif scene == "group":
            url = f"{API_BASE_URL}/v2/groups/{openid}/messages"
        else:
            return SendResult(success=False, error=f"Unsupported scene: {scene}")

        body: dict[str, Any] = {
            "content": text,
            "msg_type": MsgType.TEXT,
        }

        # 被动消息需要 msg_id
        if msg_id:
            body["msg_id"] = msg_id

        try:
            resp = await self._client.post(
                url,
                json=body,
                headers=self._build_auth_headers(),
                timeout=API_TIMEOUT_S,
            )
            resp.raise_for_status()
            data = resp.json()
            return SendResult(success=True, message_id=data.get("id", ""))
        except httpx.HTTPStatusError as exc:
            logger.error("qq_send_text_http_error", status=exc.response.status_code, body=exc.response.text)
            return SendResult(success=False, error=f"HTTP {exc.response.status_code}")
        except Exception as exc:
            logger.error("qq_send_text_error", error=str(exc))
            return SendResult(success=False, error=str(exc))

    async def _send_media(
        self,
        scene: str,
        openid: str,
        content: MessageContent,
    ) -> SendResult:
        """发送媒体消息（先上传再发送）"""
        file_data: bytes | None = None

        if content.media_data:
            file_data = content.media_data
        elif content.media_url:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(content.media_url)
                    resp.raise_for_status()
                    file_data = resp.content
            except Exception as exc:
                return SendResult(success=False, error=f"Download failed: {exc}")

        if not file_data:
            return SendResult(success=False, error="No media data")

        # 上传富媒体
        file_type = {
            ContentType.IMAGE: FileType.IMAGE,
            ContentType.VOICE: FileType.VOICE,
            ContentType.VIDEO: FileType.VIDEO,
            ContentType.FILE: FileType.FILE,
        }.get(content.content_type, FileType.FILE)

        await self._refresh_token()

        if scene == "c2c":
            url = f"{API_BASE_URL}/v2/users/{openid}/files"
        elif scene == "group":
            url = f"{API_BASE_URL}/v2/groups/{openid}/files"
        else:
            return SendResult(success=False, error=f"Unsupported scene: {scene}")

        body = {
            "file_type": file_type,
            "file_data": base64.b64encode(file_data).decode(),
            "srv_send_msg": True,
        }

        try:
            resp = await self._client.post(
                url,
                json=body,
                headers=self._build_auth_headers(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return SendResult(success=True, message_id=data.get("id", ""))
        except httpx.HTTPStatusError as exc:
            logger.error("qq_send_media_http_error", status=exc.response.status_code)
            return SendResult(success=False, error=f"HTTP {exc.response.status_code}")
        except Exception as exc:
            logger.error("qq_send_media_error", error=str(exc))
            return SendResult(success=False, error=str(exc))

    async def _deliver_response(self, scene: str, openid: str, msg_id: str, response: BotResponse) -> None:
        """投递 AI 回复"""
        if response.content.content_type == ContentType.TEXT:
            text = response.content.text or ""
            if text:
                # 分段发送（QQ 单条消息有长度限制）
                chunks = self._split_text(text, max_len=2000)
                for chunk in chunks:
                    result = await self._send_text(scene, openid, chunk, msg_id=msg_id)
                    if not result.success:
                        logger.error("qq_deliver_failed", error=result.error)
                        break
                    # 后续消息不再是被动回复
                    msg_id = ""
        else:
            await self._send_media(scene, openid, response.content)

    @staticmethod
    def _split_text(text: str, max_len: int = 2000) -> list[str]:
        """分段长文本"""
        if len(text) <= max_len:
            return [text]
        chunks = []
        while text:
            chunks.append(text[:max_len])
            text = text[max_len:]
        return chunks

    # ── WebSocket 长连接 ──────────────────────

    async def _ws_connect_loop(self) -> None:
        """WebSocket 连接主循环（断线重连）"""
        while self._running:
            try:
                await self._refresh_token()

                # 获取网关地址
                gateway_url = await self._get_gateway_url()
                if not gateway_url:
                    logger.error("qq_gateway_fetch_failed")
                    await asyncio.sleep(10)
                    continue

                # 连接 WebSocket
                await self._ws_run(gateway_url)

            except Exception as exc:
                logger.error("qq_ws_loop_error", error=str(exc))

            if self._running:
                logger.info("qq_ws_reconnecting", delay_s=5)
                await asyncio.sleep(5)

    async def _get_gateway_url(self) -> str | None:
        """获取 WebSocket 网关地址"""
        if not self._client:
            return None

        try:
            resp = await self._client.get(
                f"{API_BASE_URL}/gateway/bot",
                headers=self._build_auth_headers(),
                timeout=API_TIMEOUT_S,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("url", "")
        except Exception as exc:
            logger.error("qq_gateway_error", error=str(exc))
            return None

    async def _ws_run(self, gateway_url: str) -> None:
        """运行单次 WebSocket 会话"""
        try:
            import websockets
        except ImportError:
            logger.error("qq_websockets_not_installed", msg="pip install websockets")
            return

        async with websockets.connect(gateway_url) as ws:
            # 1. 接收 Hello (OpCode 10)
            hello_data = await asyncio.wait_for(ws.recv(), timeout=10)
            hello = json.loads(hello_data)
            if hello.get("op") != 10:
                logger.error("qq_ws_expected_hello", got=hello.get("op"))
                return

            self._ws_heartbeat_interval = hello.get("d", {}).get("heartbeat_interval", 45000) // 1000
            logger.info("qq_ws_hello", heartbeat_interval=self._ws_heartbeat_interval)

            # 2. 发送 Identify (OpCode 2)
            identify = {
                "op": 2,
                "d": {
                    "token": f"QQBot {self._access_token}",
                    "intents": self._calc_intents(),
                    "properties": {
                        "$os": "linux",
                        "$browser": "yuanbot",
                        "$device": "yuanbot",
                    },
                },
            }
            await ws.send(json.dumps(identify))

            # 3. 接收 Ready 事件
            ready_data = await asyncio.wait_for(ws.recv(), timeout=10)
            ready = json.loads(ready_data)

            if ready.get("op") == 9:  # Invalid Session
                logger.error("qq_ws_invalid_session", data=ready.get("d"))
                return

            if ready.get("op") == 0 and ready.get("t") == "READY":
                self._ws_session_id = ready.get("d", {}).get("session_id", "")
                self._ws_seq = 0
                logger.info("qq_ws_ready", session_id=self._ws_session_id)

            # 4. 启动心跳
            self._ws_heartbeat_task = asyncio.create_task(self._ws_heartbeat(ws))

            # 5. 消息接收循环
            try:
                async for message in ws:
                    if not self._running:
                        break
                    await self._ws_handle_message(message)
            except Exception as exc:
                logger.error("qq_ws_recv_error", error=str(exc))

            # 清理
            if self._ws_heartbeat_task:
                self._ws_heartbeat_task.cancel()

    async def _ws_heartbeat(self, ws: Any) -> None:
        """WebSocket 心跳"""
        try:
            while self._running:
                await asyncio.sleep(self._ws_heartbeat_interval)
                heartbeat = {"op": 1, "d": self._ws_seq}
                await ws.send(json.dumps(heartbeat))
                logger.debug("qq_ws_heartbeat_sent", seq=self._ws_seq)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("qq_ws_heartbeat_error", error=str(exc))

    async def _ws_handle_message(self, raw: str) -> None:
        """处理 WebSocket 消息"""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        op = data.get("op")

        if op == 0:  # Dispatch
            self._ws_seq = data.get("s", self._ws_seq)
            await self._ws_handle_dispatch(data)
        elif op == 7:  # Reconnect
            logger.info("qq_ws_reconnect_requested")
            self._running = True  # 触发重连
        elif op == 9:  # Invalid Session
            logger.warning("qq_ws_invalid_session", d=data.get("d"))
            # 需要重新 Identify
        elif op == 11:  # Heartbeat ACK
            logger.debug("qq_ws_heartbeat_ack")

    async def _ws_handle_dispatch(self, data: dict[str, Any]) -> None:
        """处理 Dispatch 事件"""
        event_type = data.get("t", "")
        event_data = data.get("d", {})

        if event_type == "C2C_MESSAGE_CREATE":
            await self._handle_c2c_message(event_data)
        elif event_type == "GROUP_AT_MESSAGE_CREATE":
            await self._handle_group_at_message(event_data)
        elif event_type == "AT_MESSAGE_CREATE":
            await self._handle_guild_at_message(event_data)
        elif event_type == "DIRECT_MESSAGE_CREATE":
            await self._handle_guild_dm_message(event_data)
        else:
            logger.debug("qq_unhandled_event", type=event_type)

    async def _handle_c2c_message(self, data: dict[str, Any]) -> None:
        """处理单聊消息"""
        if not self._callback:
            return

        author = data.get("author", {})
        user_openid = author.get("user_openid", "")
        content = data.get("content", "").strip()
        msg_id = data.get("id", "")

        if not content or not user_openid:
            return

        # 存储 msg_id 用于被动回复
        self._context_tokens[f"c2c:{user_openid}"] = msg_id

        yuanbot_uid = self._resolve_yuanbot_user_id(user_openid)

        user_msg = UserMessage(
            platform="qq",
            platform_user_id=user_openid,
            yuanbot_user_id=yuanbot_uid,
            session_id=f"qq:c2c:{user_openid}",
            content_type=ContentType.TEXT,
            text=content,
            metadata={
                "scene": "c2c",
                "msg_id": msg_id,
                "timestamp": data.get("timestamp", ""),
            },
        )

        response = await self._callback(user_msg)
        await self._deliver_response("c2c", user_openid, msg_id, response)

    async def _handle_group_at_message(self, data: dict[str, Any]) -> None:
        """处理群聊 @机器人 消息"""
        if not self._callback:
            return

        author = data.get("author", {})
        member_openid = author.get("member_openid", "")
        group_openid = data.get("group_openid", "")
        content = data.get("content", "").strip()
        msg_id = data.get("id", "")

        if not content or not group_openid:
            return

        # 去除 @机器人 的标记
        content = self._strip_at_mention(content)

        self._context_tokens[f"group:{group_openid}"] = msg_id

        yuanbot_uid = self._resolve_yuanbot_user_id(member_openid or group_openid)

        user_msg = UserMessage(
            platform="qq",
            platform_user_id=member_openid or group_openid,
            yuanbot_user_id=yuanbot_uid,
            session_id=f"qq:group:{group_openid}",
            content_type=ContentType.TEXT,
            text=content,
            metadata={
                "scene": "group",
                "group_openid": group_openid,
                "msg_id": msg_id,
            },
        )

        response = await self._callback(user_msg)
        await self._deliver_response("group", group_openid, msg_id, response)

    async def _handle_guild_at_message(self, data: dict[str, Any]) -> None:
        """处理频道 @机器人 消息"""
        if not self._callback:
            return

        author = data.get("author", {})
        user_id = author.get("id", "")
        channel_id = data.get("channel_id", "")
        guild_id = data.get("guild_id", "")
        content = data.get("content", "").strip()
        msg_id = data.get("id", "")

        if not content:
            return

        content = self._strip_at_mention(content)

        yuanbot_uid = self._resolve_yuanbot_user_id(user_id)

        user_msg = UserMessage(
            platform="qq",
            platform_user_id=user_id,
            yuanbot_user_id=yuanbot_uid,
            session_id=f"qq:guild:{guild_id}:{channel_id}",
            content_type=ContentType.TEXT,
            text=content,
            metadata={
                "scene": "guild",
                "guild_id": guild_id,
                "channel_id": channel_id,
                "msg_id": msg_id,
            },
        )

        response = await self._callback(user_msg)

        # 频道消息发送
        await self._send_guild_message(channel_id, response.content.text or "", msg_id)

    async def _handle_guild_dm_message(self, data: dict[str, Any]) -> None:
        """处理频道私信消息"""
        if not self._callback:
            return

        author = data.get("author", {})
        user_id = author.get("id", "")
        guild_id = data.get("guild_id", "")
        content = data.get("content", "").strip()
        msg_id = data.get("id", "")

        if not content:
            return

        yuanbot_uid = self._resolve_yuanbot_user_id(user_id)

        user_msg = UserMessage(
            platform="qq",
            platform_user_id=user_id,
            yuanbot_user_id=yuanbot_uid,
            session_id=f"qq:dms:{guild_id}",
            content_type=ContentType.TEXT,
            text=content,
            metadata={
                "scene": "dms",
                "guild_id": guild_id,
                "msg_id": msg_id,
            },
        )

        response = await self._callback(user_msg)
        await self._send_dms_message(guild_id, response.content.text or "", msg_id)

    async def _send_guild_message(self, channel_id: str, text: str, msg_id: str = "") -> SendResult:
        """发送频道消息"""
        await self._refresh_token()

        url = f"{API_BASE_URL}/channels/{channel_id}/messages"
        body: dict[str, Any] = {
            "content": text,
            "msg_type": MsgType.TEXT,
        }
        if msg_id:
            body["msg_id"] = msg_id

        try:
            resp = await self._client.post(
                url, json=body, headers=self._build_auth_headers(), timeout=API_TIMEOUT_S,
            )
            resp.raise_for_status()
            return SendResult(success=True)
        except Exception as exc:
            logger.error("qq_send_guild_error", error=str(exc))
            return SendResult(success=False, error=str(exc))

    async def _send_dms_message(self, guild_id: str, text: str, msg_id: str = "") -> SendResult:
        """发送频道私信"""
        await self._refresh_token()

        url = f"{API_BASE_URL}/dms/{guild_id}/messages"
        body: dict[str, Any] = {
            "content": text,
            "msg_type": MsgType.TEXT,
        }
        if msg_id:
            body["msg_id"] = msg_id

        try:
            resp = await self._client.post(
                url, json=body, headers=self._build_auth_headers(), timeout=API_TIMEOUT_S,
            )
            resp.raise_for_status()
            return SendResult(success=True)
        except Exception as exc:
            logger.error("qq_send_dms_error", error=str(exc))
            return SendResult(success=False, error=str(exc))

    # ── Intent 计算 ────────────────────────────

    def _calc_intents(self) -> int:
        """计算事件订阅 Intents 位掩码"""
        intents = 0

        # GUILDS (1<<0) - 频道事件
        intents |= 1 << 0

        # GROUP_AND_C2C_EVENT (1<<25) - 单聊/群聊事件
        intents |= 1 << 25

        # PUBLIC_GUILD_MESSAGES (1<<30) - 频道 @消息
        intents |= 1 << 30

        # DIRECT_MESSAGE (1<<12) - 频道私信
        intents |= 1 << 12

        # GUILD_MEMBERS (1<<1) - 频道成员
        intents |= 1 << 1

        # INTERACTION (1<<26) - 互动事件
        intents |= 1 << 26

        return intents

    # ── 工具方法 ──────────────────────────────

    @staticmethod
    def _strip_at_mention(content: str) -> str:
        """去除 @机器人 的标记

        QQ 的 @标记格式: <@!user_id> 或 <@user_id>
        """
        import re
        return re.sub(r"<@!?[^>]+>", "", content).strip()

    # ── 清理 ──────────────────────────────────

    async def shutdown(self) -> None:
        """关闭适配器"""
        self._running = False

        if self._ws_heartbeat_task:
            self._ws_heartbeat_task.cancel()

        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass

        if self._client:
            await self._client.aclose()
            self._client = None

        logger.info("qq_adapter_shutdown")
