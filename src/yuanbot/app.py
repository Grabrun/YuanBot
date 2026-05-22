"""YuanBot FastAPI 应用

集成所有子系统的完整应用入口。
使用 AIService 门面、CapabilityOrchestrator、事件队列等新组件。

设计参考: architecture-v1.4.md + 所有详细设计文档
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from starlette.websockets import WebSocket

from yuanbot.adapters.channel.web_adapter import WebAdapter
from yuanbot.config import YuanBotConfig
from yuanbot.core.types import BotResponse
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
from yuanbot.skills.manager import SkillManager
from yuanbot.tools.manager import ToolManager


def create_app(config: YuanBotConfig) -> FastAPI:
    """创建 YuanBot FastAPI 应用"""

    # ── 1. 初始化基础设施 ──────────────────────
    memory_manager = MemoryManager(config=config.memory.model_dump())

    # ── 2. 初始化 AI 提供商系统 ────────────────
    provider_registry = ProviderRegistry()
    provider_manager = ProviderManager(registry=provider_registry)
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

    # ── 7. Web 通道适配器 ─────────────────────
    web_adapter = WebAdapter()

    # ── 应用生命周期 ──────────────────────────

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """应用生命周期管理"""

        # 加载 Skills 和 Tools
        await skill_manager.load_skills()
        await tool_manager.load_tools()

        # 启动 Web 适配器
        async def on_message(msg: Any) -> BotResponse:
            return await orchestrator.process_message(msg)

        await web_adapter.listen(on_message)

        # 启动主动陪伴系统
        await proactive_scheduler.start()
        await event_engine.start()
        print("🌸 YuanBot 启动完成（含主动陪伴系统）")

        yield

        # 清理资源
        await event_engine.stop()
        await proactive_scheduler.stop()
        await web_adapter.close()
        await provider_manager.close_all()
        print("🌸 YuanBot 已停止")

    app = FastAPI(
        title="缘·Bot (YuanBot)",
        description="AI 虚拟伴侣系统",
        version=config.version,
        lifespan=lifespan,
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

    # 注册路由
    _register_routes(app, orchestrator, memory_manager, config)

    # 注册 WebSocket 路由
    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        """WebSocket 聊天端点

        连接后即可通过 JSON 消息进行实时对话：

            ws://host:port/ws

        消息格式：
            {"type": "message", "text": "你好"}
            {"type": "ping"}
        """
        await web_adapter.handle_websocket(ws)

    return app


def _load_persona(config: YuanBotConfig) -> Any:
    """加载 Agent 人设"""
    from yuanbot.persona.default import DefaultPersona

    return DefaultPersona()


def _register_routes(
    app: FastAPI,
    orchestrator: OrchestratorEngine,
    memory_manager: MemoryManager,
    config: YuanBotConfig,
) -> None:
    """注册 API 路由"""

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
            "providers": [
                {
                    "provider_id": p.provider_id,
                    "enabled": p.enabled,
                    "default_model": p.default_model,
                    "model_count": len(p.models),
                }
                for p in pm.get_enabled_providers()
            ],
            "ai_service_health": app.state.ai_service.get_health_status(),
        }

    @app.get("/api/capabilities")
    async def get_capabilities():
        """查看已加载的能力"""
        sm: SkillManager = app.state.skill_manager
        tm: ToolManager = app.state.tool_manager
        return {
            "skills": sm.get_all_skills(),
            "tools": tm.get_all_tools(),
        }
