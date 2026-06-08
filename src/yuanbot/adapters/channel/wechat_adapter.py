"""微信 iLink Bot 通道适配器

基于 @tencent-weixin/openclaw-weixin 规范实现。
通过长轮询 (getUpdates) 接收消息，通过 sendMessage 发送回复。
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
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

FIXED_BASE_URL = "https://ilinkai.weixin.qq.com"
DEFAULT_CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"
DEFAULT_BOT_TYPE = "3"
DEFAULT_BOT_AGENT = "YuanBot"

# 超时 (秒)
QR_POLL_TIMEOUT_S = 35
GET_UPDATES_TIMEOUT_S = 35
API_TIMEOUT_S = 15
LIGHT_API_TIMEOUT_S = 10

# 会话过期 errcode
SESSION_EXPIRED_ERRCODE = -14
SESSION_PAUSE_DURATION_S = 3600  # 1 小时

# 连续失败退避
MAX_CONSECUTIVE_FAILURES = 3
BACKOFF_DELAY_S = 30
RETRY_DELAY_S = 2

# 流式输出
STREAM_BUSINESS_TYPE = 10
PIECE_THROTTLE_MS = 1000
MIN_INITIAL_CHARS = 10
MAX_PIECE_BYTES = 16 * 1024


class WeixinAdapter(BaseChannelAdapter):
    """微信 iLink Bot 通道适配器

    实现 ChannelAdapter 接口，桥接微信 iLink Bot API 与 YuanBot。
    """

    def __init__(self) -> None:
        super().__init__()
        self._base_url = FIXED_BASE_URL
        self._cdn_base_url = DEFAULT_CDN_BASE_URL
        self._bot_agent = DEFAULT_BOT_AGENT
        self._token: str | None = None
        self._ilink_user_id: str | None = None
        self._bot_id: str | None = None
        self._client: httpx.AsyncClient | None = None
        self._callback: Callable[[UserMessage], Awaitable[BotResponse]] | None = None

        # 同步游标
        self._sync_buf: str = ""

        # contextToken 存储: from_user_id -> context_token
        self._context_tokens: dict[str, str] = {}

        # 会话过期守卫
        self._session_paused_until: float = 0

        # 长轮询控制
        self._running = False
        self._poll_task: asyncio.Task | None = None

        # 连续失败计数
        self._consecutive_failures = 0

        # 配置缓存 (typing_ticket)
        self._config_cache: dict[str, dict[str, Any]] = {}  # user_id -> {ticket, expires_at}

    # ── ChannelAdapter 接口实现 ────────────────

    @property
    def platform_name(self) -> str:
        return "wechat"

    @property
    def supported_content_types(self) -> list[ContentType]:
        return [
            ContentType.TEXT, ContentType.IMAGE,
            ContentType.VOICE, ContentType.VIDEO, ContentType.FILE,
        ]

    async def initialize(self, config: ChannelConfig) -> None:
        """初始化适配器"""
        cfg = config.config
        self._token = cfg.get("token", "")
        self._ilink_user_id = cfg.get("ilink_user_id", "")
        self._bot_id = cfg.get("bot_id", "")
        self._base_url = cfg.get("base_url", FIXED_BASE_URL)
        self._cdn_base_url = cfg.get("cdn_base_url", DEFAULT_CDN_BASE_URL)
        self._bot_agent = cfg.get("bot_agent", DEFAULT_BOT_AGENT)
        self._sync_buf = cfg.get("sync_buf", "")

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(API_TIMEOUT_S),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

        if self._token:
            logger.info("wechat_adapter_initialized", base_url=self._base_url)
        else:
            logger.warning("wechat_adapter_no_token", msg="需要先通过 QR 码登录获取 token")

    async def listen(
        self,
        callback: Callable[[UserMessage], Awaitable[BotResponse]],
    ) -> None:
        """启动消息监听（长轮询）"""
        if not self._token or not self._client:
            raise RuntimeError("WeChat adapter not initialized. Call initialize() first.")

        self._callback = callback
        self._running = True

        # 通知服务端启动
        await self._notify_start()

        # 启动长轮询循环
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("wechat_listen_started")

    async def send_message(
        self,
        target_id: str,
        content: MessageContent,
    ) -> SendResult:
        """发送消息到指定目标"""
        if not self._client or not self._token:
            return SendResult(success=False, error="Adapter not initialized")

        context_token = self._context_tokens.get(target_id, "")

        if content.content_type == ContentType.TEXT:
            return await self._send_text(target_id, content.text or "", context_token)
        elif content.content_type in (
            ContentType.IMAGE, ContentType.VOICE, ContentType.VIDEO, ContentType.FILE
        ):
            return await self._send_media(target_id, content, context_token)
        else:
            return SendResult(
                success=False, error=f"Unsupported content type: {content.content_type}"
            )

    def get_platform_user_id(self, raw_event: Any) -> str:
        """从原始事件中提取用户 ID"""
        if isinstance(raw_event, dict):
            return raw_event.get("from_user_id", "")
        return str(raw_event)

    # ── QR 码登录 ──────────────────────────────

    async def login_with_qr(self) -> dict[str, str]:
        """QR 码登录流程

        Returns:
            {qrcode_url, qrcode_img_url} 用于展示二维码
        """
        if not self._client:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(API_TIMEOUT_S))

        # 1. 获取二维码
        qr_data = await self._fetch_qrcode()
        return qr_data

    async def poll_login_status(self, qrcode: str, verify_code: str = "") -> dict[str, Any]:
        """轮询二维码状态

        Returns:
            {status, token?, user_id?, bot_id?, base_url?}
        """
        return await self._poll_qrcode_status(qrcode, verify_code)

    # ── 长轮询主循环 ──────────────────────────

    async def _poll_loop(self) -> None:
        """getUpdates 长轮询主循环"""
        logger.info("wechat_poll_loop_started")

        while self._running:
            try:
                # 检查会话是否过期暂停中
                if time.time() < self._session_paused_until:
                    wait_time = self._session_paused_until - time.time()
                    logger.info("wechat_session_paused", wait_seconds=int(wait_time))
                    await asyncio.sleep(min(wait_time, 60))
                    continue

                # 长轮询请求
                resp = await self._get_updates()

                if resp is None:
                    # 超时，重试
                    continue

                ret = resp.get("ret", 0)
                errcode = resp.get("errcode", 0)

                # 会话过期处理
                if errcode == SESSION_EXPIRED_ERRCODE or ret == SESSION_EXPIRED_ERRCODE:
                    self._session_paused_until = time.time() + SESSION_PAUSE_DURATION_S
                    logger.warning("wechat_session_expired", pause_seconds=SESSION_PAUSE_DURATION_S)
                    continue

                # 成功，重置失败计数
                self._consecutive_failures = 0

                # 更新同步游标
                new_buf = resp.get("get_updates_buf", "")
                if new_buf:
                    self._sync_buf = new_buf

                # 处理消息
                msgs = resp.get("msgs", [])
                for msg in msgs:
                    await self._process_message(msg)

                # 服务端建议的超时
                server_timeout = resp.get("longpolling_timeout_ms")
                if server_timeout:
                    logger.debug("wechat_server_timeout_hint", ms=server_timeout)

            except Exception as exc:
                self._consecutive_failures += 1
                logger.error(
                    "wechat_poll_error", error=str(exc),
                    failures=self._consecutive_failures,
                )

                if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    logger.warning("wechat_poll_backoff", delay_s=BACKOFF_DELAY_S)
                    await asyncio.sleep(BACKOFF_DELAY_S)
                else:
                    await asyncio.sleep(RETRY_DELAY_S)

        logger.info("wechat_poll_loop_stopped")

    async def _get_updates(self) -> dict[str, Any] | None:
        """发送 getUpdates 请求"""
        assert self._client is not None

        body = {
            "get_updates_buf": self._sync_buf,
            "base_info": self._build_base_info(),
        }

        try:
            resp = await self._client.post(
                f"{self._base_url}/ilink/bot/getupdates",
                json=body,
                headers=self._build_headers(),
                timeout=GET_UPDATES_TIMEOUT_S,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            # 客户端超时，返回空响应
            return {"ret": 0, "msgs": []}
        except httpx.HTTPStatusError as exc:
            logger.error("wechat_getupdates_http_error", status=exc.response.status_code)
            return None
        except Exception as exc:
            logger.error("wechat_getupdates_error", error=str(exc))
            return None

    async def _process_message(self, msg: dict[str, Any]) -> None:
        """处理单条入站消息"""
        from_user_id = msg.get("from_user_id", "")
        message_type = msg.get("message_type", 0)
        message_state = msg.get("message_state", 0)
        context_token = msg.get("context_token", "")

        # 只处理用户消息 (type=1) 且状态为 FINISH (state=2)
        if message_type != 1 or message_state != 2:
            return

        # 存储 contextToken
        if context_token:
            self._context_tokens[from_user_id] = context_token

        # 解析消息内容
        item_list = msg.get("item_list", [])
        for item in item_list:
            item_type = item.get("type", 0)

            if item_type == 1:  # TEXT
                text_item = item.get("text_item", {})
                text = text_item.get("text", "")
                if text:
                    await self._handle_text_message(from_user_id, text, msg)
            elif item_type == 2:  # IMAGE
                await self._handle_media_message(from_user_id, ContentType.IMAGE, item, msg)
            elif item_type == 3:  # VOICE
                await self._handle_media_message(from_user_id, ContentType.VOICE, item, msg)
            elif item_type == 4:  # FILE
                await self._handle_media_message(from_user_id, ContentType.FILE, item, msg)
            elif item_type == 5:  # VIDEO
                await self._handle_media_message(from_user_id, ContentType.VIDEO, item, msg)

    async def _handle_text_message(
        self,
        from_user_id: str,
        text: str,
        raw_msg: dict[str, Any],
    ) -> None:
        """处理文本消息"""
        if not self._callback:
            return

        yuanbot_uid = self._resolve_yuanbot_user_id(from_user_id)
        session_id = self._build_session_id(from_user_id)

        user_msg = UserMessage(
            platform="wechat",
            platform_user_id=from_user_id,
            yuanbot_user_id=yuanbot_uid,
            session_id=session_id,
            content_type=ContentType.TEXT,
            text=text,
            metadata={
                "message_id": raw_msg.get("message_id"),
                "context_token": raw_msg.get("context_token", ""),
                "create_time_ms": raw_msg.get("create_time_ms"),
            },
        )

        # 发送输入状态
        await self._send_typing(from_user_id, TypingStatus.TYPING)

        try:
            response = await self._callback(user_msg)
            # 发送回复
            await self._deliver_response(from_user_id, response)
        finally:
            # 取消输入状态
            await self._send_typing(from_user_id, TypingStatus.CANCEL)

    async def _handle_media_message(
        self,
        from_user_id: str,
        content_type: ContentType,
        item: dict[str, Any],
        raw_msg: dict[str, Any],
    ) -> None:
        """处理媒体消息（CDN 下载 + 转发到 AI 管道）"""
        from yuanbot.adapters.channel.weixin_cdn import (
            UploadMediaType,
            download_media_file,
        )

        item_type = {
            ContentType.IMAGE: UploadMediaType.IMAGE,
            ContentType.VOICE: UploadMediaType.VOICE,
            ContentType.FILE: UploadMediaType.FILE,
            ContentType.VIDEO: UploadMediaType.VIDEO,
        }.get(content_type, UploadMediaType.FILE)

        # 提取 CDN 媒体引用
        item_key = {
            UploadMediaType.IMAGE: "image_item",
            UploadMediaType.VOICE: "voice_item",
            UploadMediaType.FILE: "file_item",
            UploadMediaType.VIDEO: "video_item",
        }.get(item_type, "")

        item_data = item.get(item_key, {})
        media = item_data.get("media", {})
        encrypt_query_param = media.get("encrypt_query_param", "")
        aes_key_b64 = media.get("aes_key", "")
        full_url = media.get("full_url", "")

        media_path = ""

        if encrypt_query_param or full_url:
            # CDN 下载
            plaintext = await download_media_file(
                encrypt_query_param=encrypt_query_param,
                aes_key_b64=aes_key_b64,
                item_type=item_type,
                cdn_base_url=self._cdn_base_url,
                full_url=full_url,
            )

            if plaintext:
                # 保存到临时文件
                import tempfile
                suffix = {
                    ContentType.IMAGE: ".jpg",
                    ContentType.VOICE: ".wav",
                    ContentType.VIDEO: ".mp4",
                    ContentType.FILE: "",
                }.get(content_type, "")

                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=suffix, prefix="yuanbot_wechat_"
                ) as f:
                    f.write(plaintext)
                    media_path = f.name

                logger.info(
                    "wechat_media_downloaded",
                    type=content_type.value,
                    size=len(plaintext),
                    path=media_path,
                )
            else:
                logger.warning(
                    "wechat_media_download_failed",
                    type=content_type.value,
                )

        if not self._callback:
            return

        yuanbot_uid = self._resolve_yuanbot_user_id(from_user_id)
        session_id = self._build_session_id(from_user_id)

        # 构建消息文本
        text = f"[{content_type.value}消息]"
        if content_type == ContentType.VOICE:
            voice_text = item_data.get("text", "")
            if voice_text:
                text = f"[语音] {voice_text}"

        user_msg = UserMessage(
            platform="wechat",
            platform_user_id=from_user_id,
            yuanbot_user_id=yuanbot_uid,
            session_id=session_id,
            content_type=content_type,
            text=text,
            media_url=media_path if media_path else None,
            metadata={
                "message_id": raw_msg.get("message_id"),
                "context_token": raw_msg.get("context_token", ""),
            },
        )

        await self._callback(user_msg)

    # ── 消息发送 ──────────────────────────────

    async def _send_text(
        self,
        target_id: str,
        text: str,
        context_token: str = "",
    ) -> SendResult:
        """发送文本消息"""
        assert self._client is not None

        client_id = f"yuanbot-wechat:{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"

        body = {
            "msg": {
                "from_user_id": "",
                "to_user_id": target_id,
                "client_id": client_id,
                "message_type": 2,  # BOT
                "message_state": 2,  # FINISH
                "context_token": context_token,
                "item_list": [
                    {
                        "type": 1,  # TEXT
                        "text_item": {"text": text},
                    }
                ],
            },
            "base_info": self._build_base_info(),
        }

        try:
            resp = await self._client.post(
                f"{self._base_url}/ilink/bot/sendmessage",
                json=body,
                headers=self._build_headers(),
                timeout=API_TIMEOUT_S,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("ret", 0) != 0:
                return SendResult(success=False, error=data.get("errmsg", "Unknown error"))

            return SendResult(success=True, message_id=client_id)

        except Exception as exc:
            logger.error("wechat_send_text_error", error=str(exc))
            return SendResult(success=False, error=str(exc))

    async def _send_media(
        self,
        target_id: str,
        content: MessageContent,
        context_token: str = "",
    ) -> SendResult:
        """发送媒体消息（图片/文件/语音/视频）

        完整流程：
        1. 读取文件数据（本地路径或远程 URL）
        2. CDN 上传（加密 + 上传）
        3. 构造 MessageItem
        4. 调用 sendMessage API
        """
        assert self._client is not None

        file_data: bytes | None = None
        file_name = ""
        mime_type = "application/octet-stream"

        # 1. 获取文件数据
        if content.media_data:
            file_data = content.media_data
        elif content.media_url:
            file_data, file_name, mime_type = await self._load_media_data(
                content.media_url
            )
        elif content.text:
            # text 字段可能是本地路径
            path = Path(content.text)
            if path.exists():
                file_data = path.read_bytes()
                file_name = path.name
                from yuanbot.adapters.channel.weixin_cdn import extension_to_mime
                mime_type = extension_to_mime(path.suffix)

        if not file_data:
            return SendResult(success=False, error="No media data available")

        # 2. 确定媒体类型
        from yuanbot.adapters.channel.weixin_cdn import (
            get_media_ref_from_upload,
            mime_to_media_type,
            upload_media_file,
        )

        media_type = mime_to_media_type(mime_type)

        # 3. CDN 上传
        upload_result = await upload_media_file(
            http_client=self._client,
            base_url=self._base_url,
            cdn_base_url=self._cdn_base_url,
            headers=self._build_headers(),
            base_info=self._build_base_info(),
            file_data=file_data,
            media_type=media_type,
            to_user_id=target_id,
        )

        if not upload_result:
            return SendResult(success=False, error="CDN upload failed")

        # 4. 构造 MessageItem 并发送
        media_ref = get_media_ref_from_upload(upload_result)
        return await self._send_media_message(
            target_id, media_type, media_ref, context_token,
            file_name=file_name,
            file_size=upload_result.file_size_plain,
        )

    async def _load_media_data(
        self, media_url: str
    ) -> tuple[bytes, str, str]:
        """加载媒体数据（本地文件或远程 URL）

        Returns:
            (file_data, file_name, mime_type)
        """
        from yuanbot.adapters.channel.weixin_cdn import extension_to_mime

        if media_url.startswith("http://") or media_url.startswith("https://"):
            # 远程 URL，下载到本地
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(media_url)
                    resp.raise_for_status()
                    file_data = resp.content
                    # 从 URL 推断文件名和 MIME
                    from urllib.parse import urlparse
                    parsed = urlparse(media_url)
                    file_name = Path(parsed.path).name or "media"
                    ext = Path(file_name).suffix
                    mime_type = extension_to_mime(ext)
                    return file_data, file_name, mime_type
            except Exception as exc:
                logger.error("media_download_error", url=media_url, error=str(exc))
                return b"", "", ""
        elif media_url.startswith("file://"):
            path = Path(media_url[7:])
        else:
            path = Path(media_url)

        if path.exists():
            file_data = path.read_bytes()
            file_name = path.name
            mime_type = extension_to_mime(path.suffix)
            return file_data, file_name, mime_type

        logger.error("media_file_not_found", path=media_url)
        return b"", "", ""

    async def _send_media_message(
        self,
        target_id: str,
        media_type: int,
        media_ref: Any,
        context_token: str = "",
        file_name: str = "",
        file_size: int = 0,
    ) -> SendResult:
        """构造媒体 MessageItem 并调用 sendMessage API"""
        assert self._client is not None

        from yuanbot.adapters.channel.weixin_cdn import UploadMediaType

        client_id = f"yuanbot-wechat:{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"

        # 根据媒体类型构造 item
        media_item: dict[str, Any] = {
            "encrypt_query_param": media_ref.encrypt_query_param,
            "aes_key": media_ref.aes_key_b64,
            "encrypt_type": media_ref.encrypt_type,
        }

        if media_type == UploadMediaType.IMAGE:
            item = {
                "type": 2,
                "image_item": {
                    "media": media_item,
                    "mid_size": file_size,
                },
            }
        elif media_type == UploadMediaType.VIDEO:
            item = {
                "type": 5,
                "video_item": {
                    "media": media_item,
                    "video_size": file_size,
                },
            }
        elif media_type == UploadMediaType.VOICE:
            item = {
                "type": 3,
                "voice_item": {
                    "media": media_item,
                },
            }
        else:  # FILE
            item = {
                "type": 4,
                "file_item": {
                    "media": media_item,
                    "file_name": file_name or "file",
                    "len": str(file_size),
                },
            }

        body = {
            "msg": {
                "from_user_id": "",
                "to_user_id": target_id,
                "client_id": client_id,
                "message_type": 2,  # BOT
                "message_state": 2,  # FINISH
                "context_token": context_token,
                "item_list": [item],
            },
            "base_info": self._build_base_info(),
        }

        try:
            resp = await self._client.post(
                f"{self._base_url}/ilink/bot/sendmessage",
                json=body,
                headers=self._build_headers(),
                timeout=API_TIMEOUT_S,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("ret", 0) != 0:
                return SendResult(success=False, error=data.get("errmsg", "Unknown error"))

            return SendResult(success=True, message_id=client_id)

        except Exception as exc:
            logger.error("wechat_send_media_error", error=str(exc))
            return SendResult(success=False, error=str(exc))

    async def _deliver_response(self, target_id: str, response: BotResponse) -> None:
        """投递 AI 回复到微信"""
        context_token = self._context_tokens.get(target_id, "")

        if response.content.content_type == ContentType.TEXT:
            text = response.content.text or ""
            if text:
                # 分段发送（微信单条消息有长度限制）
                chunks = self._split_text(text, max_len=4000)
                for chunk in chunks:
                    result = await self._send_text(target_id, chunk, context_token)
                    if not result.success:
                        logger.error("wechat_deliver_failed", error=result.error)
                        break
        else:
            await self._send_media(target_id, response.content, context_token)

    @staticmethod
    def _split_text(text: str, max_len: int = 4000) -> list[str]:
        """分段长文本"""
        if len(text) <= max_len:
            return [text]
        chunks = []
        while text:
            chunks.append(text[:max_len])
            text = text[max_len:]
        return chunks

    # ── 输入状态 ──────────────────────────────

    async def _send_typing(self, user_id: str, status: int) -> None:
        """发送/取消输入状态"""
        if not self._client:
            return

        # 获取 typing_ticket (带缓存)
        ticket = await self._get_typing_ticket(user_id)
        if not ticket:
            return

        body = {
            "ilink_user_id": user_id,
            "typing_ticket": ticket,
            "status": status,
            "base_info": self._build_base_info(),
        }

        try:
            resp = await self._client.post(
                f"{self._base_url}/ilink/bot/sendtyping",
                json=body,
                headers=self._build_headers(),
                timeout=LIGHT_API_TIMEOUT_S,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.debug("wechat_typing_error", error=str(exc))

    async def _get_typing_ticket(self, user_id: str) -> str | None:
        """获取 typing_ticket（带 24 小时缓存）"""
        cached = self._config_cache.get(user_id)
        if cached and time.time() < cached.get("expires_at", 0):
            return cached.get("ticket")

        if not self._client:
            return None

        body = {
            "ilink_user_id": user_id,
            "base_info": self._build_base_info(),
        }

        try:
            resp = await self._client.post(
                f"{self._base_url}/ilink/bot/getconfig",
                json=body,
                headers=self._build_headers(),
                timeout=LIGHT_API_TIMEOUT_S,
            )
            resp.raise_for_status()
            data = resp.json()

            ticket = data.get("typing_ticket", "")
            if ticket:
                # 缓存 24 小时 + 随机抖动
                import random
                ttl = 86400 + random.randint(0, 3600)
                self._config_cache[user_id] = {
                    "ticket": ticket,
                    "expires_at": time.time() + ttl,
                }
            return ticket

        except Exception as exc:
            logger.debug("wechat_getconfig_error", error=str(exc))
            return None

    # ── 生命周期通知 ──────────────────────────

    async def _notify_start(self) -> None:
        """通知服务端渠道启动"""
        if not self._client:
            return

        try:
            resp = await self._client.post(
                f"{self._base_url}/ilink/bot/msg/notifystart",
                json={"base_info": self._build_base_info()},
                headers=self._build_headers(),
                timeout=LIGHT_API_TIMEOUT_S,
            )
            resp.raise_for_status()
            logger.info("wechat_notify_start_sent")
        except Exception as exc:
            logger.debug("wechat_notify_start_failed", error=str(exc))

    async def _notify_stop(self) -> None:
        """通知服务端渠道停止"""
        if not self._client:
            return

        try:
            resp = await self._client.post(
                f"{self._base_url}/ilink/bot/msg/notifystop",
                json={"base_info": self._build_base_info()},
                headers=self._build_headers(),
                timeout=LIGHT_API_TIMEOUT_S,
            )
            resp.raise_for_status()
            logger.info("wechat_notify_stop_sent")
        except Exception as exc:
            logger.debug("wechat_notify_stop_failed", error=str(exc))

    # ── QR 码登录 API ─────────────────────────

    async def _fetch_qrcode(self) -> dict[str, str]:
        """获取登录二维码"""
        assert self._client is not None

        body = {"local_token_list": []}

        resp = await self._client.post(
            f"{self._base_url}/ilink/bot/get_bot_qrcode?bot_type={DEFAULT_BOT_TYPE}",
            json=body,
            headers=self._build_headers(include_auth=False),
            timeout=API_TIMEOUT_S,
        )
        resp.raise_for_status()
        data = resp.json()

        return {
            "qrcode": data.get("qrcode", ""),
            "qrcode_img_url": data.get("qrcode_img_content", ""),
        }

    async def _poll_qrcode_status(
        self,
        qrcode: str,
        verify_code: str = "",
    ) -> dict[str, Any]:
        """轮询二维码状态"""
        assert self._client is not None

        params = {"qrcode": qrcode}
        if verify_code:
            params["verify_code"] = verify_code

        try:
            resp = await self._client.get(
                f"{self._base_url}/ilink/bot/get_qrcode_status",
                params=params,
                headers=self._build_headers(include_auth=False),
                timeout=QR_POLL_TIMEOUT_S,
            )
            resp.raise_for_status()
            data = resp.json()

            status = data.get("status", "wait")

            result: dict[str, Any] = {"status": status}

            if status == "confirmed":
                result["token"] = data.get("bot_token", "")
                result["user_id"] = data.get("ilink_user_id", "")
                result["bot_id"] = data.get("ilink_bot_id", "")
                result["base_url"] = data.get("baseurl", self._base_url)
                result["redirect_host"] = data.get("redirect_host", "")
            elif status == "scaned_but_redirect":
                result["redirect_host"] = data.get("redirect_host", "")

            return result

        except httpx.TimeoutException:
            return {"status": "wait"}
        except Exception as exc:
            logger.error("wechat_qr_poll_error", error=str(exc))
            return {"status": "error", "error": str(exc)}

    # ── HTTP 工具方法 ─────────────────────────

    def _build_headers(self, include_auth: bool = True) -> dict[str, str]:
        """构建请求头"""
        import base64
        import os

        # X-WECHAT-UIN: base64(random uint32)
        rand_bytes = os.urandom(4)
        uint32_val = int.from_bytes(rand_bytes, "big")
        uin_b64 = base64.b64encode(str(uint32_val).encode()).decode()

        # iLink-App-ClientVersion: major<<16 | minor<<8 | patch
        version_parts = [2, 4, 3]  # 2.4.3
        client_version = (version_parts[0] << 16) | (version_parts[1] << 8) | version_parts[2]

        headers = {
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "X-WECHAT-UIN": uin_b64,
            "iLink-App-Id": "bot",
            "iLink-App-ClientVersion": str(client_version),
        }

        if include_auth and self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        return headers

    def _build_base_info(self) -> dict[str, str]:
        """构建 base_info 请求体"""
        return {
            "channel_version": "2.4.3",
            "bot_agent": self._bot_agent,
        }

    # ── 流式输出 ──────────────────────────────

    async def send_stream_init(self, device_id: str) -> dict[str, Any] | None:
        """初始化流式输出"""
        if not self._client:
            return None

        client_stream_id = f"{device_id}:{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"

        body = {
            "device_id": device_id,
            "client_stream_id": client_stream_id,
            "business_type": STREAM_BUSINESS_TYPE,
            "base_info": self._build_base_info(),
        }

        try:
            resp = await self._client.post(
                f"{self._base_url}/ilink/bot/native_init_stream",
                json=body,
                headers=self._build_headers(),
                timeout=API_TIMEOUT_S,
            )
            resp.raise_for_status()
            data = resp.json()
            base_resp = data.get("base_response", {})
            if base_resp.get("ret", 0) != 0:
                return None

            return {
                "stream_ticket": data.get("stream_ticket", ""),
                "client_stream_id": client_stream_id,
            }
        except Exception as exc:
            logger.error("wechat_stream_init_error", error=str(exc))
            return None

    async def send_stream_piece(
        self,
        client_stream_id: str,
        device_id: str,
        piece_seq: int,
        piece_data: dict[str, Any],
        stream_ticket: str,
    ) -> bool:
        """发送流式数据 piece"""
        if not self._client:
            return False

        import base64
        import json as json_mod

        piece_json = json_mod.dumps(piece_data, ensure_ascii=False)
        piece_b64 = base64.b64encode(piece_json.encode()).decode()

        body = {
            "device_id": device_id,
            "client_stream_id": client_stream_id,
            "business_type": STREAM_BUSINESS_TYPE,
            "up_piece_list": [
                {
                    "piece_seq": piece_seq,
                    "piece_data": piece_b64,
                }
            ],
            "end_up_piece_seq": 0,
            "abort_info": None,
            "base_info": self._build_base_info(),
        }

        try:
            resp = await self._client.post(
                f"{self._base_url}/ilink/bot/sync_stream",
                json=body,
                headers=self._build_headers(),
                timeout=API_TIMEOUT_S,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("base_response", {}).get("ret", 0) == 0
        except Exception as exc:
            logger.error("wechat_stream_piece_error", error=str(exc))
            return False

    async def send_stream_end(
        self,
        client_stream_id: str,
        device_id: str,
        last_piece_seq: int,
    ) -> bool:
        """结束流式输出"""
        if not self._client:
            return False

        body = {
            "device_id": device_id,
            "client_stream_id": client_stream_id,
            "business_type": STREAM_BUSINESS_TYPE,
            "up_piece_list": [],
            "end_up_piece_seq": last_piece_seq,
            "abort_info": None,
            "base_info": self._build_base_info(),
        }

        try:
            resp = await self._client.post(
                f"{self._base_url}/ilink/bot/sync_stream",
                json=body,
                headers=self._build_headers(),
                timeout=API_TIMEOUT_S,
            )
            resp.raise_for_status()
            return True
        except Exception as exc:
            logger.error("wechat_stream_end_error", error=str(exc))
            return False

    # ── 清理 ──────────────────────────────────

    async def shutdown(self) -> None:
        """关闭适配器"""
        self._running = False

        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._poll_task

        await self._notify_stop()

        if self._client:
            await self._client.aclose()
            self._client = None

        logger.info("wechat_adapter_shutdown")


# ── 辅助枚举 ──────────────────────────────────

class TypingStatus:
    TYPING = 1
    CANCEL = 2


class MessageType:
    USER = 1
    BOT = 2


class MessageState:
    NEW = 0
    GENERATING = 1
    FINISH = 2


class MessageItemType:
    TEXT = 1
    IMAGE = 2
    VOICE = 3
    FILE = 4
    VIDEO = 5
