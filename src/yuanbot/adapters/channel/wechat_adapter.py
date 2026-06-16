"""微信 iLink Bot 通道适配器

基于 @tencent-weixin/openclaw-weixin 规范实现。
通过长轮询 (getUpdates) 接收消息，通过 sendMessage 发送回复。

增强功能：
- CDN 媒体上传 (AES-128-ECB 加密) 与下载/解密
- QR 登录完整状态机（过期自动刷新、配对码、重定向）
- 持久化存储（sync_buf、context_token、账号凭据）
- 会话守卫（Session Guard: errcode=-14 暂停 1 小时）
- WeixinConfigManager（getConfig 缓存，24h TTL + 指数退避）
- 增强错误处理（连续失败退避、CDN 上传重试、错误分类）
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
import random
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
QR_TOTAL_TIMEOUT_S = 480  # 8 分钟总登录超时
QR_MAX_REFRESH_COUNT = 3
GET_UPDATES_TIMEOUT_S = 35
API_TIMEOUT_S = 15
LIGHT_API_TIMEOUT_S = 10
CDN_TIMEOUT_S = 30
CDN_MAX_RETRIES = 3

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


# ── WeixinConfigManager ───────────────────────


class WeixinConfigManager:
    """getConfig 缓存管理器

    每个用户有独立的配置缓存，24 小时 TTL（带随机抖动）。
    失败时指数退避重试（2s→4s→8s→...→1h）。
    """

    CONFIG_CACHE_TTL_MS = 24 * 60 * 60 * 1000
    CONFIG_INITIAL_RETRY_MS = 2000
    CONFIG_MAX_RETRY_MS = 60 * 60 * 1000

    def __init__(
        self,
        base_url: str,
        token: str | None,
        build_headers_fn: Callable[[], dict[str, str]],
        build_base_info_fn: Callable[[], dict[str, str]],
        timeout: int = 10,
    ) -> None:
        self._base_url = base_url
        self._token = token
        self._build_headers = build_headers_fn
        self._build_base_info = build_base_info_fn
        self._timeout = timeout
        self._cache: dict[str, _ConfigEntry] = {}
        self._http_client: httpx.AsyncClient | None = None

    async def get_typing_ticket(
        self,
        user_id: str,
        context_token: str | None = None,
    ) -> str:
        """获取 typing_ticket（带缓存/退避）

        Args:
            user_id: 用户 ID
            context_token: 可选的上下文 Token

        Returns:
            typing_ticket 字符串，失败返回空字符串
        """
        now_ms = int(time.time() * 1000)
        entry = self._cache.get(user_id)

        if entry and now_ms < entry.next_fetch_at_ms:
            return entry.config.typing_ticket

        # 到达刷新时间，发起请求
        ticket = ""
        fetch_ok = False

        try:
            fetch_result = await self._do_get_config(user_id, context_token)
            if fetch_result is not None:
                ticket = fetch_result
                fetch_ok = True
        except Exception as exc:
            logger.debug("weixin_config_fetch_failed", user_id=user_id, error=str(exc))

        if fetch_ok:
            # 成功：24h TTL + 随机抖动（5分钟内）
            jitter_ms = random.randint(0, 300_000)
            self._cache[user_id] = _ConfigEntry(
                config=_CachedConfig(typing_ticket=ticket),
                ever_succeeded=True,
                next_fetch_at_ms=now_ms + self.CONFIG_CACHE_TTL_MS + jitter_ms,
                retry_delay_ms=self.CONFIG_INITIAL_RETRY_MS,
            )
            logger.debug(
                "weixin_config_cached",
                user_id=user_id,
                ever_succeeded=True,
            )
        else:
            # 失败：指数退避
            prev_delay = entry.retry_delay_ms if entry else self.CONFIG_INITIAL_RETRY_MS
            next_delay = min(prev_delay * 2, self.CONFIG_MAX_RETRY_MS)
            self._cache[user_id] = _ConfigEntry(
                config=_CachedConfig(typing_ticket=entry.config.typing_ticket if entry else ""),
                ever_succeeded=entry.ever_succeeded if entry else False,
                next_fetch_at_ms=now_ms + next_delay,
                retry_delay_ms=next_delay,
            )

        return self._cache[user_id].config.typing_ticket

    async def _do_get_config(self, user_id: str, context_token: str | None = None) -> str | None:
        """执行 getConfig API 调用"""
        if not self._http_client:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )

        body: dict[str, Any] = {
            "ilink_user_id": user_id,
            "base_info": self._build_base_info(),
        }
        if context_token:
            body["context_token"] = context_token

        resp = await self._http_client.post(
            f"{self._base_url}/ilink/bot/getconfig",
            json=body,
            headers=self._build_headers(),
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("ret", 0) == 0:
            return data.get("typing_ticket", "")
        return None

    async def close(self) -> None:
        """释放 HTTP 客户端"""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


class _CachedConfig:
    """缓存配置项（内部使用）"""

    __slots__ = ("typing_ticket",)

    def __init__(self, typing_ticket: str) -> None:
        self.typing_ticket = typing_ticket


class _ConfigEntry:
    """缓存条目（内部使用）"""

    __slots__ = ("config", "ever_succeeded", "next_fetch_at_ms", "retry_delay_ms")

    def __init__(
        self,
        config: _CachedConfig,
        ever_succeeded: bool,
        next_fetch_at_ms: int,
        retry_delay_ms: int,
    ) -> None:
        self.config = config
        self.ever_succeeded = ever_succeeded
        self.next_fetch_at_ms = next_fetch_at_ms
        self.retry_delay_ms = retry_delay_ms


# ── WeixinAdapter ─────────────────────────────


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
        self._config_mgr: WeixinConfigManager | None = None
        self._callback: Callable[[UserMessage], Awaitable[BotResponse]] | None = None

        # 同步游标（持久化）
        self._sync_buf: str = ""

        # contextToken 存储: from_user_id -> context_token（持久化）
        self._context_tokens: dict[str, str] = {}

        # 会话过期守卫
        self._session_paused_until: float = 0

        # 长轮询控制
        self._running = False
        self._poll_task: asyncio.Task | None = None

        # 连续失败计数
        self._consecutive_failures = 0

        # ── 持久化状态目录 ──
        self._state_dir: str = ""
        self._state_dir_initialized = False

    # ── 属性 ───────────────────────────────────

    @property
    def platform_name(self) -> str:
        return "wechat"

    @property
    def supported_content_types(self) -> list[ContentType]:
        return [
            ContentType.TEXT,
            ContentType.IMAGE,
            ContentType.VOICE,
            ContentType.VIDEO,
            ContentType.FILE,
        ]

    # ── ChannelAdapter 接口实现 ────────────────

    async def initialize(self, config: ChannelConfig) -> None:
        """初始化适配器"""
        cfg = config.config
        self._token = cfg.get("token", "")
        self._ilink_user_id = cfg.get("ilink_user_id", "")
        self._bot_id = cfg.get("bot_id", "")
        self._base_url = cfg.get("base_url", FIXED_BASE_URL)
        self._cdn_base_url = cfg.get("cdn_base_url", DEFAULT_CDN_BASE_URL)
        self._bot_agent = cfg.get("bot_agent", DEFAULT_BOT_AGENT)
        self._state_dir = cfg.get("state_dir", "")

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(API_TIMEOUT_S),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

        # 初始化配置管理器
        self._config_mgr = WeixinConfigManager(
            base_url=self._base_url,
            token=self._token,
            build_headers_fn=lambda: self._build_headers(),
            build_base_info_fn=lambda: self._build_base_info(),
            timeout=LIGHT_API_TIMEOUT_S,
        )

        # 恢复持久化状态
        await self._load_persisted_state()

        if self._token:
            logger.info(
                "wechat_adapter_initialized",
                base_url=self._base_url,
                bot_id=self._bot_id,
            )
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

        # 会话守卫
        try:
            self._assert_session_active()
        except RuntimeError as exc:
            return SendResult(success=False, error=str(exc))

        context_token = self._context_tokens.get(target_id, "")

        if content.content_type == ContentType.TEXT:
            return await self._send_text(target_id, content.text or "", context_token)
        elif content.content_type in (
            ContentType.IMAGE,
            ContentType.VOICE,
            ContentType.VIDEO,
            ContentType.FILE,
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

        qr_data = await self._fetch_qrcode()
        return qr_data

    async def poll_login_status(self, qrcode: str, verify_code: str = "") -> dict[str, Any]:
        """轮询二维码状态（单次轮询）

        Returns:
            {status, token?, user_id?, bot_id?, base_url?, redirect_host?}
        """
        return await self._poll_qrcode_status(qrcode, verify_code)

    async def login_with_qr_full(self) -> dict[str, Any]:
        """完整 QR 码登录流程（状态机）

        包含完整的状态跳转、过期自动刷新（最多 3 次）、配对码输入支持。

        Returns:
            成功: {status:"confirmed", token, user_id, bot_id, base_url}
            失败: {status:"error", error:"错误消息"}
        """
        if not self._client:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(API_TIMEOUT_S))

        deadline = time.time() + QR_TOTAL_TIMEOUT_S
        qr_refresh_count = 0
        current_base_url = self._base_url
        pending_verify_code = ""
        local_token_list: list[str] = []

        # 首次获取二维码
        qr_data = await self._fetch_qrcode_with_local_tokens(local_token_list)
        qrcode = qr_data.get("qrcode", "")
        qrcode_img_url = qr_data.get("qrcode_img_url", "")

        logger.info("wechat_qr_login_started", qrcode_img_url=qrcode_img_url)

        while time.time() < deadline:
            # 二维码过期刷新
            if not qrcode:
                qr_refresh_count += 1
                if qr_refresh_count > QR_MAX_REFRESH_COUNT:
                    return {
                        "status": "error",
                        "error": f"二维码已失效 {QR_MAX_REFRESH_COUNT} 次，登录流程已停止",
                    }

                logger.info("wechat_qr_refresh", attempt=qr_refresh_count)
                qr_data = await self._fetch_qrcode_with_local_tokens(local_token_list)
                qrcode = qr_data.get("qrcode", "")
                qrcode_img_url = qr_data.get("qrcode_img_url", "")

                if not qrcode:
                    continue

                logger.info("wechat_qr_refreshed", qrcode_img_url=qrcode_img_url)

            # 轮询状态
            status_data = await self._poll_qrcode_status_with_base_url(
                qrcode=qrcode,
                verify_code=pending_verify_code,
                base_url=current_base_url,
            )

            status = status_data.get("status", "wait")

            if status in ("wait", "scaned"):
                # 配对码已提交，继续
                if pending_verify_code:
                    pending_verify_code = ""
                # 等待中
                continue

            elif status == "need_verifycode":
                # 需要配对码，标记后继续轮询（首次空字符串，之后由外部设置）
                if not pending_verify_code:
                    return {
                        "status": "need_verifycode",
                        "qrcode": qrcode,
                        "qrcode_img_url": qrcode_img_url,
                        "message": "请在手机微信中输入配对码后重新调用 poll_login_status",
                    }
                continue

            elif status == "scaned_but_redirect":
                redirect_host = status_data.get("redirect_host", "")
                if redirect_host:
                    current_base_url = f"https://{redirect_host}"
                    logger.info("wechat_qr_redirect", new_base_url=current_base_url)
                continue

            elif status == "binded_redirect":
                return {
                    "status": "binded_redirect",
                    "message": "已绑定到此实例，无需重复登录",
                }

            elif status == "expired":
                qrcode = ""  # 触发刷新
                qr_refresh_count += 1
                if qr_refresh_count > QR_MAX_REFRESH_COUNT:
                    return {
                        "status": "error",
                        "error": f"二维码已过期 {QR_MAX_REFRESH_COUNT} 次，登录流程已停止",
                    }
                logger.info("wechat_qr_expired_refresh", attempt=qr_refresh_count)
                continue

            elif status == "verify_code_blocked":
                pending_verify_code = ""
                qrcode = ""  # 触发刷新
                qr_refresh_count += 1
                if qr_refresh_count > QR_MAX_REFRESH_COUNT:
                    return {
                        "status": "error",
                        "error": "验证码多次错误，登录流程已停止",
                    }
                logger.info("wechat_qr_verify_code_blocked_refresh", attempt=qr_refresh_count)
                continue

            elif status == "confirmed":
                # 登录成功
                token = status_data.get("token", "")
                user_id = status_data.get("user_id", "")
                bot_id = status_data.get("bot_id", "")
                base_url = status_data.get("base_url", current_base_url)

                self._token = token
                self._ilink_user_id = user_id
                self._bot_id = bot_id
                self._base_url = base_url

                # 持久化账号凭据
                await self._save_account_credentials()

                # 更新配置管理器
                if self._config_mgr:
                    self._config_mgr._base_url = base_url

                logger.info(
                    "wechat_qr_login_success",
                    bot_id=bot_id,
                    user_id=user_id,
                    base_url=base_url,
                )

                return {
                    "status": "confirmed",
                    "token": token,
                    "user_id": user_id,
                    "bot_id": bot_id,
                    "base_url": base_url,
                }

            elif status == "error":
                return {"status": "error", "error": status_data.get("error", "未知错误")}

        return {"status": "error", "error": "登录超时，请重试"}

    # ── 长轮询主循环 ──────────────────────────

    async def _poll_loop(self) -> None:
        """getUpdates 长轮询主循环"""
        logger.info("wechat_poll_loop_started")

        while self._running:
            try:
                # 会话守卫
                if time.time() < self._session_paused_until:
                    wait_time = self._session_paused_until - time.time()
                    logger.info("wechat_session_paused", wait_seconds=int(wait_time))
                    await asyncio.sleep(min(wait_time, 60))
                    continue

                # 长轮询请求
                resp = await self._get_updates()

                if resp is None:
                    continue

                ret = resp.get("ret", 0)
                errcode = resp.get("errcode", 0)

                # 会话过期处理
                if errcode == SESSION_EXPIRED_ERRCODE or ret == SESSION_EXPIRED_ERRCODE:
                    self._session_paused_until = time.time() + SESSION_PAUSE_DURATION_S
                    logger.warning(
                        "wechat_session_expired",
                        pause_seconds=SESSION_PAUSE_DURATION_S,
                    )
                    continue

                # 成功，重置失败计数
                self._consecutive_failures = 0

                # 更新同步游标并持久化
                new_buf = resp.get("get_updates_buf", "")
                if new_buf and new_buf != self._sync_buf:
                    self._sync_buf = new_buf
                    await self._save_sync_buf()

                # 处理消息
                msgs = resp.get("msgs", [])
                for msg in msgs:
                    await self._process_message(msg)

                # 持久化 context_tokens（有更新时）
                if msgs:
                    await self._save_context_tokens()

                # 服务端建议的超时
                server_timeout = resp.get("longpolling_timeout_ms")
                if server_timeout:
                    logger.debug("wechat_server_timeout_hint", ms=server_timeout)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._consecutive_failures += 1
                logger.error(
                    "wechat_poll_error",
                    error=str(exc),
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
            return {"ret": 0, "msgs": []}
        except httpx.HTTPStatusError as exc:
            if self._is_server_error(exc.response.status_code):
                logger.error(
                    "wechat_getupdates_server_error",
                    status=exc.response.status_code,
                )
            else:
                logger.error(
                    "wechat_getupdates_client_error",
                    status=exc.response.status_code,
                )
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
            old_token = self._context_tokens.get(from_user_id)
            if context_token != old_token:
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

        # 图片消息可能有单独 aeskey 字段（hex 编码）
        image_aeskey_hex = item_data.get("aeskey", "")

        media_path = ""

        if encrypt_query_param or full_url:
            try:
                if image_aeskey_hex and content_type == ContentType.IMAGE:
                    # 优先使用 image_item.aeskey (hex 编码)
                    aes_key_bytes = bytes.fromhex(image_aeskey_hex)
                    aes_key_b64_for_download = base64.b64encode(aes_key_bytes).decode()
                else:
                    aes_key_b64_for_download = aes_key_b64

                plaintext = await download_media_file(
                    encrypt_query_param=encrypt_query_param,
                    aes_key_b64=aes_key_b64_for_download,
                    item_type=item_type,
                    cdn_base_url=self._cdn_base_url,
                    full_url=full_url,
                )

                if plaintext:
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
                    logger.warning("wechat_media_download_failed", type=content_type.value)

            except Exception as exc:
                logger.error("wechat_media_download_error", type=content_type.value, error=str(exc))

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
            file_data, file_name, mime_type = await self._load_media_data(content.media_url)
        elif content.text:
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
        )

        media_type = mime_to_media_type(mime_type)

        # 3. CDN 上传（使用增强版上传，正确捕获 x-encrypted-param）
        upload_result = await self._upload_media_to_cdn(
            file_data=file_data,
            media_type=media_type,
            to_user_id=target_id,
        )

        if not upload_result:
            return SendResult(success=False, error="CDN upload failed")

        # 4. 构造 MessageItem 并发送
        media_ref = get_media_ref_from_upload(upload_result)
        return await self._send_media_message(
            target_id,
            media_type,
            media_ref,
            context_token,
            file_name=file_name,
            file_size=upload_result.file_size_plain,
        )

    async def _load_media_data(self, media_url: str) -> tuple[bytes, str, str]:
        """加载媒体数据（本地文件或远程 URL）

        Returns:
            (file_data, file_name, mime_type)
        """
        from yuanbot.adapters.channel.weixin_cdn import extension_to_mime

        if media_url.startswith("http://") or media_url.startswith("https://"):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(media_url)
                    resp.raise_for_status()
                    file_data = resp.content
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
        if not self._client or not self._config_mgr:
            return

        ticket = await self._config_mgr.get_typing_ticket(user_id)
        if not ticket:
            return

        body = {
            "ilink_user_id": user_id,
            "typing_ticket": ticket,
            "status": status,
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

    # ── CDN 媒体上传 ──────────────────────────

    async def _upload_media_to_cdn(
        self,
        file_data: bytes,
        media_type: int,
        to_user_id: str,
    ) -> Any:
        """通用 CDN 上传流程

        完整的 CDN 上传流程：
        1. 生成 file_key + aes_key
        2. 计算明文 MD5 + 大小
        3. 调用 getUploadUrl 获取预签名参数
        4. AES-128-ECB 加密文件
        5. POST 加密数据到 CDN
        6. 从 CDN 响应头 x-encrypted-param 获取下载参数

        Args:
            file_data: 明文文件数据
            media_type: 媒体类型 (1=IMAGE, 2=VIDEO, 3=FILE, 4=VOICE)
            to_user_id: 目标用户 ID

        Returns:
            UploadResult(dataclass) 或 None
        """
        from yuanbot.adapters.channel.weixin_cdn import (
            UploadResult,
            aes_ecb_encrypt,
            aes_ecb_padded_size,
            call_get_upload_url,
            compute_md5,
            generate_aes_key,
            generate_file_key,
        )

        raw_size = len(file_data)
        if raw_size > 100 * 1024 * 1024:  # 100MB
            logger.error("file_too_large", size=raw_size, max=100 * 1024 * 1024)
            return None

        # 1. 生成密钥和文件标识
        file_key = generate_file_key()
        aes_key_bytes, aes_key_hex = generate_aes_key()

        # 2. 计算 MD5 和密文大小
        raw_md5 = compute_md5(file_data)
        cipher_size = aes_ecb_padded_size(raw_size)

        # 3. 调用 getUploadUrl
        upload_url_data = await call_get_upload_url(
            http_client=self._client,
            base_url=self._base_url,
            headers=self._build_headers(),
            base_info=self._build_base_info(),
            file_key=file_key,
            media_type=media_type,
            to_user_id=to_user_id,
            raw_size=raw_size,
            raw_md5=raw_md5,
            cipher_size=cipher_size,
            aes_key_hex=aes_key_hex,
        )

        if not upload_url_data:
            return None

        upload_param = upload_url_data.get("upload_param", "")
        upload_full_url = upload_url_data.get("upload_full_url", "")

        # 4. 构建 CDN 上传 URL
        cdn_url = upload_full_url or self._build_cdn_upload_url(upload_param, file_key)
        if not cdn_url:
            logger.error("no_cdn_upload_url")
            return None

        # 5. AES 加密
        ciphertext = aes_ecb_encrypt(file_data, aes_key_bytes)

        # 6. 上传到 CDN（捕获 x-encrypted-param）
        download_param = await self._upload_buffer_to_cdn(ciphertext, cdn_url)
        if not download_param:
            return None

        logger.info(
            "wechat_cdn_upload_success",
            file_key=file_key,
            raw_size=raw_size,
            cipher_size=cipher_size,
            media_type=media_type,
        )

        return UploadResult(
            file_key=file_key,
            download_encrypted_param=download_param,
            aes_key_hex=aes_key_hex,
            file_size_plain=raw_size,
            file_size_cipher=cipher_size,
        )

    async def _upload_image(self, file_data: bytes, to_user_id: str) -> Any:
        """上传图片并返回上传结果"""
        from yuanbot.adapters.channel.weixin_cdn import UploadMediaType

        return await self._upload_media_to_cdn(
            file_data=file_data,
            media_type=UploadMediaType.IMAGE,
            to_user_id=to_user_id,
        )

    async def _upload_video(self, file_data: bytes, to_user_id: str) -> Any:
        """上传视频并返回上传结果"""
        from yuanbot.adapters.channel.weixin_cdn import UploadMediaType

        return await self._upload_media_to_cdn(
            file_data=file_data,
            media_type=UploadMediaType.VIDEO,
            to_user_id=to_user_id,
        )

    async def _upload_file(self, file_data: bytes, to_user_id: str) -> Any:
        """上传文件并返回上传结果"""
        from yuanbot.adapters.channel.weixin_cdn import UploadMediaType

        return await self._upload_media_to_cdn(
            file_data=file_data,
            media_type=UploadMediaType.FILE,
            to_user_id=to_user_id,
        )

    # ── CDN 媒体下载与解密 ────────────────────

    async def _download_and_decrypt_buffer(
        self,
        encrypt_query_param: str,
        aes_key_b64: str,
        label: str = "media",
        full_url: str = "",
    ) -> bytes | None:
        """CDN 下载 + AES 解密

        Args:
            encrypt_query_param: CDN 加密查询参数
            aes_key_b64: base64 编码的 AES 密钥
            label: 日志标签
            full_url: 服务端返回的完整下载 URL（优先使用）

        Returns:
            解密后的明文数据，失败返回 None
        """
        from yuanbot.adapters.channel.weixin_cdn import (
            download_media_file,
        )

        return await download_media_file(
            encrypt_query_param=encrypt_query_param,
            aes_key_b64=aes_key_b64,
            item_type=0,
            cdn_base_url=self._cdn_base_url,
            full_url=full_url,
        )

    @staticmethod
    def _parse_aes_key(aes_key_b64: str) -> bytes | None:
        """解析 AES 密钥，支持两种编码格式

        方式 1: base64(raw 16 bytes) → 直接得到 16 字节密钥
        方式 2: base64(32 字符 hex 字符串) → 先 base64 解码得 32 字节 hex 字符串，
           再解析为 16 字节密钥

        Args:
            aes_key_b64: base64 编码的 AES 密钥

        Returns:
            16 字节密钥，失败返回 None
        """
        import base64

        if not aes_key_b64:
            return None

        try:
            decoded = base64.b64decode(aes_key_b64)
        except Exception:
            return None

        # 方式 1: 直接 16 字节密钥
        if len(decoded) == 16:
            return decoded

        # 方式 2: 32 字符 hex 字符串
        if len(decoded) == 32:
            try:
                hex_str = decoded.decode("ascii")
                if all(c in "0123456789abcdefABCDEF" for c in hex_str):
                    return bytes.fromhex(hex_str)
            except (ValueError, UnicodeDecodeError):
                pass

        return None

    @staticmethod
    def _build_cdn_download_url(encrypt_query_param: str, cdn_base_url: str) -> str:
        """构建 CDN 下载 URL"""
        from urllib.parse import quote

        return f"{cdn_base_url}/download?encrypted_query_param={quote(encrypt_query_param)}"

    @staticmethod
    def _build_cdn_upload_url(upload_param: str, file_key: str) -> str:
        """构建 CDN 上传 URL"""
        from urllib.parse import quote

        return (
            f"{DEFAULT_CDN_BASE_URL}/upload"
            f"?encrypted_query_param={quote(upload_param)}"
            f"&filekey={quote(file_key)}"
        )

    async def _upload_buffer_to_cdn(
        self,
        ciphertext: bytes,
        cdn_url: str,
    ) -> str | None:
        """POST 加密数据到 CDN，捕获 x-encrypted-param 响应头

        最多重试 CDN_MAX_RETRIES 次。
        客户端错误 (4xx) 直接抛出，不重试。

        Args:
            ciphertext: AES-128-ECB 加密后的密文
            cdn_url: CDN 上传完整 URL

        Returns:
            x-encrypted-param 响应头值（下载参数），失败返回 None
        """
        for attempt in range(1, CDN_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(CDN_TIMEOUT_S)) as cdn_client:
                    resp = await cdn_client.post(
                        cdn_url,
                        content=ciphertext,
                        headers={"Content-Type": "application/octet-stream"},
                    )

                    # 客户端错误：不重试
                    if 400 <= resp.status_code < 500:
                        logger.error(
                            "cdn_upload_client_error",
                            status=resp.status_code,
                            attempt=attempt,
                        )
                        return None

                    # 服务端错误：重试
                    if resp.status_code >= 500:
                        logger.warning(
                            "cdn_upload_server_error",
                            status=resp.status_code,
                            attempt=attempt,
                        )
                        if attempt < CDN_MAX_RETRIES:
                            continue
                        return None

                    # 成功 (200)
                    download_param = resp.headers.get("x-encrypted-param")
                    if not download_param:
                        logger.error(
                            "cdn_upload_missing_x_encrypted_param",
                            attempt=attempt,
                        )
                        if attempt < CDN_MAX_RETRIES:
                            continue
                        return None

                    return download_param

            except httpx.TimeoutException:
                logger.warning("cdn_upload_timeout", attempt=attempt)
                if attempt < CDN_MAX_RETRIES:
                    continue
                return None
            except Exception as exc:
                logger.error("cdn_upload_error", error=str(exc), attempt=attempt)
                if attempt < CDN_MAX_RETRIES:
                    continue
                return None

        return None

    # ── QR 码登录 API ─────────────────────────

    async def _fetch_qrcode(self) -> dict[str, str]:
        """获取登录二维码"""
        assert self._client is not None

        body = {"local_token_list": []}

        resp = await self._client.post(
            f"{FIXED_BASE_URL}/ilink/bot/get_bot_qrcode?bot_type={DEFAULT_BOT_TYPE}",
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

    async def _fetch_qrcode_with_local_tokens(
        self,
        local_token_list: list[str],
    ) -> dict[str, str]:
        """获取登录二维码（携带本地已有 token 去重）"""
        assert self._client is not None

        # 最多携带 10 个 token
        tokens = local_token_list[-10:]

        body = {"local_token_list": tokens}

        resp = await self._client.post(
            f"{FIXED_BASE_URL}/ilink/bot/get_bot_qrcode?bot_type={DEFAULT_BOT_TYPE}",
            json=body,
            headers=self._build_headers(include_auth=False),
            timeout=API_TIMEOUT_S,
        )
        resp.raise_for_status()
        data = resp.json()

        qrcode = data.get("qrcode", "")
        qrcode_img_url = data.get("qrcode_img_content", "")

        return {
            "qrcode": qrcode,
            "qrcode_img_url": qrcode_img_url,
        }

    async def _poll_qrcode_status(
        self,
        qrcode: str,
        verify_code: str = "",
    ) -> dict[str, Any]:
        """轮询二维码状态（使用当前 base_url）"""
        return await self._poll_qrcode_status_with_base_url(
            qrcode=qrcode,
            verify_code=verify_code,
            base_url=self._base_url,
        )

    async def _poll_qrcode_status_with_base_url(
        self,
        qrcode: str,
        verify_code: str = "",
        base_url: str = "",
    ) -> dict[str, Any]:
        """轮询二维码状态（指定 base_url）"""
        assert self._client is not None

        base_url = base_url or self._base_url
        params: dict[str, str] = {"qrcode": qrcode}
        if verify_code:
            params["verify_code"] = verify_code

        try:
            resp = await self._client.get(
                f"{base_url}/ilink/bot/get_qrcode_status",
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
                result["base_url"] = data.get("baseurl", base_url)
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
        rand_bytes = os.urandom(4)
        uint32_val = int.from_bytes(rand_bytes, "big")
        uin_b64 = base64.b64encode(str(uint32_val).encode()).decode()

        version_parts = [2, 4, 3]
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

    # ── 会话守卫 ──────────────────────────────

    def _assert_session_active(self) -> None:
        """断言会话活跃，否则抛出 RuntimeError"""
        if time.time() < self._session_paused_until:
            remaining_min = int((self._session_paused_until - time.time()) / 60)
            raise RuntimeError(
                f"会话已暂停 (errcode={SESSION_EXPIRED_ERRCODE})，剩余 {remaining_min} 分钟恢复"
            )

    # ── 持久化存储 ────────────────────────────

    async def _init_state_dir(self) -> None:
        """初始化持久化状态目录"""
        if self._state_dir_initialized:
            return

        if not self._state_dir:
            # 默认使用 WORKSPACE/.yuanbot/weixin 目录
            workspace_dir = os.environ.get(
                "YUANBOT_WORKSPACE",
                os.path.join(os.path.expanduser("~"), ".openclaw", "workspace"),
            )
            self._state_dir = os.path.join(workspace_dir, ".yuanbot", "weixin")

        os.makedirs(self._state_dir, exist_ok=True)
        self._state_dir_initialized = True
        logger.debug("wechat_state_dir_initialized", path=self._state_dir)

    @property
    def _sync_buf_path(self) -> str:
        """get_updates_buf 持久化文件路径"""
        account_suffix = self._bot_id or "default"
        safe_name = account_suffix.replace("@", "-").replace(".", "-")
        return os.path.join(self._state_dir, f"sync_buf_{safe_name}.json")

    @property
    def _context_tokens_path(self) -> str:
        """context_tokens 持久化文件路径"""
        account_suffix = self._bot_id or "default"
        safe_name = account_suffix.replace("@", "-").replace(".", "-")
        return os.path.join(self._state_dir, f"context_tokens_{safe_name}.json")

    @property
    def _account_credentials_path(self) -> str:
        """账号凭据持久化文件路径"""
        account_suffix = self._bot_id or "default"
        safe_name = account_suffix.replace("@", "-").replace(".", "-")
        return os.path.join(self._state_dir, f"account_{safe_name}.json")

    async def _load_persisted_state(self) -> None:
        """加载持久化状态（启动时恢复）"""
        await self._init_state_dir()

        # 1. 恢复 sync_buf
        try:
            sync_path = self._sync_buf_path
            if os.path.exists(sync_path):
                with open(sync_path) as f:
                    data = json.load(f)
                persisted_buf = data.get("get_updates_buf", "")
                if persisted_buf:
                    self._sync_buf = persisted_buf
                    logger.info("wechat_restored_sync_buf")
        except Exception as exc:
            logger.warning("wechat_restore_sync_buf_failed", error=str(exc))

        # 2. 恢复 context_tokens
        try:
            tokens_path = self._context_tokens_path
            if os.path.exists(tokens_path):
                with open(tokens_path) as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self._context_tokens.update(data)
                    logger.info(
                        "wechat_restored_context_tokens",
                        count=len(data),
                    )
        except Exception as exc:
            logger.warning("wechat_restore_context_tokens_failed", error=str(exc))

        # 3. 恢复账号凭据
        try:
            cred_path = self._account_credentials_path
            if os.path.exists(cred_path):
                with open(cred_path) as f:
                    data = json.load(f)
                if data.get("token") and not self._token:
                    self._token = data["token"]
                    self._base_url = data.get("base_url", self._base_url)
                    self._bot_id = data.get("bot_id", self._bot_id)
                    self._ilink_user_id = data.get("user_id", self._ilink_user_id)
                    logger.info("wechat_restored_account_credentials")
        except Exception as exc:
            logger.warning("wechat_restore_account_failed", error=str(exc))

    async def _save_sync_buf(self) -> None:
        """持久化 get_updates_buf"""
        if not self._state_dir_initialized:
            return

        try:
            sync_path = self._sync_buf_path
            os.makedirs(os.path.dirname(sync_path), exist_ok=True)
            with open(sync_path, "w") as f:
                json.dump({"get_updates_buf": self._sync_buf}, f)
        except Exception as exc:
            logger.warning("wechat_save_sync_buf_failed", error=str(exc))

    async def _save_context_tokens(self) -> None:
        """持久化 context_tokens"""
        if not self._state_dir_initialized or not self._context_tokens:
            return

        try:
            tokens_path = self._context_tokens_path
            os.makedirs(os.path.dirname(tokens_path), exist_ok=True)
            with open(tokens_path, "w") as f:
                json.dump(self._context_tokens, f)
        except Exception as exc:
            logger.warning("wechat_save_context_tokens_failed", error=str(exc))

    async def _save_account_credentials(self) -> None:
        """持久化账号凭据（token/baseUrl/userId）"""
        if not self._state_dir_initialized:
            return

        try:
            cred_path = self._account_credentials_path
            os.makedirs(os.path.dirname(cred_path), exist_ok=True)
            data = {
                "token": self._token or "",
                "base_url": self._base_url,
                "bot_id": self._bot_id or "",
                "user_id": self._ilink_user_id or "",
            }
            with open(cred_path, "w") as f:
                json.dump(data, f, indent=2)
            # 权限保护
            try:
                os.chmod(cred_path, 0o600)
            except OSError:
                pass
            logger.info("wechat_saved_account_credentials")
        except Exception as exc:
            logger.warning("wechat_save_account_failed", error=str(exc))

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

    # ── 错误处理工具 ──────────────────────────

    @staticmethod
    def _is_server_error(status_code: int) -> bool:
        """判断是否为服务端错误（5xx）"""
        return 500 <= status_code < 600

    @staticmethod
    def _is_client_error(status_code: int) -> bool:
        """判断是否为客户端错误（4xx）"""
        return 400 <= status_code < 500

    @staticmethod
    def _should_retry(status_code: int) -> bool:
        """判断是否应该重试（服务端错误可重试，客户端错误不可重试）"""
        return 500 <= status_code < 600

    # ── 清理 ──────────────────────────────────

    async def shutdown(self) -> None:
        """关闭适配器"""
        self._running = False

        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._poll_task

        await self._notify_stop()

        # 持久化最终状态
        await self._save_sync_buf()
        await self._save_context_tokens()

        if self._config_mgr:
            await self._config_mgr.close()

        if self._client:
            await self._client.aclose()
            self._client = None

        logger.info("wechat_adapter_shutdown")


# ── 辅助枚举 ──────────────────────────────────


class TypingStatus:
    """输入状态枚举"""

    TYPING = 1
    CANCEL = 2


class MessageType:
    """消息类型枚举"""

    USER = 1
    BOT = 2


class MessageState:
    """消息状态枚举"""

    NEW = 0
    GENERATING = 1
    FINISH = 2


class MessageItemType:
    """消息段类型枚举"""

    TEXT = 1
    IMAGE = 2
    VOICE = 3
    FILE = 4
    VIDEO = 5
