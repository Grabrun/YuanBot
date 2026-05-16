"""YuanBot FastAPI 应用"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from yuanbot.config import YuanBotConfig
from yuanbot.memory.manager import MemoryManager
from yuanbot.orchestrator.engine import OrchestratorEngine
from yuanbot.skills.manager import SkillManager
from yuanbot.tools.manager import ToolManager


def create_app(config: YuanBotConfig) -> FastAPI:
    """创建 YuanBot FastAPI 应用"""

    # 初始化核心组件
    memory_manager = MemoryManager(config=config.memory.model_dump())
    skill_manager = SkillManager()
    tool_manager = ToolManager()

    # 初始化 AI 提供商
    ai_provider = _create_ai_provider(config)

    # 初始化 Agent 人设
    persona = _load_persona(config)

    # 初始化编排引擎
    orchestrator = OrchestratorEngine(
        ai_provider=ai_provider,
        persona=persona,
        memory_manager=memory_manager,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """应用生命周期管理"""
        print("🌸 YuanBot 启动完成")
        yield
        # 清理资源
        if hasattr(ai_provider, "close"):
            await ai_provider.close()
        print("🌸 YuanBot 已停止")

    app = FastAPI(
        title="缘·Bot (YuanBot)",
        description="AI 虚拟伴侣系统",
        version=config.version,
        lifespan=lifespan,
    )

    # 注册路由
    _register_routes(app, orchestrator, memory_manager, config)

    # 注册 WebSocket 路由（Web 通道）
    _register_websocket(app, config, orchestrator)

    return app


def _create_ai_provider(config: YuanBotConfig) -> Any:
    """根据配置创建 AI 提供商适配器"""
    provider_id = config.ai_provider.provider_id

    if provider_id == "openai":
        from yuanbot.adapters.ai.openai_adapter import OpenAIAdapter
        return OpenAIAdapter(config.ai_provider.model_dump())
    elif provider_id == "anthropic":
        from yuanbot.adapters.ai.anthropic_adapter import AnthropicAdapter
        return AnthropicAdapter(config.ai_provider.model_dump())
    else:
        raise ValueError(f"Unsupported AI provider: {provider_id}")


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

    @app.get("/health")
    async def health():
        """健康检查"""
        return {"status": "ok", "version": config.version}

    @app.post("/api/chat")
    async def chat(request: dict[str, Any]):
        """对话接口（用于 Web Chat 通道）"""
        from yuanbot.core.types import UserMessage, ContentType

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
                {"id": m.id, "content": m.content, "importance": m.importance_score}
                for m in fact_memories
            ],
        }


def _register_websocket(
    app: FastAPI,
    config: YuanBotConfig,
    orchestrator: OrchestratorEngine,
) -> None:
    """注册 WebSocket 路由（Web 通道适配器）"""
    from starlette.websockets import WebSocket

    from yuanbot.adapters.channel.web_adapter import WebAdapter
    from yuanbot.core.types import BotResponse, MessageContent, ContentType

    web_adapter = WebAdapter()

    # 构建回调：编排层 → Web 响应
    async def on_message(msg) -> BotResponse:
        response = await orchestrator.process_message(msg)
        return response

    # 启动适配器
    @app.on_event("startup")
    async def start_web_adapter():
        await web_adapter.listen(on_message)

    @app.on_event("shutdown")
    async def stop_web_adapter():
        await web_adapter.close()

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
