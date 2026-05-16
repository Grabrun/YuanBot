"""YuanBot 编排层 - 核心对话编排引擎

串联意图识别、情感分析、角色管理、主动触发调度、
上下文组装、记忆检索、Token 预算管理等核心流程。
"""

from yuanbot.orchestrator.engine import OrchestratorEngine

__all__ = ["OrchestratorEngine"]
