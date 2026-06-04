"""YuanBot FastAPI 应用

集成所有子系统的完整应用入口。
使用 AIService 门面、CapabilityOrchestrator、事件队列等新组件。

设计参考: architecture-v1.4.md + 所有详细设计文档
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from starlette.websockets import WebSocket

from yuanbot.adapters.channel.web_adapter import WebAdapter
from yuanbot.auth.admin_routes import init_admin_stores
from yuanbot.auth.admin_routes import router as admin_router
from yuanbot.auth.conversation_routes import init_conversation_store
from yuanbot.auth.conversation_routes import router as conversation_router
from yuanbot.auth.middleware import AuthManager, init_auth_manager
from yuanbot.auth.routes import router as auth_router
from yuanbot.auth.store import ConversationStore, UserStore
from yuanbot.config import YuanBotConfig
from yuanbot.core.types import BotResponse
from yuanbot.gateway.privacy import PrivacyManager
from yuanbot.infrastructure.config_watcher import ConfigWatcher
from yuanbot.memory.manager import MemoryManager
from yuanbot.orchestrator.engine import OrchestratorEngine
from yuanbot.persona.engines.context_builder import ContextBuilder
from yuanbot.persona.engines.dialogue_decision import DialogueDecisionEngine
from yuanbot.proactive.event_engine import EventEngine
from yuanbot.proactive.scheduler import ProactiveScheduler
from yuanbot.proactive.strategy import ProactiveStrategy
from yuanbot.providers.manager import ProviderManager
from yuanbot.providers.registry import ProviderRegistry
from yuanbot.services.ai_service import AIService
from yuanbot.services.capability_orchestrator import CapabilityOrchestrator
from yuanbot.services.extension_standard import ExtensionManifest, ExtensionValidator
from yuanbot.skills.manager import SkillManager
from yuanbot.tools.manager import ToolManager


def create_app(config: YuanBotConfig) -> FastAPI:
    """创建 YuanBot FastAPI 应用"""

    # ── 0. 配置日志文件输出与轮转 ──────────────
    try:
        from yuanbot.infrastructure.logging_config import setup_file_logging
        setup_file_logging(
            level=config.log_level.upper() if hasattr(config, 'log_level') else "INFO",
        )
    except Exception:
        pass  # 日志配置失败不影响启动

    # ── 1. 初始化基础设施 ──────────────────────
    memory_manager = MemoryManager(config=config.memory.model_dump())

    # ── 2. 初始化 AI 提供商系统 ────────────────
    config_dir = Path("configs")
    provider_registry = ProviderRegistry()
    provider_manager = ProviderManager(
        registry=provider_registry,
        config_dir=config_dir,
    )
    # 从 configs/Providers/*.yaml 加载所有 Provider 配置
    provider_manager.load_providers()

    # 设置默认提供商（从 bot.yaml 读取）
    if hasattr(config, "ai") and hasattr(config.ai, "default_provider"):
        try:
            provider_manager.set_default_provider(config.ai.default_provider)
        except ValueError:
            pass

    ai_service = AIService(
        provider_manager=provider_manager,
        config=config.ai.model_dump() if hasattr(config, "ai") else {},
    )

    # ── 3. 初始化能力系统 ──────────────────────
    skill_manager = SkillManager()
    tool_manager = ToolManager()
    capability_orchestrator = CapabilityOrchestrator(
        skill_manager=skill_manager,
        tool_manager=tool_manager,
        ai_service=ai_service,
    )

    # ── 4. 初始化人格与决策系统 ────────────────
    persona = _load_persona(config)

    # 初始化人设管理器
    from yuanbot.persona.manager import PersonaManager

    persona_manager = PersonaManager(
        config_dir=config_dir,
        default_persona_id=config.persona.id if hasattr(config, 'persona') else "default",
    )
    persona_manager.load_personas()
    # 用管理器中的活跃人设替换默认人设
    persona = persona_manager.active_persona

    decision_engine = DialogueDecisionEngine()
    context_builder = ContextBuilder(persona)

    # ── 5. 初始化编排引擎 ─────────────────────
    orchestrator = OrchestratorEngine(
        ai_service=ai_service,
        persona=persona,
        memory_manager=memory_manager,
        decision_engine=decision_engine,
        context_builder=context_builder,
        capability_orchestrator=capability_orchestrator,
    )

    # ── 6. 初始化主动陪伴系统 ──────────────────
    proactive_config = config.proactive.model_dump()
    from yuanbot.gateway.push_dispatcher import PushDispatcher

    push_dispatcher = PushDispatcher()

    proactive_scheduler = ProactiveScheduler(
        config=proactive_config,
        memory_manager=memory_manager,
        ai_service=ai_service,
        push_dispatcher=push_dispatcher,
    )

    proactive_strategy = ProactiveStrategy(
        config=proactive_config,
        memory_manager=memory_manager,
        ai_service=ai_service,
        persona=persona,
    )

    event_engine = EventEngine(
        config=proactive_config,
        memory_manager=memory_manager,
    )

    # ── 7. 认证与用户系统 ───────────────────────
    import hashlib

    auth_secret = hashlib.sha256(
        f"yuanbot-{config.app_name}-{config.version}".encode()
    ).hexdigest()
    auth_manager = AuthManager(
        secret_key=auth_secret,
        token_expire_hours=24,
    )
    user_store = UserStore(data_dir="data")
    conv_store = ConversationStore(data_dir="data")
    auth_manager.set_user_store(user_store)
    init_auth_manager(auth_manager)
    init_conversation_store(conv_store)
    init_admin_stores(user_store, conv_store)

    # ── 8. Web 通道适配器 ─────────────────────
    web_adapter = WebAdapter()

    # ── 8. TTS 系统 ─────────────────────────────
    from yuanbot.tts.manager import TTSManager

    tts_manager = TTSManager()
    try:
        from yuanbot.tts.edge_tts_adapter import EdgeTTSAdapter

        tts_manager.register_adapter(EdgeTTSAdapter())
    except Exception:
        pass
    try:
        from yuanbot.tts.openai_tts_adapter import OpenAITTSAdapter

        tts_manager.register_adapter(OpenAITTSAdapter())
    except Exception:
        pass

    # ── 9. 配置热加载监听器 ─────────────────────
    config_dir = Path("configs")
    config_watcher = ConfigWatcher(config_dir=config_dir)

    async def _on_provider_config_change(file_path: str, new_config: dict) -> None:
        """提供商配置变化回调：重载提供商"""
        import structlog

        _logger = structlog.get_logger("config_watcher")
        _logger.info("provider_config_changed", file=file_path)
        try:
            provider_id = Path(file_path).stem
            await provider_manager.reload_provider(provider_id, new_config)
        except Exception:
            _logger.exception("provider_reload_failed", file=file_path)

    async def _on_channel_config_change(file_path: str, new_config: dict) -> None:
        """通道配置变化回调：重载通道适配器"""
        import structlog

        _logger = structlog.get_logger("config_watcher")
        _logger.info("channel_config_changed", file=file_path)

    config_watcher.on_change("Providers/*.yaml", _on_provider_config_change)
    config_watcher.on_change("Channels/*.yaml", _on_channel_config_change)

    # ── 应用生命周期 ──────────────────────────

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """应用生命周期管理"""

        # 加载 Skills 和 Tools
        await skill_manager.load_skills()
        await tool_manager.load_tools()

        # 初始化记忆管理器（包括自动 Redis 缓存）
        await memory_manager.initialize()

        # 初始化用户与会话存储
        await user_store.initialize()
        await conv_store.initialize()

        # 首次启动自动创建管理员
        if user_store.user_count == 0:
            import os

            admin_password = os.environ.get("YUANBOT_ADMIN_PASSWORD", "admin123")
            user_store.create_user(
                username="admin",
                password=admin_password,
                display_name="管理员",
                role="admin",
            )
            print(f"🌸 已自动创建管理员账号 (admin / {admin_password})")
            print("   请通过环境变量 YUANBOT_ADMIN_PASSWORD 设置安全密码")

        # 启动 Web 适配器
        async def on_message(msg: Any) -> BotResponse:
            return await orchestrator.process_message(msg)

        await web_adapter.listen(on_message)

        # 启动主动陪伴系统
        await proactive_scheduler.start()
        await event_engine.start()

        # 启动配置热加载监听器
        await config_watcher.start()
        print("🌸 YuanBot 启动完成（含主动陪伴系统 + 配置热加载）")

        yield

        # 清理资源
        await config_watcher.stop()
        await event_engine.stop()
        await proactive_scheduler.stop()
        await web_adapter.close()
        await memory_manager.close()
        await provider_manager.close_all()
        print("🌸 YuanBot 已停止")

    app = FastAPI(
        title="缘·Bot (YuanBot)",
        description="AI 虚拟伴侣系统",
        version=config.version,
        lifespan=lifespan,
    )

    # CORS 配置
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 将组件存储到 app.state 供外部访问
    app.state.memory_manager = memory_manager
    app.state.skill_manager = skill_manager
    app.state.tool_manager = tool_manager
    app.state.ai_service = ai_service
    app.state.provider_manager = provider_manager
    app.state.capability_orchestrator = capability_orchestrator
    app.state.orchestrator = orchestrator
    app.state.persona_manager = persona_manager
    app.state.web_adapter = web_adapter
    app.state.proactive_scheduler = proactive_scheduler
    app.state.proactive_strategy = proactive_strategy
    app.state.event_engine = event_engine
    app.state.config_watcher = config_watcher
    app.state.auth_manager = auth_manager
    app.state.user_store = user_store
    app.state.conv_store = conv_store
    app.state.tts_manager = tts_manager

    # 初始化隐私管理器
    privacy_manager = PrivacyManager(memory_manager=memory_manager)
    app.state.privacy_manager = privacy_manager

    # 注册认证和会话路由
    app.include_router(auth_router)
    app.include_router(conversation_router)
    app.include_router(admin_router)

    # 注册路由
    _register_routes(app, orchestrator, memory_manager, config)

    # 注册请求指标中间件
    _register_metrics_middleware(app)

    # 将 Prometheus 指标注入 AIService
    ai_service._metrics = getattr(app.state, "metrics", {})

    # 注册静态文件服务（WebUI）
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        from fastapi.staticfiles import StaticFiles

        app.mount("/assets", StaticFiles(directory=str(static_dir / "assets")), name="assets")

        @app.get("/vite.svg")
        async def serve_vite_svg():
            from fastapi.responses import FileResponse

            svg = static_dir / "vite.svg"
            if svg.exists():
                return FileResponse(svg)
            return {"error": "not found"}

    # SPA fallback: 所有未匹配的路由返回 index.html
    @app.get("/{path:path}")
    async def serve_spa(path: str):
        """SPA fallback - 返回 index.html 让前端路由处理"""
        from fastapi.responses import FileResponse

        index = static_dir / "index.html" if static_dir.exists() else None
        if index and index.exists():
            return FileResponse(index)
        return {
            "message": "YuanBot API is running. WebUI not built yet. Run: cd webui && npm run build"
        }

    # 注册 WebSocket 路由
    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        """WebSocket 聊天端点（无认证，向后兼容）"""
        await web_adapter.handle_websocket(ws)

    @app.websocket("/ws/chat")
    async def websocket_chat_endpoint(ws: WebSocket):
        """WebSocket 认证聊天端点

        连接时需要在 URL 参数中携带 JWT token:
            ws://host:port/ws/chat?token=<jwt>

        消息格式：
            {"type": "message", "text": "你好", "conversation_id": "xxx"}
            {"type": "ping"}
            {"type": "subscribe", "conversation_id": "xxx"}

        服务端推送：
            {"type": "response", "text": "...", "conversation_id": "..."}
            {"type": "stream_start", "conversation_id": "..."}
            {"type": "stream_delta", "delta": "..."}
            {"type": "stream_end", "conversation_id": "..."}
        """
        import json

        import structlog

        from yuanbot.auth.middleware import get_current_user_from_ws

        logger = structlog.get_logger("websocket")

        user = await get_current_user_from_ws(ws)
        if not user:
            await ws.close(code=4001, reason="Unauthorized")
            return

        await ws.accept()
        session_id = f"ws_{user.user_id}"
        active_conv_id: str | None = None
        logger.info("ws_chat_connected", user_id=user.user_id, username=user.username)

        try:
            while True:
                raw = await ws.receive_text()
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    await ws.send_text(json.dumps({"type": "error", "message": "Invalid JSON"}))
                    continue

                msg_type = data.get("type", "message")

                if msg_type == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
                    continue

                if msg_type == "subscribe":
                    active_conv_id = data.get("conversation_id")
                    await ws.send_text(json.dumps({
                        "type": "subscribed",
                        "conversation_id": active_conv_id,
                    }))
                    continue

                if msg_type == "message":
                    text = data.get("text", "")
                    conv_id = data.get("conversation_id") or active_conv_id
                    if not text:
                        continue

                    # 保存用户消息到会话
                    conv_store_inst = app.state.conv_store
                    if conv_id:
                        conv_store_inst.add_message(conv_id, user.user_id, "user", text)

                    # 通知开始生成
                    await ws.send_text(json.dumps({
                        "type": "stream_start",
                        "conversation_id": conv_id,
                    }))

                    try:
                        response = await orchestrator.process_message(
                            _make_user_message(user, text, session_id)
                        )
                        reply_text = response.content.text if response.content else "收到~"

                        # 模拟流式推送（逐句发送）
                        sentences = (
                            reply_text
                            .replace("。", "。\n")
                            .replace("！", "！\n")
                            .replace("？", "？\n")
                            .split("\n")
                        )
                        for sent in sentences:
                            if sent.strip():
                                await ws.send_text(json.dumps({
                                    "type": "stream_delta",
                                    "delta": sent,
                                }, ensure_ascii=False))

                        # 保存 AI 回复
                        if conv_id:
                            conv_store_inst.add_message(
                                conv_id, user.user_id, "assistant", reply_text
                            )

                        await ws.send_text(json.dumps({
                            "type": "stream_end",
                            "conversation_id": conv_id,
                            "full_text": reply_text,
                        }, ensure_ascii=False))

                    except Exception as e:
                        logger.error("ws_chat_error", error=str(e))
                        await ws.send_text(json.dumps({
                            "type": "error",
                            "message": "AI 服务暂时不可用",
                        }))

        except Exception as e:
            logger.info("ws_chat_disconnected", user_id=user.user_id, error=str(e))

    @app.websocket("/ws/tts")
    async def websocket_tts_endpoint(ws: WebSocket):
        """WebSocket TTS 流式合成端点

        连接时需要在 URL 参数中携带 JWT token:
            ws://host:port/ws/tts?token=<jwt>

        客户端发送:
            {"type": "synthesize", "text": "...",
             "engine": "edge-tts", "voice": "zh-CN-XiaoxiaoNeural"}
            {"type": "ping"}

        服务端推送:
            {"type": "audio_start", "format": "mp3"}
            {"type": "audio_chunk", "data": "<base64编码的音频块>"}
            {"type": "audio_end", "chunks": N}
            {"type": "error", "message": "..."}
            {"type": "pong"}
        """
        import base64
        import json

        import structlog

        from yuanbot.auth.middleware import get_current_user_from_ws

        logger = structlog.get_logger("websocket.tts")

        user = await get_current_user_from_ws(ws)
        if not user:
            await ws.close(code=4001, reason="Unauthorized")
            return

        await ws.accept()
        logger.info("ws_tts_connected", user_id=user.user_id, username=user.username)

        try:
            while True:
                raw = await ws.receive_text()
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    await ws.send_text(json.dumps({"type": "error", "message": "Invalid JSON"}))
                    continue

                msg_type = data.get("type", "")

                if msg_type == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
                    continue

                if msg_type == "synthesize":
                    text = data.get("text", "")
                    if not text:
                        await ws.send_text(json.dumps(
                            {"type": "error", "message": "text is required"}
                        ))
                        continue

                    engine = data.get("engine")
                    voice = data.get("voice")

                    tts = app.state.tts_manager

                    try:
                        await ws.send_text(json.dumps({
                            "type": "audio_start",
                            "format": "mp3",
                        }))

                        # 将完整文本包装为单元素异步迭代器
                        async def _text_iter(t=text):
                            yield t

                        chunk_count = 0
                        async for audio_chunk in tts.synthesize_streaming_buffered(
                            text_stream=_text_iter(),
                            engine=engine,
                            voice=voice,
                        ):
                            b64_data = base64.b64encode(audio_chunk).decode("ascii")
                            await ws.send_text(json.dumps({
                                "type": "audio_chunk",
                                "data": b64_data,
                            }))
                            chunk_count += 1

                        await ws.send_text(json.dumps({
                            "type": "audio_end",
                            "chunks": chunk_count,
                        }))
                        logger.info(
                            "ws_tts_synthesized",
                            user_id=user.user_id,
                            text_len=len(text),
                            chunks=chunk_count,
                        )

                    except Exception as e:
                        logger.error("ws_tts_error", error=str(e))
                        await ws.send_text(json.dumps({
                            "type": "error",
                            "message": f"TTS 合成失败: {e}",
                        }))

                else:
                    await ws.send_text(json.dumps({
                        "type": "error",
                        "message": f"Unknown message type: {msg_type}",
                    }))

        except Exception as e:
            logger.info("ws_tts_disconnected", user_id=user.user_id, error=str(e))

    @app.websocket("/ws/logs")
    async def websocket_logs_endpoint(ws: WebSocket):
        """WebSocket 实时日志流（仅管理员）"""
        import json

        import structlog

        from yuanbot.auth.middleware import get_current_user_from_ws

        logger = structlog.get_logger("websocket")

        user = await get_current_user_from_ws(ws)
        if not user or user.role.value != "admin":
            await ws.close(code=4003, reason="Admin access required")
            return

        await ws.accept()
        logger.info("ws_logs_connected", user_id=user.user_id)
        try:
            # 简单实现：定期推送系统状态
            import asyncio

            while True:
                await asyncio.sleep(5)
                try:
                    import psutil

                    status = {
                        "type": "log",
                        "level": "info",
                        "message": f"CPU: {psutil.cpu_percent(interval=0.1)}% | "
                                    f"Memory: {psutil.virtual_memory().percent}%",
                        "timestamp": datetime.now().isoformat(),
                    }
                except ImportError:
                    status = {
                        "type": "log",
                        "level": "info",
                        "message": "系统运行正常",
                        "timestamp": datetime.now().isoformat(),
                    }
                await ws.send_text(json.dumps(status))
        except Exception:
            pass

    return app


def _load_persona(config: YuanBotConfig) -> Any:
    """加载 Agent 人设"""
    from yuanbot.persona.default import DefaultPersona

    return DefaultPersona(relationship_stage="initial")


def _make_user_message(user: Any, text: str, session_id: str) -> Any:
    """将认证用户的消息转换为 UserMessage"""
    from yuanbot.core.types import ContentType, UserMessage

    return UserMessage(
        platform="web",
        platform_user_id=user.user_id,
        yuanbot_user_id=user.user_id,
        session_id=session_id,
        content_type=ContentType.TEXT,
        text=text,
    )


def _register_metrics_middleware(app: FastAPI) -> None:
    """注册请求指标中间件

    自动记录请求计数和延迟到 Prometheus 指标。
    """
    import time

    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response

    class MetricsMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: Any) -> Response:
            # 跳过 /metrics 端点自身
            if request.url.path == "/metrics":
                return await call_next(request)

            metrics = getattr(app.state, "metrics", {})
            request_count = metrics.get("request_count")
            request_latency = metrics.get("request_latency")
            active_connections = metrics.get("active_connections")

            if active_connections:
                active_connections.inc()

            start_time = time.time()
            try:
                response = await call_next(request)
                status = str(response.status_code)
            except Exception:
                status = "500"
                raise
            finally:
                duration = time.time() - start_time
                if request_count:
                    request_count.labels(
                        method=request.method,
                        endpoint=request.url.path,
                        status=status,
                    ).inc()
                if request_latency:
                    request_latency.labels(
                        method=request.method,
                        endpoint=request.url.path,
                    ).observe(duration)
                if active_connections:
                    active_connections.dec()

            return response

    app.add_middleware(MetricsMiddleware)


def _register_routes(
    app: FastAPI,
    orchestrator: OrchestratorEngine,
    memory_manager: MemoryManager,
    config: YuanBotConfig,
) -> None:
    """注册 API 路由"""

    # ── Prometheus 监控指标 ─────────────────────
    try:
        from fastapi.responses import Response
        from prometheus_client import (
            CONTENT_TYPE_LATEST,
            CollectorRegistry,
            Counter,
            Gauge,
            Histogram,
            generate_latest,
        )

        # 使用独立注册表避免重复注册
        metrics_registry = CollectorRegistry()

        # 定义指标
        request_count = Counter(
            "yuanbot_request_total",
            "Total request count",
            ["method", "endpoint", "status"],
            registry=metrics_registry,
        )
        request_latency = Histogram(
            "yuanbot_request_duration_seconds",
            "Request latency in seconds",
            ["method", "endpoint"],
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
            registry=metrics_registry,
        )
        active_connections = Gauge(
            "yuanbot_active_connections",
            "Number of active connections",
            registry=metrics_registry,
        )
        ai_call_count = Counter(
            "yuanbot_ai_call_total",
            "Total AI provider call count",
            ["provider", "model", "status"],
            registry=metrics_registry,
        )
        ai_call_latency = Histogram(
            "yuanbot_ai_call_duration_seconds",
            "AI provider call latency in seconds",
            ["provider", "model"],
            buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
            registry=metrics_registry,
        )
        memory_operations = Counter(
            "yuanbot_memory_operations_total",
            "Total memory operations",
            ["operation", "memory_type"],
            registry=metrics_registry,
        )
        proactive_tasks_executed = Counter(
            "yuanbot_proactive_tasks_executed_total",
            "Total proactive tasks executed",
            ["task_name", "status"],
            registry=metrics_registry,
        )

        # 将指标注册到 app.state 供其他组件使用
        app.state.metrics = {
            "request_count": request_count,
            "request_latency": request_latency,
            "active_connections": active_connections,
            "ai_call_count": ai_call_count,
            "ai_call_latency": ai_call_latency,
            "memory_operations": memory_operations,
            "proactive_tasks_executed": proactive_tasks_executed,
        }

        @app.get("/metrics")
        async def metrics():
            """Prometheus 监控指标端点

            暴露系统运行指标，包括：
            - 请求计数和延迟
            - 活跃连接数
            - AI 调用次数和延迟
            - 记忆操作计数
            - 主动任务执行计数
            """
            return Response(
                content=generate_latest(metrics_registry),
                media_type=CONTENT_TYPE_LATEST,
            )

    except ImportError:
        # prometheus_client 未安装时降级
        import structlog

        _logger = structlog.get_logger("metrics")
        _logger.warning("prometheus_client_not_installed", msg="Metrics endpoint disabled")
        app.state.metrics = {}

        @app.get("/metrics")
        async def metrics():
            return {"error": "prometheus_client not installed"}

    # ── 知识图谱 API ───────────────────────────

    # 初始化图谱存储
    from yuanbot.infrastructure.graph_store import GraphStore

    _graph_store = GraphStore(
        db_path=getattr(config, 'graph_db_path', None)
    ) if hasattr(config, 'graph_db_path') else GraphStore()
    app.state.graph_store = _graph_store

    # 节点类型到分类索引的映射
    node_type_category: dict[str, int] = {
        "User": 0,
        "Entity": 1,
        "Event": 2,
        "AIPersona": 3,
        "Trait": 1,       # Trait 归入 Entity 类别
        "SemanticMemory": 1,
    }

    # 节点类型对应的基础符号大小
    node_base_size: dict[str, int] = {
        "User": 40,
        "AIPersona": 36,
        "Entity": 24,
        "Event": 28,
        "Trait": 20,
        "SemanticMemory": 22,
    }

    @app.get("/api/memory/graph")
    async def get_memory_graph(
        user_id: str | None = None,
        depth: int = 2,
        center_node_id: str | None = None,
    ):
        """获取知识图谱数据（ECharts graph 格式）

        Args:
            user_id: 用户 ID（可选，作为中心节点）
            depth: 遍历深度，1-3（默认 2）
            center_node_id: 中心节点 ID（可选，优先于 user_id）
        """

        gs: GraphStore = app.state.graph_store

        # 限制深度范围
        depth = max(1, min(3, depth))

        # 确定中心节点
        center_id = center_node_id or user_id

        if not center_id:
            # 无指定中心节点时，返回所有节点
            all_nodes = await gs.get_all_nodes()
            if not all_nodes:
                return {
                    "nodes": [],
                    "links": [],
                    "categories": [
                        {"name": "User"},
                        {"name": "Entity"},
                        {"name": "Event"},
                        {"name": "AIPersona"},
                    ],
                }
            # 默认以第一个 User 节点为中心
            user_nodes = [n for n in all_nodes if n.get("type") == "User"]
            center_id = user_nodes[0]["id"] if user_nodes else all_nodes[0]["id"]

        # 获取子图
        subgraph = await gs.get_knowledge_subgraph(
            center_id=center_id,
            depth=depth,
            max_nodes=100,
        )

        # 转换为 ECharts graph 格式
        echarts_nodes: list[dict[str, Any]] = []
        for node in subgraph.get("nodes", []):
            node_type = node.get("type", "Entity")
            props = node.get("properties", {})
            name = props.get("name", node.get("id", "unknown"))
            category = node_type_category.get(node_type, 1)
            base_size = node_base_size.get(node_type, 24)

            echarts_nodes.append({
                "id": node.get("id", ""),
                "name": name,
                "category": category,
                "value": 1,
                "symbolSize": base_size,
                "nodeType": node_type,
                "properties": props,
                "isCenter": node.get("id") == center_id,
            })

        # 转换边
        echarts_links: list[dict[str, Any]] = [
            {
                "source": edge.get("source", ""),
                "target": edge.get("target", ""),
                "relation": edge.get("type", "unknown"),
            }
            for edge in subgraph.get("edges", [])
        ]

        return {
            "nodes": echarts_nodes,
            "links": echarts_links,
            "categories": [
                {"name": "User"},
                {"name": "Entity"},
                {"name": "Event"},
                {"name": "AIPersona"},
            ],
            "center_id": center_id,
            "depth": depth,
        }

    # ── 健康检查与业务路由 ─────────────────────
    @app.get("/healthz")
    async def healthz():
        """Liveness probe - 服务基本健康状态

        只要进程存活即返回 OK，不检查下游依赖。
        用于 Kubernetes livenessProbe。
        """
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz():
        """Readiness probe - 服务就绪状态

        检查所有关键依赖是否就绪，包括 AI 服务、
        主动调度器和事件引擎。
        用于 Kubernetes readinessProbe。
        """
        checks: dict[str, Any] = {}
        all_ready = True

        # AI 服务检查
        try:
            ai_health = app.state.ai_service.get_health_status()
            checks["ai_service"] = ai_health
        except Exception as e:
            checks["ai_service"] = {"status": "error", "error": str(e)}
            all_ready = False

        # 主动调度器检查
        scheduler: ProactiveScheduler = app.state.proactive_scheduler
        checks["proactive_scheduler"] = {
            "status": "ok" if scheduler.is_running else "stopped",
            "task_count": len(scheduler.get_all_tasks()),
        }
        if not scheduler.is_running:
            all_ready = False

        # 事件引擎检查
        engine: EventEngine = app.state.event_engine
        checks["event_engine"] = {
            "status": "ok" if engine.is_running else "stopped",
            "trigger_count": len(engine.get_triggers()),
        }
        if not engine.is_running:
            all_ready = False

        status_code = 200 if all_ready else 503
        from fastapi.responses import JSONResponse

        return JSONResponse(
            content={
                "status": "ready" if all_ready else "not_ready",
                "checks": checks,
            },
            status_code=status_code,
        )

    @app.get("/health")
    async def health():
        """健康检查（向后兼容）"""
        ai_health = app.state.ai_service.get_health_status()
        return {
            "status": "ok",
            "version": config.version,
            "ai_service": ai_health,
        }

    @app.post("/api/chat")
    async def chat(request: dict[str, Any]):
        """对话接口（用于 Web Chat 通道）"""
        from yuanbot.core.types import ContentType, UserMessage

        message = UserMessage(
            platform="web",
            platform_user_id=request.get("user_id", "anonymous"),
            yuanbot_user_id=f"yb_{request.get('user_id', 'anonymous')}",
            session_id=f"web:{request.get('user_id', 'anonymous')}",
            content_type=ContentType.TEXT,
            text=request.get("message", ""),
        )

        response = await orchestrator.process_message(message)
        return {
            "content": response.content.text,
            "proactive_followups": [
                t.model_dump() for t in (response.proactive_followups or [])
            ],
        }

    @app.get("/api/memory/{user_id}")
    async def get_memory(user_id: str):
        """查看用户记忆"""
        fact_memories = await memory_manager.get_fact_memories(user_id)
        profile = await memory_manager.get_or_create_user_profile(user_id)
        return {
            "profile": profile.model_dump(),
            "fact_memories": [
                {
                    "id": m.id,
                    "content": m.content,
                    "importance": m.importance_score,
                }
                for m in fact_memories
            ],
        }

    @app.get("/api/proactive/tasks")
    async def get_proactive_tasks():
        """查看主动任务列表"""
        scheduler: ProactiveScheduler = app.state.proactive_scheduler
        tasks = scheduler.get_all_tasks()
        return {
            "tasks": [
                {
                    "task_id": t.task_id,
                    "name": t.name,
                    "task_type": t.task_type,
                    "trigger": t.trigger,
                    "priority": t.priority,
                    "enabled": t.enabled,
                    "next_run": t.next_run.isoformat() if t.next_run else None,
                    "last_run": t.last_run.isoformat() if t.last_run else None,
                }
                for t in tasks
            ]
        }

    @app.get("/api/proactive/stats")
    async def get_proactive_stats():
        """查看主动交互统计"""
        strategy: ProactiveStrategy = app.state.proactive_strategy
        return {
            "daily_stats": strategy.get_daily_stats(),
            "config": strategy.get_config().__dict__,
        }

    @app.get("/api/providers")
    async def get_providers():
        """查看 AI 提供商状态"""
        pm: ProviderManager = app.state.provider_manager
        return {
            "providers": pm.list_providers(),
            "ai_service_health": app.state.ai_service.get_health_status(),
        }

    @app.get("/api/providers/{provider_id}")
    async def get_provider_detail(provider_id: str):
        """查看单个提供商详情"""
        from fastapi.responses import JSONResponse

        pm: ProviderManager = app.state.provider_manager
        provider = pm.get_provider(provider_id)
        if not provider:
            return JSONResponse(
                status_code=404,
                content={"error": f"Provider '{provider_id}' not found"},
            )
        return {
            "provider_id": provider.provider_id,
            "name": provider.name,
            "adapter": provider.adapter,
            "enabled": provider.enabled,
            "default_model": provider.default_model,
            "embedding_model": provider.embedding_model,
            "models": [
                {
                    "id": m.id,
                    "type": m.type,
                    "max_tokens": m.max_tokens,
                    "dimension": m.dimension,
                }
                for m in provider.models
            ],
        }

    @app.put("/api/providers/active")
    async def set_active_provider(request: dict[str, Any]):
        """动态切换活跃提供商

        请求体：
            {
                "provider_id": "deepseek",   // 切换默认对话提供商
                "type": "default"             // "default" 或 "embedding"
            }
        """
        from fastapi.responses import JSONResponse

        pm: ProviderManager = app.state.provider_manager
        provider_id = request.get("provider_id")
        switch_type = request.get("type", "default")

        if not provider_id:
            return JSONResponse(
                status_code=400,
                content={"error": "provider_id is required"},
            )

        provider = pm.get_provider(provider_id)
        if not provider:
            return JSONResponse(
                status_code=404,
                content={"error": f"Provider '{provider_id}' not found"},
            )

        if not provider.enabled:
            return JSONResponse(
                status_code=400,
                content={"error": f"Provider '{provider_id}' is disabled"},
            )

        try:
            if switch_type == "embedding":
                pm.set_embedding_provider(provider_id)
            else:
                pm.set_default_provider(provider_id)
        except ValueError as e:
            return JSONResponse(
                status_code=400,
                content={"error": str(e)},
            )

        return {
            "status": "ok",
            "message": f"{'Embedding' if switch_type == 'embedding' else 'Default'} "
                        f"provider switched to '{provider_id}'",
            "provider_id": provider_id,
            "default_model": provider.default_model,
        }

    @app.post("/api/providers/{provider_id}/reload")
    async def reload_provider(provider_id: str):
        """热重载指定提供商配置"""
        from fastapi.responses import JSONResponse

        pm: ProviderManager = app.state.provider_manager
        provider = pm.get_provider(provider_id)
        if not provider:
            return JSONResponse(
                status_code=404,
                content={"error": f"Provider '{provider_id}' not found"},
            )

        # 从 YAML 重新加载
        import yaml

        yaml_path = Path("configs/Providers") / f"{provider_id}.yaml"
        if not yaml_path.exists():
            return JSONResponse(
                status_code=404,
                content={"error": f"Config file not found: {yaml_path}"},
            )

        with open(yaml_path) as f:
            new_config = yaml.safe_load(f)

        await pm.reload_provider(provider_id, new_config)
        return {"status": "ok", "message": f"Provider '{provider_id}' reloaded"}

    @app.get("/api/gdpr/export")
    async def gdpr_export(user_id: str):
        """GDPR 数据导出

        导出指定用户的所有数据（记忆、画像、对话历史）为 JSON。
        符合 GDPR 数据可携带权要求。

        Args:
            user_id: 用户 ID
        """
        import structlog

        _logger = structlog.get_logger("gdpr")
        _logger.info("gdpr_export_requested", user_id=user_id)
        privacy: PrivacyManager = app.state.privacy_manager
        data = await privacy.export_user_data(user_id)
        _logger.info(
            "gdpr_export_completed",
            user_id=user_id,
            has_error="error" in data and data["error"] is not None,
        )
        return data

    @app.post("/api/gdpr/delete")
    async def gdpr_delete(request: dict[str, Any]):
        """GDPR 数据删除

        删除指定用户的所有数据。
        符合 GDPR 被遗忘权要求。
        需要用户确认（传入 user_id 参数）。

        请求体:
            {"user_id": "xxx", "confirm": true}
        """
        import structlog

        _logger = structlog.get_logger("gdpr")
        user_id = request.get("user_id")
        if not user_id:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                content={"error": "user_id is required"},
                status_code=400,
            )

        confirm = request.get("confirm", False)
        if not confirm:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                content={
                    "error": "Confirmation required",
                    "hint": "Set 'confirm': true in request body to proceed with data deletion.",
                },
                status_code=400,
            )

        _logger.info("gdpr_delete_requested", user_id=user_id)
        privacy: PrivacyManager = app.state.privacy_manager
        result = await privacy.delete_user_data(user_id)
        has_error = "error" in result and result["error"] is not None
        _logger.info(
            "gdpr_delete_completed",
            user_id=user_id,
            items_deleted=result.get("items_deleted", {}),
            has_error=has_error,
        )
        return result

    @app.get("/api/gdpr/audit-log")
    async def gdpr_audit_log(user_id: str | None = None):
        """GDPR 审计日志

        查看 GDPR 操作的审计记录，包括数据导出和删除操作。
        可选按 user_id 过滤。

        Args:
            user_id: 可选，过滤指定用户的日志
        """
        privacy: PrivacyManager = app.state.privacy_manager
        log_entries = privacy.get_audit_log(user_id)
        return {"audit_log": log_entries, "count": len(log_entries)}

    @app.get("/api/capabilities")
    async def get_capabilities():
        """查看已加载的能力"""
        sm: SkillManager = app.state.skill_manager
        tm: ToolManager = app.state.tool_manager
        return {
            "skills": sm.get_all_skills(),
            "tools": tm.get_all_tools(),
        }

    # ── TTS 语音合成 API ─────────────────────────

    @app.post("/api/tts")
    async def tts_synthesize(request: dict[str, Any]):
        """语音合成接口

        请求体:
            {
                "text": "你好世界",         // 必填，待合成文本
                "engine": "edge-tts",       // 可选，指定引擎
                "voice": "zh-CN-XiaoxiaoNeural", // 可选，指定音色
                "persona_id": "default",    // 可选，人设 ID
                "rate": 1.0,                // 可选，语速倍率
                "pitch": 1.0,               // 可选，音调倍率
                "format": "mp3"             // 可选，输出格式
            }

        响应: 音频文件 (audio/mpeg)
        """
        from fastapi.responses import JSONResponse, Response

        tts = app.state.tts_manager
        text = request.get("text", "")
        if not text:
            return JSONResponse(
                status_code=400,
                content={"error": "text is required"},
            )

        try:
            audio = await tts.synthesize(
                text=text,
                engine=request.get("engine"),
                voice=request.get("voice"),
                persona_id=request.get("persona_id"),
                rate=request.get("rate"),
                pitch=request.get("pitch"),
                output_format=request.get("format", "mp3"),
            )
            return Response(
                content=audio,
                media_type="audio/mpeg",
                headers={"Content-Disposition": "inline; filename=tts.mp3"},
            )
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"error": str(e)},
            )

    @app.get("/api/tts/voices")
    async def tts_voices(engine: str | None = None):
        """列出可用音色

        Args:
            engine: 可选，指定引擎名称过滤
        """
        tts = app.state.tts_manager
        voices = tts.list_voices(engine)
        return {
            "voices": [
                {
                    "id": v.id,
                    "name": v.name,
                    "language": v.language,
                    "gender": v.gender,
                }
                for v in voices
            ],
            "engines": tts.list_engines(),
        }

    @app.get("/api/tts/status")
    async def tts_status():
        """查看 TTS 系统状态"""
        tts = app.state.tts_manager
        return await tts.get_status()

    # ── 扩展市场 API ────────────────────────────

    _extensions_dir = Path(os.environ.get("YUANBOT_EXTENSIONS_DIR", "data/extensions"))

    @app.get("/api/extensions")
    async def list_extensions():
        """列出已安装的扩展"""
        if not _extensions_dir.exists():
            return {"extensions": [], "count": 0}

        extensions = []
        for ext_dir in sorted(_extensions_dir.iterdir()):
            if not ext_dir.is_dir():
                continue
            manifest_path = ext_dir / "manifest.json"
            if manifest_path.exists():
                try:
                    manifest = ExtensionManifest.from_file(manifest_path)
                    extensions.append(manifest.to_dict())
                except Exception as e:
                    extensions.append(
                        {"id": ext_dir.name, "error": f"Failed to load manifest: {e}"}
                    )

        return {"extensions": extensions, "count": len(extensions)}

    @app.get("/api/extensions/{ext_id}")
    async def get_extension(ext_id: str):
        """获取扩展详情"""
        ext_dir = _extensions_dir / ext_id
        if not ext_dir.exists():
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=404,
                content={"error": f"Extension '{ext_id}' not found"},
            )

        manifest_path = ext_dir / "manifest.json"
        if not manifest_path.exists():
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=404,
                content={"error": f"Extension '{ext_id}' has no manifest.json"},
            )

        manifest = ExtensionManifest.from_file(manifest_path)
        return manifest.to_dict()

    @app.post("/api/extensions/install")
    async def install_extension(request: dict[str, Any]):
        """安装扩展（从 URL 下载 zip 或从本地路径安装）"""
        import shutil
        import zipfile

        from fastapi.responses import JSONResponse

        from yuanbot.services.extension_standard import VersionManager

        source_url = request.get("url")
        source_path = request.get("path")
        force = request.get("force", False)

        if not source_url and not source_path:
            return JSONResponse(
                status_code=400,
                content={"error": "Must provide either 'url' or 'path'"},
            )

        _extensions_dir.mkdir(parents=True, exist_ok=True)
        tmp_dir = _extensions_dir / ".tmp_install"

        try:
            if source_url:
                import httpx

                tmp_dir.mkdir(parents=True, exist_ok=True)
                zip_path = tmp_dir / "extension.zip"
                async with httpx.AsyncClient(timeout=60) as client:
                    resp = await client.get(source_url)
                    resp.raise_for_status()
                    zip_path.write_bytes(resp.content)

                with zipfile.ZipFile(zip_path) as zf:
                    zf.extractall(tmp_dir)

                manifest_found = False
                for item in tmp_dir.iterdir():
                    if item.is_dir() and (item / "manifest.json").exists():
                        source_dir = item
                        manifest_found = True
                        break
                if not manifest_found and (tmp_dir / "manifest.json").exists():
                    source_dir = tmp_dir
                    manifest_found = True

                if not manifest_found:
                    return JSONResponse(
                        status_code=400,
                        content={"error": "No manifest.json found in downloaded archive"},
                    )
            else:
                source_dir = Path(source_path)
                if not source_dir.exists():
                    return JSONResponse(
                        status_code=400,
                        content={"error": f"Path does not exist: {source_path}"},
                    )

            manifest_path = source_dir / "manifest.json"
            manifest = ExtensionManifest.from_file(manifest_path)
            manifest_errors = manifest.validate()
            if manifest_errors:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Invalid manifest", "details": manifest_errors},
                )

            errors = ExtensionValidator.validate_extension_dir(source_dir)
            errors = [e for e in errors if "README" not in e]
            if errors:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Extension validation failed", "details": errors},
                )

            # 版本兼容性检查
            installed: dict[str, str] = {}
            if _extensions_dir.exists():
                for ext_dir in _extensions_dir.iterdir():
                    if ext_dir.is_dir() and (ext_dir / "manifest.json").exists():
                        try:
                            m = ExtensionManifest.from_file(ext_dir / "manifest.json")
                            installed[m.id] = m.version
                        except Exception:
                            pass

            dep_errors = VersionManager.check_dependencies(manifest, installed)
            if dep_errors and not force:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "Dependency check failed",
                        "details": dep_errors,
                        "hint": "Use 'force': true to skip dependency check",
                    },
                )

            # 检查是否已安装同版本
            dest_dir = _extensions_dir / manifest.id
            if dest_dir.exists():
                existing_manifest_path = dest_dir / "manifest.json"
                if existing_manifest_path.exists():
                    existing = ExtensionManifest.from_file(existing_manifest_path)
                    if existing.version == manifest.version and not force:
                        return JSONResponse(
                            status_code=409,
                            content={
                                "error": (
                            f"Extension '{manifest.id}' version"
                            f" {manifest.version} is already installed"
                        ),
                                "hint": "Use 'force': true to reinstall",
                            },
                        )
                shutil.rmtree(dest_dir)

            shutil.copytree(str(source_dir), str(dest_dir))

            return {"status": "installed", "extension": manifest.to_dict()}

        finally:
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)

    @app.post("/api/extensions/uninstall")
    async def uninstall_extension(request: dict[str, Any]):
        """卸载扩展"""
        import shutil

        from fastapi.responses import JSONResponse

        ext_id = request.get("id")
        if not ext_id:
            return JSONResponse(
                status_code=400,
                content={"error": "Must provide 'id'"},
            )

        ext_dir = _extensions_dir / ext_id
        if not ext_dir.exists():
            return JSONResponse(
                status_code=404,
                content={"error": f"Extension '{ext_id}' not found"},
            )

        shutil.rmtree(ext_dir)
        return {"status": "uninstalled", "id": ext_id}

    # ── 人设管理 API ─────────────────────────────

    @app.get("/api/persona")
    async def get_persona_status():
        """查看当前人设状态"""
        pm = app.state.persona_manager
        persona = pm.active_persona
        return {
            "active_id": pm.active_id,
            "name": persona.name,
            "relationship_stage": persona.relationship_stage,
            "voice_style": persona.get_voice_style(),
            "capability_domains": persona.get_capability_domains(),
        }

    @app.get("/api/persona/list")
    async def list_personas():
        """列出所有人设"""
        pm = app.state.persona_manager
        return {
            "personas": pm.list_personas(),
            "total": len(pm.list_personas()),
        }

    @app.put("/api/persona/switch")
    async def switch_persona(request: dict[str, Any]):
        """运行时切换人设

        请求体:
            {
                "persona_id": "cheerful"  // 目标人设 ID
            }
        """
        from fastapi.responses import JSONResponse

        pm = app.state.persona_manager
        persona_id = request.get("persona_id")

        if not persona_id:
            return JSONResponse(
                status_code=400,
                content={"error": "persona_id is required"},
            )

        try:
            result = pm.switch_persona(persona_id)
            # 同步更新编排引擎的人设引用
            app.state.orchestrator._persona = pm.active_persona
            return result
        except ValueError as e:
            return JSONResponse(
                status_code=404,
                content={"error": str(e)},
            )

    @app.put("/api/persona/stage")
    async def set_persona_stage(request: dict[str, Any]):
        """设置关系阶段

        请求体:
            {
                "stage": "familiar"  // initial | familiar | intimate | deep
            }
        """
        from fastapi.responses import JSONResponse

        pm = app.state.persona_manager
        stage = request.get("stage")

        if not stage:
            return JSONResponse(
                status_code=400,
                content={"error": "stage is required"},
            )

        try:
            result = pm.set_relationship_stage(stage)
            # 同步更新编排引擎的人设引用
            app.state.orchestrator._persona = pm.active_persona
            return result
        except ValueError as e:
            return JSONResponse(
                status_code=404,
                content={"error": str(e)},
            )

    @app.post("/api/persona/reload")
    async def reload_persona(request: dict[str, Any]):
        """重新加载人设配置"""
        pm = app.state.persona_manager
        persona_id = request.get("persona_id", "")

        if persona_id:
            ok = pm.reload_persona(persona_id)
            if ok:
                app.state.orchestrator._persona = pm.active_persona
                return {"status": "ok", "reloaded": persona_id}
            return {"status": "error", "message": f"Persona '{persona_id}' not found"}
        else:
            pm.load_personas()
            app.state.orchestrator._persona = pm.active_persona
            return {"status": "ok", "reloaded": "all", "count": len(pm.list_personas())}

    # ── 人格商店 API ─────────────────────────────

    from yuanbot.services.marketplace import MarketplaceClient

    _marketplace_client = MarketplaceClient()

    from yuanbot.services.marketplace import ExtensionReviewStore

    _review_store = ExtensionReviewStore()

    @app.get("/api/personas")
    async def list_all_personas():
        """列出本地已安装人设 + 市场可用人设"""
        pm = app.state.persona_manager
        local_personas = pm.list_personas()

        # 从市场获取 persona 类型的扩展
        marketplace_personas = []
        try:
            result = await _marketplace_client.search(
                query="",
                ext_type="persona",
                limit=50,
            )
            marketplace_personas = result.get("extensions", [])
        except Exception:
            pass

        # 获取评分统计
        installed_ids = {p["id"] for p in local_personas}
        for mp in marketplace_personas:
            mp["is_installed"] = mp["id"] in installed_ids
            stats = _review_store.get_stats(mp["id"])
            mp["rating"] = stats.average_rating
            mp["review_count"] = stats.total_reviews

        return {
            "local": local_personas,
            "marketplace": marketplace_personas,
        }

    @app.post("/api/personas/install/{persona_id}")
    async def install_persona(persona_id: str):
        """从市场下载安装人设包到 configs/Personas/"""
        from fastapi.responses import JSONResponse

        # 从市场获取扩展详情
        entry = await _marketplace_client.get_extension(persona_id)
        if not entry:
            return JSONResponse(
                status_code=404,
                content={"error": f"Persona '{persona_id}' not found in marketplace"},
            )

        if entry.type != "persona":
            return JSONResponse(
                status_code=400,
                content={"error": f"Extension '{persona_id}' is not a persona"},
            )

        personas_dir = Path("configs/Personas")
        personas_dir.mkdir(parents=True, exist_ok=True)

        try:
            import httpx

            if entry.download_url:
                # 下载 zip 并解压
                import shutil
                import zipfile

                tmp_zip = personas_dir / f".tmp_{persona_id}.zip"
                async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                    resp = await client.get(entry.download_url)
                    resp.raise_for_status()
                    tmp_zip.write_bytes(resp.content)

                # 解压并查找 YAML 文件
                tmp_dir = personas_dir / f".tmp_{persona_id}"
                if tmp_dir.exists():
                    shutil.rmtree(tmp_dir)
                with zipfile.ZipFile(tmp_zip) as zf:
                    zf.extractall(tmp_dir)

                # 查找 persona yaml 文件
                yaml_found = False
                for yaml_file in tmp_dir.rglob("*.yaml"):
                    dest = personas_dir / yaml_file.name
                    shutil.copy2(str(yaml_file), str(dest))
                    yaml_found = True
                    break

                if not yaml_found:
                    # 尝试查找 yml 文件
                    for yml_file in tmp_dir.rglob("*.yml"):
                        dest = personas_dir / yml_file.name
                        shutil.copy2(str(yml_file), str(dest))
                        yaml_found = True
                        break

                # 清理临时文件
                tmp_zip.unlink(missing_ok=True)
                shutil.rmtree(tmp_dir, ignore_errors=True)

                if not yaml_found:
                    return JSONResponse(
                        status_code=400,
                        content={"error": "No YAML persona config found in the package"},
                    )

            elif entry.homepage:
                # 尝试直接下载 YAML
                import httpx

                async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
                    resp = await client.get(entry.homepage)
                    resp.raise_for_status()
                    dest = personas_dir / f"{persona_id}.yaml"
                    dest.write_text(resp.text, encoding="utf-8")
            else:
                return JSONResponse(
                    status_code=400,
                    content={"error": "No download URL available for this persona"},
                )

            # 重载人设管理器
            pm = app.state.persona_manager
            pm.load_personas()
            app.state.orchestrator._persona = pm.active_persona

            return {
                "status": "installed",
                "persona_id": persona_id,
                "name": entry.name,
            }

        except Exception as e:
            import structlog
            _logger = structlog.get_logger("persona_install")
            _logger.error("persona_install_failed", persona_id=persona_id, error=str(e))
            return JSONResponse(
                status_code=500,
                content={"error": f"Installation failed: {e}"},
            )

    @app.post("/api/personas/activate/{persona_id}")
    async def activate_persona(persona_id: str):
        """切换当前活跃人设"""
        from fastapi.responses import JSONResponse

        pm = app.state.persona_manager
        try:
            result = pm.switch_persona(persona_id)
            app.state.orchestrator._persona = pm.active_persona
            return result
        except ValueError as e:
            return JSONResponse(
                status_code=404,
                content={"error": str(e)},
            )

    @app.get("/api/personas/active")
    async def get_active_persona():
        """获取当前活跃人设信息"""
        pm = app.state.persona_manager
        persona = pm.active_persona
        return {
            "persona_id": pm.active_id,
            "name": persona.name,
            "relationship_stage": persona.relationship_stage,
            "voice_style": persona.get_voice_style(),
            "capability_domains": persona.get_capability_domains(),
            "behavior_rules": persona.get_behavior_rules(),
        }

    @app.delete("/api/personas/{persona_id}")
    async def delete_persona(persona_id: str):
        """删除已安装的人设（不能删除当前活跃人设和默认人设）"""
        from fastapi.responses import JSONResponse

        pm = app.state.persona_manager

        if persona_id == "default":
            return JSONResponse(
                status_code=400,
                content={"error": "Cannot delete the default persona"},
            )

        if persona_id == pm.active_id:
            return JSONResponse(
                status_code=400,
                content={"error": (
                    "Cannot delete the currently active persona."
                    " Switch to another persona first."
                )},
            )

        personas_dir = Path("configs/Personas")
        yaml_file = personas_dir / f"{persona_id}.yaml"
        if not yaml_file.exists():
            return JSONResponse(
                status_code=404,
                content={"error": f"Persona '{persona_id}' not found"},
            )

        yaml_file.unlink()
        pm.load_personas()

        return {"status": "deleted", "persona_id": persona_id}

    @app.get("/api/marketplace/search")
    async def marketplace_search(
        q: str = "",
        type: str = "",
        limit: int = 20,
        offset: int = 0,
    ):
        """搜索社区扩展市场

        Args:
            q: 搜索关键词
            type: 过滤扩展类型
            limit: 返回数量
            offset: 分页偏移
        """
        result = await _marketplace_client.search(
            query=q,
            ext_type=type,
            limit=limit,
            offset=offset,
        )
        return result

    @app.get("/api/marketplace/extensions")
    async def marketplace_list(
        type: str = "",
        limit: int = 50,
        offset: int = 0,
        sort: str = "downloads",
    ):
        """列出市场扩展"""
        result = await _marketplace_client.list_extensions(
            ext_type=type,
            limit=limit,
            offset=offset,
            sort_by=sort,
        )
        return result

    @app.get("/api/marketplace/extensions/{ext_id}")
    async def marketplace_extension_detail(ext_id: str):
        """获取市场扩展详情"""
        from fastapi.responses import JSONResponse

        entry = await _marketplace_client.get_extension(ext_id)
        if not entry:
            return JSONResponse(
                status_code=404,
                content={"error": f"Extension '{ext_id}' not found in marketplace"},
            )
        return entry.to_dict()

    @app.get("/api/marketplace/categories")
    async def marketplace_categories():
        """获取扩展分类统计"""
        categories = await _marketplace_client.get_categories()
        return {"categories": categories}

    @app.post("/api/marketplace/refresh")
    async def marketplace_refresh():
        """刷新市场索引缓存"""
        ok = await _marketplace_client.refresh_index()
        return {"status": "ok" if ok else "error"}

    @app.get("/api/marketplace/installed")
    async def marketplace_installed():
        """获取已安装扩展列表

        扫描 data/extensions 目录，返回每个已安装扩展的 ID 和 manifest 信息。"""
        if not _extensions_dir.exists():
            return {"installed": [], "count": 0}

        installed = []
        for ext_dir in sorted(_extensions_dir.iterdir()):
            if not ext_dir.is_dir():
                continue
            manifest_path = ext_dir / "manifest.json"
            if manifest_path.exists():
                try:
                    manifest = ExtensionManifest.from_file(manifest_path)
                    installed.append({
                        "id": manifest.id,
                        "name": manifest.name,
                        "version": manifest.version,
                        "type": manifest.type if hasattr(manifest, "type") else "",
                    })
                except Exception:
                    installed.append({"id": ext_dir.name, "version": "unknown", "type": ""})
            else:
                installed.append({"id": ext_dir.name, "version": "unknown", "type": ""})

        return {"installed": installed, "count": len(installed)}

    @app.post("/api/marketplace/extensions/{ext_id}/install")
    async def marketplace_install(ext_id: str, request: dict[str, Any] | None = None):
        """从市场下载并安装扩展到 data/extensions

        通过 MarketplaceClient 下载扩展 zip 包并解压到扩展目录。"""
        from fastapi.responses import JSONResponse

        # 检查是否已安装
        ext_dir = _extensions_dir / ext_id
        force = (request or {}).get("force", False)
        if ext_dir.exists() and not force:
            manifest_path = ext_dir / "manifest.json"
            if manifest_path.exists():
                try:
                    existing = ExtensionManifest.from_file(manifest_path)
                    return JSONResponse(
                        status_code=409,
                        content={
                            "error": (
                                f"Extension '{ext_id}' is already installed"
                                f" (version {existing.version})"
                            ),
                            "hint": "Use 'force': true to reinstall",
                        },
                    )
                except Exception:
                    pass

        _extensions_dir.mkdir(parents=True, exist_ok=True)

        # 使用 MarketplaceClient 下载
        result_path = await _marketplace_client.download_extension(
            ext_id=ext_id,
            dest_dir=_extensions_dir,
        )

        if not result_path:
            return JSONResponse(
                status_code=404,
                content={"error": f"Failed to download extension '{ext_id}' from marketplace"},
            )

        # 读取已安装的 manifest 信息
        manifest_path = result_path / "manifest.json"
        manifest_info = {}
        if manifest_path.exists():
            try:
                manifest = ExtensionManifest.from_file(manifest_path)
                manifest_info = manifest.to_dict()
            except Exception:
                pass

        return {
            "status": "installed",
            "extension_id": ext_id,
            "manifest": manifest_info,
        }

    @app.delete("/api/marketplace/extensions/{ext_id}/uninstall")
    async def marketplace_uninstall(ext_id: str):
        """卸载扩展（从 data/extensions 中删除）"""
        import shutil

        from fastapi.responses import JSONResponse

        ext_dir = _extensions_dir / ext_id
        if not ext_dir.exists():
            return JSONResponse(
                status_code=404,
                content={"error": f"Extension '{ext_id}' is not installed"},
            )

        shutil.rmtree(ext_dir)
        return {"status": "uninstalled", "extension_id": ext_id}

    # ── 扩展评分与评论 API ──────────────────────────
    from fastapi import Depends
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, Field

    from yuanbot.auth.middleware import get_current_user
    from yuanbot.auth.models import User

    class ReviewCreateRequest(BaseModel):
        rating: int = Field(..., ge=1, le=5, description="评分 1-5 星")
        title: str = Field("", max_length=200)
        content: str = Field("", max_length=5000)

    @app.post("/api/marketplace/extensions/{ext_id}/reviews")
    async def create_review(
        ext_id: str,
        req: ReviewCreateRequest,
        user: User = Depends(get_current_user),
    ):
        """为扩展添加或更新评论（每人每扩展限一条）"""
        review = _review_store.add_review(
            ext_id=ext_id,
            user_id=user.user_id,
            rating=req.rating,
            title=req.title,
            content=req.content,
        )
        return review.to_dict()

    @app.get("/api/marketplace/extensions/{ext_id}/reviews")
    async def list_reviews(
        ext_id: str,
        limit: int = 20,
        offset: int = 0,
        sort: str = "created_at",
        order: str = "desc",
    ):
        """列出扩展的评论"""
        return _review_store.list_reviews(
            ext_id=ext_id,
            limit=limit,
            offset=offset,
            sort_by=sort,
            order=order,
        )

    @app.get("/api/marketplace/extensions/{ext_id}/reviews/stats")
    async def review_stats(ext_id: str):
        """获取扩展评分统计"""
        stats = _review_store.get_stats(ext_id)
        return stats.to_dict()

    @app.delete("/api/marketplace/extensions/{ext_id}/reviews/{review_id}")
    async def delete_review(
        ext_id: str,
        review_id: str,
        user: User = Depends(get_current_user),
    ):
        """删除自己的评论"""
        deleted = _review_store.delete_review(review_id, user.user_id)
        if not deleted:
            return JSONResponse(
                status_code=404,
                content={"error": "Review not found or not owned by user"},
            )
        return {"status": "deleted"}

    @app.post("/api/marketplace/extensions/{ext_id}/reviews/{review_id}/helpful")
    async def mark_review_helpful(
        ext_id: str,
        review_id: str,
        user: User = Depends(get_current_user),
    ):
        """标记评论为有帮助"""
        ok = _review_store.mark_helpful(review_id, user.user_id)
        if not ok:
            return JSONResponse(
                status_code=409,
                content={"error": "Already marked as helpful"},
            )
        return {"status": "ok"}
