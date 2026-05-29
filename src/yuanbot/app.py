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

    # ── 8. 配置热加载监听器 ─────────────────────
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
    app.state.web_adapter = web_adapter
    app.state.proactive_scheduler = proactive_scheduler
    app.state.proactive_strategy = proactive_strategy
    app.state.event_engine = event_engine
    app.state.config_watcher = config_watcher
    app.state.auth_manager = auth_manager
    app.state.user_store = user_store
    app.state.conv_store = conv_store

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
